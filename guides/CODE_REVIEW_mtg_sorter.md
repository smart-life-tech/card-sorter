# Code Review: mtg_sorter.py - Issues & Fixes

## Status: ❌ **WILL NOT WORK** - Multiple Critical Bugs Found

---

## Critical Issues (Must Fix)

### 1. ❌ Missing `numpy` Import
**Location**: Line ~120 in `detect_card_and_warp()`

**Problem**: Code uses `np.diff()`, `np.argmin()`, `np.argmax()`, and `np.array()` but numpy is never imported.

**Error**: `NameError: name 'np' is not defined`

**Fix**:
```python
# Add at top of file with other imports
import numpy as np
```

---

### 2. ❌ Wrong Variable Name in `_tick()` Method
**Location**: Line ~280 in `SorterGUI._tick()`

**Problem**: 
```python
move_servo(self.pwm_map, bin_name, self.servo_cfg.open_dc, ...)
```
- `self.pwm_map` doesn't exist (should be `self.pca`)
- `self.servo_cfg.open_dc` doesn't exist (should be `pulse_open_us`)
- `self.servo_cfg.close_dc` doesn't exist (should be `pulse_close_us`)

**Error**: `AttributeError: 'SorterGUI' object has no attribute 'pwm_map'`

**Fix**:
```python
# Change line ~280 from:
move_servo(self.pwm_map, bin_name, self.servo_cfg.open_dc, self.servo_cfg.close_dc, mock=self.cfg.mock_mode)

# To:
ch = self.channel_map.get(bin_name, -1)
if ch >= 0:
    move_servo(self.pca, bin_name, ch, self.servo_cfg.pulse_open_us, self.servo_cfg.pulse_close_us, mock=self.cfg.mock_mode)
```

---

### 3. ❌ Missing `pytesseract` in requirements.txt
**Location**: requirements.txt

**Problem**: Code imports and uses `pytesseract` but it's not in requirements.txt

**Fix**: Add to requirements.txt:
```
pytesseract
```

**Also Required**: System package installation on Raspberry Pi:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng
```

---

### 4. ❌ Incorrect Servo Function Parameters
**Location**: Multiple locations

**Problem**: The `move_servo()` function signature is:
```python
def move_servo(pca, name, channel, pulse_open_us, pulse_close_us, dwell_s=0.3, mock=True)
```

But `ServoConfig` doesn't have `open_dc` or `close_dc` attributes - it has `pulse_open_us` and `pulse_close_us`.

**Impact**: Any call using `open_dc`/`close_dc` will fail with AttributeError.

---

## Medium Priority Issues

### 5. ⚠️ Camera Error Handling
**Location**: `_tick()` method

**Problem**: If camera capture fails repeatedly, the app will keep retrying without clear feedback.

**Recommendation**: Add a failure counter and stop after N consecutive failures:
```python
def __init__(self, ...):
    # ... existing code ...
    self.capture_failures = 0
    self.max_failures = 10

def _tick(self):
    try:
        ret, frame = self.cap.read()
        if not ret:
            self.capture_failures += 1
            if self.capture_failures >= self.max_failures:
                self.status_var.set("Camera failed - stopping")
                self.stop()
                return
            self.status_var.set(f"Capture failed ({self.capture_failures}/{self.max_failures})")
            self._schedule_tick()
            return
        self.capture_failures = 0  # Reset on success
        # ... rest of code ...
```

---

### 6. ⚠️ No Validation of Servo Channels
**Location**: `move_servo()` function

**Problem**: If an invalid channel number is passed (e.g., -1, 16+), the code will crash.

**Recommendation**: Add validation:
```python
def move_servo(pca, name, channel, pulse_open_us, pulse_close_us, dwell_s=0.3, mock=True):
    if channel < 0 or channel > 15:
        print(f"[ERROR] Invalid servo channel {channel} for {name}")
        return
    # ... rest of function ...
```

---

### 7. ⚠️ Hardcoded Camera Device Index
**Location**: `open_camera()` function

**Problem**: Uses hardcoded `cv2.VideoCapture(0)` - may not work if camera is on different index.

**Recommendation**: Make it configurable via AppConfig:
```python
@dataclass
class AppConfig:
    # ... existing fields ...
    camera_device_index: int = 0  # Add this
```

---

## Low Priority Issues

### 8. ℹ️ Integer Division in Pulse Calculation
**Location**: `move_servo()` function

**Current Code**:
```python
open_val = int(pulse_open_us * 4096 / 20000)
```

**Note**: This works fine in Python 3, but for clarity and Python 2 compatibility (if ever needed), use:
```python
open_val = int(pulse_open_us * 4096 / 20000.0)
```

---

### 9. ℹ️ No Scryfall Rate Limiting
**Location**: `scryfall_lookup()` function

**Problem**: Scryfall API has rate limits (~10 requests/second). Rapid sorting could hit limits.

**Recommendation**: Add a small delay or implement request throttling:
```python
import time

last_request_time = 0
MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests

def scryfall_lookup(name: str, timeout: float = 6.0) -> Optional[CardInfo]:
    global last_request_time
    elapsed = time.time() - last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    
    try:
        last_request_time = time.time()
        # ... rest of function ...
```

---

### 10. ℹ️ OCR Configuration Could Be Improved
**Location**: `ocr_name_from_image()` function

**Current**: Uses `--psm 7` (single line)

**Recommendation**: MTG card names can span multiple lines. Try:
```python
config = "--psm 6 -l eng"  # Assume uniform block of text
```

Or add preprocessing:
```python
# After thresholding, add:
gray = cv2.medianBlur(gray, 3)  # Reduce noise
gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)  # Upscale for better OCR
```

---

## Hardware Compatibility Check

### ✅ PCA9685 Integration
- Correctly uses `adafruit-circuitpython-pca9685` library
- Proper I2C initialization with `board.SCL` and `board.SDA`
- Correct frequency setting (50 Hz for servos)
- Pulse width to duty cycle conversion is mathematically correct

### ✅ Servo Control
- Pulse range (1000-2000 µs) matches standard servo specs
- Channel assignments (0-5) match WIRING.md documentation
- Proper open/close sequence with dwell time

### ✅ Camera Integration
- Uses OpenCV VideoCapture (standard for USB webcams)
- Resolution setting is appropriate (1280x720)
- Perspective warp logic is sound for card detection

### ⚠️ I2C Considerations
**Must verify on Raspberry Pi**:
1. I2C is enabled: `sudo raspi-config` → Interface Options → I2C
2. PCA9685 is detected: `i2cdetect -y 1` should show `0x40`
3. User has I2C permissions: Add user to `i2c` group if needed

---

## Testing Checklist

Before running on Raspberry Pi:

- [ ] Fix all critical issues (1-4)
- [ ] Install system dependencies:
  ```bash
  sudo apt-get update
  sudo apt-get install tesseract-ocr tesseract-ocr-eng
  sudo apt-get install python3-opencv  # Or use pip
  ```
- [ ] Install Python dependencies:
  ```bash
  pip3 install -r requirements.txt
  pip3 install pytesseract numpy
  ```
- [ ] Enable I2C:
  ```bash
  sudo raspi-config
  # Navigate to: Interface Options → I2C → Enable
  sudo reboot
  ```
- [ ] Verify I2C device:
  ```bash
  i2cdetect -y 1
  # Should show 0x40 (or your configured address)
  ```
- [ ] Test camera:
  ```bash
  ls /dev/video*
  # Should show /dev/video0 (or similar)
  ```
- [ ] Run in mock mode first:
  ```python
  # In mtg_sorter.py, temporarily set:
  cfg.mock_mode = True
  ```
- [ ] Test each servo individually using GUI "Test" buttons
- [ ] Verify servo angles and adjust `pulse_open_us`/`pulse_close_us` if needed

---

## Summary

**Current Status**: Code will **NOT run** due to critical bugs.

**Required Fixes**:
1. Add `import numpy as np`
2. Fix `_tick()` method servo call
3. Add `pytesseract` to requirements.txt
4. Install tesseract-ocr system package

**Estimated Fix Time**: 15-30 minutes

**After Fixes**: Code should work on Raspberry Pi with proper hardware setup per WIRING.md.

---

## Recommended Next Steps

1. **Fix critical bugs** (issues 1-4)
2. **Test in mock mode** on development machine
3. **Deploy to Raspberry Pi** and test hardware
4. **Calibrate servos** using GUI test buttons
5. **Tune OCR** for your lighting/camera setup
6. **Add medium priority fixes** as needed during testing
