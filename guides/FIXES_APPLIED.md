# Fixes Applied to mtg_sorter.py

## Summary
Created `mtg_sorter_fixed.py` with all critical bugs fixed and additional improvements implemented.

---

## Critical Fixes (Required for Functionality)

### ✅ Fix #1: Added Missing `numpy` Import
**File**: mtg_sorter_fixed.py, Line 13-14

**Problem**: Code used `np.diff()`, `np.argmin()`, `np.argmax()`, and `np.array()` without importing numpy.

**Solution**:
```python
try:
    import cv2
    import numpy as np  # ← Added this line
except Exception:
    cv2 = None
    np = None
```

**Impact**: Prevents `NameError: name 'np' is not defined` crash in `detect_card_and_warp()`.

---

### ✅ Fix #2: Corrected Servo Function Call in `_tick()`
**File**: mtg_sorter_fixed.py, Lines 382-392

**Problem**: 
- Used non-existent `self.pwm_map` instead of `self.pca`
- Used non-existent `self.servo_cfg.open_dc` and `close_dc` instead of `pulse_open_us` and `pulse_close_us`

**Original Code** (BROKEN):
```python
move_servo(self.pwm_map, bin_name, self.servo_cfg.open_dc, self.servo_cfg.close_dc, mock=self.cfg.mock_mode)
```

**Fixed Code**:
```python
ch = self.channel_map.get(bin_name, -1)
if ch >= 0:
    move_servo(
        self.pca,                           # ← Fixed: use self.pca
        bin_name, 
        ch,                                 # ← Fixed: pass channel number
        self.servo_cfg.pulse_open_us,      # ← Fixed: correct attribute
        self.servo_cfg.pulse_close_us,     # ← Fixed: correct attribute
        mock=self.cfg.mock_mode
    )
```

**Impact**: Prevents `AttributeError` crashes during card sorting.

---

### ✅ Fix #3: Added `pytesseract` to requirements.txt
**File**: requirements.txt, Line 4

**Problem**: Code imports and uses `pytesseract` but it wasn't in requirements.txt.

**Solution**: Added `pytesseract` to the dependencies list.

**Impact**: Ensures OCR functionality works when dependencies are installed via `pip install -r requirements.txt`.

---

### ✅ Fix #4: Added Null Check for numpy
**File**: mtg_sorter_fixed.py, Line 133

**Problem**: If numpy import fails, `detect_card_and_warp()` would crash.

**Solution**:
```python
def detect_card_and_warp(frame) -> Optional[any]:
    if np is None:  # ← Added null check
        return None
    # ... rest of function
```

**Impact**: Graceful degradation if numpy is unavailable.

---

## Additional Improvements

### 🔧 Improvement #1: Configurable Camera Device Index
**File**: mtg_sorter_fixed.py, Lines 56, 127

**Added to AppConfig**:
```python
camera_device_index: int = 0  # Configurable camera index
```

**Updated `open_camera()` function**:
```python
def open_camera(resolution: Tuple[int, int], device_index: int = 0):
    cap = cv2.VideoCapture(device_index)  # ← Now configurable
```

**Benefit**: Allows using cameras on different device indices (e.g., `/dev/video1`).

---

### 🔧 Improvement #2: Camera Failure Tracking
**File**: mtg_sorter_fixed.py, Lines 57, 289, 337-347

**Added to AppConfig**:
```python
max_capture_failures: int = 10  # Max consecutive failures before stopping
```

**Added to SorterGUI**:
```python
self.capture_failures = 0  # Track consecutive failures
```

**Enhanced error handling in `_tick()`**:
```python
if not ret:
    self.capture_failures += 1
    if self.capture_failures >= self.cfg.max_capture_failures:
        self.status_var.set(f"Camera failed {self.capture_failures} times - stopping")
        self.stop()
        return
    self.status_var.set(f"Capture failed ({self.capture_failures}/{self.cfg.max_capture_failures})")
    self._schedule_tick()
    return

# Reset on success
self.capture_failures = 0
```

**Benefit**: Prevents infinite retry loops if camera disconnects or fails permanently.

---

### 🔧 Improvement #3: Servo Channel Validation
**File**: mtg_sorter_fixed.py, Lines 99-102

**Added validation**:
```python
def move_servo(...):
    if channel < 0 or channel > 15:
        print(f"[ERROR] Invalid servo channel {channel} for {name}")
        return
    # ... rest of function
```

**Benefit**: Prevents crashes from invalid channel numbers.

---

### 🔧 Improvement #4: Enhanced OCR Preprocessing
**File**: mtg_sorter_fixed.py, Lines 169-172

**Added preprocessing steps**:
```python
gray = cv2.medianBlur(gray, 3)  # Reduce noise
gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)  # Upscale
```

**Changed PSM mode**:
```python
config = "--psm 6 -l eng"  # Assume uniform block of text (better for multi-line names)
```

**Benefit**: Improved OCR accuracy for card names.

---

### 🔧 Improvement #5: Scryfall API Rate Limiting
**File**: mtg_sorter_fixed.py, Lines 183-186, 191-196

**Added rate limiting**:
```python
_last_scryfall_request = 0
_MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests

def scryfall_lookup(name: str, timeout: float = 6.0) -> Optional[CardInfo]:
    global _last_scryfall_request
    
    # Enforce rate limiting
    elapsed = time.time() - _last_scryfall_request
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    
    _last_scryfall_request = time.time()
    # ... rest of function
```

**Benefit**: Prevents hitting Scryfall API rate limits (~10 requests/second).

---

### 🔧 Improvement #6: Better Error Handling
**File**: mtg_sorter_fixed.py, Lines 111-113, 210-211, 397-400

**Added try-catch blocks and error messages**:
```python
try:
    pca.channels[channel].duty_cycle = open_val
    time.sleep(dwell_s)
    pca.channels[channel].duty_cycle = close_val
except Exception as e:
    print(f"[ERROR] Failed to move servo {name} on channel {channel}: {e}")
```

**Benefit**: Better debugging and graceful error handling.

---

### 🔧 Improvement #7: Float Division for Pulse Calculation
**File**: mtg_sorter_fixed.py, Lines 108-109

**Changed**:
```python
open_val = int(pulse_open_us * 4096 / 20000.0)  # ← Added .0 for explicit float division
close_val = int(pulse_close_us * 4096 / 20000.0)
```

**Benefit**: Ensures correct calculation in all Python versions.

---

## Installation Instructions

### On Raspberry Pi:

1. **Install system dependencies**:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng
sudo apt-get install python3-opencv python3-pip
```

2. **Enable I2C**:
```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
sudo reboot
```

3. **Install Python dependencies**:
```bash
cd /path/to/card-sorter
pip3 install -r requirements.txt
```

4. **Verify I2C device**:
```bash
i2cdetect -y 1
# Should show 0x40 (or your configured PCA9685 address)
```

5. **Test camera**:
```bash
ls /dev/video*
# Should show /dev/video0 (or similar)
```

6. **Run the fixed version**:
```bash
python3 mtg_sorter_fixed.py
```

---

## Testing Checklist

- [ ] **Mock Mode Test** (on any computer):
  ```bash
  python3 mtg_sorter_fixed.py
  # Should start in mock mode with GUI
  # Test all 6 servo buttons - should print mock messages
  ```

- [ ] **I2C Detection** (on Raspberry Pi):
  ```bash
  i2cdetect -y 1
  # Verify 0x40 appears in the grid
  ```

- [ ] **Camera Test** (on Raspberry Pi):
  - Disable mock mode in GUI
  - Click "Start"
  - Verify camera opens without errors
  - Place a card in view
  - Check if card detection works

- [ ] **Servo Test** (on Raspberry Pi):
  - Use GUI "Test" buttons for each bin
  - Verify servos move to open position then close
  - Adjust `pulse_open_us` and `pulse_close_us` if angles are wrong

- [ ] **OCR Test** (on Raspberry Pi):
  - Place a well-lit MTG card in camera view
  - Check if name is extracted correctly
  - Adjust lighting or `name_roi` if needed

- [ ] **Full Sorting Test** (on Raspberry Pi):
  - Start the sorter
  - Feed cards one at a time
  - Verify correct bin routing based on price/color
  - Check Scryfall lookups succeed

---

## Comparison: Original vs Fixed

| Issue | Original Code | Fixed Code | Status |
|-------|--------------|------------|--------|
| numpy import | ❌ Missing | ✅ Added | **FIXED** |
| Servo call in _tick() | ❌ Wrong variables | ✅ Correct parameters | **FIXED** |
| pytesseract in requirements | ❌ Missing | ✅ Added | **FIXED** |
| Camera device index | ⚠️ Hardcoded | ✅ Configurable | **IMPROVED** |
| Capture failure handling | ⚠️ Infinite retry | ✅ Max failures limit | **IMPROVED** |
| Servo channel validation | ⚠️ None | ✅ Validates 0-15 | **IMPROVED** |
| OCR preprocessing | ⚠️ Basic | ✅ Enhanced | **IMPROVED** |
| Scryfall rate limiting | ⚠️ None | ✅ 100ms throttle | **IMPROVED** |
| Error messages | ⚠️ Minimal | ✅ Detailed logging | **IMPROVED** |

---

## Files Modified

1. ✅ **mtg_sorter_fixed.py** - New fixed version with all corrections
2. ✅ **requirements.txt** - Added `pytesseract` dependency
3. ✅ **CODE_REVIEW_mtg_sorter.md** - Detailed analysis of all issues
4. ✅ **FIXES_APPLIED.md** - This document

---

## Next Steps

1. **Deploy to Raspberry Pi**: Copy `mtg_sorter_fixed.py` to your Pi
2. **Install dependencies**: Follow installation instructions above
3. **Test in mock mode**: Verify GUI and logic work
4. **Test with hardware**: Connect servos and camera, test each component
5. **Calibrate**: Adjust servo angles and OCR ROI for your setup
6. **Production use**: Start sorting cards!

---

## Support

If you encounter issues:

1. Check `CODE_REVIEW_mtg_sorter.md` for detailed troubleshooting
2. Verify all system dependencies are installed
3. Confirm I2C is enabled and PCA9685 is detected
4. Test camera with `ls /dev/video*`
5. Run in mock mode first to isolate hardware vs software issues
