#!/usr/bin/env python3
"""
Camera Calibration Tool for MTG Card Sorter
Shows live preview with OCR region overlay for adjusting settings
"""

import cv2
import numpy as np
import sys
import argparse
from typing import Tuple, Optional

try:
    import pytesseract
except Exception:
    pytesseract = None

################################################################################
# Configuration
################################################################################

class CalibrationConfig:
    def __init__(self):
        self.resolution = (1280, 720)
        self.device_index = 0
        # OCR ROI (x1, y1, x2, y2) as fractions of warped image
        self.name_roi = [0.08, 0.08, 0.92, 0.22]
        self.warp_width = 720
        self.warp_height = 1024

################################################################################
# Card Detection
################################################################################

def detect_card_and_warp(frame, config: CalibrationConfig) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Detect card and return both original with overlay and warped image"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None, None
    
    # Find largest contour
    cnt = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    
    if len(approx) != 4:
        return None, None
    
    # Draw contour on original frame
    frame_with_overlay = frame.copy()
    cv2.drawContours(frame_with_overlay, [approx], -1, (0, 255, 0), 3)
    
    # Warp perspective
    pts = approx.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    ordered = np.array([tl, tr, br, bl], dtype="float32")
    
    w = config.warp_width
    h = config.warp_height
    dst = np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(frame, M, (w, h))
    
    return frame_with_overlay, warped

################################################################################
# OCR Preview
################################################################################

def draw_ocr_region(warped: np.ndarray, config: CalibrationConfig) -> np.ndarray:
    """Draw OCR region on warped image"""
    h, w = warped.shape[:2]
    x1 = int(config.name_roi[0] * w)
    y1 = int(config.name_roi[1] * h)
    x2 = int(config.name_roi[2] * w)
    y2 = int(config.name_roi[3] * h)
    
    # Draw rectangle
    result = warped.copy()
    cv2.rectangle(result, (x1, y1), (x2, y2), (0, 255, 0), 2)
    
    # Add label
    cv2.putText(result, "OCR REGION", (x1, y1-10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    return result

def extract_and_process_ocr_region(warped: np.ndarray, config: CalibrationConfig) -> Tuple[np.ndarray, str]:
    """Extract OCR region and perform OCR"""
    h, w = warped.shape[:2]
    x1 = int(config.name_roi[0] * w)
    y1 = int(config.name_roi[1] * h)
    x2 = int(config.name_roi[2] * w)
    y2 = int(config.name_roi[3] * h)
    
    # Extract ROI
    roi = warped[y1:y2, x1:x2]
    
    # Preprocess
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Upscale for better OCR
    gray_upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    # OCR
    text = ""
    if pytesseract:
        try:
            config_str = "--psm 6 -l eng"
            text = pytesseract.image_to_string(gray_upscaled, config=config_str)
            text = text.strip().replace("\n", " ").strip("-—_ :")
        except Exception as e:
            text = f"OCR Error: {e}"
    else:
        text = "pytesseract not available"
    
    # Convert grayscale to BGR for display
    gray_bgr = cv2.cvtColor(gray_upscaled, cv2.COLOR_GRAY2BGR)
    
    return gray_bgr, text

################################################################################
# Main Calibration Loop
################################################################################

def run_calibration(config: CalibrationConfig, save_mode: bool = False):
    """Run interactive calibration"""
    print("=" * 70)
    print("MTG Card Sorter - Camera Calibration Tool")
    print("=" * 70)
    print(f"Camera: Device {config.device_index} @ {config.resolution[0]}x{config.resolution[1]}")
    print(f"OCR ROI: {config.name_roi}")
    print("=" * 70)
    print("\nControls:")
    print("  q - Quit")
    print("  s - Save current frame and OCR region")
    print("  r - Reset ROI to defaults")
    print("  Arrow Keys - Adjust ROI position")
    print("  +/- - Adjust ROI size")
    print("  SPACE - Freeze frame for adjustment")
    print("=" * 70)
    
    # Open camera
    cap = cv2.VideoCapture(config.device_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution[1])
    
    if not cap.isOpened():
        print(f"ERROR: Could not open camera device {config.device_index}")
        return
    
    print("\n✓ Camera opened successfully")
    print("\nPlace a card in view and press SPACE to freeze for adjustment\n")
    
    frozen = False
    frozen_frame = None
    frozen_warped = None
    frame_count = 0
    
    while True:
        if not frozen:
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to capture frame")
                break
            frame_count += 1
        else:
            frame = frozen_frame.copy()
        
        # Detect card
        frame_with_overlay, warped = detect_card_and_warp(frame, config)
        
        if warped is not None:
            if frozen:
                warped = frozen_warped.copy()
            
            # Draw OCR region
            warped_with_roi = draw_ocr_region(warped, config)
            
            # Extract and OCR
            ocr_preview, ocr_text = extract_and_process_ocr_region(warped, config)
            
            # Resize for display
            display_warped = cv2.resize(warped_with_roi, (360, 512))
            display_ocr = cv2.resize(ocr_preview, (360, 100))
            
            # Add text overlay
            cv2.putText(display_warped, "Card (Warped)", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(display_ocr, "OCR Region (Processed)", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # Create info panel
            info_panel = np.zeros((512, 360, 3), dtype=np.uint8)
            y_pos = 30
            
            # ROI values
            cv2.putText(info_panel, "OCR ROI Settings:", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            y_pos += 30
            cv2.putText(info_panel, f"X1: {config.name_roi[0]:.3f}", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_pos += 25
            cv2.putText(info_panel, f"Y1: {config.name_roi[1]:.3f}", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_pos += 25
            cv2.putText(info_panel, f"X2: {config.name_roi[2]:.3f}", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_pos += 25
            cv2.putText(info_panel, f"Y2: {config.name_roi[3]:.3f}", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_pos += 40
            
            # OCR result
            cv2.putText(info_panel, "OCR Result:", (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            y_pos += 30
            
            # Word wrap OCR text
            words = ocr_text.split()
            line = ""
            for word in words:
                test_line = line + word + " "
                if len(test_line) > 25:
                    cv2.putText(info_panel, line, (10, y_pos),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
                    y_pos += 20
                    line = word + " "
                else:
                    line = test_line
            if line:
                cv2.putText(info_panel, line, (10, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            
            y_pos += 40
            
            # Status
            status = "FROZEN - Adjust ROI" if frozen else "LIVE - Press SPACE to freeze"
            color = (0, 255, 255) if frozen else (0, 255, 0)
            cv2.putText(info_panel, status, (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            # Combine displays
            top_row = np.hstack([display_warped, info_panel])
            bottom_row = np.hstack([display_ocr, np.zeros((100, 360, 3), dtype=np.uint8)])
            combined = np.vstack([top_row, bottom_row])
            
            cv2.imshow("Calibration", combined)
        else:
            # No card detected
            display = frame.copy() if frame_with_overlay is None else frame_with_overlay
            display = cv2.resize(display, (720, 405))
            
            cv2.putText(display, "NO CARD DETECTED", (50, 200),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            cv2.putText(display, "Place card in view", (50, 250),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            cv2.imshow("Calibration", display)
        
        # Handle keyboard input
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord(' '):  # Space - freeze/unfreeze
            if warped is not None:
                frozen = not frozen
                if frozen:
                    frozen_frame = frame.copy()
                    frozen_warped = warped.copy()
                    print("\n[FROZEN] Frame frozen - adjust ROI with arrow keys")
                else:
                    print("\n[LIVE] Resuming live view")
        elif key == ord('r'):  # Reset ROI
            config.name_roi = [0.08, 0.08, 0.92, 0.22]
            print(f"\n[RESET] ROI reset to defaults: {config.name_roi}")
        elif key == ord('s'):  # Save
            if warped is not None:
                cv2.imwrite("calibration_warped.jpg", warped)
                cv2.imwrite("calibration_ocr_region.jpg", ocr_preview)
                print(f"\n[SAVED] Images saved:")
                print(f"  - calibration_warped.jpg")
                print(f"  - calibration_ocr_region.jpg")
                print(f"  - Current ROI: {config.name_roi}")
        
        # Arrow keys for ROI adjustment (only when frozen)
        if frozen:
            step = 0.01
            if key == 82:  # Up arrow
                config.name_roi[1] = max(0.0, config.name_roi[1] - step)
                config.name_roi[3] = max(config.name_roi[1] + 0.05, config.name_roi[3] - step)
            elif key == 84:  # Down arrow
                config.name_roi[1] = min(0.95, config.name_roi[1] + step)
                config.name_roi[3] = min(1.0, config.name_roi[3] + step)
            elif key == 81:  # Left arrow
                config.name_roi[0] = max(0.0, config.name_roi[0] - step)
                config.name_roi[2] = max(config.name_roi[0] + 0.05, config.name_roi[2] - step)
            elif key == 83:  # Right arrow
                config.name_roi[0] = min(0.95, config.name_roi[0] + step)
                config.name_roi[2] = min(1.0, config.name_roi[2] + step)
            elif key == ord('+') or key == ord('='):  # Increase height
                config.name_roi[3] = min(1.0, config.name_roi[3] + step)
            elif key == ord('-') or key == ord('_'):  # Decrease height
                config.name_roi[3] = max(config.name_roi[1] + 0.05, config.name_roi[3] - step)
    
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "=" * 70)
    print("Final ROI Settings:")
    print(f"  name_roi: {config.name_roi}")
    print("\nTo use these settings, update your config:")
    print(f"  name_roi = ({config.name_roi[0]:.3f}, {config.name_roi[1]:.3f}, {config.name_roi[2]:.3f}, {config.name_roi[3]:.3f})")
    print("=" * 70)

################################################################################
# Main
################################################################################

def main():
    parser = argparse.ArgumentParser(description="Camera Calibration Tool for MTG Card Sorter")
    parser.add_argument('--device', type=int, default=0, help='Camera device index (default: 0)')
    parser.add_argument('--width', type=int, default=1280, help='Camera width (default: 1280)')
    parser.add_argument('--height', type=int, default=720, help='Camera height (default: 720)')
    
    args = parser.parse_args()
    
    config = CalibrationConfig()
    config.device_index = args.device
    config.resolution = (args.width, args.height)
    
    run_calibration(config)

if __name__ == "__main__":
    main()
