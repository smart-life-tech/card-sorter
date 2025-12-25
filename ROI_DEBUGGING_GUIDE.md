# ROI Debugging Guide

The OCR is now detecting "OS" instead of card names. This indicates the ROI (Region of Interest) is capturing the wrong part of the card.

## Quick Fix: Test Different ROI Coordinates

The OCR test now saves the extracted ROI image so you can see exactly what text is being read.

### Step 1: Run a test with default ROI (to see current behavior)

```bash
python mtg_sorter_cli.py test-ocr-live --duration 15
```

Check the output:
```
[OCR TEST] ROI: x=8%-92%, y=8%-22%
[OCR TEST] ROI pixels: (51, 38) to (589, 105)
[OCR TEST] Saving ROI images to 'ocr_roi_*.png' for debugging
```

The generated files `ocr_roi_001.png`, `ocr_roi_002.png`, etc. show exactly what the OCR is reading.

### Step 2: Download and inspect the ROI images

Copy the `ocr_roi_*.png` files to your computer to see what text region is being captured.

**If you see "OS" or other wrong text:**
- The ROI is capturing the wrong region of the card
- You need to adjust the ROI coordinates

### Step 3: Adjust ROI and retest

The card name is usually:
- **Horizontally**: Full width (maybe 0.05 to 0.95)
- **Vertically**: Upper portion of the card

Try adjusting the vertical coordinates (Y1, Y2) to capture higher up on the card:

```bash
# Move ROI higher - original was y=0.08-0.22, try y=0.04-0.14
python mtg_sorter_cli.py test-ocr-live --duration 15 --roi 0.08 0.04 0.92 0.14
```

Or try capturing a different vertical band:

```bash
# Try middle of card
python mtg_sorter_cli.py test-ocr-live --duration 15 --roi 0.08 0.15 0.92 0.35
```

Or try wider area:

```bash
# More generous area
python mtg_sorter_cli.py test-ocr-live --duration 15 --roi 0.05 0.05 0.95 0.25
```

## ROI Coordinate Format

When using `--roi X1 Y1 X2 Y2`:

- **X1**: Left edge (0.0 = left edge, 1.0 = right edge)
- **Y1**: Top edge (0.0 = top, 1.0 = bottom)
- **X2**: Right edge
- **Y2**: Bottom edge

Example: `--roi 0.08 0.08 0.92 0.22` means:
- 8% from left, 8% from top
- 92% from left, 22% from top
- Roughly the upper 14% of the card height (22%-8%=14%)

## When You Find the Right ROI

Once you find ROI coordinates that correctly capture the card name:

1. **Update the config file** at [src/card_sorter/config_loader.py](src/card_sorter/config_loader.py#L25):

```python
name_roi: Tuple[float, float, float, float] = (0.08, 0.04, 0.92, 0.14)  # Your new values
```

2. **Save and test the full system**:

```bash
python mtg_sorter_cli.py test-ocr-live --duration 30
```

## Troubleshooting

### "OS" detected instead of card name
- ROI is capturing logo or edition area
- Try moving Y1 lower (e.g., from 0.08 to 0.12)

### Empty text or dots detected
- ROI might be in a gap between text and image
- Try adjusting Y1 up or Y2 down to capture more/less height

### Multiple different wrong texts
- ROI might be capturing multiple text regions at once
- Narrow the Y range (reduce Y2-Y1)

### Still wrong after adjusting
- Card might not be straight/centered in frame
- Check that card is positioned perpendicular to camera
- Ensure card is fully in frame and name area is visible

## Files Generated

During testing:
- `ocr_roi_001.png` - Extracted ROI from 1st detected card
- `ocr_roi_002.png` - Extracted ROI from 2nd detected card
- ... up to 5 detections

These are the actual pixel regions being sent to Tesseract OCR.
