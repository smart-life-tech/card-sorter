# OCR Debugging & ROI Adjustment - Complete Documentation Index

## The Problem You're Experiencing

Your OCR test on Raspberry Pi hardware is detecting **"OS"** instead of actual card names.

This means:
- ✅ Card detection works (cards found)
- ✅ OCR preprocessing works (text extracted)
- ❌ **ROI is wrong** (capturing wrong region of card)

The **Region of Interest (ROI)** defines which part of the detected card to read. If it's off, you get wrong results.

## Solution: Visual ROI Debugging

The new feature automatically **saves the ROI region as PNG images** so you can see exactly what's being read, then **test different coordinates easily** without editing files.

## Start Here (Pick One)

### 🚀 I just want to fix it quickly
Read: **[ROI_QUICK_REFERENCE.md](ROI_QUICK_REFERENCE.md)**
- 3-step guide
- Common scenarios with exact commands
- Examples for moving ROI up/down/wider/narrower

### 📚 I want detailed explanations
Read: **[ROI_DEBUGGING_GUIDE.md](ROI_DEBUGGING_GUIDE.md)**
- Complete workflow with reasoning
- How to interpret debug images
- Step-by-step troubleshooting
- How to update config when done

### 🔧 I want technical details
Read: **[ROI_IMPLEMENTATION_SUMMARY.md](ROI_IMPLEMENTATION_SUMMARY.md)**
- Code changes made
- Function signatures and parameters
- Implementation details
- File modifications list

### ✨ Just want a quick overview
Read: **[ROI_FEATURE_READY.md](ROI_FEATURE_READY.md)**
- Executive summary
- Feature overview
- Example usage
- Quick command reference

## The Workflow (Same Regardless of Docs)

### Step 1: Capture debug images
```bash
python mtg_sorter_cli.py test-ocr-live --duration 20
```

Saves PNG files: `ocr_roi_001.png`, `ocr_roi_002.png`, etc.

### Step 2: Download and inspect
Transfer PNG files to your computer and open them. They show the **exact pixels** being sent to OCR.

### Step 3: Adjust based on what you see
```bash
# Example: if ROI is too high, move it down
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.12 0.92 0.22
```

### Step 4: Update config when found
Edit `src/card_sorter/config_loader.py` with the working ROI coordinates.

## Command Reference

### Run OCR test with debug images (default ROI)
```bash
python mtg_sorter_cli.py test-ocr-live --duration 20
```

### Test with custom ROI coordinates
```bash
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi X1 Y1 X2 Y2
```

Format: `--roi 0.08 0.08 0.92 0.22`
- First two numbers: left/top margins
- Last two numbers: right/bottom margins
- All values 0.0-1.0 (fractions of card)

### Examples
```bash
# Move ROI higher (increase Y1, decrease Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.04 0.92 0.14

# Move ROI lower (decrease Y1, increase Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.12 0.92 0.22

# Make ROI taller (decrease Y1, increase Y2)
python mtg_sorter_cli.py test-ocr-live --duration 20 --roi 0.08 0.02 0.92 0.25

# Test with different camera
python mtg_sorter_cli.py test-ocr-live --duration 20 --camera 1
```

## Common Issues & Solutions

| What You See | Problem | Solution |
|--------------|---------|----------|
| "OS" in images | ROI too high, capturing set symbol | `--roi 0.08 0.12 0.92 0.22` (move Y1 down) |
| Empty space | ROI in wrong location entirely | Adjust both Y1 and Y2 to find text area |
| Partial text cut off | ROI boundaries too tight | Expand region: increase Y2, decrease Y1 |
| Multiple text regions | ROI too large | Narrow it: decrease Y2, increase Y1 |

## File Organization

### User-Facing Documentation
- **ROI_QUICK_REFERENCE.md** ← Start here for quick fixes
- **ROI_DEBUGGING_GUIDE.md** ← Detailed troubleshooting
- **ROI_FEATURE_READY.md** ← Feature overview
- **ROI_IMPLEMENTATION_SUMMARY.md** ← Technical details

### Previous OCR Documentation
- **OCR_IMPROVEMENTS.md** - OCR preprocessing details
- **OCR_CONFIG_GUIDE.md** - OCR configuration parameters
- **CLI_OCR_TESTING.md** - Full CLI documentation
- **CLI_OCR_QUICK_REFERENCE.md** - CLI quick reference

## Implementation Files Modified

- **mtg_sorter_cli.py**
  - `test_ocr_live()` function enhanced
  - New `--roi` CLI parameter added
  - ROI image saving implemented

## What the Feature Does

✅ **Saves debug images** - First 5 card ROI regions saved as PNG files
✅ **Shows pixel coordinates** - Prints exact ROI region being tested
✅ **Easy parameter testing** - Use `--roi` to test different coordinates
✅ **No file editing needed** - Test before updating config
✅ **SSH-friendly** - Works headless on Raspberry Pi via SSH
✅ **Visual feedback** - See exactly what OCR is reading

## Key Insights

1. **The PNG images are your best friend**
   - They show the **exact pixels** being sent to Tesseract OCR
   - If the image shows the card name → ROI is correct
   - If the image shows wrong text → ROI coordinates need adjustment

2. **ROI coordinates are fractions, not pixels**
   - 0.08 = 8% from edge
   - 0.92 = 92% from edge (or 8% from other edge)
   - Easy to adjust without calculating pixel sizes

3. **Test systematically**
   - Start with large adjustments (e.g., 0.08 to 0.04)
   - Check images after each test
   - Make fine adjustments once you're close

4. **Update config when working**
   - Don't rely on `--roi` parameter permanently
   - Update `src/card_sorter/config_loader.py`
   - Then test without parameters to confirm

## Next Actions

### Immediate (Right Now)
1. Open terminal on Raspberry Pi
2. Run: `python mtg_sorter_cli.py test-ocr-live --duration 20`
3. Download the `ocr_roi_*.png` files

### Short Term (Next 10 minutes)
1. Open PNG files on your computer
2. See what text is in each image
3. Determine what adjustment is needed

### Implementation (Next 30 minutes)
1. Test with adjusted `--roi` coordinates
2. Download and check new PNG files
3. Repeat until images show card names clearly

### Final (When working)
1. Update config file with working ROI
2. Test full system again
3. Celebrate! 🎉

## Questions?

- **How do ROI coordinates work?** → See ROI_QUICK_REFERENCE.md or ROI_DEBUGGING_GUIDE.md
- **Which ROI value should I change?** → Check ROI_DEBUGGING_GUIDE.md for scenarios
- **How do I update the config?** → See ROI_DEBUGGING_GUIDE.md "When You Find the Right ROI" section
- **What if images still look wrong after adjustment?** → See troubleshooting in ROI_DEBUGGING_GUIDE.md

## Summary

**You now have:**
- ✅ Automatic ROI debug image generation
- ✅ Easy parameter testing without code editing
- ✅ Visual feedback (PNG images)
- ✅ Comprehensive documentation with examples
- ✅ Quick reference guides

**The path forward:**
1. Test and capture images
2. Inspect images to see what's being read
3. Adjust ROI based on visual inspection
4. Update config when working
5. Verify full system

Start with [ROI_QUICK_REFERENCE.md](ROI_QUICK_REFERENCE.md) for the fastest path to a fix!
