# CLI OCR Testing - Quick Reference

## Three Main Commands

### 1. Live Camera Test
```bash
python mtg_sorter_cli.py test-ocr-live
```
- Real-time detection and OCR
- Hold cards in front of camera
- Press Ctrl+C to stop
- Shows success rate

### 2. Test Single Image
```bash
python mtg_sorter_cli.py test-ocr-image --image card.png
```
- Test pre-captured image
- Shows detected name
- Fast (instant)

### 3. Test Folder of Images
```bash
python mtg_sorter_cli.py test-ocr-dir --directory ./captures
```
- Batch test multiple images
- Shows success rate
- Lists all detected cards

---

## Common Usage

| What | Command |
|------|---------|
| Test live (60s) | `python mtg_sorter_cli.py test-ocr-live` |
| Test live (30s) | `python mtg_sorter_cli.py test-ocr-live --duration 30` |
| Test live (2 min) | `python mtg_sorter_cli.py test-ocr-live --duration 120` |
| Test image | `python mtg_sorter_cli.py test-ocr-image --image card.png` |
| Test folder | `python mtg_sorter_cli.py test-ocr-dir --directory ./captures` |
| Use camera 1 | Add `--camera 1` to any command |
| Test on Windows | Add `--mock` to any command |

---

## Output Examples

### Live Test Success
```
[OCR TEST] ✓ Card detected: 'Lightning Bolt'
[OCR TEST] ✓ Card detected: 'Forest'
Success rate: 100%
```

### Image Test
```
[OCR TEST] Testing: card.png
[OCR TEST] ✓ Detected: 'Lightning Bolt'
```

### Batch Test
```
[1/5] ✓ frame_0001.png → Lightning Bolt
[2/5] ⚠ frame_0002.png (OCR failed)
[3/5] ✓ frame_0003.png → Forest
Success rate: 66%
```

---

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera not found | Try: `--camera 0`, `--camera 1`, `--camera 2` |
| File not found | Use full path: `--image /full/path/file.png` |
| Windows testing | Add `--mock` flag |
| Low success rate | Check lighting, focus camera, see debug guide |
| Want debug info | Use: `python test_ocr.py card.png --debug` |

---

## Workflow

1. **Quick test**: 
   ```bash
   python mtg_sorter_cli.py test-ocr-image --image test.png
   ```

2. **Batch test**:
   ```bash
   python mtg_sorter_cli.py test-ocr-dir --directory ./test_cards
   ```

3. **Live test**:
   ```bash
   python mtg_sorter_cli.py test-ocr-live --duration 30
   ```

4. **If issues**: 
   ```bash
   python test_ocr.py problem.png --debug
   ```

---

## Performance Targets

✅ **Success Rate**:
- 95%+ = Excellent
- 80%+ = Good
- 70%+ = Acceptable
- <70% = Needs improvement

✅ **Speed**:
- 2-5 cards/second = Normal
- <1 card/second = Acceptable

---

For detailed guide: See `CLI_OCR_TESTING.md`
