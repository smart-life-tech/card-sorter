import os
import sys
import time
import csv
import math
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Optional imports (work on Windows in mock mode)
try:
    import cv2
    import numpy as np  # FIX #1: Added missing numpy import
except Exception:
    cv2 = None
    np = None

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
    # PCA9685 channel numbers (0-15)
    # Channel 0 is reserved for card hopper
    hopper: int = 0              # Card hopper/dispenser servo
    price_bin: int = 1           # High-value cards bin
    combined_bin: int = 2        # Multi-color/low-value cards bin
    white_blue_bin: int = 3      # White/Blue mono-color bin
    black_bin: int = 4           # Black mono-color bin
    red_bin: int = 5             # Red mono-color bin
    green_bin: int = 6           # Green mono-color bin
    extra_bin: int = 7           # Extra bin (future use)
    # Servo pulse range (in microseconds): 500-2500 typical
    # These convert to 16-bit values for PCA9685
    pulse_open_us: int = 2000    # ~90 degrees
    pulse_close_us: int = 1000   # ~0 degrees
    hopper_dispense_us: int = 1500  # Hopper dispense position
    hopper_rest_us: int = 1000      # Hopper rest position
    pca_address: int = 0x40      # Default PCA9685 I2C address

@dataclass
class AppConfig:
    mock_mode: bool = True  # auto-set below depending on platform
    price_threshold_usd: float = 0.25
    scryfall_timeout: float = 6.0
    capture_resolution: Tuple[int, int] = (1280, 720)
    name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)  # x1,y1,x2,y2 relative
    camera_device_index: int = 0  # IMPROVEMENT: Configurable camera index
    max_capture_failures: int = 10  # IMPROVEMENT: Max consecutive capture failures before stopping

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
    # IMPROVEMENT: Validate channel number
    if channel < 0 or channel > 15:
        print(f"[ERROR] Invalid servo channel {channel} for {name}")
        return
    
    if mock or pca is None:
        print(f"[MOCK SERVO] {name} (ch {channel}) -> open ({pulse_open_us}µs) then close ({pulse_close_us}µs)")
        time.sleep(dwell_s)
        return
    
    # Convert microseconds to 16-bit value (4096 steps per 20ms = 20000µs)
    # PCA9685 runs at 50 Hz (20ms period), 4096 steps per period
    # 1µs = 4096 / 20000 ≈ 0.2048 steps
    open_val = int(pulse_open_us * 4096 / 20000.0)  # IMPROVEMENT: Use float division
    close_val = int(pulse_close_us * 4096 / 20000.0)
    
    try:
        pca.channels[channel].duty_cycle = open_val
        time.sleep(dwell_s)
        pca.channels[channel].duty_cycle = close_val
    except Exception as e:
        print(f"[ERROR] Failed to move servo {name} on channel {channel}: {e}")


def cleanup_pca9685(pca: Optional[any]) -> None:
    if pca is not None:
        try:
            pca.deinit()
        except Exception:
            pass

################################################################################
# Capture + Detection + OCR
################################################################################

def open_camera(resolution: Tuple[int, int], device_index: int = 0):
    if cv2 is None:
        raise RuntimeError("OpenCV not available")
    cap = cv2.VideoCapture(device_index)  # IMPROVEMENT: Configurable device index
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    if not cap.isOpened():
        raise RuntimeError(f"Camera failed to open (device index {device_index})")
    return cap


def detect_card_and_warp(frame) -> Optional[any]:
    if np is None:
        return None
    
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
    
    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Multi-step preprocessing for better OCR accuracy
    # Step 1: Denoise while preserving edges
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Step 2: Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Step 3: Apply morphological operations to clean up text
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    
    # Step 4: Adaptive thresholding for variable lighting conditions
    # Use Otsu's method first for reference
    _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Also try adaptive threshold
    adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY, 11, 2)
    
    # Step 5: Upscale for better Tesseract recognition
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    otsu_thresh = cv2.resize(otsu_thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    adaptive_thresh = cv2.resize(adaptive_thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Try multiple OCR configurations and pick the best result
    configs = [
        "--psm 6 -l eng --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',.-",
        "--psm 7 -l eng --oem 3",  # Single text line
        "--psm 6 -l eng --oem 1",  # Alternate OCR engine
    ]
    
    preprocessed_images = [
        ("grayscale", gray),
        ("otsu", otsu_thresh),
        ("adaptive", adaptive_thresh),
    ]
    
    best_text = None
    best_confidence = 0.0
    
    for prep_name, prep_img in preprocessed_images:
        for config in configs:
            try:
                # Get both text and confidence data
                data = pytesseract.image_to_data(prep_img, config=config, output_type=pytesseract.Output.DICT)
                text = pytesseract.image_to_string(prep_img, config=config)
                
                # Calculate average confidence
                confidences = []
                for conf_str in data['confidence']:
                    try:
                        conf = float(conf_str)
                        if conf > 0:  # Ignore -1 (no detection)
                            confidences.append(conf)
                    except:
                        pass
                
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                if text and len(text.strip()) >= 2 and avg_confidence > best_confidence:
                    best_text = text
                    best_confidence = avg_confidence
            except Exception:
                continue
    
    if not best_text:
        return None
    
    # Post-process the recognized text
    name = best_text.strip().replace("\n", " ")
    # Remove common OCR artifacts
    name = name.strip("-—_ :'\"")
    # Clean up extra spaces
    name = " ".join(name.split())
    
    # Additional validation: MTG card names typically have 2+ characters
    # and don't have excessive repeated characters
    if len(name) < 2:
        return None
    
    # Check for obviously corrupted text (excessive special characters)
    special_count = sum(1 for c in name if not (c.isalnum() or c.isspace() or c in "'-"))
    if special_count > len(name) * 0.3:  # More than 30% special chars = likely OCR error
        return None
    
    return name

################################################################################
# Scryfall Lookup
################################################################################

# IMPROVEMENT: Rate limiting for Scryfall API
_last_scryfall_request = 0
_MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests

def scryfall_lookup(name: str, timeout: float = 6.0) -> Optional[CardInfo]:
    global _last_scryfall_request
    
    # IMPROVEMENT: Enforce rate limiting
    elapsed = time.time() - _last_scryfall_request
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    
    try:
        _last_scryfall_request = time.time()
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
    except Exception as e:
        print(f"[ERROR] Scryfall lookup failed for '{name}': {e}")
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
            "price_bin": self.servo_cfg.price_bin,
            "combined_bin": self.servo_cfg.combined_bin,
            "white_blue_bin": self.servo_cfg.white_blue_bin,
            "black_bin": self.servo_cfg.black_bin,
            "red_bin": self.servo_cfg.red_bin,
            "green_bin": self.servo_cfg.green_bin,
        }
        self.cap = None
        self.capture_failures = 0  # IMPROVEMENT: Track consecutive failures

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
        for name in ["price_bin","combined_bin","white_blue_bin","black_bin","red_bin","green_bin"]:
            ttk.Button(frm, text=f"Test {name}", command=lambda n=name: self.test_bin(n)).grid(row=r, column=0, columnspan=2, sticky="we")
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

    def start(self):
        # Open camera
        try:
            self.cap = open_camera(self.cfg.capture_resolution, self.cfg.camera_device_index)
            self.capture_failures = 0  # Reset failure counter
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
                # IMPROVEMENT: Track consecutive failures
                self.capture_failures += 1
                if self.capture_failures >= self.cfg.max_capture_failures:
                    self.status_var.set(f"Camera failed {self.capture_failures} times - stopping")
                    self.stop()
                    return
                self.status_var.set(f"Capture failed ({self.capture_failures}/{self.cfg.max_capture_failures})")
                self._schedule_tick()
                return
            
            # Reset failure counter on successful capture
            self.capture_failures = 0
            
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
            
            # FIX #2: Correct servo call with proper parameters
            ch = self.channel_map.get(bin_name, -1)
            if ch >= 0:
                move_servo(
                    self.pca, 
                    bin_name, 
                    ch, 
                    self.servo_cfg.pulse_open_us, 
                    self.servo_cfg.pulse_close_us, 
                    mock=self.cfg.mock_mode
                )
            
            self.status_var.set(f"{info.name} → {bin_name} (${info.price_usd if info.price_usd is not None else 'N/A'})")
        except Exception as e:
            print(f"[ERROR] Exception in _tick: {e}")
            import traceback
            traceback.print_exc()
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
