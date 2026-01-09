# CLI OCR Testing Guide

## Quick Commands

### Test OCR with Live Camera (60 seconds)
```bash
python mtg_sorter_cli.py test-ocr-live
```

**What it does:**
- Opens camera and waits for cards
- When a card is detected, runs OCR on the name
- Shows detected card names in real-time
- Runs for 60 seconds (customizable)

**Output example:**
```
[OCR TEST] Live camera OCR test (60s)
[OCR TEST] Hold cards in front of camera
[OCR TEST] Press Ctrl+C to stop

  [1] ✓ Lightning Bolt
  [2] ✓ Forest
  [3] ⚠ Card detected but OCR failed

============================================================
[OCR TEST] Results:
  Duration: 45.2s
  Frames processed: 450
  Cards detected: 3
  OCR success: 2
  Success rate: 66%

  Detected cards:
    - Lightning Bolt: 1x
    - Forest: 1x
============================================================
```

---

## Test OCR on Single Image

### Test Image File
```bash
python mtg_sorter_cli.py test-ocr-image --image card.png
```

**Output example:**
```
[OCR TEST] Testing: card.png
  Image size: (1024, 720, 3)
  ROI: x=8%-92%, y=8%-22%

[OCR TEST] ✓ Detected: 'Lightning Bolt'
```

### Test with Custom ROI
```bash
python mtg_sorter_cli.py test-ocr-image --image card.png --roi 0.05 0.10 0.95 0.25
```

---

## Test OCR on Directory

### Test All Images in Folder
```bash
python mtg_sorter_cli.py test-ocr-dir --directory ./captures
```

**Output example:**
```
[OCR TEST] Testing 5 images from ./captures
============================================================

  [1/5] ✓ frame_0001.png
                → Lightning Bolt
  [2/5] ✓ frame_0002.png
                → Forest
  [3/5] ⚠ frame_0003.png (OCR failed)
  [4/5] ✓ frame_0004.png
                → Island
  [5/5] ✓ frame_0005.png
                → Swamp

============================================================
[OCR TEST] Results:
  Total images: 5
  OCR success: 4
  Success rate: 80%

  Detected cards:
    - Lightning Bolt: 1x
    - Forest: 1x
    - Island: 1x
    - Swamp: 1x
============================================================
```

---

## Advanced Options

### Change Duration (test-ocr-live)
```bash
# Test for 30 seconds
python mtg_sorter_cli.py test-ocr-live --duration 30

# Test for 120 seconds
python mtg_sorter_cli.py test-ocr-live --duration 120
```

### Use Different Camera
```bash
# Use camera 1 instead of camera 0
python mtg_sorter_cli.py test-ocr-live --camera 1

# Or with image test (for consistency)
python mtg_sorter_cli.py test-ocr-image --image card.png
```

### Test in Mock Mode
```bash
# All tests work in mock mode (Windows)
python mtg_sorter_cli.py test-ocr-live --mock

# This is automatic on non-Raspberry Pi systems
```

---

## Complete Command Reference

### Live Camera Test
```bash
python mtg_sorter_cli.py test-ocr-live [--duration SECONDS] [--camera INDEX] [--mock]
```

**Options:**
- `--duration SECONDS`: How long to run (default: 60)
- `--camera INDEX`: Camera device (default: 0)
- `--mock`: Force mock mode

**Examples:**
```bash
# Basic: 60 seconds, camera 0
python mtg_sorter_cli.py test-ocr-live

# 30 seconds with camera 1
python mtg_sorter_cli.py test-ocr-live --duration 30 --camera 1

# Windows testing
python mtg_sorter_cli.py test-ocr-live --mock
```

---

### Single Image Test
```bash
python mtg_sorter_cli.py test-ocr-image --image FILE_PATH [--mock]
```

**Options:**
- `--image FILE_PATH`: Path to image (required)
- `--mock`: Force mock mode

**Examples:**
```bash
# Test image
python mtg_sorter_cli.py test-ocr-image --image card.png

# Test from subfolder
python mtg_sorter_cli.py test-ocr-image --image ./captures/frame_001.png

# With mock mode
python mtg_sorter_cli.py test-ocr-image --image card.png --mock
```

---

### Directory Test
```bash
python mtg_sorter_cli.py test-ocr-dir --directory DIR_PATH [--mock]
```

**Options:**
- `--directory DIR_PATH`: Path to folder (required)
- `--mock`: Force mock mode

**Examples:**
```bash
# Test all images in captures folder
python mtg_sorter_cli.py test-ocr-dir --directory ./captures

# Test with absolute path
python mtg_sorter_cli.py test-ocr-dir --directory /home/pi/card-sorter/captures

# With mock mode
python mtg_sorter_cli.py test-ocr-dir --directory ./captures --mock
```

---

## Workflow Examples

### Capture and Test (Step by Step)

**Step 1: Capture frames**
```bash
python capture_frames.py  # Captures 30 frames (see earlier script)
```

**Step 2: Test all captured frames**
```bash
python mtg_sorter_cli.py test-ocr-dir --directory ./captures
```

**Step 3: Test specific frame with debug**
```bash
python test_ocr.py captures/frame_0010.png --debug
```

---

### Quick Live Test
```bash
# Hold cards in front of camera for 30 seconds
python mtg_sorter_cli.py test-ocr-live --duration 30
```

---

### Batch Testing on SSH
```bash
# Over SSH, test pre-captured images
python mtg_sorter_cli.py test-ocr-dir --directory ./test_cards
```

---

## Troubleshooting

### "Camera not found"
```bash
# Check available cameras
# Windows: (usually 0)
# Linux/Pi: Try 0, 1, 2, etc.

python mtg_sorter_cli.py test-ocr-live --camera 0
python mtg_sorter_cli.py test-ocr-live --camera 1
python mtg_sorter_cli.py test-ocr-live --camera 2
```

### "File not found"
```bash
# Use full path
python mtg_sorter_cli.py test-ocr-image --image /full/path/to/card.png

# Or relative path from current directory
python mtg_sorter_cli.py test-ocr-image --image ./cards/test.png
```

### "Directory is empty"
```bash
# Check what images exist
ls ./captures/*.png

# Or use absolute path
python mtg_sorter_cli.py test-ocr-dir --directory /home/pi/captures
```

---

## Help & Info

### Show all available commands
```bash
python mtg_sorter_cli.py --help
```

Output:
```
usage: mtg_sorter_cli.py [-h] {test-servo,...,test-ocr-live,test-ocr-image,test-ocr-dir,run} ...

MTG Card Sorter - CLI Version

positional arguments:
  {test-servo,test-hopper,test-all,test-all-channels,test-camera,test-i2c,test-ocr-live,test-ocr-image,test-ocr-dir,run}
                        Command to execute

optional arguments:
  -h, --help            show this help message and exit
  --image IMAGE         Image file for test-ocr-image
  --directory DIRECTORY
                        Directory for test-ocr-dir
  --duration DURATION   Duration in seconds for test-ocr-live (default: 60)
  --camera CAMERA       Camera device index (default: 0)
  --mock                Enable mock mode (no hardware)
```

---

## Tips & Best Practices

### 1. **Start with Images**
If you have pre-captured card images, start with testing those:
```bash
python mtg_sorter_cli.py test-ocr-image --image card.png
```

### 2. **Batch Test Directory First**
Before live testing, batch test a directory of images:
```bash
python mtg_sorter_cli.py test-ocr-dir --directory ./test_cards
```

### 3. **Use Debug Tool for Detailed Analysis**
For problematic images, use the debug tool:
```bash
python test_ocr.py problem_card.png --debug
```

### 4. **Check Success Rate**
Monitor the success rate in test results:
```
Success rate: 80%  # Good
Success rate: 50%  # Need to improve lighting/focus
```

### 5. **Test Different Durations**
For live testing:
```bash
# Quick test (15 seconds)
python mtg_sorter_cli.py test-ocr-live --duration 15

# Extended test (5 minutes)
python mtg_sorter_cli.py test-ocr-live --duration 300
```

---

## Integration with Full System

Once OCR tests pass, run full sorter:
```bash
python mtg_sorter_cli.py run --count 5 --mode price
```

This will:
1. Capture cards
2. Detect card edges
3. Run improved OCR
4. Look up on Scryfall
5. Route to correct bin
6. Actuate servos to sort

---

## Common Test Sequences

### Sequence 1: Full Validation (Before Production)
```bash
# 1. Test single card
python mtg_sorter_cli.py test-ocr-image --image sample.png

# 2. Test batch
python mtg_sorter_cli.py test-ocr-dir --directory ./test_cards

# 3. Test live for 60 seconds
python mtg_sorter_cli.py test-ocr-live --duration 60

# 4. Check results and decide
# If >85% success → Ready for production
# If <85% → Adjust lighting/focus and retry
```

### Sequence 2: Quick Validation (Already Tested Before)
```bash
# Just run live test
python mtg_sorter_cli.py test-ocr-live --duration 30
```

### Sequence 3: Troubleshooting
```bash
# 1. Test single problematic card with debug
python test_ocr.py problem_card.png --debug

# 2. Check the debug_*.png files to identify issue
# 3. Adjust settings and retry
# 4. Test again
python mtg_sorter_cli.py test-ocr-image --image problem_card.png
```

---

## Expected Performance

### Accuracy by Condition
- **Clean lighting**: 95%+ ✅
- **Normal lighting**: 85-90% ✅
- **Poor lighting**: 70-80% ⚠
- **Very poor lighting**: <70% ❌

### Speed
- Live test: ~2-5 cards per second
- Image test: <1 second per image
- Directory test: ~1-2 seconds per image

---

That's it! You now have full CLI OCR testing capabilities. 🚀
