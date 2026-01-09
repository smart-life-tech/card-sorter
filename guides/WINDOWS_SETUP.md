# Windows Setup Guide for MTG Card Sorter

## Issue: "pytesseract not installed or not in path"

You have `pytesseract` (the Python wrapper) installed, but you need the **Tesseract OCR engine** itself.

---

## Solution: Install Tesseract OCR

### Step 1: Download Tesseract Installer

Download the Windows installer from:
**https://github.com/UB-Mannheim/tesseract/wiki**

Or direct link:
**https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe**

### Step 2: Run the Installer

1. Run the downloaded `.exe` file
2. **Important:** During installation, note the installation path (usually `C:\Program Files\Tesseract-OCR`)
3. Complete the installation

### Step 3: Add Tesseract to PATH

**Option A: Automatic (Recommended)**

The installer should add it to PATH automatically. Restart your terminal and test:

```bash
tesseract --version
```

If this works, you're done! Skip to Step 4.

**Option B: Manual (if Option A didn't work)**

1. Open **System Properties**:
   - Press `Win + R`
   - Type `sysdm.cpl`
   - Press Enter

2. Click **Environment Variables** button

3. Under **System variables**, find and select **Path**

4. Click **Edit**

5. Click **New**

6. Add: `C:\Program Files\Tesseract-OCR`

7. Click **OK** on all windows

8. **Restart your terminal** (important!)

9. Test:
   ```bash
   tesseract --version
   ```

### Step 4: Configure pytesseract (if needed)

If tesseract is installed but pytesseract still can't find it, you can specify the path directly.

**Edit `camera_calibration.py`** and add this near the top (after imports):

```python
try:
    import pytesseract
    # Specify tesseract path if not in PATH
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except Exception:
    pytesseract = None
```

---

## Quick Test

After installation, test if it works:

```bash
# Test tesseract directly
tesseract --version

# Should output something like:
# tesseract 5.3.3
#  leptonica-1.83.1
#  ...

# Test with Python
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"

# Should output version number like: (5, 3, 3)
```

---

## Alternative: Quick Fix for Testing

If you want to test the calibration tool **without OCR** (just to see the camera and adjust the region visually), the tool will still work! It will just show "pytesseract not available" instead of the OCR result.

The visual adjustment of the green box will still work perfectly, and you can save your ROI settings.

---

## Full Installation Checklist

- [ ] Python 3.8+ installed
- [ ] pip installed
- [ ] pytesseract installed: `pip install pytesseract`
- [ ] Tesseract OCR engine installed (from link above)
- [ ] Tesseract added to PATH (or path configured in code)
- [ ] Terminal restarted after PATH changes
- [ ] Test: `tesseract --version` works
- [ ] Test: `python -c "import pytesseract; print(pytesseract.get_tesseract_version())"` works

---

## Troubleshooting

### "tesseract is not recognized as an internal or external command"

**Problem:** Tesseract not in PATH

**Solution:**
1. Find where Tesseract is installed (usually `C:\Program Files\Tesseract-OCR`)
2. Add to PATH (see Step 3 above)
3. Restart terminal
4. Or hardcode path in Python (see Step 4 above)

### "Failed to load tesseract"

**Problem:** Wrong path or 32-bit/64-bit mismatch

**Solution:**
1. Verify installation path
2. Make sure you downloaded the correct version (64-bit for 64-bit Python)
3. Reinstall Tesseract if needed

### "Permission denied" during pip install

**Problem:** Python installation in protected directory

**Solution:**
```bash
# Install for current user only
pip install --user pytesseract

# Or run as administrator
# Right-click PowerShell/CMD -> Run as Administrator
pip install pytesseract
```

---

## For Raspberry Pi

On Raspberry Pi, installation is simpler:

```bash
# Install system package
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng

# Install Python package
pip3 install pytesseract

# Test
tesseract --version
```

---

## Current Status

Based on your output:
- ✅ Python installed (Python 3.11 and 3.8 detected)
- ✅ pytesseract package installed
- ✅ Camera working (calibration tool opened successfully)
- ❌ Tesseract OCR engine not installed or not in PATH

**Next step:** Install Tesseract OCR engine from the link above, then restart your terminal and try again!

---

## After Installing Tesseract

Once Tesseract is installed and working, run the calibration tool again:

```bash
python camera_calibration.py
```

Now you should see:
- Card detection ✓
- OCR region overlay ✓
- **OCR results** ✓ (this will now work!)

Place a card in view, press SPACE to freeze, and adjust the green box until the OCR correctly reads the card name!
