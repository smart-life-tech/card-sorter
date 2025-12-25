#!/usr/bin/env python3
"""
MTG Card Sorter - Command Line Interface
Headless version for SSH/remote testing without GUI
"""

import os
import sys
import time
import argparse
import platform
from dataclasses import dataclass
from typing import Optional, Tuple, List

# Optional imports (work on Windows in mock mode)
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from adafruit_servokit import ServoKit
except Exception:
    ServoKit = None

import requests

################################################################################
# Config & Models
################################################################################

@dataclass
class ServoConfig:
    # PCA9685 channel numbers (0-15)
    # Channel 0 is reserved for card hopper (360° continuous rotation)
    hopper: int = 0              # Card hopper/dispenser servo (360° continuous)
    price_bin: int = 1           # High-value cards bin (SG90 0-180°)
    combined_bin: int = 2        # Multi-color/low-value cards bin (SG90 0-180°)
    white_blue_bin: int = 3      # White/Blue mono-color bin (SG90 0-180°)
    black_bin: int = 4           # Black mono-color bin (SG90 0-180°)
    red_bin: int = 5             # Red mono-color bin (SG90 0-180°)
    green_bin: int = 6           # Green mono-color bin (SG90 0-180°)
    extra_bin: int = 7           # Extra bin (future use)
    # Servo angles (0-180° positional servos)
    angle_open: int = 180        # Fully open position
    angle_close: int = 0         # Fully closed position
    # Continuous rotation servo (hopper) - uses throttle (-1.0 to 1.0)
    hopper_throttle: float = 0.2  # Forward rotation speed (0.0 = stop, 1.0 = full speed)
    # SG90 servo pulse width range (microseconds)
    pulse_min: int = 500         # Minimum pulse width for 0° (SG90: 500-1000µs)
    pulse_max: int = 2500        # Maximum pulse width for 180° (SG90: 2000-2500µs)
    # PCA9685 settings
    num_channels: int = 16       # Number of servo channels
    pca_address: int = 0x40      # Default PCA9685 I2C address

@dataclass
class AppConfig:
    mock_mode: bool = True
    price_threshold_usd: float = 0.25
    scryfall_timeout: float = 6.0
    capture_resolution: Tuple[int, int] = (1280, 720)
    name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)
    camera_device_index: int = 0
    max_capture_failures: int = 10

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
    return platform.system() == "Linux" and ServoKit is not None


def setup_servokit(servo_cfg: ServoConfig, mock: bool) -> Optional[any]:
    """Initialize ServoKit for controlling servos via PCA9685"""
    if mock:
        print(f"[MOCK SERVOKIT] Using mock servo outputs ({servo_cfg.num_channels} channels)")
        return None
    
    print(f"\n[SERVOKIT DEBUG] Starting initialization...")
    print(f"[SERVOKIT DEBUG] Channels: {servo_cfg.num_channels}")
    print(f"[SERVOKIT DEBUG] I2C Address: 0x{servo_cfg.pca_address:02x}")
    print(f"[SERVOKIT DEBUG] Pulse range: {servo_cfg.pulse_min}µs - {servo_cfg.pulse_max}µs")
    
    try:
        print(f"[SERVOKIT DEBUG] Creating ServoKit instance...")
        kit = ServoKit(channels=servo_cfg.num_channels, address=servo_cfg.pca_address)
        print(f"[SERVOKIT DEBUG] ✓ ServoKit instance created successfully")
        
        # Configure pulse width range for all positional servos (channels 1-15)
        # Channel 0 is for continuous rotation servo (hopper)
        print(f"[SERVOKIT DEBUG] Configuring positional servos (channels 1-15)...")
        configured_channels = []
        failed_channels = []
        
        for channel in range(1, 16):  # Skip channel 0 (hopper)
            try:
                print(f"[SERVOKIT DEBUG]   Channel {channel}: Setting pulse width range...", end="", flush=True)
                kit.servo[channel].set_pulse_width_range(servo_cfg.pulse_min, servo_cfg.pulse_max)
                kit.servo[channel].actuation_range = 180
                configured_channels.append(channel)
                print(" ✓")
            except Exception as e:
                failed_channels.append(channel)
                print(f" ✗ Error: {e}")
        
        print(f"[SERVOKIT DEBUG] Configured channels: {configured_channels}")
        if failed_channels:
            print(f"[SERVOKIT DEBUG] Failed channels: {failed_channels}")
        
        # Configure continuous servo on channel 0 (hopper)
        print(f"[SERVOKIT DEBUG] Configuring continuous servo (channel 0)...")
        try:
            kit.continuous_servo[0].set_pulse_width_range(1000, 2000)
            print(f"[SERVOKIT DEBUG] ✓ Channel 0 (hopper) configured")
        except Exception as e:
            print(f"[SERVOKIT DEBUG] ✗ Channel 0 (hopper) failed: {e}")
        
        print(f"[SERVOKIT] ✓ Initialized {servo_cfg.num_channels} channels at 0x{servo_cfg.pca_address:02x}")
        print(f"[SERVOKIT] IMPORTANT: Ensure servos have external 5-6V power supply!")
        print(f"[SERVOKIT] IMPORTANT: Raspberry Pi 3.3V/5V pins CANNOT power servos!\n")
        return kit
    except Exception as e:
        print(f"[SERVOKIT] ✗ Failed to initialize: {e}")
        print(f"[SERVOKIT DEBUG] Exception type: {type(e).__name__}")
        print(f"[SERVOKIT DEBUG] Exception details: {str(e)}")
        print(f"\n[TROUBLESHOOTING] If initialization failed:")
        print(f"  1. Check I2C is enabled: sudo raspi-config -> Interface Options -> I2C")
        print(f"  2. Verify PCA9685 connection: i2cdetect -y 1")
        print(f"  3. Check wiring: SDA->GPIO2, SCL->GPIO3, VCC->3.3V, GND->GND")
        print(f"  4. Install dependencies: pip3 install adafruit-circuitpython-servokit\n")
        return None


def move_servo(kit: Optional[any], name: str, channel: int, angle_open: int, angle_close: int, dwell_s: float = 0.5, mock: bool = True) -> None:
    """Move a standard positional servo (0-180°) - for channels 1-15 (SG90 servos)"""
    print(f"\n[SERVO DEBUG] ========== SERVO MOVEMENT START ==========")
    print(f"[SERVO DEBUG] Name: {name}")
    print(f"[SERVO DEBUG] Channel: {channel}")
    print(f"[SERVO DEBUG] Target angles: OPEN={angle_open}°, CLOSE={angle_close}°")
    print(f"[SERVO DEBUG] Dwell time: {dwell_s}s")
    print(f"[SERVO DEBUG] Mock mode: {mock}")
    print(f"[SERVO DEBUG] Kit object: {kit}")
    
    if channel < 0 or channel > 15:
        print(f"[SERVO ERROR] Invalid servo channel {channel} for {name}")
        print(f"[SERVO DEBUG] Valid channels: 0-15")
        return
    
    if mock or kit is None:
        print(f"[SERVO MOCK] {name} (ch {channel}) -> OPEN ({angle_open}°) ... CLOSE ({angle_close}°)")
        print(f"[SERVO DEBUG] Running in MOCK mode - no hardware commands sent")
        time.sleep(dwell_s * 2)  # Mock takes longer to simulate movement
        print(f"[SERVO DEBUG] ========== SERVO MOVEMENT END (MOCK) ==========\n")
        return
    
    try:
        print(f"[SERVO HARDWARE] Attempting to move {name} on channel {channel}")
        print(f"[SERVO DEBUG] Step 1: Setting angle to {angle_open}° (OPEN)...", end="", flush=True)
        
        # Set to open position
        kit.servo[channel].angle = angle_open
        print(f" ✓ Command sent")
        print(f"[SERVO DEBUG] Waiting {dwell_s}s for servo to reach position...")
        time.sleep(dwell_s)
        
        print(f"[SERVO DEBUG] Step 2: Setting angle to {angle_close}° (CLOSE)...", end="", flush=True)
        
        # Set to close position
        kit.servo[channel].angle = angle_close
        print(f" ✓ Command sent")
        print(f"[SERVO DEBUG] Waiting 0.3s for servo to reach position...")
        time.sleep(0.3)  # Give servo time to reach closed position
        
        print(f"[SERVO SUCCESS] {name} movement complete")
        print(f"[SERVO DEBUG] ========== SERVO MOVEMENT END (SUCCESS) ==========\n")
        
        # Verify movement
        print(f"[SERVO VERIFY] If servo did NOT move, check:")
        print(f"  1. External power supply connected (5-6V, 1-2A per servo)")
        print(f"  2. Servo signal wire connected to channel {channel} on PCA9685")
        print(f"  3. Servo power (red) and ground (brown/black) connected")
        print(f"  4. PCA9685 V+ terminal has external power (NOT from Pi)")
        print(f"  5. Common ground between Pi and servo power supply")
        print(f"  6. Servo is functional (test with another controller)")
        
    except Exception as e:
        print(f"\n[SERVO ERROR] Failed to move servo {name}: {e}")
        print(f"[SERVO DEBUG] Exception type: {type(e).__name__}")
        print(f"[SERVO DEBUG] Exception details: {str(e)}")
        print(f"[SERVO DEBUG] Channel: {channel}")
        print(f"[SERVO DEBUG] ========== SERVO MOVEMENT END (ERROR) ==========\n")


def move_continuous_servo(kit: Optional[any], name: str, channel: int, throttle: float, duration_s: float = 0.5, mock: bool = True) -> None:
    """Move a continuous rotation servo (360°) - for channel 0 (hopper)
    
    Args:
        throttle: -1.0 to 1.0 (negative = reverse, 0 = stop, positive = forward)
    """
    print(f"\n[CONTINUOUS SERVO DEBUG] ========== CONTINUOUS SERVO START ==========")
    print(f"[CONTINUOUS SERVO DEBUG] Name: {name}")
    print(f"[CONTINUOUS SERVO DEBUG] Channel: {channel}")
    print(f"[CONTINUOUS SERVO DEBUG] Throttle: {throttle} (-1.0=reverse, 0=stop, 1.0=forward)")
    print(f"[CONTINUOUS SERVO DEBUG] Duration: {duration_s}s")
    print(f"[CONTINUOUS SERVO DEBUG] Mock mode: {mock}")
    print(f"[CONTINUOUS SERVO DEBUG] Kit object: {kit}")
    
    if channel < 0 or channel > 15:
        print(f"[CONTINUOUS SERVO ERROR] Invalid servo channel {channel} for {name}")
        return
    
    if mock or kit is None:
        print(f"[CONTINUOUS SERVO MOCK] {name} (ch {channel}) -> ROTATE (throttle={throttle}) for {duration_s}s ... STOP")
        print(f"[CONTINUOUS SERVO DEBUG] Running in MOCK mode - no hardware commands sent")
        time.sleep(duration_s)
        print(f"[CONTINUOUS SERVO DEBUG] ========== CONTINUOUS SERVO END (MOCK) ==========\n")
        return
    
    try:
        print(f"[CONTINUOUS SERVO HARDWARE] Attempting to rotate {name} on channel {channel}")
        print(f"[CONTINUOUS SERVO DEBUG] Step 1: Setting throttle to {throttle}...", end="", flush=True)
        
        kit.continuous_servo[channel].throttle = throttle
        print(f" ✓ Command sent")
        print(f"[CONTINUOUS SERVO DEBUG] Rotating for {duration_s}s...")
        time.sleep(duration_s)
        
        print(f"[CONTINUOUS SERVO DEBUG] Step 2: Stopping (throttle=0)...", end="", flush=True)
        kit.continuous_servo[channel].throttle = 0  # Stop
        print(f" ✓ Command sent")
        time.sleep(0.2)  # Brief pause after stopping
        
        print(f"[CONTINUOUS SERVO SUCCESS] {name} rotation complete")
        print(f"[CONTINUOUS SERVO DEBUG] ========== CONTINUOUS SERVO END (SUCCESS) ==========\n")
        
        # Verify movement
        print(f"[CONTINUOUS SERVO VERIFY] If servo did NOT rotate, check:")
        print(f"  1. Servo is a 360° continuous rotation servo (not standard 0-180°)")
        print(f"  2. External power supply connected (5-6V, 1-2A)")
        print(f"  3. Servo signal wire connected to channel {channel} on PCA9685")
        print(f"  4. Throttle value is sufficient (try 0.5 or higher)")
        
    except Exception as e:
        print(f"\n[CONTINUOUS SERVO ERROR] Failed to move continuous servo {name}: {e}")
        print(f"[CONTINUOUS SERVO DEBUG] Exception type: {type(e).__name__}")
        print(f"[CONTINUOUS SERVO DEBUG] Exception details: {str(e)}")
        print(f"[CONTINUOUS SERVO DEBUG] ========== CONTINUOUS SERVO END (ERROR) ==========\n")


def cleanup_servokit(kit: Optional[any]) -> None:
    """Stop all servos and clean up"""
    if kit is not None:
        try:
            # Stop all continuous servos
            for i in range(16):
                try:
                    kit.continuous_servo[i].throttle = 0
                except Exception:
                    pass
            print("[SERVOKIT] Cleaned up")
        except Exception:
            pass

################################################################################
# Capture + Detection + OCR
################################################################################

def open_camera(resolution: Tuple[int, int], device_index: int = 0):
    if cv2 is None:
        raise RuntimeError("OpenCV not available")
    cap = cv2.VideoCapture(device_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    if not cap.isOpened():
        raise RuntimeError(f"Camera failed to open (device {device_index})")
    print(f"[CAMERA] ✓ Opened device {device_index} at {resolution[0]}x{resolution[1]}")
    return cap


def detect_card_and_warp(frame) -> Optional[any]:
    if np is None:
        return None
    
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

_last_scryfall_request = 0
_MIN_REQUEST_INTERVAL = 0.1

def scryfall_lookup(name: str, timeout: float = 6.0) -> Optional[CardInfo]:
    global _last_scryfall_request
    
    elapsed = time.time() - _last_scryfall_request
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    
    try:
        _last_scryfall_request = time.time()
        r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
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
        print(f"[SCRYFALL] ✗ Lookup failed: {e}")
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
# CLI Commands
################################################################################

def test_hopper(kit, servo_cfg, mock: bool):
    """Test the hopper servo (channel 0) - 360° continuous rotation"""
    print(f"\n[TEST] Testing hopper servo (channel {servo_cfg.hopper})...")
    print("[INFO] Hopper is a 360° continuous rotation servo")
    move_continuous_servo(kit, "hopper", servo_cfg.hopper, servo_cfg.hopper_throttle, duration_s=0.5, mock=mock)
    print("[TEST] Complete\n")


def test_servo(kit, servo_cfg, bin_name: str, mock: bool):
    """Test a single servo bin"""
    channel_map = {
        "hopper": servo_cfg.hopper,
        "price": servo_cfg.price_bin,
        "combined": servo_cfg.combined_bin,
        "white_blue": servo_cfg.white_blue_bin,
        "black": servo_cfg.black_bin,
        "red": servo_cfg.red_bin,
        "green": servo_cfg.green_bin,
    }
    
    ch = channel_map.get(bin_name, -1)
    if ch < 0:
        print(f"[ERROR] Unknown bin: {bin_name}")
        print(f"Available bins: {', '.join(channel_map.keys())}")
        return
    
    # Hopper uses continuous rotation servo (360°)
    if bin_name == "hopper":
        print(f"\n[TEST] Testing {bin_name} (channel {ch}) - 360° continuous rotation servo...")
        move_continuous_servo(kit, bin_name, ch, servo_cfg.hopper_throttle, duration_s=0.5, mock=mock)
    else:
        # Bins use standard positional servos (0-180°)
        print(f"\n[TEST] Testing {bin_name}_bin (channel {ch}) - 0-180° positional servo...")
        move_servo(kit, f"{bin_name}_bin", ch, servo_cfg.angle_open, servo_cfg.angle_close, mock=mock)
    print("[TEST] Complete\n")


def test_all_servos(kit, servo_cfg, mock: bool):
    """Test all servo bins in sequence"""
    bins = ["hopper", "price", "combined", "white_blue", "black", "red", "green"]
    print("\n[TEST] Testing all servos...")
    for bin_name in bins:
        test_servo(kit, servo_cfg, bin_name, mock)
        time.sleep(0.5)
    print("[TEST] All servos tested\n")


def test_all_channels(kit, servo_cfg, mock: bool):
    """Test all 16 servo channels with different angles"""
    print("\n[TEST] Testing all 16 servo channels...")
    print("[INFO] This will test each channel at different angles")
    print("[INFO] Watch for ANY movement on ANY servo\n")
    
    if mock or kit is None:
        print("[MOCK] Skipping hardware test in mock mode\n")
        print("[DEBUG] To test hardware, run with --no-mock flag")
        return
    
    print(f"[DEBUG] Kit object type: {type(kit)}")
    print(f"[DEBUG] Kit object: {kit}")
    print(f"[DEBUG] Starting comprehensive channel test...\n")
    
    # Test angles to try
    test_angles = [0, 45, 90, 135, 180]
    
    for channel in range(16):
        print(f"\n{'='*60}")
        print(f"Channel {channel}:")
        print(f"{'='*60}")
        print(f"[DEBUG] Testing channel {channel} with angles: {test_angles}")
        
        for angle in test_angles:
            print(f"  Setting {angle}°...", end="", flush=True)
            
            try:
                print(f" [sending command]...", end="", flush=True)
                kit.servo[channel].angle = angle
                print(f" [waiting 0.8s]...", end="", flush=True)
                time.sleep(0.8)  # Give servo time to move
                print(" ✓")
            except Exception as e:
                print(f" ✗ Error: {e}")
                print(f"    [DEBUG] Exception type: {type(e).__name__}")
        
        # Return to neutral
        try:
            print(f"  Returning to 90° (neutral)...", end="", flush=True)
            kit.servo[channel].angle = 90
            time.sleep(0.3)
            print(" ✓")
        except Exception as e:
            print(f" ✗ Error: {e}")
        
        time.sleep(0.3)
    
    print(f"\n{'='*60}")
    print("[TEST] All 16 channels tested")
    print(f"{'='*60}")
    print("\n[TROUBLESHOOTING] If you saw NO movement on ANY channel:")
    print("  1. POWER SUPPLY:")
    print("     - Servos need external 5-6V power (1-2A per servo)")
    print("     - Connect power supply to PCA9685 V+ and GND terminals")
    print("     - DO NOT power servos from Raspberry Pi 5V pin!")
    print("  2. WIRING:")
    print("     - PCA9685 to Pi: SDA->GPIO2, SCL->GPIO3, VCC->3.3V, GND->GND")
    print("     - Servo to PCA9685: Signal->Channel pin, Red->V+, Brown/Black->GND")
    print("     - Common ground: Connect Pi GND to power supply GND")
    print("  3. I2C CONNECTION:")
    print("     - Run: i2cdetect -y 1")
    print("     - Should show '40' at address 0x40")
    print("  4. SERVO TYPE:")
    print("     - Standard servos: 0-180° (SG90, MG90S, etc.)")
    print("     - Continuous servos: 360° rotation (for hopper)")
    print("  5. TEST SERVO SEPARATELY:")
    print("     - Try servo with Arduino or servo tester")
    print("     - Verify servo is functional")
    print(f"{'='*60}\n")


def test_camera(cfg: AppConfig):
    """Test camera capture"""
    print("\n[TEST] Testing camera...")
    try:
        cap = open_camera(cfg.capture_resolution, cfg.camera_device_index)
        print("[TEST] Capturing 5 frames...")
        for i in range(5):
            ret, frame = cap.read()
            if ret:
                print(f"  Frame {i+1}/5: ✓ {frame.shape}")
            else:
                print(f"  Frame {i+1}/5: ✗ Failed")
            time.sleep(0.2)
        cap.release()
        print("[TEST] Camera test complete\n")
    except Exception as e:
        print(f"[ERROR] Camera test failed: {e}\n")


def test_i2c():
    """Test I2C connection"""
    print("\n[TEST] Testing I2C...")
    try:
        import subprocess
        result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
        print(result.stdout)
        if '40' in result.stdout:
            print("[TEST] ✓ PCA9685 detected at 0x40\n")
        else:
            print("[TEST] ✗ PCA9685 not found at 0x40\n")
    except Exception as e:
        print(f"[ERROR] I2C test failed: {e}")
        print("Try running: i2cdetect -y 1\n")


def run_sorter(cfg: AppConfig, servo_cfg: ServoConfig, kit, mode: str, count: int):
    """Run the card sorter for N cards"""
    print(f"\n[SORTER] Starting in {mode} mode...")
    print(f"[SORTER] Will process {count} card(s)")
    print(f"[SORTER] Threshold: ${cfg.price_threshold_usd}")
    print("[SORTER] Press Ctrl+C to stop\n")
    
    channel_map = {
        "price_bin": servo_cfg.price_bin,
        "combined_bin": servo_cfg.combined_bin,
        "white_blue_bin": servo_cfg.white_blue_bin,
        "black_bin": servo_cfg.black_bin,
        "red_bin": servo_cfg.red_bin,
        "green_bin": servo_cfg.green_bin,
    }
    
    try:
        cap = open_camera(cfg.capture_resolution, cfg.camera_device_index)
        
        processed = 0
        failures = 0
        
        while processed < count:
            print(f"\n[{processed+1}/{count}] Waiting for card...", end="", flush=True)
            
            # Wait for card detection
            detected = False
            for attempt in range(50):  # 5 seconds timeout
                ret, frame = cap.read()
                if not ret:
                    failures += 1
                    if failures >= cfg.max_capture_failures:
                        print(f"\n[ERROR] Camera failed {failures} times. Stopping.")
                        break
                    continue
                
                failures = 0
                warped = detect_card_and_warp(frame)
                if warped is not None:
                    detected = True
                    print(" DETECTED!")
                    break
                time.sleep(0.1)
            
            if not detected:
                print(" TIMEOUT")
                continue
            
            # OCR
            print("  [OCR] Reading card name...", end="", flush=True)
            name = ocr_name_from_image(warped, cfg.name_roi)
            if not name:
                print(" FAILED")
                continue
            print(f" '{name}'")
            
            # Scryfall lookup
            print(f"  [SCRYFALL] Looking up...", end="", flush=True)
            info = scryfall_lookup(name, cfg.scryfall_timeout)
            if not info:
                print(" NOT FOUND")
                continue
            
            price_str = f"${info.price_usd:.2f}" if info.price_usd else "N/A"
            colors_str = ",".join(info.colors) if info.colors else "colorless"
            print(f" {price_str} ({colors_str})")
            
            # Route
            bin_name = decide_bin(info, mode, cfg.price_threshold_usd)
            ch = channel_map.get(bin_name, -1)
            
            print(f"  [ROUTE] → {bin_name}")
            
            if ch >= 0:
                move_servo(kit, bin_name, ch, servo_cfg.angle_open, servo_cfg.angle_close, mock=cfg.mock_mode)
            
            processed += 1
            time.sleep(1)  # Cooldown between cards
        
        cap.release()
        print(f"\n[SORTER] Complete! Processed {processed} card(s)\n")
        
    except KeyboardInterrupt:
        print("\n\n[SORTER] Stopped by user\n")
    except Exception as e:
        print(f"\n[ERROR] {e}\n")

################################################################################
# Main CLI
################################################################################

def main():
    parser = argparse.ArgumentParser(description="MTG Card Sorter - CLI Version")
    parser.add_argument('command', choices=['test-servo', 'test-hopper', 'test-all', 'test-all-channels', 'test-camera', 'test-i2c', 'run'],
                       help='Command to execute')
    parser.add_argument('--bin', type=str, help='Bin name for test-servo (hopper, price, combined, white_blue, black, red, green)')
    parser.add_argument('--mode', type=str, default='price', choices=['price', 'color'],
                       help='Sorting mode (default: price)')
    parser.add_argument('--count', type=int, default=10, help='Number of cards to process (default: 10)')
    parser.add_argument('--threshold', type=float, default=0.25, help='Price threshold in USD (default: 0.25)')
    parser.add_argument('--mock', action='store_true', help='Enable mock mode (no hardware)')
    parser.add_argument('--no-mock', action='store_true', help='Disable mock mode (use hardware)')
    
    args = parser.parse_args()
    
    # Setup config
    cfg = AppConfig()
    if args.no_mock:
        cfg.mock_mode = False
    elif args.mock:
        cfg.mock_mode = True
    else:
        cfg.mock_mode = not is_rpi()
    
    cfg.price_threshold_usd = args.threshold
    
    servo_cfg = ServoConfig()
    
    print("=" * 60)
    print("MTG Card Sorter - CLI Version")
    print("=" * 60)
    print(f"Mode: {'MOCK' if cfg.mock_mode else 'HARDWARE'}")
    print(f"Platform: {platform.system()}")
    print("=" * 60)
    
    # Setup hardware
    kit = setup_servokit(servo_cfg, mock=cfg.mock_mode)
    
    try:
        # Execute command
        if args.command == 'test-servo':
            if not args.bin:
                print("[ERROR] --bin required for test-servo")
                print("Example: python3 mtg_sorter_cli.py test-servo --bin price")
                return
            test_servo(kit, servo_cfg, args.bin, cfg.mock_mode)
        
        elif args.command == 'test-hopper':
            test_hopper(kit, servo_cfg, cfg.mock_mode)
        
        elif args.command == 'test-all':
            test_all_servos(kit, servo_cfg, cfg.mock_mode)
        
        elif args.command == 'test-all-channels':
            test_all_channels(kit, servo_cfg, cfg.mock_mode)
        
        elif args.command == 'test-camera':
            test_camera(cfg)
        
        elif args.command == 'test-i2c':
            test_i2c()
        
        elif args.command == 'run':
            run_sorter(cfg, servo_cfg, kit, args.mode, args.count)
    
    finally:
        cleanup_servokit(kit)
        print("[CLEANUP] Done")


if __name__ == "__main__":
    main()
