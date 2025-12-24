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
    try:
        kit = ServoKit(channels=servo_cfg.num_channels, address=servo_cfg.pca_address)
        print(f"[SERVOKIT] ✓ Initialized {servo_cfg.num_channels} channels at 0x{servo_cfg.pca_address:02x}")
        return kit
    except Exception as e:
        print(f"[SERVOKIT] ✗ Failed to initialize: {e}")
        return None


def move_servo(kit: Optional[any], name: str, channel: int, angle_open: int, angle_close: int, dwell_s: float = 0.5, mock: bool = True) -> None:
    """Move a standard positional servo (0-180°) - for channels 1-15 (SG90 servos)"""
    if channel < 0 or channel > 15:
        print(f"[ERROR] Invalid servo channel {channel} for {name}")
        return
    
    if mock or kit is None:
        print(f"[SERVO] {name} (ch {channel}) -> OPEN ({angle_open}°) ... CLOSE ({angle_close}°)")
        time.sleep(dwell_s * 2)  # Mock takes longer to simulate movement
        return
    
    try:
        print(f"[SERVO] {name} (ch {channel}) -> OPEN ({angle_open}°)", end="", flush=True)
        kit.servo[channel].angle = angle_open
        time.sleep(dwell_s)
        print(f" ... CLOSE ({angle_close}°)", flush=True)
        kit.servo[channel].angle = angle_close
        time.sleep(0.3)  # Give servo time to reach closed position
    except Exception as e:
        print(f"\n[ERROR] Failed to move servo {name}: {e}")


def move_continuous_servo(kit: Optional[any], name: str, channel: int, throttle: float, duration_s: float = 0.5, mock: bool = True) -> None:
    """Move a continuous rotation servo (360°) - for channel 0 (hopper)
    
    Args:
        throttle: -1.0 to 1.0 (negative = reverse, 0 = stop, positive = forward)
    """
    if channel < 0 or channel > 15:
        print(f"[ERROR] Invalid servo channel {channel} for {name}")
        return
    
    if mock or kit is None:
        print(f"[CONTINUOUS SERVO] {name} (ch {channel}) -> ROTATE (throttle={throttle}) for {duration_s}s ... STOP")
        time.sleep(duration_s)
        return
    
    try:
        print(f"[CONTINUOUS SERVO] {name} (ch {channel}) -> ROTATE (throttle={throttle})", end="", flush=True)
        kit.continuous_servo[channel].throttle = throttle
        time.sleep(duration_s)
        print(" ... STOP", flush=True)
        kit.continuous_servo[channel].throttle = 0  # Stop
        time.sleep(0.2)  # Brief pause after stopping
    except Exception as e:
        print(f"\n[ERROR] Failed to move continuous servo {name}: {e}")


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
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    config = "--psm 6 -l eng"
    text = pytesseract.image_to_string(gray, config=config)
    if not text:
        return None
    name = text.strip().replace("\n", " ")
    name = name.strip("-—_ :")
    return name if len(name) >= 2 else None

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
        return
    
    # Test angles to try
    test_angles = [0, 45, 90, 135, 180]
    
    for channel in range(16):
        print(f"\n{'='*60}")
        print(f"Channel {channel}:")
        print(f"{'='*60}")
        
        for angle in test_angles:
            print(f"  Setting {angle}°...", end="", flush=True)
            
            try:
                kit.servo[channel].angle = angle
                time.sleep(0.8)  # Give servo time to move
                print(" ✓")
            except Exception as e:
                print(f" ✗ Error: {e}")
        
        # Return to neutral
        try:
            kit.servo[channel].angle = 90
            print("  Returning to 90°...")
        except Exception:
            pass
        
        time.sleep(0.3)
    
    print(f"\n{'='*60}")
    print("[TEST] All 16 channels tested")
    print("[INFO] If you saw NO movement on channels 1-15, check:")
    print("  1. Power supply to servos (5-6V with sufficient current)")
    print("  2. Servo connections (signal, power, ground)")
    print("  3. Servo type (SG90 or similar 0-180° servos)")
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
