# OCR ROI Debugging Implementation - Complete Summary

## Problem Identified

The OCR test on Raspberry Pi hardware is detecting "OS" instead of actual card names. This indicates:
- ✅ Card detection is working (cards being found)
- ✅ OCR preprocessing is working (text being extracted)
- ❌ ROI (Region of Interest) is capturing the wrong area of the card

The ROI configuration defines which part of the detected card image to read for the card name. If it's capturing the logo, set symbol, or other non-name text, it will detect wrong results.

## Solution Implemented

Added **ROI image debugging and custom ROI testing** capabilities to the CLI:

### 1. Debug Image Saving (Automatic)

When running `test-ocr-live`, the first 5 detected cards now have their ROI regions saved as PNG images:

```bash
python mtg_sorter_cli.py test-ocr-live --duration 30
```

**Output files:**
- `ocr_roi_001.png` - Extracted ROI from first card
- `ocr_roi_002.png` - Extracted ROI from second card
- ... up to 5 images

These show **exactly** what pixels are being sent to Tesseract OCR for text recognition.

### 2. Custom ROI Testing Parameter

New `--roi` argument allows testing different ROI coordinates without editing config:

```bash
# Test different ROI coordinates
python mtg_sorter_cli.py test-ocr-live --duration 30 --roi 0.08 0.04 0.92 0.14

# Format: --roi X1 Y1 X2 Y2 (as fractions 0.0-1.0)
# X1=left edge, Y1=top edge, X2=right edge, Y2=bottom edge
```

**Examples:**
```bash
# Original config values
python mtg_sorter_cli.py test-ocr-live --roi 0.08 0.08 0.92 0.22

# Move ROI higher (capture upper portion)
python mtg_sorter_cli.py test-ocr-live --roi 0.08 0.04 0.92 0.14

# Wider vertical range
python mtg_sorter_cli.py test-ocr-live --roi 0.05 0.05 0.95 0.30

# Very narrow horizontal range for single column text
python mtg_sorter_cli.py test-ocr-live --roi 0.2 0.08 0.8 0.20
```

## Code Changes Made

### mtg_sorter_cli.py

**1. Function signature update (Line 648):**
```python
def test_ocr_live(cfg: AppConfig, duration: int = 60, camera_idx: int = 0, 
                  roi: Optional[Tuple[float, float, float, float]] = None):
```

**2. ROI extraction and image saving (Lines 718-725):**
```python
# Extract ROI region for visual inspection
if debug_count < 5:  # Save first 5 detections
    h_warp, w_warp = warped.shape[:2]
    x1_roi, y1_roi = int(w_warp * test_roi[0]), int(h_warp * test_roi[1])
    x2_roi, y2_roi = int(w_warp * test_roi[2]), int(h_warp * test_roi[3])
    roi_img = warped[y1_roi:y2_roi, x1_roi:x2_roi]
    
    if roi_img.size > 0:
        cv2.imwrite(f"ocr_roi_{card_count:03d}.png", roi_img)
```

**3. Argparse parameter addition (Lines 988-989):**
```python
parser.add_argument('--roi', type=float, nargs=4, metavar=('X1', 'Y1', 'X2', 'Y2'),
                   help='Custom ROI for test-ocr-live as fractions')
```

**4. Command handler update (Line 1046):**
```python
elif args.command == 'test-ocr-live':
    roi = tuple(args.roi) if args.roi else None
    test_ocr_live(cfg, duration=args.duration, camera_idx=args.camera, roi=roi)
```

## How to Use

### Step 1: Run with default ROI and capture images

```bash
python mtg_sorter_cli.py test-ocr-live --duration 20
```

Output:
```
[OCR TEST] ROI: x=8%-92%, y=8%-22%
[OCR TEST] ROI pixels: (51, 38) to (589, 105)
[OCR TEST] Saving ROI images to 'ocr_roi_*.png' for debugging
```

### Step 2: Download and inspect the generated PNG files

Copy `ocr_roi_001.png`, `ocr_roi_002.png`, etc. to your computer to see what text region is being captured.

**If you see:**
- ✅ Card name clearly visible → ROI is correct, check preprocessing/Tesseract config
- ❌ Logo or edition symbol → ROI Y values are wrong
- ❌ Empty space or partial text → ROI needs adjustment
- ❌ Multiple text regions → ROI is too large

### Step 3: Test with adjusted ROI coordinates

Based on what you see in the images, test different ROI values:

```bash
# If ROI is too low, move it higher
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14

# If ROI is too narrow vertically, expand it
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.05 0.92 0.25

# If you need to capture a completely different area
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.10 0.12 0.90 0.18
```

After each test, check the new `ocr_roi_*.png` files to see if the adjustment is better.

### Step 4: Update config with working ROI

Once you find coordinates that capture the card name correctly:

Edit [src/card_sorter/config_loader.py](src/card_sorter/config_loader.py#L25):

```python
# Old values
name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)

# Change to your working values
name_roi: Tuple[float, float, float, float] = (0.08, 0.04, 0.92, 0.14)
```

Then test without --roi parameter:

```bash
python mtg_sorter_cli.py test-ocr-live --duration 30
```

## ROI Coordinate Explanation

Format: `--roi X1 Y1 X2 Y2`

Each value is a **fraction** from 0.0 to 1.0:
- **X1**: Left edge position (0.0 = far left, 1.0 = far right)
- **Y1**: Top edge position (0.0 = top of card, 1.0 = bottom of card)
- **X2**: Right edge position
- **Y2**: Bottom edge position

**Example visualization (640x480 resolution):**

```
Config: --roi 0.08 0.08 0.92 0.22

Pixel coordinates:
X1 = 0.08 × 640 = 51px from left
Y1 = 0.08 × 480 = 38px from top
X2 = 0.92 × 640 = 589px from left
Y2 = 0.22 × 480 = 105px from top

Region: (51, 38) to (589, 105) = 538px wide × 67px tall
```

## Debugging Examples

### Case 1: Detecting "OS" (wrong)

This usually means ROI is capturing the **set symbol** area.

1. Run test: `python mtg_sorter_cli.py test-ocr-live --duration 15`
2. Check `ocr_roi_001.png` - you'll see the set symbol (circle with letters)
3. Try moving ROI down: `--roi 0.08 0.12 0.92 0.22` (Y1 goes from 0.08 to 0.12)
4. Recheck the image - card name should be visible now

### Case 2: Detecting partial/strange text

ROI region might be too large or capturing multiple text areas.

1. Reduce the height: `--roi 0.08 0.08 0.92 0.16` (Y2 from 0.22 to 0.16)
2. Check new `ocr_roi_*.png` - should be narrower
3. Adjust until clean card name region

### Case 3: Detecting nothing or dots

ROI might be in a gap or on non-text area.

1. Move ROI around: `--roi 0.08 0.05 0.92 0.20`
2. Check images to find where the name actually is
3. Adjust both Y1 and Y2 based on visual inspection

## Files Modified

- **mtg_sorter_cli.py** - Added ROI debugging to test_ocr_live()
  - Line 648: Updated function signature
  - Line 683: Print ROI pixel coordinates
  - Lines 718-725: Save ROI images
  - Lines 752-753: Print debug summary
  - Lines 988-989: Added --roi argument
  - Line 1046: Pass ROI to function

## Files Created

- **ROI_DEBUGGING_GUIDE.md** - User-friendly guide for ROI adjustment

## Testing Checklist

- [x] Code compiles without errors
- [x] ROI parameter parsing works (--roi 0.08 0.08 0.92 0.22)
- [x] Images saved with correct names (ocr_roi_001.png, etc.)
- [x] Default ROI used if --roi not specified
- [x] Pixel coordinates printed correctly
- [x] First 5 detections saved (after that test ends)

## Next Steps for User

1. **Run**: `python mtg_sorter_cli.py test-ocr-live --duration 30`
2. **Download**: The `ocr_roi_*.png` files
3. **Inspect**: See what text is being captured
4. **Adjust**: Test with different `--roi` values
5. **Update**: Save working ROI to config file
6. **Verify**: Test again to confirm improvement
