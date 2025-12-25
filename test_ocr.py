#!/usr/bin/env python3
"""
OCR Test Utility - Debug and test OCR detection on sample images
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    print("ERROR: OpenCV not installed. Install with: pip install opencv-python numpy")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("ERROR: pytesseract not installed. Install with: pip install pytesseract")
    print("Also requires Tesseract OCR engine: sudo apt-get install tesseract-ocr")
    sys.exit(1)


def ocr_name_from_image(img, roi_rel: Tuple[float, float, float, float], debug: bool = False) -> Optional[str]:
    """Improved OCR with debugging output."""
    
    h, w = img.shape[:2]
    x1 = int(roi_rel[0] * w)
    y1 = int(roi_rel[1] * h)
    x2 = int(roi_rel[2] * w)
    y2 = int(roi_rel[3] * h)
    roi = img[y1:y2, x1:x2]
    
    if debug:
        print(f"  ROI dimensions: {roi.shape}")
    
    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Step 1: Bilateral filtering
    gray_filtered = cv2.bilateralFilter(gray, 9, 75, 75)
    if debug:
        cv2.imwrite("debug_01_bilateral.png", gray_filtered)
        print("  ✓ Bilateral filter applied")
    
    # Step 2: CLAHE enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray_clahe = clahe.apply(gray_filtered)
    if debug:
        cv2.imwrite("debug_02_clahe.png", gray_clahe)
        print("  ✓ CLAHE contrast enhancement applied")
    
    # Step 3: Morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    gray_morph = cv2.morphologyEx(gray_clahe, cv2.MORPH_CLOSE, kernel)
    if debug:
        cv2.imwrite("debug_03_morphology.png", gray_morph)
        print("  ✓ Morphological closing applied")
    
    # Step 4: Thresholding
    _, otsu_thresh = cv2.threshold(gray_morph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive_thresh = cv2.adaptiveThreshold(gray_morph, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
    if debug:
        cv2.imwrite("debug_04_otsu.png", otsu_thresh)
        cv2.imwrite("debug_05_adaptive.png", adaptive_thresh)
        print("  ✓ Otsu and Adaptive thresholding applied")
    
    # Step 5: Upscaling
    gray_scaled = cv2.resize(gray_morph, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    otsu_scaled = cv2.resize(otsu_thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    adaptive_scaled = cv2.resize(adaptive_thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    if debug:
        cv2.imwrite("debug_06_gray_3x.png", gray_scaled)
        cv2.imwrite("debug_07_otsu_3x.png", otsu_scaled)
        cv2.imwrite("debug_08_adaptive_3x.png", adaptive_scaled)
        print("  ✓ 3x upscaling applied")
    
    # OCR attempts
    configs = [
        "--psm 6 -l eng --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',.-",
        "--psm 7 -l eng --oem 3",
        "--psm 6 -l eng --oem 1",
    ]
    
    preprocessed = [
        ("grayscale", gray_scaled),
        ("otsu", otsu_scaled),
        ("adaptive", adaptive_scaled),
    ]
    
    results = []
    best_text = None
    best_confidence = 0.0
    
    if debug:
        print("\n  OCR Attempts:")
    
    for prep_name, prep_img in preprocessed:
        for i, config in enumerate(configs):
            try:
                data = pytesseract.image_to_data(prep_img, config=config, output_type=pytesseract.Output.DICT)
                text = pytesseract.image_to_string(prep_img, config=config)
                
                confidences = []
                for conf_str in data['confidence']:
                    try:
                        conf = float(conf_str)
                        if conf > 0:
                            confidences.append(conf)
                    except:
                        pass
                
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                result = {
                    'prep': prep_name,
                    'config': i,
                    'text': text.strip(),
                    'confidence': avg_confidence,
                    'num_chars': len(confidences)
                }
                results.append(result)
                
                if debug:
                    status = "✓" if text.strip() else "✗"
                    print(f"    {status} {prep_name:10} cfg{i}: '{text.strip():20}' (conf: {avg_confidence:.1f}%)")
                
                if text and len(text.strip()) >= 2 and avg_confidence > best_confidence:
                    best_text = text
                    best_confidence = avg_confidence
            
            except Exception as e:
                if debug:
                    print(f"    ✗ {prep_name:10} cfg{i}: ERROR - {e}")
    
    if not best_text:
        if debug:
            print("\n  ⚠ No valid text detected")
        return None
    
    # Post-process
    name = best_text.strip().replace("\n", " ")
    name = name.strip("-—_ :'\"")
    name = " ".join(name.split())
    
    if len(name) < 2:
        if debug:
            print(f"\n  ⚠ Name too short: '{name}'")
        return None
    
    special_count = sum(1 for c in name if not (c.isalnum() or c.isspace() or c in "'-"))
    if special_count > len(name) * 0.3:
        if debug:
            print(f"\n  ⚠ Too many special characters: {special_count}/{len(name)}")
        return None
    
    if debug:
        print(f"\n  ✓ RESULT: '{name}' (confidence: {best_confidence:.1f}%)")
        print(f"    Best from: {results[results.index([r for r in results if r['text'] == best_text][0])]['prep']} mode")
    
    return name


def test_image(image_path: str, roi: Optional[Tuple[float, float, float, float]] = None, debug: bool = False):
    """Test OCR on a single image."""
    
    path = Path(image_path)
    if not path.exists():
        print(f"ERROR: Image not found: {image_path}")
        return False
    
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: Failed to read image: {image_path}")
        return False
    
    # Default ROI: top 8-22% of image (typical card name position)
    if roi is None:
        roi = (0.08, 0.08, 0.92, 0.22)
    
    print(f"\nTesting: {path.name}")
    print(f"Image size: {img.shape}")
    print(f"ROI: x={roi[0]:.0%}-{roi[2]:.0%}, y={roi[1]:.0%}-{roi[3]:.0%}")
    
    result = ocr_name_from_image(img, roi, debug=debug)
    
    return result is not None


def test_directory(dir_path: str, pattern: str = "*.png", debug: bool = False):
    """Test OCR on all images in directory."""
    
    path = Path(dir_path)
    if not path.is_dir():
        print(f"ERROR: Directory not found: {dir_path}")
        return
    
    images = list(path.glob(pattern))
    if not images:
        print(f"WARNING: No images found matching '{pattern}' in {dir_path}")
        return
    
    print(f"Found {len(images)} images\n")
    
    success = 0
    for img_path in sorted(images):
        if test_image(str(img_path), debug=debug):
            success += 1
    
    print(f"\n{'='*50}")
    print(f"Success Rate: {success}/{len(images)} ({success*100//len(images)}%)")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Test OCR detection on card images")
    parser.add_argument("image", nargs="?", help="Path to image file or directory")
    parser.add_argument("--dir", action="store_true", help="Treat input as directory")
    parser.add_argument("--pattern", default="*.png", help="File pattern for directory mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and save intermediate images")
    parser.add_argument("--roi", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"),
                       help="Custom ROI as relative coordinates (0-1)")
    
    args = parser.parse_args()
    
    if not args.image:
        parser.print_help()
        print("\nExample:")
        print("  python test_ocr.py card.png --debug")
        print("  python test_ocr.py ./captures --dir --debug")
        sys.exit(1)
    
    roi = tuple(args.roi) if args.roi else None
    
    if args.dir:
        test_directory(args.image, pattern=args.pattern, debug=args.debug)
    else:
        test_image(args.image, roi=roi, debug=args.debug)


if __name__ == "__main__":
    main()
