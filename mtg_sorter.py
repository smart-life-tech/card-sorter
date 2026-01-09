import csv
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Optional heavy deps: run in mock mode if missing
try:  # pragma: no cover - optional
    import cv2
except Exception:  # pragma: no cover - optional
    cv2 = None

try:  # pragma: no cover - optional
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional
    ort = None

try:  # pragma: no cover - optional
    import board
    import busio
    from adafruit_pca9685 import PCA9685
except Exception:  # pragma: no cover - optional
    board = None
    busio = None
    PCA9685 = None

import requests
import tkinter as tk
from tkinter import ttk


###############################################################################
# Models & Config
###############################################################################


@dataclass
class ServoConfig:
    price_bin: int = 0
    combined_bin: int = 1
    white_blue_bin: int = 2
    black_bin: int = 3
    red_bin: int = 4
    green_bin: int = 5
    reserve: List[int] = field(default_factory=lambda: [6, 7])
    open_deg: Dict[str, float] = field(
        default_factory=lambda: {
            "price_bin": 110.0,
            "combined_bin": 120.0,
            "white_blue_bin": 115.0,
            "black_bin": 110.0,
            "red_bin": 120.0,
            "green_bin": 115.0,
        }
    )
    closed_deg: Dict[str, float] = field(
        default_factory=lambda: {
            "price_bin": 60.0,
            "combined_bin": 70.0,
            "white_blue_bin": 65.0,
            "black_bin": 60.0,
            "red_bin": 70.0,
            "green_bin": 65.0,
        }
    )
    pca_address: int = 0x40
    pwm_freq_hz: int = 50
    supply_voltage_v: float = 5.5


@dataclass
class AppConfig:
    mode: str = "price"  # price | color | mixed
    mock_mode: bool = True
    price_threshold_usd: float = 0.25
    price_primary: str = "scryfall"
    price_fallback: str = "tcgplayer"
    price_cache_ttl_hours: int = 24
    logging_dir: Path = Path("./logs")
    persistence_file: Path = Path("./config/state.json")
    recognition_model_path: Path = Path("./models/card_recognizer.onnx")
    recognition_label_map: Path = Path("./models/label_map.json")
    recognition_card_index: Path = Path("./models/card_index.json")
    camera_resolution: Tuple[int, int] = (1920, 1080)
    camera_device_index: int = 0


@dataclass
class CardMetadata:
    name: str
    set_code: str
    collector_number: str
    art_id: str
    colors: List[str]
    color_identity: List[str]


@dataclass
class CardRecognitionResult:
    name: Optional[str]
    set_code: Optional[str]
    collector_number: Optional[str]
    art_id: Optional[str]
    confidence: float
    colors: Optional[List[str]] = None
    color_identity: Optional[List[str]] = None
    image_path: Optional[str] = None


@dataclass
class PriceQuote:
    price_usd: Optional[float]
    source: str
    fetched_at: datetime


@dataclass
class RoutingDecision:
    bin_name: str
    reason: str
    flags: List[str] = field(default_factory=list)


###############################################################################
# Helpers: PCA9685
###############################################################################


def setup_pca9685(cfg: ServoConfig, mock: bool) -> Optional["PCA9685"]:
    if mock:
        print(f"[MOCK PCA9685] address=0x{cfg.pca_address:02x}")
        return None
    if board is None or busio is None or PCA9685 is None:
        print("[PCA9685] Hardware libraries not available; switching to mock mode")
        return None
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=cfg.pca_address)
        pca.frequency = cfg.pwm_freq_hz
        print(f"[PCA9685] Initialized @0x{cfg.pca_address:02x}, {cfg.pwm_freq_hz} Hz")
        return pca
    except Exception as exc:
        print(f"[PCA9685] Init failed: {exc}; switching to mock mode")
        return None


def angle_to_pwm(angle_deg: float, supply_voltage_v: float) -> int:
    angle_deg = max(0.0, min(180.0, angle_deg))
    # 500–2500us range over 0–180deg; scale to 16-bit duty for 20ms period
    pulse_us = 500.0 + (angle_deg / 180.0) * 2000.0
    duty = int((pulse_us / 20000.0) * 65535)
    # Voltage currently unused but reserved for future calibration
    return duty


def move_servo(pca: Optional["PCA9685"], channel: int, angle_deg: float, cfg: ServoConfig, mock: bool) -> None:
    duty = angle_to_pwm(angle_deg, cfg.supply_voltage_v)
    if mock or pca is None:
        print(f"[MOCK SERVO] ch={channel} angle={angle_deg:.1f} duty={duty}")
        return
    try:
        pca.channels[channel].duty_cycle = duty
    except Exception as exc:
        print(f"[SERVO] Failed channel {channel}: {exc}")


def cleanup_pca9685(pca: Optional["PCA9685"]) -> None:
    if pca is not None:
        try:
            pca.deinit()
        except Exception:
            pass


###############################################################################
# Recognition (ONNX)
###############################################################################


class CardIndex:
    def __init__(self, records: Dict[str, CardMetadata]):
        self.records = records

    @classmethod
    def load(cls, path: Path) -> "CardIndex":
        raw = json.loads(path.read_text(encoding="utf-8"))
        records: Dict[str, CardMetadata] = {}

        def coerce_row(art_id: str, row: Dict[str, object]) -> None:
            meta = CardMetadata(
                name=str(row.get("name")),
                set_code=str(row.get("set_code") or row.get("set")),
                collector_number=str(row.get("collector_number")),
                art_id=art_id,
                colors=list(row.get("colors", [])),
                color_identity=list(row.get("color_identity", row.get("colors", []))),
            )
            records[meta.art_id] = meta

        if isinstance(raw, list):
            for row in raw:
                art_id = row.get("art_id") or row.get("id")
                if art_id:
                    coerce_row(art_id, row)
        elif isinstance(raw, dict):
            for art_id, row in raw.items():
                if isinstance(row, dict):
                    coerce_row(art_id, row)

        return cls(records)

    def get(self, art_id: str) -> Optional[CardMetadata]:
        return self.records.get(art_id)


class Recognizer:
    def __init__(self, model_path: Path, label_map_path: Path, card_index_path: Path, mock_mode: bool = False) -> None:
        self.model_path = model_path
        self.label_map_path = label_map_path
        self.card_index_path = card_index_path
        self.mock_mode = mock_mode

        self.session = self._load_session()
        self.label_map = self._load_label_map()
        self.card_index = self._load_index()

    def _load_session(self):
        if self.mock_mode:
            return None
        if ort and self.model_path.exists():
            try:
                return ort.InferenceSession(str(self.model_path))
            except Exception as exc:
                print(f"[RECOGNIZER] Failed to load model: {exc}")
        else:
            print("[RECOGNIZER] onnxruntime missing or model path invalid; mock recognition active")
        return None

    def _load_label_map(self) -> List[str]:
        if not self.label_map_path.exists():
            print(f"[RECOGNIZER] Label map missing at {self.label_map_path}")
            return []
        data = json.loads(self.label_map_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            try:
                ordered = sorted(data.items(), key=lambda kv: int(kv[0]))
                return [v for _, v in ordered]
            except Exception:
                return list(data.values())
        return []

    def _load_index(self) -> Optional[CardIndex]:
        if not self.card_index_path.exists():
            print(f"[RECOGNIZER] Card index missing at {self.card_index_path}")
            return None
        return CardIndex.load(self.card_index_path)

    def _preprocess(self, image_path: Path) -> np.ndarray:
        if cv2 is None:
            raise RuntimeError("OpenCV is required for preprocessing")
        img = cv2.imread(str(image_path))
        if img is None:
            raise RuntimeError("Failed to read captured image")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (224, 224))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # CHW
        return np.expand_dims(img, axis=0)

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        m = np.max(logits)
        exps = np.exp(logits - m)
        return exps / np.sum(exps)

    def _art_id_from_idx(self, idx: int) -> Optional[str]:
        if 0 <= idx < len(self.label_map):
            return self.label_map[idx]
        return None

    def recognize(self, image_path: Path) -> CardRecognitionResult:
        if self.session is None or cv2 is None:
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.0,
                image_path=str(image_path),
            )

        try:
            input_tensor = self._preprocess(image_path)
            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]
            probs = self._softmax(logits)
            top_idx = int(np.argmax(probs))
            confidence = float(probs[top_idx])
            art_id = self._art_id_from_idx(top_idx)
            meta = self.card_index.get(art_id) if (art_id and self.card_index) else None
            if meta:
                return CardRecognitionResult(
                    name=meta.name,
                    set_code=meta.set_code,
                    collector_number=meta.collector_number,
                    art_id=meta.art_id,
                    confidence=confidence,
                    colors=meta.colors,
                    color_identity=meta.color_identity,
                    image_path=str(image_path),
                )
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=art_id,
                confidence=confidence,
                colors=None,
                color_identity=None,
                image_path=str(image_path),
            )
        except Exception as exc:
            print(f"[RECOGNIZER] Error: {exc}")
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.0,
                image_path=str(image_path),
            )


###############################################################################
# Capture
###############################################################################


class CameraCapture:
    def __init__(self, device_index: int, resolution: Tuple[int, int], output_dir: Path, mock_mode: bool) -> None:
        self.device_index = device_index
        self.resolution = resolution
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mock_mode = mock_mode
        self._cap: Optional["cv2.VideoCapture"] = None

    def _ensure_camera(self) -> None:
        if self.mock_mode:
            return
        if cv2 is None:
            raise RuntimeError("OpenCV not installed")
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.device_index)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        if not self._cap.isOpened():
            raise RuntimeError("Camera failed to open")

    def capture(self) -> Path:
        filename = datetime.utcnow().strftime("capture_%Y%m%d_%H%M%S.jpg")
        path = self.output_dir / filename

        if self.mock_mode:
            mock_img = (np.random.rand(self.resolution[1], self.resolution[0], 3) * 255).astype(np.uint8)
            if cv2:
                cv2.imwrite(str(path), mock_img)
            else:
                path.write_bytes(b"")
            return path

        self._ensure_camera()
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Camera read failed")
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError("Failed to write capture")
        return path

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


###############################################################################
# Pricing (Scryfall primary, optional TCG fallback)
###############################################################################


class PriceProvider:
    name: str

    def fetch(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        raise NotImplementedError


class ScryfallProvider(PriceProvider):
    name = "scryfall"

    def fetch(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        if collector_number and set_code:
            url = f"https://api.scryfall.com/cards/{set_code}/{collector_number}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        else:
            url = "https://api.scryfall.com/cards/named"
            resp = requests.get(url, params={"exact": name}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        price = data.get("prices", {}).get("usd")
        price_val = float(price) if price else None
        return PriceQuote(price_usd=price_val, source=self.name, fetched_at=datetime.utcnow())


class TcgplayerProvider(PriceProvider):
    name = "tcgplayer"

    def __init__(self, public_key: Optional[str] = None, private_key: Optional[str] = None) -> None:
        self.public_key = public_key or None
        self.private_key = private_key or None
        self.session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _ensure_token(self) -> Optional[str]:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token
        if not self.public_key or not self.private_key:
            return None
        url = "https://api.tcgplayer.com/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.public_key,
            "client_secret": self.private_key,
        }
        resp = self.session.post(url, data=payload, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        self._token = data.get("access_token")
        expires_in = data.get("expires_in", 900)
        self._token_expiry = now + expires_in - 30
        return self._token

    def _get(self, url: str, headers: Dict[str, str]) -> Optional[requests.Response]:
        retries = 3
        backoff = 0.4
        for _ in range(retries):
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff)
                backoff *= 2
                continue
            return resp
        return None

    def _find_product_id(self, name: str, set_code: Optional[str], collector_number: Optional[str], token: str) -> Optional[int]:
        headers = {"Authorization": f"bearer {token}"}
        params = {
            "categoryId": 1,
            "productName": name,
            "getExtendedFields": True,
        }
        resp = self.session.get("https://api.tcgplayer.com/catalog/products", headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        products = resp.json().get("results", [])
        if not products:
            return None
        if set_code:
            set_code_lower = set_code.lower()
            for prod in products:
                for ext in prod.get("extendedData", []):
                    if ext.get("name") == "Set Code" and ext.get("value", "").lower() == set_code_lower:
                        return prod.get("productId")
        return products[0].get("productId")

    def _fetch_market(self, product_id: int, token: str) -> Optional[float]:
        headers = {"Authorization": f"bearer {token}"}
        url = f"https://api.tcgplayer.com/pricing/product/{product_id}"
        resp = self._get(url, headers=headers)
        if not resp or resp.status_code != 200:
            return None
        prices = resp.json().get("results", [])
        if not prices:
            return None
        market = prices[0].get("marketPrice")
        try:
            return float(market) if market is not None else None
        except Exception:
            return None

    def fetch(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        token = self._ensure_token()
        if not token:
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.utcnow())
        product_id = self._find_product_id(name, set_code, collector_number, token)
        if not product_id:
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.utcnow())
        price = self._fetch_market(product_id, token)
        return PriceQuote(price_usd=price, source=self.name, fetched_at=datetime.utcnow())


class PriceService:
    def __init__(self, primary: PriceProvider, fallback: PriceProvider, ttl_hours: int) -> None:
        self.primary = primary
        self.fallback = fallback
        self.ttl = timedelta(hours=ttl_hours)
        self.cache: Dict[str, Dict[str, object]] = {}

    def _key(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> str:
        return "|".join([name.lower(), set_code or "", collector_number or ""])

    def get_price(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        key = self._key(name, set_code, collector_number)
        now = datetime.utcnow()
        cached = self.cache.get(key)
        if cached and cached["expires_at"] > now:
            return PriceQuote(price_usd=cached["price"], source=cached["source"], fetched_at=cached["fetched_at"])

        quote = self._try_provider(self.primary, name, set_code, collector_number)
        if quote.price_usd is None:
            fallback_quote = self._try_provider(self.fallback, name, set_code, collector_number)
            if fallback_quote.price_usd is not None:
                quote = fallback_quote

        self.cache[key] = {
            "price": quote.price_usd,
            "source": quote.source,
            "fetched_at": quote.fetched_at,
            "expires_at": now + self.ttl,
        }
        return quote

    @staticmethod
    def _try_provider(provider: PriceProvider, name: str, set_code: Optional[str], collector_number: Optional[str]) -> PriceQuote:
        try:
            return provider.fetch(name, set_code, collector_number)
        except Exception:
            return PriceQuote(price_usd=None, source=provider.name, fetched_at=datetime.utcnow())


###############################################################################
# Routing
###############################################################################


class Router:
    def __init__(self, cfg: AppConfig, disabled_bins: Optional[set] = None) -> None:
        self.cfg = cfg
        self.disabled_bins = disabled_bins or set()

    def route(self, card: CardRecognitionResult, price_usd: Optional[float]) -> RoutingDecision:
        flags: List[str] = []
        price_bin = "price_bin"
        combined_bin = "combined_bin"

        if price_bin in self.disabled_bins:
            price_bin = combined_bin
            flags.append("price_bin_disabled")
        if combined_bin in self.disabled_bins:
            combined_bin = price_bin
            flags.append("combined_bin_disabled")

        if card.confidence < 0.5:
            return RoutingDecision(bin_name=combined_bin, reason="low_confidence", flags=flags + ["low_confidence"])
        if not card.name:
            return RoutingDecision(bin_name=combined_bin, reason="unrecognized", flags=flags + ["unrecognized"])

        if self.cfg.mode == "price":
            if price_usd is None:
                return RoutingDecision(bin_name=combined_bin, reason="unpriced", flags=flags + ["unpriced"])
            if price_usd >= self.cfg.price_threshold_usd:
                return RoutingDecision(bin_name=price_bin, reason="price_above_threshold", flags=flags)
            return RoutingDecision(bin_name=combined_bin, reason="price_below_threshold", flags=flags)

        if self.cfg.mode == "color":
            return RoutingDecision(bin_name=self._route_color(card), reason="color_mode", flags=flags)

        if self.cfg.mode == "mixed":
            if price_usd is not None and price_usd >= self.cfg.price_threshold_usd:
                return RoutingDecision(bin_name=price_bin, reason="price_above_threshold", flags=flags)
            return RoutingDecision(bin_name=self._route_color(card), reason="color_mode", flags=flags)

        return RoutingDecision(bin_name=combined_bin, reason="default", flags=flags + ["fallback"])

    def _route_color(self, card: CardRecognitionResult) -> str:
        identity = card.color_identity or []
        if len(identity) != 1:
            return "combined_bin"
        single = identity[0]
        if single in ("W", "U"):
            return "white_blue_bin"
        if single == "B":
            return "black_bin"
        if single == "R":
            return "red_bin"
        if single == "G":
            return "green_bin"
        return "combined_bin"


###############################################################################
# Logging & State
###############################################################################


class CsvLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def append(self, row: Dict[str, object]) -> None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        path = self.log_dir / f"cards_{date_str}.csv"
        is_new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if is_new:
                writer.writeheader()
            writer.writerow(row)


def load_state(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = dict(state)
    if isinstance(serializable.get("disabled_bins"), set):
        serializable["disabled_bins"] = list(serializable["disabled_bins"])
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


###############################################################################
# Application core
###############################################################################


class CardSorterApp:
    def __init__(self, cfg: AppConfig, servo_cfg: ServoConfig):
        self.cfg = cfg
        self.servo_cfg = servo_cfg
        self.state = load_state(cfg.persistence_file)
        self.disabled_bins = set(self.state.get("disabled_bins", []))

        self.camera = CameraCapture(cfg.camera_device_index, cfg.camera_resolution, Path("captures"), cfg.mock_mode)
        self.recognizer = Recognizer(cfg.recognition_model_path, cfg.recognition_label_map, cfg.recognition_card_index, mock_mode=cfg.mock_mode)
        self.price_service = PriceService(
            primary=ScryfallProvider(),
            fallback=TcgplayerProvider(),
            ttl_hours=cfg.price_cache_ttl_hours,
        )
        self.router = Router(cfg, disabled_bins=self.disabled_bins)
        self.logger = CsvLogger(cfg.logging_dir)

        self.pca = setup_pca9685(servo_cfg, cfg.mock_mode)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _move_bin(self, bin_name: str) -> None:
        channel_map = {
            "price_bin": self.servo_cfg.price_bin,
            "combined_bin": self.servo_cfg.combined_bin,
            "white_blue_bin": self.servo_cfg.white_blue_bin,
            "black_bin": self.servo_cfg.black_bin,
            "red_bin": self.servo_cfg.red_bin,
            "green_bin": self.servo_cfg.green_bin,
        }
        ch = channel_map.get(bin_name)
        if ch is None:
            print(f"[ACTUATE] Unknown bin {bin_name}")
            return
        open_deg = self.servo_cfg.open_deg.get(bin_name, 110.0)
        close_deg = self.servo_cfg.closed_deg.get(bin_name, 60.0)
        move_servo(self.pca, ch, open_deg, self.servo_cfg, self.cfg.mock_mode)
        time.sleep(0.25)
        move_servo(self.pca, ch, close_deg, self.servo_cfg, self.cfg.mock_mode)

    def process_once(self) -> RoutingDecision:
        image_path = self.camera.capture()
        rec = self.recognizer.recognize(image_path)

        price_quote = None
        if rec.name:
            price_quote = self.price_service.get_price(rec.name, rec.set_code, rec.collector_number)

        decision = self.router.route(rec, price_quote.price_usd if price_quote else None)
        self._move_bin(decision.bin_name)

        flags = list(decision.flags)
        if price_quote and price_quote.price_usd is None:
            flags.append("unpriced")
        if price_quote is None:
            flags.append("no_price_lookup")

        self.logger.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "name": rec.name,
                "set_code": rec.set_code,
                "collector_number": rec.collector_number,
                "art_id": rec.art_id,
                "confidence": rec.confidence,
                "price_usd": price_quote.price_usd if price_quote else None,
                "price_source": price_quote.source if price_quote else None,
                "bin": decision.bin_name,
                "flags": ";".join(flags),
                "image_path": rec.image_path,
            }
        )

        self.state["last_bin"] = decision.bin_name
        save_state(self.cfg.persistence_file, {"disabled_bins": list(self.disabled_bins), "last_bin": decision.bin_name})
        return decision

    def start_loop(self, on_update):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, args=(on_update,), daemon=True)
        self._thread.start()

    def _loop(self, on_update):
        while not self._stop_event.is_set():
            try:
                decision = self.process_once()
                on_update(decision)
            except Exception as exc:
                on_update(f"Error: {exc}")
            time.sleep(0.2)

    def stop_loop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def shutdown(self):
        self.stop_loop()
        self.camera.release()
        cleanup_pca9685(self.pca)


###############################################################################
# GUI
###############################################################################


class SorterGUI:
    def __init__(self, app: CardSorterApp):
        self.app = app
        self.root = tk.Tk()
        self.root.title("MTG Card Sorter (Offline)")

        self.mode_var = tk.StringVar(value=self.app.cfg.mode)
        self.threshold_var = tk.DoubleVar(value=self.app.cfg.price_threshold_usd)
        self.status_var = tk.StringVar(value="Idle")
        self.mock_var = tk.BooleanVar(value=self.app.cfg.mock_mode)

        self._build()

    def _build(self):
        frm = ttk.Frame(self.root, padding=8)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Mode:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(frm, text="Price", variable=self.mode_var, value="price", command=self._on_mode).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(frm, text="Color", variable=self.mode_var, value="color", command=self._on_mode).grid(row=0, column=2, sticky="w")
        ttk.Radiobutton(frm, text="Mixed", variable=self.mode_var, value="mixed", command=self._on_mode).grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Price threshold ($)").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.threshold_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Button(frm, text="Set", command=self._on_threshold).grid(row=1, column=2, sticky="w")

        ttk.Checkbutton(frm, text="Mock Mode", variable=self.mock_var, state="disabled").grid(row=2, column=0, sticky="w")

        ttk.Button(frm, text="Start", command=self.start).grid(row=3, column=0, sticky="we")
        ttk.Button(frm, text="Stop", command=self.stop).grid(row=3, column=1, sticky="we")

        ttk.Label(frm, textvariable=self.status_var).grid(row=4, column=0, columnspan=4, sticky="we")

        # Bin test buttons
        r = 5
        for name in ["price_bin", "combined_bin", "white_blue_bin", "black_bin", "red_bin", "green_bin"]:
            ttk.Button(frm, text=f"Test {name}", command=lambda n=name: self._test_bin(n)).grid(row=r, column=0, columnspan=2, sticky="we")
            r += 1

    def _test_bin(self, name: str):
        try:
            self.app._move_bin(name)
        except Exception as exc:
            self.status_var.set(f"Test error: {exc}")

    def _on_mode(self):
        self.app.cfg.mode = self.mode_var.get()
        self.status_var.set(f"Mode set to {self.app.cfg.mode}")

    def _on_threshold(self):
        try:
            value = float(self.threshold_var.get())
            self.app.cfg.price_threshold_usd = value
            self.status_var.set(f"Threshold set to ${value:.2f}")
        except Exception:
            self.status_var.set("Invalid threshold")

    def start(self):
        self.status_var.set("Running...")
        self.app.start_loop(self._on_update)

    def stop(self):
        self.app.stop_loop()
        self.status_var.set("Stopped")

    def _on_update(self, msg):
        if isinstance(msg, RoutingDecision):
            self.status_var.set(f"{msg.bin_name} ({msg.reason})")
        else:
            self.status_var.set(str(msg))

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        try:
            self.stop()
            self.app.shutdown()
        finally:
            self.root.destroy()


###############################################################################
# Main
###############################################################################


def main():
    cfg = AppConfig()
    cfg.mock_mode = cfg.mock_mode or cv2 is None or ort is None
    servo_cfg = ServoConfig()
    app = CardSorterApp(cfg, servo_cfg)
    gui = SorterGUI(app)
    print(f"Starting MTG sorter (mock_mode={cfg.mock_mode})")
    gui.run()


if __name__ == "__main__":
    main()
import os
import sys
import time
import csv
import math
import platform
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Optional imports (work on Windows in mock mode)
try:
    import cv2
except Exception:
    cv2 = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
except Exception:
    board = None
    busio = None
    PCA9685 = None

import requests
import tkinter as tk
from tkinter import ttk

################################################################################
# Config & Models
################################################################################

@dataclass
class ServoConfig:
    # PCA9685 channel numbers (0-15) for each bin's servo signal
    # Channel 0 reserved for hopper/feed servo on your controller
    hopper_channel: int = 0
    price_bin: int = 1
    combined_bin: int = 2
    white_blue_bin: int = 3
    black_bin: int = 4
    red_bin: int = 5
    green_bin: int = 6
    extra_bin: int = 7  # optional 7th bin if wired
    # Servo pulse range (in microseconds): 500-2500 typical
    # These convert to 16-bit values for PCA9685
    pulse_open_us: int = 2400    # Wider open pulse (increase angle)
    pulse_close_us: int = 600    # Wider close pulse (decrease angle)
    pca_address: int = 0x40      # Default PCA9685 I2C address

@dataclass
class AppConfig:
    mock_mode: bool = True  # auto-set below depending on platform
    price_threshold_usd: float = 0.25
    scryfall_timeout: float = 6.0
    capture_resolution: Tuple[int, int] = (1280, 720)
    name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)  # x1,y1,x2,y2 relative

@dataclass
class CardInfo:
    name: Optional[str]
    colors: List[str]
    price_usd: Optional[float]
    set_code: Optional[str]
    type_line: Optional[str]

################################################################################
# Helpers
################################################################################

def is_rpi() -> bool:
    return platform.system() == "Linux" and board is not None


def setup_pca9685(servo_cfg: ServoConfig, mock: bool) -> Optional[any]:
    if mock:
        print(f"[MOCK PCA9685] Using mock servo outputs (address 0x{servo_cfg.pca_address:02x})")
        return None
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=servo_cfg.pca_address)
        pca.frequency = 50  # Standard servo frequency: 50 Hz
        print(f"[PCA9685] Initialized at 0x{servo_cfg.pca_address:02x}, 50 Hz")
        return pca
    except Exception as e:
        print(f"[PCA9685] Failed to initialize: {e}")
        return None


def move_servo(pca: Optional[any], name: str, channel: int, pulse_open_us: int, pulse_close_us: int, dwell_s: float = 0.3, mock: bool = True) -> None:
    if mock or pca is None:
        print(f"[MOCK SERVO] {name} (ch {channel}) -> open ({pulse_open_us}µs) then close ({pulse_close_us}µs)")
        time.sleep(dwell_s)
        return
    # Clamp to safe servo range 500–2500 µs
    pulse_open_us = max(500, min(2500, pulse_open_us))
    pulse_close_us = max(500, min(2500, pulse_close_us))
    # PCA9685 uses 16-bit duty_cycle (0-65535) for a 20ms period at 50Hz
    # 1µs = 65535 / 20000 ≈ 3.27675 steps
    open_val = int(pulse_open_us * 65535 / 20000)
    close_val = int(pulse_close_us * 65535 / 20000)
    print(f"[PCA SERVO] {name} (ch {channel}) open={pulse_open_us}µs({open_val}) close={pulse_close_us}µs({close_val})")
    pca.channels[channel].duty_cycle = open_val
    time.sleep(dwell_s)
    pca.channels[channel].duty_cycle = close_val


def cleanup_pca9685(pca: Optional[any]) -> None:
    if pca is not None:
        try:
            pca.deinit()
        except Exception:
            pass

################################################################################
# Capture + Detection + OCR
################################################################################

def open_camera(resolution: Tuple[int, int]):
    if cv2 is None:
        raise RuntimeError("OpenCV not available")
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    if not cap.isOpened():
        raise RuntimeError("Camera failed to open")
    return cap


def detect_card_and_warp(frame) -> Optional[any]:
    # Simple largest contour approx as card
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    if len(approx) != 4:
        return None
    pts = approx.reshape(4, 2).astype("float32")
    # Order points (tl,tr,br,bl)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    ordered = np.array([tl, tr, br, bl], dtype="float32")
    w = 720
    h = 1024
    dst = np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(frame, M, (w, h))
    return warped


def ocr_name_from_image(img, roi_rel: Tuple[float,float,float,float]) -> Optional[str]:
    if pytesseract is None:
        return None
    h, w = img.shape[:2]
    x1 = int(roi_rel[0] * w)
    y1 = int(roi_rel[1] * h)
    x2 = int(roi_rel[2] * w)
    y2 = int(roi_rel[3] * h)
    roi = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    config = "--psm 7 -l eng"
    text = pytesseract.image_to_string(gray, config=config)
    if not text:
        return None
    # Clean name: remove non-letters/digits basic
    name = text.strip().replace("\n", " ")
    name = name.strip("-—_ :")
    return name if len(name) >= 2 else None

################################################################################
# Scryfall Lookup
################################################################################

def scryfall_lookup(name: str, timeout: float = 6.0) -> Optional[CardInfo]:
    try:
        r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        # Price
        usd = None
        prices = data.get("prices", {})
        if isinstance(prices, dict):
            p = prices.get("usd") or prices.get("usd_foil") or prices.get("usd_etched")
            try:
                usd = float(p) if p else None
            except Exception:
                usd = None
        colors = data.get("color_identity") or data.get("colors") or []
        set_code = data.get("set")
        type_line = data.get("type_line")
        return CardInfo(name=name, colors=colors, price_usd=usd, set_code=set_code, type_line=type_line)
    except Exception:
        return None

################################################################################
# Routing
################################################################################

def decide_bin(info: CardInfo, mode: str, threshold: float) -> str:
    if info is None:
        return "combined_bin"
    if mode == "price":
        if info.price_usd is not None and info.price_usd >= threshold:
            return "price_bin"
        return "combined_bin"
    # color mode or mixed
    colors = info.colors or []
    mono = len(colors) == 1
    if mono:
        c = colors[0]
        if c in ("W", "U"):
            return "white_blue_bin"
        if c == "B":
            return "black_bin"
        if c == "R":
            return "red_bin"
        if c == "G":
            return "green_bin"
    return "combined_bin"

################################################################################
# GUI App
################################################################################

class SorterGUI:
    def __init__(self, config: AppConfig, servo_cfg: ServoConfig):
        self.cfg = config
        self.servo_cfg = servo_cfg
        self.root = tk.Tk()
        self.root.title("MTG Card Sorter (OCR)")
        self.mode_var = tk.StringVar(value="price")
        self.threshold_var = tk.DoubleVar(value=self.cfg.price_threshold_usd)
        self.status_var = tk.StringVar(value="Idle")
        self.mock_var = tk.BooleanVar(value=self.cfg.mock_mode)
        self.pca = setup_pca9685(self.servo_cfg, mock=self.cfg.mock_mode)
        self.channel_map = {
            "hopper": self.servo_cfg.hopper_channel,
            "price_bin": self.servo_cfg.price_bin,
            "combined_bin": self.servo_cfg.combined_bin,
            "white_blue_bin": self.servo_cfg.white_blue_bin,
            "black_bin": self.servo_cfg.black_bin,
            "red_bin": self.servo_cfg.red_bin,
            "green_bin": self.servo_cfg.green_bin,
            "extra_bin": self.servo_cfg.extra_bin,
        }
        self.cap = None

        self._build()
        self._tick_job = None

    def _build(self):
        frm = ttk.Frame(self.root, padding=8)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Mode:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(frm, text="Price", variable=self.mode_var, value="price").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(frm, text="Color", variable=self.mode_var, value="color").grid(row=0, column=2, sticky="w")

        ttk.Label(frm, text="Threshold ($)").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.threshold_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Checkbutton(frm, text="Mock Mode", variable=self.mock_var, command=self._on_toggle_mock).grid(row=2, column=0, sticky="w")

        ttk.Button(frm, text="Start", command=self.start).grid(row=3, column=0, sticky="we")
        ttk.Button(frm, text="Stop", command=self.stop).grid(row=3, column=1, sticky="we")

        # Test buttons
        r = 4
        for name in ["hopper","price_bin","combined_bin","white_blue_bin","black_bin","red_bin","green_bin","extra_bin"]:
            ttk.Button(frm, text=f"Test {name}", command=lambda n=name: self.test_bin(n)).grid(row=r, column=0, columnspan=2, sticky="we")
            r += 1

        # All-on / all-off controls
        ttk.Button(frm, text="All ON (open)", command=self.all_on).grid(row=r, column=0, columnspan=1, sticky="we")
        ttk.Button(frm, text="All OFF (close)", command=self.all_off).grid(row=r, column=1, columnspan=1, sticky="we")
        r += 1

        # Full 16-channel sweep test
        ttk.Button(frm, text="Test All 16 Ch", command=self.test_all_channels).grid(row=r, column=0, columnspan=2, sticky="we")
        r += 1

        ttk.Label(frm, textvariable=self.status_var).grid(row=r, column=0, columnspan=3, sticky="we")

    def _on_toggle_mock(self):
        self.cfg.mock_mode = bool(self.mock_var.get())
        cleanup_pca9685(self.pca)
        self.pca = setup_pca9685(self.servo_cfg, mock=self.cfg.mock_mode)
        self.status_var.set(f"Mock mode={'ON' if self.cfg.mock_mode else 'OFF'}")

    def test_bin(self, name: str):
        print(f"[TEST] {name}")
        ch = self.channel_map.get(name, -1)
        if ch >= 0:
            move_servo(self.pca, name, ch, self.servo_cfg.pulse_open_us, self.servo_cfg.pulse_close_us, mock=self.cfg.mock_mode)

    def all_on(self):
        for name, ch in self.channel_map.items():
            if ch >= 0:
                move_servo(self.pca, name, ch, self.servo_cfg.pulse_open_us, self.servo_cfg.pulse_close_us, dwell_s=0.3, mock=self.cfg.mock_mode)

    def all_off(self):
        for name, ch in self.channel_map.items():
            if ch >= 0:
                move_servo(self.pca, name, ch, self.servo_cfg.pulse_close_us, self.servo_cfg.pulse_close_us, dwell_s=0.1, mock=self.cfg.mock_mode)

    def test_all_channels(self):
        # Cycle through all 16 PCA9685 channels regardless of mapping
        for ch in range(16):
            move_servo(self.pca, f"ch{ch}", ch, self.servo_cfg.pulse_open_us, self.servo_cfg.pulse_close_us, dwell_s=0.25, mock=self.cfg.mock_mode)

    def start(self):
        # Open camera
        try:
            self.cap = open_camera(self.cfg.capture_resolution)
        except Exception as e:
            self.status_var.set(f"Camera error: {e}")
            return
        self.status_var.set("Running...")
        self._schedule_tick()

    def stop(self):
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.status_var.set("Stopped")

    def _schedule_tick(self):
        self._tick_job = self.root.after(300, self._tick)

    def _tick(self):
        try:
            ret, frame = self.cap.read()
            if not ret:
                self.status_var.set("Capture failed")
                self._schedule_tick()
                return
            warped = detect_card_and_warp(frame)
            if warped is None:
                self.status_var.set("No card detected")
                self._schedule_tick()
                return
            name = ocr_name_from_image(warped, self.cfg.name_roi)
            if not name:
                self.status_var.set("OCR failed")
                self._schedule_tick()
                return
            info = scryfall_lookup(name, self.cfg.scryfall_timeout)
            if not info:
                self.status_var.set(f"Lookup failed for '{name}'")
                self._schedule_tick()
                return
            bin_name = decide_bin(info, self.mode_var.get(), float(self.threshold_var.get()))
            ch = self.channel_map.get(bin_name, -1)
            if ch >= 0:
                move_servo(self.pca, bin_name, ch, self.servo_cfg.pulse_open_us, self.servo_cfg.pulse_close_us, mock=self.cfg.mock_mode)
            self.status_var.set(f"{info.name} → {bin_name} (${info.price_usd if info.price_usd is not None else 'N/A'})")
        except Exception as e:
            self.status_var.set(f"Error: {e}")
        finally:
            self._schedule_tick()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        try:
            self.stop()
            cleanup_pca9685(self.pca)
        finally:
            self.root.destroy()

################################################################################
# Main
################################################################################

def main():
    cfg = AppConfig()
    cfg.mock_mode = not is_rpi()  # auto-enable mock on non-Pi
    servo_cfg = ServoConfig()
    app = SorterGUI(cfg, servo_cfg)
    print(f"Starting MTG OCR sorter (mock_mode={cfg.mock_mode})")
    app.run()

if __name__ == "__main__":
    main()
