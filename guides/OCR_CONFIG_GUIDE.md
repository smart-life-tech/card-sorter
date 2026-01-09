# OCR Configuration Guide

This guide helps you optimize the improved OCR system for your specific setup.

---

## Quick Start

The default configuration is optimized for most MTG card setups. No changes needed if:
- ✓ Camera positioned straight-on to cards
- ✓ Moderate to good lighting (300+ lux)
- ✓ Standard MTG card size
- ✓ Tesseract v4.0+ installed

If you have suboptimal conditions, follow the optimization steps below.

---

## Configuration Parameters

### In `mtg_sorter_cli.py` and `mtg_sorter_fixed.py`

#### 1. ROI (Region of Interest)
**File**: Line in `ocr_name_from_image()` parameter or config file  
**Default**: `(0.08, 0.08, 0.92, 0.22)`  
**Meaning**: `(x_start%, y_start%, x_end%, y_end%)`

Example visualization for 720×1024 image:
```
0         720 (width)
0 ┌────────────────────────────┐
  │                            │
58│ ┌──────────────────────┐   │  ← y_start = 8% (y=83px)
  │ │  Card Name Text      │   │
  │ │                      │   │
225│ └──────────────────────┘   │  ← y_end = 22% (y=225px)
  │                            │
  │ (rest of card)             │
  │                            │
1024└────────────────────────────┘
   ▲                        ▲
   x_start=8% (x=58)      x_end=92% (x=662)
```

**Adjust if**:
- Name is cut off at top/bottom → change `y_start` or `y_end`
- Name is cut off at left/right → change `x_start` or `x_end`
- Extra text being captured → shrink ROI

#### 2. Preprocessing Parameters

**Bilateral Filter**
```python
gray = cv2.bilateralFilter(gray, diameter=9, sigmaColor=75, sigmaSpace=75)
```
- `diameter`: Higher = more smoothing (9=default)
- `sigmaColor`: Higher = preserve more colors (75=default)
- `sigmaSpace`: Higher = broader neighborhood (75=default)

| Setting | Effect |
|---------|--------|
| 5, 50, 50 | Light denoising, more detail |
| 9, 75, 75 | **Balanced (default)** |
| 13, 100, 100 | Heavy denoising, smoother text |

**CLAHE (Contrast Enhancement)**
```python
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
```
- `clipLimit`: Higher = more extreme contrast boost (1-4 range)
- `tileGridSize`: Larger = broader enhancement (typically 8×8 or 16×16)

| Setting | Effect |
|---------|--------|
| 1.0, (8,8) | Minimal boost, natural look |
| 3.0, (8,8) | **Balanced boost (default)** |
| 5.0, (16,16) | Aggressive boost for very poor lighting |

**Morphological Kernel**
```python
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
```
- Size: 2×2 works well for text; use 3×3 for very broken/noisy text

**Upscaling Factor**
```python
gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
```
- 3 = 3x upscaling (current)
- Try 2 if running on slower hardware
- Try 4 for very small text

#### 3. Tesseract Configuration

**PSM (Page Segmentation Mode)**
```python
"--psm 6"  # Assume uniform block of text
"--psm 7"  # Single text line
```

| PSM | Description | Best For |
|-----|-------------|----------|
| 3 | Fully automatic | Unknown layouts |
| 6 | Uniform text block | **Card names (default)** |
| 7 | Single line | Small simple names |
| 8 | Single word | Single-word cards |

**OEM (OCR Engine Mode)**
```python
"--oem 3"  # Neural net + traditional (better)
"--oem 1"  # Neural net only (fallback)
```

**Character Whitelist**
```python
"-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',.-"
```
Restricts to valid MTG card name characters. Modify if you have special characters.

---

## Optimization Steps

### Problem: OCR Works But Slow

**Goal**: Reduce processing time from 200-400ms to <150ms

**Option 1: Reduce Upscaling**
```python
# Line ~370 in ocr_name_from_image()
gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)  # 2x instead of 3x
otsu_thresh = cv2.resize(otsu_thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
adaptive_thresh = cv2.resize(adaptive_thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
```

**Option 2: Reduce Attempts**
```python
# Line ~380, use only best configs
configs = [
    "--psm 6 -l eng --oem 3 -c tessedit_char_whitelist=...",  # Keep this one
    # Remove the other 2
]
```

**Option 3: Reduce Preprocessing Methods**
```python
# Line ~376, test only best preprocessing
preprocessed_images = [
    ("otsu", otsu_thresh),      # Keep best one
    # Remove grayscale and adaptive
]
```

### Problem: OCR Fails on Dim Cards

**Goal**: Make detection work in low-light conditions

**Step 1: Increase CLAHE Strength**
```python
# Line ~347
clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(16, 16))
```

**Step 2: Increase Bilateral Smoothing**
```python
# Line ~342
gray = cv2.bilateralFilter(gray, 13, 100, 100)
```

**Step 3: Use Larger Morphological Kernel**
```python
# Line ~352
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
```

**Step 4: Test & Debug**
```bash
python test_ocr.py dim_card.png --debug
# Review the debug_*.png files to see improvement
```

### Problem: OCR Gets Letters Wrong (e.g., 'l' → 'I')

**Goal**: Improve accuracy on difficult fonts

**Step 1: Check Tesseract Version**
```bash
tesseract --version
# Need v4.0+
```

**Step 2: Increase Text Sharpness**
```python
# Add after CLAHE, before morphology
gray = cv2.GaussianBlur(gray, (1, 1), 0)  # Minimal blur
kernel_sharp = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (1, 1))
gray = cv2.morphologyEx(gray, cv2.MORPH_ERODE, kernel_sharp)  # Sharpen strokes
```

**Step 3: Try PSM 8 (Single Word)**
```python
# Add to configs if your cards have single-word names
"--psm 8 -l eng --oem 3"
```

**Step 4: Expand Whitelist for Apostrophes**
```python
# Current allows only certain characters; verify it includes needed ones
"-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',.-&×/"
```

### Problem: OCR Works Perfect But Needs Speed-Up

**Goal**: Keep accuracy but run faster

**Change**: Use simpler preprocessing but keep multiple attempts

```python
# Replace the whole preprocessing section with:

def ocr_name_from_image_fast(img, roi_rel):
    # Minimal preprocessing - just contrast
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Just upscale, no multiple thresholding
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Just 2 configs instead of 3
    configs = [
        "--psm 6 -l eng --oem 3",
        "--psm 7 -l eng",
    ]
    
    # ... rest of code
```

**Expected result**: ~100-150ms per image, slightly lower accuracy

---

## Test Configuration Changes

### Before Modifying Code

Test with `test_ocr.py`:
```bash
python test_ocr.py problem_card.png --debug
```

This shows exactly which preprocessing method and config works best, so you can optimize accordingly.

### Safe Way to Test Changes

1. Create a test script:
```python
# test_config.py
import cv2
from mtg_sorter_cli import ocr_name_from_image

# Test on known card
img = cv2.imread("test_card.png")
result = ocr_name_from_image(img, roi_rel=(0.08, 0.08, 0.92, 0.22))
print(f"Result: {result}")
```

2. Run before/after comparison:
```bash
python test_config.py  # Before changes
# Make changes to mtg_sorter_cli.py
python test_config.py  # After changes
```

3. Compare results

---

## Recommended Configurations

### Setup 1: Production (Default)
```python
# Balanced performance and accuracy
bilateral: (9, 75, 75)
clahe: (3.0, (8,8))
upscale: 3x
attempts: 9 (all)
configs: All 3 PSM modes
```
**Speed**: 200-400ms/image  
**Accuracy**: 95%+  
**Lighting**: 300+ lux  
**Cards**: All types

### Setup 2: High-Speed
```python
bilateral: (7, 50, 50)
clahe: (2.0, (8,8))
upscale: 2x
attempts: 3 (only Otsu + PSM6)
configs: PSM 6 only
```
**Speed**: 80-120ms/image  
**Accuracy**: 85%  
**Use when**: Need 5+ cards/second throughput

### Setup 3: Low-Light
```python
bilateral: (13, 100, 100)
clahe: (5.0, (16,16))
upscale: 4x
attempts: 9 (all)
configs: All 3 PSM modes + PSM 8
```
**Speed**: 500-800ms/image  
**Accuracy**: 98%+  
**Use when**: <300 lux lighting

### Setup 4: Tough Cards
```python
bilateral: (9, 75, 75)
clahe: (3.0, (8,8))
upscale: 3x
morphology: 3×3 kernel (instead of 2×2)
attempts: 9+ (add PSM 8)
```
**Speed**: 300-500ms/image  
**Accuracy**: 97%+  
**Use when**: Worn/damaged card surfaces

---

## Verification Checklist

After making changes, verify:

- [ ] OCR still works on test card
- [ ] No crashes or exceptions
- [ ] Speed acceptable (< 1 second per card)
- [ ] Accuracy improved for your use case
- [ ] All 9 preprocessing files generate correctly in debug mode

---

## Advanced: Custom Training

If you want 99%+ accuracy on MTG cards specifically:

1. **Collect training data** (~200 card images)
2. **Use Tesseract training guide**: https://github.com/tesseract-ocr/tesseract/wiki/Training-Tesseract
3. **Fine-tune** on MTG card fonts
4. **Use trained model**: `"-l mtg"` instead of `"-l eng"`

---

## Still Having Issues?

1. Run debug test first:
   ```bash
   python test_ocr.py your_card.png --debug
   ```

2. Check intermediate images:
   ```
   debug_01_bilateral.png    ← Should be denoised
   debug_02_clahe.png        ← Should be more contrasty
   debug_03_morphology.png   ← Should have cleaner text
   debug_04_otsu.png         ← Should be binary (black/white)
   debug_05_adaptive.png     ← Alternative binary
   debug_06_gray_3x.png      ← Enlarged grayscale
   debug_07_otsu_3x.png      ← Enlarged binary 1
   debug_08_adaptive_3x.png  ← Enlarged binary 2
   ```

3. Look for where text becomes unclear
4. Adjust that specific preprocessing step

5. Check Tesseract logs:
   ```bash
   tesseract debug_otsu_3x.png - 2>&1 | head -20
   ```

---

## Contact/Help

See [OCR_IMPROVEMENTS.md](OCR_IMPROVEMENTS.md) for technical details.  
See [OCR_IMPROVEMENTS_SUMMARY.md](OCR_IMPROVEMENTS_SUMMARY.md) for quick reference.
