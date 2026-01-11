import csv
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Optional heavy deps: run in mock mode if missing
try:  # pragma: no cover - optional
    import cv2
except Exception:  # pragma: no cover - optional
    cv2 = None

try:  # pragma: no cover - optional
    import pytesseract
except Exception:  # pragma: no cover - optional
    pytesseract = None

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
from PIL import Image, ImageTk


###############################################################################
# Models & Config
###############################################################################


@dataclass
class ServoConfig:
    price_bin: int = 0
    combined_bin: int = 1
    white_blue_bin: int = 2
    black_bin: int = 3
    red_bin: int = 15
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
    mock_mode: bool = False
    price_threshold_usd: float = 0.25
    price_primary: str = "scryfall"
    price_fallback: str = "tcgplayer"
    price_cache_ttl_hours: int = 24
    logging_dir: Path = Path("./logs")
    persistence_file: Path = Path("./config/state.json")
    camera_resolution: Tuple[int, int] = (640, 480)
    camera_device_index: int = 0
    name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)  # x1,y1,x2,y2 relative
    card_index_path: Path = Path("./models/card_index.json")


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
        print(f"[SERVO] Moved channel {channel} to angle {angle_deg:.1f} (duty {duty})")
    except Exception as exc:
        print(f"[SERVO] Failed channel {channel}: {exc}")


def cleanup_pca9685(pca: Optional["PCA9685"]) -> None:
    if pca is not None:
        try:
            pca.deinit()
        except Exception:
            pass


###############################################################################
# Recognition (Tesseract OCR + Scryfall online lookup)
###############################################################################


class Recognizer:
    def __init__(self, cfg: AppConfig, mock_mode: bool = False) -> None:
        self.cfg = cfg
        self.mock_mode = mock_mode
        self.card_index = self._load_card_index()
    
    def _load_card_index(self) -> Dict[str, CardMetadata]:
        """Load card index from JSON file"""
        if not self.cfg.card_index_path.exists():
            print(f"[RECOGNIZER] Card index not found at {self.cfg.card_index_path}")
            return {}
        
        try:
            with open(self.cfg.card_index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            card_index = {}
            for key, card_data in data.items():
                name = card_data.get('name', '')
                if name and name not in card_index:
                    card_index[name] = CardMetadata(
                        name=name,
                        set_code=card_data.get('set', ''),
                        collector_number=card_data.get('collector_number', ''),
                        art_id=key,
                        colors=card_data.get('colors', []),
                        color_identity=card_data.get('color_identity', []),
                    )
            print(f"[RECOGNIZER] Loaded {len(card_index)} unique card names from index")
            return card_index
        except Exception as exc:
            print(f"[RECOGNIZER] Failed to load card index: {exc}")
            return {}
    
    def _find_best_match(self, detected_name: str) -> Optional[str]:
        """Find the best matching card name from the local index using fuzzy matching"""
        if not self.card_index:
            return None
        
        # Try exact match first (case-insensitive)
        for card_name in self.card_index.keys():
            if card_name.lower() == detected_name.lower():
                print(f"[RECOGNIZER] Exact match: '{detected_name}' -> '{card_name}'")
                return card_name
        
        # Create variations to try
        variations = [detected_name]
        
        # Try removing common prefixes like 'if', 'I', 'a', etc.
        words = detected_name.split()
        if len(words) > 1:
            # Try without first word if it's short
            if len(words[0]) <= 2:
                variations.append(' '.join(words[1:]))
            # Try without last word if it's short
            if len(words[-1]) <= 2:
                variations.append(' '.join(words[:-1]))
            # Try middle part if we have 3+ words
            if len(words) >= 3:
                variations.append(' '.join(words[1:-1]))
        
        # Try fuzzy matching with each variation, using lower threshold
        best_match = None
        best_ratio = 0.0
        
        for variant in variations:
            if not variant or len(variant) < 2:
                continue
            matches = get_close_matches(variant, self.card_index.keys(), n=1, cutoff=0.5)
            if matches:
                # Calculate similarity ratio
                match = matches[0]
                ratio = self._similarity_ratio(variant.lower(), match.lower())
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = match
        
        if best_match:
            print(f"[RECOGNIZER] Fuzzy match: '{detected_name}' -> '{best_match}' (score: {best_ratio:.2f})")
            return best_match
        
        print(f"[RECOGNIZER] No match found for '{detected_name}'")
        return None
    
    def _similarity_ratio(self, s1: str, s2: str) -> float:
        """Calculate similarity ratio between two strings"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, s1, s2).ratio()

    def _extract_name_from_image(self, image_path: Path) -> Optional[str]:
        """Extract card name from name ROI using Tesseract OCR"""
        if pytesseract is None or cv2 is None:
            print("[RECOGNIZER] pytesseract or cv2 not available")
            return None
        
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                return None
            
            h, w = img.shape[:2]
            x1 = int(self.cfg.name_roi[0] * w)
            y1 = int(self.cfg.name_roi[1] * h)
            x2 = int(self.cfg.name_roi[2] * w)
            y2 = int(self.cfg.name_roi[3] * h)
            roi = img[y1:y2, x1:x2]
            
            # Save raw ROI for debugging
            debug_raw = Path("captures") / f"debug_raw_{datetime.now(timezone.utc).strftime('%H%M%S')}.jpg"
            cv2.imwrite(str(debug_raw), roi)
            print(f"[OCR] Raw ROI saved: {debug_raw}")
            
            # Convert to grayscale
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Check image quality (variance of Laplacian for blur detection)
            variance = cv2.Laplacian(gray, cv2.CV_64F).var()
            print(f"[OCR] Image sharpness: {variance:.2f} (higher is sharper)")
            if variance < 50:
                print(f"[OCR] Warning: Image may be too blurry")
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            gray = clahe.apply(gray)
            
            # Denoise before processing
            gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            
            # Sharpen the image
            kernel_sharpen = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            gray = cv2.filter2D(gray, -1, kernel_sharpen)
            
            # Upscale for better OCR (target 600px width for stability)
            if gray.shape[1] < 600:
                scale = 600.0 / gray.shape[1]
                new_w = int(gray.shape[1] * scale)
                new_h = int(gray.shape[0] * scale)
                gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
            # Try multiple preprocessing approaches and vote on result
            results = []
            
            # Method 1: Simple OTSU
            _, binary1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text1 = pytesseract.image_to_string(binary1, config="--psm 7 --oem 1 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz").strip()
            if text1:
                results.append(text1)
                cv2.imwrite(str(Path("captures") / f"debug_otsu_{datetime.now(timezone.utc).strftime('%H%M%S')}.jpg"), binary1)
            
            # Method 2: Inverted OTSU
            _, binary2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            text2 = pytesseract.image_to_string(binary2, config="--psm 7 --oem 1 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz").strip()
            if text2:
                results.append(text2)
                cv2.imwrite(str(Path("captures") / f"debug_inv_{datetime.now(timezone.utc).strftime('%H%M%S')}.jpg"), binary2)
            
            # Method 3: Adaptive threshold (for uneven lighting)
            binary3 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY, 21, 10)
            text3 = pytesseract.image_to_string(binary3, config="--psm 7 --oem 1 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz").strip()
            if text3:
                results.append(text3)
                cv2.imwrite(str(Path("captures") / f"debug_adaptive_{datetime.now(timezone.utc).strftime('%H%M%S')}.jpg"), binary3)
            
            # Fallback: word-level extraction via image_to_data if string methods failed
            if not results:
                try:
                    from pytesseract import Output as TessOutput
                    data_variants = [
                        ("gray", gray),
                        ("otsu", binary1),
                        ("inv", binary2),
                        ("adaptive", binary3),
                    ]
                    for tag, imgv in data_variants:
                        data = pytesseract.image_to_data(imgv, config="--psm 7 --oem 1 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", output_type=TessOutput.DICT)
                        words = []
                        confs = data.get("conf", [])
                        texts = data.get("text", [])
                        for i in range(len(confs)):
                            conf_str = confs[i]
                            try:
                                conf_val = float(conf_str)
                            except Exception:
                                conf_val = -1.0
                            if conf_val >= 40.0:
                                wtxt = texts[i].strip()
                                if wtxt and any(ch.isalpha() for ch in wtxt):
                                    words.append(wtxt)
                        candidate = " ".join(words).strip()
                        if candidate:
                            print(f"[OCR] data() candidate ({tag}): {candidate}")
                            results.append(candidate)
                except Exception as exd:
                    print(f"[OCR] data() fallback error: {exd}")

            if not results:
                print("[OCR] No text detected with any method")
                return None
            
            # Pick the most common result (majority vote)
            from collections import Counter
            print(f"[OCR] All results: {results}")
            
            # Clean all results and find most common
            cleaned_results = []
            for text in results:
                name = text.strip().replace("\n", " ")
                name = ''.join(c for c in name if c.isalpha() or c.isspace())
                name = ' '.join(name.split()).strip()
                if name and len(name) >= 2:
                    cleaned_results.append(name)
            
            if not cleaned_results:
                print("[OCR] No valid text after cleaning")
                return None
            
            # Use most common result
            counter = Counter(cleaned_results)
            best_name = counter.most_common(1)[0][0]
            
            # Remove single-letter words from start and end
            words = best_name.split()
            if len(words) > 1:
                while words and len(words[0]) == 1:
                    words.pop(0)
                while words and len(words[-1]) == 1:
                    words.pop()
                best_name = ' '.join(words)
            
            print(f"[OCR] Final result (voted): '{best_name}'")
            return best_name if len(best_name) >= 2 else None
        except Exception as exc:
            print(f"[RECOGNIZER] OCR error: {exc}")
            return None

    def _lookup_card(self, name: str) -> Optional[CardMetadata]:
        """Look up card metadata from Scryfall API"""
        try:
            resp = requests.get(
                "https://api.scryfall.com/cards/named",
                params={"exact": name},
                timeout=5,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return CardMetadata(
                name=data.get("name", name),
                set_code=data.get("set", ""),
                collector_number=data.get("collector_number", ""),
                art_id=data.get("illustration_id", ""),
                colors=data.get("colors", []),
                color_identity=data.get("color_identity", []),
            )
        except Exception as exc:
            print(f"[RECOGNIZER] Scryfall lookup error: {exc}")
            return None

    def recognize(self, image_path: Path) -> CardRecognitionResult:
        """Recognize card using OCR + fuzzy matching + online lookup"""
        detected_name = self._extract_name_from_image(image_path)
        if not detected_name:
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.0,
                image_path=str(image_path),
            )
        
        # Try to find best match in local index first
        matched_name = self._find_best_match(detected_name)
        
        # If we found a match in the local index, use it directly
        if matched_name and matched_name in self.card_index:
            meta = self.card_index[matched_name]
            print(f"[RECOGNIZER] Using local index match: {matched_name}")
            return CardRecognitionResult(
                name=meta.name,
                set_code=meta.set_code,
                collector_number=meta.collector_number,
                art_id=meta.art_id,
                confidence=0.9,  # High confidence for local match
                colors=meta.colors,
                color_identity=meta.color_identity,
                image_path=str(image_path),
            )
        
        # Fall back to Scryfall lookup with the best matched name (or original if no match)
        lookup_name = matched_name if matched_name else detected_name
        meta = self._lookup_card(lookup_name)
        if not meta:
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.5,  # OCR worked but lookup failed
                image_path=str(image_path),
            )
        
        return CardRecognitionResult(
            name=meta.name,
            set_code=meta.set_code,
            collector_number=meta.collector_number,
            art_id=meta.art_id,
            confidence=0.85,  # High confidence when Scryfall matches
            colors=meta.colors,
            color_identity=meta.color_identity,
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
            # Match preview settings: set resolution only
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            # Small delay for camera to stabilize
            time.sleep(0.2)
        if not self._cap.isOpened():
            raise RuntimeError("Camera failed to open")

    def capture(self) -> Path:
        filename = datetime.now(timezone.utc).strftime("capture_%Y%m%d_%H%M%S.jpg")
        path = self.output_dir / filename

        if self.mock_mode:
            mock_img = (np.random.rand(self.resolution[1], self.resolution[0], 3) * 255).astype(np.uint8)
            if cv2:
                cv2.imwrite(str(path), mock_img)
            else:
                path.write_bytes(b"")
            return path

        self._ensure_camera()
        # Retry up to 3 times for V4L2 timeout issues
        for attempt in range(3):
            ret, frame = self._cap.read()
            if ret:
                if not cv2.imwrite(str(path), frame):
                    raise RuntimeError("Failed to write capture")
                return path
            if attempt < 2:
                print(f"[CAMERA] Read attempt {attempt + 1} failed, retrying...")
                time.sleep(0.2)
        raise RuntimeError("Camera read failed after 3 attempts")

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
        return PriceQuote(price_usd=price_val, source=self.name, fetched_at=datetime.now(timezone.utc))


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
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.now(timezone.utc))
        product_id = self._find_product_id(name, set_code, collector_number, token)
        if not product_id:
            return PriceQuote(price_usd=None, source=self.name, fetched_at=datetime.now(timezone.utc))
        price = self._fetch_market(product_id, token)
        return PriceQuote(price_usd=price, source=self.name, fetched_at=datetime.now(timezone.utc))


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
        now = datetime.now(timezone.utc)
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
            return PriceQuote(price_usd=None, source=provider.name, fetched_at=datetime.now(timezone.utc))


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
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        self.recognizer = Recognizer(cfg, mock_mode=cfg.mock_mode)
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

    def process_once(self) -> tuple[RoutingDecision, CardRecognitionResult]:
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
        print(decision)
        return decision, rec

    def start_loop(self, on_update):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, args=(on_update,), daemon=True)
        self._thread.start()

    def _loop(self, on_update):
        while not self._stop_event.is_set():
            try:
                decision, rec = self.process_once()
                on_update(decision, rec)
            except Exception as exc:
                on_update(f"Error: {exc}", None)
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
        self.root.title("MTG Card Sorter (Online OCR)")
        self.root.geometry("800x600")

        self.mode_var = tk.StringVar(value=self.app.cfg.mode)
        self.threshold_var = tk.DoubleVar(value=self.app.cfg.price_threshold_usd)
        self.status_var = tk.StringVar(value="Idle")
        self.mock_var = tk.BooleanVar(value=self.app.cfg.mock_mode)
        self.ocr_text_var = tk.StringVar(value="")
        self.card_info_var = tk.StringVar(value="")

        self._build()

    def _build(self):
        # Main container with two columns: controls on left, text display on right
        container = ttk.Frame(self.root)
        container.grid(row=0, column=0, sticky="nsew")
        
        # Left side: controls
        frm = ttk.Frame(container, padding=8)
        frm.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ttk.Label(frm, text="Mode:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(frm, text="Price", variable=self.mode_var, value="price", command=self._on_mode).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(frm, text="Color", variable=self.mode_var, value="color", command=self._on_mode).grid(row=0, column=2, sticky="w")
        ttk.Radiobutton(frm, text="Mixed", variable=self.mode_var, value="mixed", command=self._on_mode).grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Price threshold ($)").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.threshold_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Button(frm, text="Set", command=self._on_threshold).grid(row=1, column=2, sticky="w")

        ttk.Checkbutton(frm, text="Mock Mode", variable=self.mock_var, state="disabled").grid(row=2, column=0, sticky="w")

        ttk.Button(frm, text="Capture & OCR", command=self._capture_ocr).grid(row=3, column=0, sticky="we")
        ttk.Button(frm, text="Start Loop", command=self.start).grid(row=3, column=1, sticky="we")
        ttk.Button(frm, text="Stop", command=self.stop).grid(row=3, column=2, sticky="we")

        ttk.Label(frm, textvariable=self.status_var).grid(row=4, column=0, columnspan=4, sticky="we")

        ttk.Label(frm, text="").grid(row=5)  # spacer

        # Bin test buttons
        ttk.Label(frm, text="Test Bins:").grid(row=6, column=0, sticky="w")
        r = 7
        for name in ["price_bin", "combined_bin", "white_blue_bin", "black_bin", "red_bin", "green_bin"]:
            ttk.Button(frm, text=f"Test {name}", command=lambda n=name: self._test_bin(n)).grid(row=r, column=0, columnspan=2, sticky="we")
            r += 1
        
        # Test all 16 channels button
        ttk.Button(frm, text="Test All 16 Channels", command=self._test_all_channels).grid(row=r, column=0, columnspan=3, sticky="we")
        
        # Right side: OCR text display
        right_frame = ttk.Frame(container, padding=8)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        ttk.Label(right_frame, text="Extracted Text (OCR)", font=("Arial", 12, "bold")).pack(fill=tk.X)
        
        # OCR text display box
        ocr_frame = ttk.LabelFrame(right_frame, text="Card Name", padding=5)
        ocr_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.ocr_text_label = tk.Label(ocr_frame, textvariable=self.ocr_text_var, bg="white", fg="black", 
                                        font=("Courier", 14, "bold"), wraplength=250, justify=tk.CENTER, padx=10, pady=10)
        self.ocr_text_label.pack(fill=tk.BOTH, expand=True)
        
        # Card info display
        info_frame = ttk.LabelFrame(right_frame, text="Card Info (from Scryfall)", padding=5)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.card_info_text = tk.Text(info_frame, height=8, width=30, font=("Courier", 9), bg="white", fg="black")
        self.card_info_text.pack(fill=tk.BOTH, expand=True)
        self.card_info_text.config(state=tk.DISABLED)

    def _test_bin(self, name: str):
        try:
            self.app._move_bin(name)
        except Exception as exc:
            self.status_var.set(f"Test error: {exc}")
    
    def _test_all_channels(self):
        """Test all 16 PCA9685 channels sequentially"""
        try:
            for ch in range(16):
                move_servo(self.app.pca, ch, 110.0, self.app.servo_cfg, self.app.cfg.mock_mode)
                time.sleep(0.15)
                move_servo(self.app.pca, ch, 60.0, self.app.servo_cfg, self.app.cfg.mock_mode)
                time.sleep(0.15)
            self.status_var.set("All 16 channels tested")
        except Exception as exc:
            self.status_var.set(f"Test all error: {exc}")

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

    def _on_update(self, msg, rec=None):
        if isinstance(msg, RoutingDecision):
            self.status_var.set(f"{msg.bin_name} ({msg.reason})")
            # Update card info display with recognized card
            if rec and rec.name:
                self.ocr_text_var.set(rec.name)
                info_text = f"Name: {rec.name}\nSet: {rec.set_code or 'N/A'}\nCollector #: {rec.collector_number or 'N/A'}\nConfidence: {rec.confidence:.2f}"
                if rec.colors:
                    info_text += f"\nColors: {', '.join(rec.colors)}"
                self.card_info_text.config(state=tk.NORMAL)
                self.card_info_text.delete(1.0, tk.END)
                self.card_info_text.insert(1.0, info_text)
                self.card_info_text.config(state=tk.DISABLED)
            else:
                self.ocr_text_var.set("[No card detected]")
        else:
            self.status_var.set(str(msg))
    
    def _capture_ocr(self):
        """Capture a frame and perform OCR"""
        try:
            self.status_var.set("Capturing...")
            self.root.update()
            
            # Capture image
            image_path = self.app.camera.capture()
            self.status_var.set(f"OCR processing...")
            self.root.update()
            
            # Extract text using OCR
            name = self.app.recognizer._extract_name_from_image(image_path)
            
            if name:
                self.ocr_text_var.set(name)
                self.status_var.set(f"OCR: '{name}'")
                
                # Try to look up the card
                meta = self.app.recognizer._lookup_card(name)
                if meta:
                    info_text = f"Name: {meta.name}\nSet: {meta.set_code}\nCollector #: {meta.collector_number}\nArt ID: {meta.art_id}\nColors: {', '.join(meta.colors) or 'Colorless'}\nColor ID: {', '.join(meta.color_identity) or 'Colorless'}"
                    self.card_info_text.config(state=tk.NORMAL)
                    self.card_info_text.delete(1.0, tk.END)
                    self.card_info_text.insert(1.0, info_text)
                    self.card_info_text.config(state=tk.DISABLED)
                    self.status_var.set(f"Found: {meta.name}")
                else:
                    self.card_info_text.config(state=tk.NORMAL)
                    self.card_info_text.delete(1.0, tk.END)
                    self.card_info_text.insert(1.0, "[Scryfall lookup failed]")
                    self.card_info_text.config(state=tk.DISABLED)
                    self.status_var.set(f"OCR found text but Scryfall lookup failed: {name}")
            else:
                self.ocr_text_var.set("[No text detected]")
                self.card_info_text.config(state=tk.NORMAL)
                self.card_info_text.delete(1.0, tk.END)
                self.card_info_text.insert(1.0, "[OCR failed to extract text]")
                self.card_info_text.config(state=tk.DISABLED)
                self.status_var.set("OCR failed")
        except Exception as exc:
            self.status_var.set(f"Error: {exc}")
            self.ocr_text_var.set(f"Error: {exc}")

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
    # Only enable mock mode if critical dependencies are missing
    if board is None or busio is None or PCA9685 is None:
        print("[WARNING] PCA9685 hardware libraries not available; mock mode enabled")
        cfg.mock_mode = True
    if pytesseract is None:
        print("[WARNING] pytesseract not installed; OCR will not work")
    servo_cfg = ServoConfig()
    app = CardSorterApp(cfg, servo_cfg)
    gui = SorterGUI(app)
    print(f"Starting MTG sorter (online OCR + Scryfall, mock_mode={cfg.mock_mode})")
    gui.run()


if __name__ == "__main__":
    main()
