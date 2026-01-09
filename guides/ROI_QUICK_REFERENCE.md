# ROI Debugging - Quick Reference

## The Problem
OCR detecting "OS" instead of card names → ROI is capturing wrong part of card

## The Solution
1. Save ROI images automatically
2. Test different ROI coordinates easily
3. Find the right region visually

## Quick Start (3 steps)

### 1. Capture images with current ROI
```bash
python mtg_sorter_cli.py test-ocr-live --duration 20
```
Generates: `ocr_roi_001.png`, `ocr_roi_002.png`, ... `ocr_roi_005.png`

### 2. Download images and inspect them
Look at the PNG files - what do they show?
- Card name? → ROI is good
- Logo/symbol? → ROI is wrong, adjust coordinates
- Empty space? → ROI is missing the text

### 3. Test adjusted coordinates
Based on what you saw, try a new ROI:
```bash
# Move ROI higher (reduce Y1, reduce Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14

# Move ROI lower (increase Y1, increase Y2)  
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.12 0.92 0.22

# Make ROI taller (decrease Y1, increase Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.02 0.92 0.25

# Make ROI shorter (increase Y1, decrease Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.10 0.92 0.16
```

Repeat until the PNG shows the card name clearly.

## ROI Parameter Format
```
--roi X1 Y1 X2 Y2
```
- **X1**: Fraction from left (0.08 = 8% from left)
- **Y1**: Fraction from top
- **X2**: Fraction from right (0.92 = 92% from left, 8% from right)
- **Y2**: Fraction from bottom (0.22 = 22% from top, 78% from bottom)

Example: `--roi 0.08 0.08 0.92 0.22`
- Left: 8%, Right: 8%
- Top: 8%, Bottom: 78%
- Height: 22% - 8% = 14% of card

## Common Scenarios

### "OS" or other set symbol detected
```bash
# This is the edition area - ROI is too high, move it down
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.12 0.92 0.22
```

### Empty space or dots detected
```bash
# ROI is in a gap or on the wrong region, expand it
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.08 0.92 0.28
```

### Getting closer but still not quite right
```bash
# Fine-tune Y1 and Y2 in small increments
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.06 0.92 0.16
```

### Card name partially cut off
```bash
# Expand the region vertically
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.08 0.92 0.26
```

## Update Config Once Working

When you find the right ROI coordinates:

Edit **src/card_sorter/config_loader.py** (around line 25):

```python
# Change this:
name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)

# To your working values (example):
name_roi: Tuple[float, float, float, float] = (0.08, 0.04, 0.92, 0.14)
```

Then test without `--roi`:
```bash
python mtg_sorter_cli.py test-ocr-live --duration 30
```

## Command Reference

| Command | Purpose |
|---------|---------|
| `python mtg_sorter_cli.py test-ocr-live --duration 20` | Test with default ROI, save debug images |
| `python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14` | Test with custom ROI |
| `python mtg_sorter_cli.py test-ocr-live --duration 60 --camera 1` | Test different camera |
| `python mtg_sorter_cli.py test-ocr-image card.png` | Test single image (no ROI changes) |

## What the Images Show

`ocr_roi_001.png`, etc. = **Exact pixels sent to Tesseract OCR**

If the PNG shows:
- ✅ Card name clearly → Preprocessing/Tesseract needs adjustment (not ROI issue)
- ❌ Wrong text or symbols → ROI coordinates are wrong (adjust and retry)
- ❌ Empty/blurry → ROI capturing unrelated area

## Tips

- **Start with large ROI**: Make it bigger, then narrow it down
- **Test systematically**: Only change Y values (top/bottom) first, leave X (left/right) at defaults
- **Save working ROI**: Once it works, update the config file
- **Check card position**: Make sure card is straight and centered in camera frame
- **Good lighting**: Poor lighting makes OCR harder even with right ROI

## See Also
- **ROI_DEBUGGING_GUIDE.md** - Detailed guide with troubleshooting
- **ROI_IMPLEMENTATION_SUMMARY.md** - Complete technical details
- **CLI_OCR_TESTING.md** - Full CLI documentation
