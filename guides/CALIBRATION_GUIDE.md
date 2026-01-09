# Camera Calibration Guide

Visual tool for adjusting OCR region settings on Windows before deploying to Raspberry Pi.

---

## Quick Start

### On Windows (for testing/calibration):

```bash
python camera_calibration.py
```

This opens a live preview window showing:
- **Card detection** (green outline on detected card)
- **Warped card image** (perspective-corrected)
- **OCR region** (green rectangle showing where text is read)
- **Processed OCR region** (what the OCR actually sees)
- **OCR result** (extracted text)

---

## Window Layout

```
┌─────────────────────────────────────────────────────────┐
│  Card (Warped)          │  OCR ROI Settings             │
│  [Shows warped card     │  X1: 0.080                    │
│   with green OCR box]   │  Y1: 0.080                    │
│                         │  X2: 0.920                    │
│                         │  Y2: 0.220                    │
│                         │                               │
│                         │  OCR Result:                  │
│                         │  Lightning Bolt               │
│                         │                               │
│                         │  Status: LIVE                 │
├─────────────────────────────────────────────────────────┤
│  OCR Region (Processed) │                               │
│  [Shows preprocessed    │                               │
│   grayscale text area]  │                               │
└─────────────────────────────────────────────────────────┘
```

---

## Controls

| Key | Action |
|-----|--------|
| **SPACE** | Freeze/unfreeze frame (freeze to adjust ROI) |
| **Arrow Keys** | Move OCR region (when frozen) |
| **+** / **-** | Increase/decrease ROI height (when frozen) |
| **r** | Reset ROI to defaults |
| **s** | Save current frame and settings |
| **q** | Quit |

---

## Calibration Workflow

### Step 1: Start the Tool
```bash
python camera_calibration.py
```

### Step 2: Position a Card
- Place an MTG card in front of the camera
- Ensure good lighting (no glare on card surface)
- Card should fill most of the frame
- Wait for green outline to appear (card detected)

### Step 3: Freeze the Frame
- Press **SPACE** to freeze the current frame
- Status will change to "FROZEN - Adjust ROI"

### Step 4: Adjust OCR Region
The OCR region (green rectangle) should cover the **card name area** at the top of the card.

**Use arrow keys to adjust:**
- **↑** / **↓** - Move region up/down
- **←** / **→** - Move region left/right
- **+** / **-** - Make region taller/shorter

**Watch the "OCR Result" to see if the name is being read correctly!**

### Step 5: Fine-Tune
- Look at the "OCR Region (Processed)" window
- This shows exactly what the OCR sees (black text on white background)
- Adjust until the card name is clearly visible and centered

### Step 6: Save Settings
- Press **s** to save the current frame and settings
- Note the ROI values displayed in the info panel
- These will be printed when you quit

### Step 7: Test with Multiple Cards
- Press **SPACE** to unfreeze
- Try different cards to ensure ROI works for all
- Adjust if needed

### Step 8: Apply Settings
When you quit (press **q**), the final ROI settings will be printed:

```
Final ROI Settings:
  name_roi: [0.080, 0.080, 0.920, 0.220]

To use these settings, update your config:
  name_roi = (0.080, 0.080, 0.920, 0.220)
```

Copy these values to your sorter configuration!

---

## Updating the Sorter with New ROI

### For `mtg_sorter_fixed.py` (GUI version):
Edit the file and change:
```python
@dataclass
class AppConfig:
    # ... other settings ...
    name_roi: Tuple[float, float, float, float] = (0.080, 0.080, 0.920, 0.220)  # ← Update these values
```

### For `mtg_sorter_cli.py` (CLI version):
Edit the file and change:
```python
@dataclass
class AppConfig:
    # ... other settings ...
    name_roi: Tuple[float, float, float, float] = (0.080, 0.080, 0.920, 0.220)  # ← Update these values
```

---

## Understanding ROI Values

The ROI is defined as `(x1, y1, x2, y2)` where:
- **x1, y1** = Top-left corner (as fraction of image width/height)
- **x2, y2** = Bottom-right corner (as fraction of image width/height)

**Example:**
```
name_roi = (0.08, 0.08, 0.92, 0.22)
```
Means:
- Start at 8% from left, 8% from top
- End at 92% from left, 22% from top
- This captures the top ~14% of the card (where names typically are)

---

## Troubleshooting

### "NO CARD DETECTED"
**Problem:** Card outline not appearing

**Solutions:**
- Improve lighting (avoid shadows and glare)
- Ensure card has clear edges against background
- Try a darker/lighter background
- Move card closer to camera
- Ensure card is flat (not bent)

### OCR Reading Wrong Text
**Problem:** OCR result shows gibberish or wrong text

**Solutions:**
1. **Adjust ROI position** - Make sure green box covers only the name area
2. **Check lighting** - Text should be clearly visible
3. **Avoid glare** - Shiny card surfaces can confuse OCR
4. **Check focus** - Camera should be in focus on the card
5. **Try different cards** - Some card styles OCR better than others

### OCR Region Too Small/Large
**Problem:** Green box doesn't cover the name properly

**Solutions:**
- Press **SPACE** to freeze
- Use **arrow keys** to reposition
- Use **+/-** to resize height
- Press **r** to reset if you get lost

### Camera Not Opening
**Problem:** Error opening camera device

**Solutions:**
```bash
# Try different device index
python camera_calibration.py --device 1

# Or device 2, 3, etc.
python camera_calibration.py --device 2
```

### Low Resolution
**Problem:** Image quality too low

**Solutions:**
```bash
# Increase resolution
python camera_calibration.py --width 1920 --height 1080
```

---

## Tips for Best Results

### Lighting
- ✅ Bright, even lighting from above
- ✅ Diffused light (no harsh shadows)
- ❌ Avoid direct sunlight (causes glare)
- ❌ Avoid backlighting (card appears dark)

### Card Position
- ✅ Card fills 60-80% of frame
- ✅ Card is flat and parallel to camera
- ✅ All 4 corners visible
- ❌ Card too close (corners cut off)
- ❌ Card at angle (perspective distortion)

### Background
- ✅ Solid color background (black, white, or green work well)
- ✅ High contrast with card edges
- ❌ Busy/patterned background
- ❌ Similar color to card

### OCR Region
- ✅ Covers entire name area
- ✅ Includes some margin above/below text
- ✅ Excludes mana cost symbols
- ❌ Too tight (cuts off letters)
- ❌ Too large (includes non-text areas)

---

## Example Calibration Session

```bash
$ python camera_calibration.py

======================================================================
MTG Card Sorter - Camera Calibration Tool
======================================================================
Camera: Device 0 @ 1280x720
OCR ROI: [0.08, 0.08, 0.92, 0.22]
======================================================================

Controls:
  q - Quit
  s - Save current frame and OCR region
  r - Reset ROI to defaults
  Arrow Keys - Adjust ROI position
  +/- - Adjust ROI size
  SPACE - Freeze frame for adjustment
======================================================================

✓ Camera opened successfully

Place a card in view and press SPACE to freeze for adjustment

[User places "Lightning Bolt" card]
[Presses SPACE to freeze]

[FROZEN] Frame frozen - adjust ROI with arrow keys

[User adjusts with arrow keys until OCR shows "Lightning Bolt"]
[Presses 's' to save]

[SAVED] Images saved:
  - calibration_warped.jpg
  - calibration_ocr_region.jpg
  - Current ROI: [0.08, 0.09, 0.92, 0.21]

[User presses 'q' to quit]

======================================================================
Final ROI Settings:
  name_roi: [0.08, 0.09, 0.92, 0.21]

To use these settings, update your config:
  name_roi = (0.080, 0.090, 0.920, 0.210)
======================================================================
```

---

## Advanced Options

### Custom Camera Device
```bash
python camera_calibration.py --device 1
```

### Custom Resolution
```bash
python camera_calibration.py --width 1920 --height 1080
```

### Combined
```bash
python camera_calibration.py --device 1 --width 1920 --height 1080
```

---

## Saved Files

When you press **'s'**, two files are saved:

1. **`calibration_warped.jpg`** - The warped card image with ROI overlay
2. **`calibration_ocr_region.jpg`** - The processed OCR region (what OCR sees)

These are useful for:
- Documenting your calibration
- Troubleshooting OCR issues
- Sharing with others for help

---

## Next Steps

After calibration:

1. **Note your final ROI values**
2. **Update the sorter code** with new ROI
3. **Test on Raspberry Pi** with `mtg_sorter_cli.py test-camera`
4. **Run a small batch** to verify: `python3 mtg_sorter_cli.py run --count 5`
5. **Adjust if needed** and repeat calibration

---

## Common ROI Presets

Different card layouts may need different ROIs:

### Standard Modern Cards
```python
name_roi = (0.08, 0.08, 0.92, 0.22)  # Default
```

### Older Cards (Pre-8th Edition)
```python
name_roi = (0.10, 0.06, 0.90, 0.20)  # Name slightly higher
```

### Full-Art Cards
```python
name_roi = (0.08, 0.05, 0.92, 0.18)  # Name at very top
```

### Planeswalkers
```python
name_roi = (0.08, 0.08, 0.92, 0.24)  # Slightly taller for longer names
```

Try these presets if the default doesn't work well!

---

## Support

If OCR still isn't working after calibration:

1. Check saved images (`calibration_*.jpg`) to see what OCR is seeing
2. Try different lighting conditions
3. Test with multiple card types
4. Consider using a higher resolution camera
5. Ensure pytesseract and tesseract-ocr are properly installed
