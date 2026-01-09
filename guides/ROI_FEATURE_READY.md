# ROI Debugging Feature - Implemented ✓

## What Was Done

Fixed the issue where OCR detects "OS" instead of actual card names by implementing **ROI debugging and testing capabilities**.

### Changes Made

1. **Enhanced test_ocr_live() function** (mtg_sorter_cli.py, line 648)
   - Added optional `roi` parameter to accept custom ROI coordinates
   - Extracts and saves first 5 card ROI regions as PNG images
   - Shows pixel coordinates of the ROI region being tested
   - Displays summary of saved images

2. **Added --roi CLI parameter** (mtg_sorter_cli.py, line 988)
   - Accepts 4 float values: `--roi X1 Y1 X2 Y2`
   - Each value is a fraction from 0.0 to 1.0
   - Allows testing different ROI coordinates without editing config

3. **New Documentation Files**
   - **ROI_QUICK_REFERENCE.md** - Quick 3-step guide with examples
   - **ROI_DEBUGGING_GUIDE.md** - Detailed guide with troubleshooting
   - **ROI_IMPLEMENTATION_SUMMARY.md** - Complete technical details

## How to Use It

### Step 1: Run OCR test and capture ROI images
```bash
python mtg_sorter_cli.py test-ocr-live --duration 20
```

This will:
- Run OCR test for 20 seconds
- Detect cards and run OCR on each
- Save the **exact ROI region** being sent to OCR as images
- Print ROI coordinates and summary

**Output:**
```
[OCR TEST] ROI: x=8%-92%, y=8%-22%
[OCR TEST] ROI pixels: (51, 38) to (589, 105)
[OCR TEST] Saving ROI images to 'ocr_roi_*.png' for debugging

[OCR TEST] Results:
  Cards detected: 5
  OCR success: 5
  Debug: Saved 5 ROI images (ocr_roi_001.png - ocr_roi_005.png)
```

### Step 2: Download and inspect the PNG files
Copy `ocr_roi_001.png`, `ocr_roi_002.png`, etc. to your computer and open them.

**What you might see:**
- ✅ Card name clearly visible → Good! ROI is correct
- ❌ "OS" or other wrong text → ROI is too high, needs to move down
- ❌ Empty space or nothing → ROI is in wrong location
- ❌ Multiple text regions → ROI is too large

### Step 3: Test with adjusted ROI coordinates
```bash
# If you saw the wrong area, adjust coordinates and test again
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14
```

For each test, check the new `ocr_roi_*.png` images to see what's being captured.

Adjust until the PNG clearly shows the card name.

### Step 4: Update config with working ROI
Once you find the right coordinates:

Edit **src/card_sorter/config_loader.py** (around line 25):
```python
# Change from:
name_roi: Tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.22)

# To your working values, e.g.:
name_roi: Tuple[float, float, float, float] = (0.08, 0.04, 0.92, 0.14)
```

Test without --roi to confirm:
```bash
python mtg_sorter_cli.py test-ocr-live --duration 30
```

## ROI Coordinate Format

```
--roi X1 Y1 X2 Y2
```

Each value is a **fraction from 0.0 to 1.0**:
- **0.0** = left/top edge
- **1.0** = right/bottom edge
- **0.5** = middle

Example: `--roi 0.08 0.08 0.92 0.22`
- X1=0.08 → 8% from left (left margin)
- Y1=0.08 → 8% from top (top margin)
- X2=0.92 → 92% from left (8% from right, right margin)
- Y2=0.22 → 22% from top (78% from bottom)
- Result: 84% width × 14% height region

## Example Scenarios

### Scenario 1: Detecting "OS" (wrong)
Edition symbol is being captured instead of card name.
```bash
# Move ROI down by increasing Y1
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.12 0.92 0.22

# If still wrong, keep adjusting:
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.14 0.92 0.24
```

### Scenario 2: Empty/blurry text
ROI is in a gap or capturing wrong area entirely.
```bash
# Expand the region vertically
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.08 0.92 0.30
```

### Scenario 3: Partial text
Card name is being cut off.
```bash
# Increase bottom boundary to capture full name
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.08 0.92 0.26
```

## What the Debug Images Show

When you run the test, `ocr_roi_001.png`, `ocr_roi_002.png`, etc. are created.

**These images show EXACTLY what pixels Tesseract is trying to read.**

If the image shows:
- Card name clearly visible → Tesseract config/preprocessing might need adjustment (not ROI issue)
- Wrong text (like "OS") → **ROI coordinates are wrong** (adjust them)
- Empty space → **ROI is in wrong location** (adjust coordinates)
- Blurry/partial text → **ROI bounds need tweaking** (adjust dimensions)

## Quick Command Reference

```bash
# Default ROI, save debug images
python mtg_sorter_cli.py test-ocr-live --duration 20

# Custom ROI coordinates
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14

# Different camera
python mtg_sorter_cli.py test-ocr-live --duration 20 --camera 1

# All options combined
python mtg_sorter_cli.py test-ocr-live --duration 30 --camera 0 --roi 0.08 0.08 0.92 0.22

# Longer test to accumulate more detections
python mtg_sorter_cli.py test-ocr-live --duration 60
```

## Files Modified

- **mtg_sorter_cli.py**
  - Line 648: Updated test_ocr_live() signature with roi parameter
  - Lines 683-724: Added ROI coordinate display and image saving
  - Lines 752-753: Added debug summary output
  - Lines 988-989: Added --roi argument to argparse
  - Line 1046: Pass roi parameter to function

## Files Created

- **ROI_QUICK_REFERENCE.md** - Quick reference guide
- **ROI_DEBUGGING_GUIDE.md** - Detailed troubleshooting guide
- **ROI_IMPLEMENTATION_SUMMARY.md** - Complete technical documentation

## Key Features

✅ Automatic debug image generation (first 5 detections saved)
✅ Visual ROI inspection without code editing
✅ Easy parameter testing with --roi flag
✅ Pixel coordinate display for precision
✅ Works on Raspberry Pi via SSH (headless mode)
✅ No config file editing needed for testing

## Testing the Feature (on Pi)

```bash
# On Raspberry Pi via SSH:
ssh pi@raspberry.local

cd ~/card-sorter

# Run test with default ROI
python mtg_sorter_cli.py test-ocr-live --duration 20

# You should see output like:
# [OCR TEST] Saving ROI images to 'ocr_roi_*.png' for debugging
# [OCR TEST] Debug: Saved 5 ROI images (ocr_roi_001.png - ocr_roi_005.png)

# Then download the PNG files:
scp pi@raspberry.local:~/card-sorter/ocr_roi_*.png .

# Open them in an image viewer to see what's being captured
```

## What's Next

1. Run the test command
2. Download the PNG files
3. Inspect them to see what text is being captured
4. Adjust ROI coordinates based on what you see
5. Update the config file once working
6. Test the full system

## Documentation

For more details, see:
- **ROI_QUICK_REFERENCE.md** - Start here for quick examples
- **ROI_DEBUGGING_GUIDE.md** - Detailed guide and troubleshooting
- **ROI_IMPLEMENTATION_SUMMARY.md** - Technical implementation details
- **CLI_OCR_TESTING.md** - Full OCR testing documentation
