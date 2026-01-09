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
