# How to Use the Card Sorter System

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Python Path
**Windows PowerShell:**
```powershell
$env:PYTHONPATH="src"
```

**Windows CMD:**
```cmd
set PYTHONPATH=src
```

**Linux/macOS:**
```bash
export PYTHONPATH=src
```

### 3. Run the Application
```bash
python -m card_sorter.main
```

You'll see startup logs in the terminal, then the GUI window opens.

---

## GUI Controls

### Startup Screen
- **Status badge** (top): shows Ready/Processing/Stopped/Error
- **Mode buttons**: Price, Color, Mixed (select sorting strategy)
- **Price threshold**: slider + numeric field (default $0.25)
- **Price source**: Scryfall or TCGplayer dropdown
- **Bin toggles**: Enable/disable each bin (disabled bins reroute to Combined)
- **Test buttons**: trigger a one-shot servo move per bin
- **Start/Stop buttons**: control the processing loop

### Operation
1. Select **Mode** (price, color, or mixed)
2. Adjust **Price threshold** if needed
3. Enable/disable bins as desired
4. Click **Start** to begin processing
5. Monitor **Last bin** and **Counts** display
6. Click **Stop** to pause

---

## Hardware Setup

### Camera
- **Required**: USB webcam (tested with Nexigo 4K, adjust resolution if needed)
- **Connection**: USB to Pi or PC
- **Issue**: If camera doesn't open, check:
  - Camera is plugged in and recognized by OS
  - No other app is using it
  - Try changing device index in code (default is 0; try 1, 2, etc.)
  - On Windows, check Device Manager for USB video devices

### Development Mode (No Camera/Hardware)
If you don't have hardware connected, the app has a **mock mode**:

**To enable mock mode:**
Edit [config/default_config.yaml](../config/default_config.yaml):
```yaml
app:
  mock_mode: true  # Enable mock recognition/servo/camera
```

In mock mode:
- Camera: generates random test images
- Recognizer: returns random card data with confidence
- Servos: skip actual actuation (safe for testing)
- All other logic (routing, pricing, logging) works normally

### Servos & PCA9685
- **I2C address**: 0x40 (check with `i2cdetect -y 1` on Pi)
- **Power**: external 5–6V supply, common ground with Pi
- **Channels**: 0=Price, 1=Combined, 2=W+U, 3=Black, 4=Red, 5=Green
- **Calibration**: test each bin with GUI "Test" button; adjust `open_deg`/`closed_deg` in config

---

## Configuration Files

### config/default_config.yaml
- **app**: mode, price threshold, price sources, logging paths
- **recognition**: paths to ONNX model, label map, card index
- **hardware**: camera resolution, servo driver address, channels, angles
- **routing**: rules for disabled bins, low confidence, etc.

### Model Assets
Place your card recognition files in `models/`:
- `card_recognizer.onnx` — trained offline classifier
- `label_map.json` — array of art_ids indexed by model output
- `card_index.json` — array of card metadata (name, set, collector, colors, color_identity)

**Example card_index.json entry:**
```json
{
  "name": "Black Lotus",
  "set_code": "LEA",
  "collector_number": "233",
  "art_id": "lea_233_alt1",
  "colors": ["B"],
  "color_identity": ["B"]
}
```

---

## Pricing Setup

### Scryfall (Free)
- No setup needed; API is public

### TCGplayer (Requires Keys)
1. Register at https://tcgplayer.com/api/
2. Get **Public Key** and **Private Key** (client credentials)
3. Set environment variables:
   ```bash
   export TCGPLAYER_PUBLIC_KEY=your_public_key
   export TCGPLAYER_PRIVATE_KEY=your_private_key
   ```
4. TCGplayer client handles OAuth, retries, and rate-limit backoff

---

## Logging & Output

### Console Logs
- Real-time stream to terminal (INFO+ level)
- Shows: startup, card recognition, pricing, routing, errors

### Log Files
- **Daily CSV**: `logs/cards_YYYY-MM-DD.csv`
  - Columns: timestamp, name, set_code, collector_number, art_id, price_usd, price_source, bin, flags
  - Exported when you close the app or manually
- **App log**: `logs/app.log`
  - Full DEBUG+ messages for troubleshooting

---

## Sorting Modes

### Price Mode
- High-price cards (≥ threshold) → Price bin
- All others → Combined bin

### Color Mode
- Single-color cards → dedicated color bin (W+U combined, B, R, G)
- Multicolor, colorless, artifacts, lands → Combined bin

### Mixed Mode
- High-price (≥ threshold) → Price bin (overrides color)
- Otherwise → sort by color

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **"No module named 'card_sorter'"** | Set `PYTHONPATH=src` before running |
| **Camera doesn't open** | Check USB connection, try device index 1–2, enable mock mode for testing |
| **"No price found"** | Card not in Scryfall/TCGplayer; check spelling or use mock mode |
| **Servo doesn't move** | Calibrate angles in config; check PCA9685 address and power |
| **"Object of type set is not JSON serializable"** | Should be fixed; update to latest code |
| **GUI freezes during processing** | Processing loop runs in background; UI updates every 500ms |

---

## Custom Sensor/Trigger Integration

To use a real sensor (e.g., IR beam-break):

1. Create a trigger function that blocks and returns True when a card is detected:
   ```python
   def my_trigger():
       # Check GPIO/sensor, return True if card present
       return gpio.read_pin(17)  # example
   ```

2. Pass it when launching:
   ```python
   from card_sorter.main import CardSorterApp
   from card_sorter.gui import launch_gui
   
   app = CardSorterApp(config_path)
   launch_gui(app, trigger_waiter=my_trigger)
   ```

---

## Example Workflow

1. **Setup** (one-time):
   - Place ONNX model + card_index in `models/`
   - Calibrate servo angles
   - Set TCGplayer keys (optional)

2. **Development** (testing without hardware):
   - Enable mock_mode in config
   - Run app, click Start
   - Check logs and CSV output

3. **Deployment** (on Raspberry Pi with hardware):
   - Disable mock_mode
   - Connect camera + servos
   - Run app with a custom trigger function (sensor-based or timed)

---

## Performance Tuning

- **Recognition latency**: depends on model size; 2–4s target
- **Price cache TTL**: default 24h; reduce for real-time price updates
- **Servo dwell time**: default 0.3s; adjust if servos need more time
- **Processing loop**: sleeps 50ms between trigger checks when idle

---

## Support Files

- [README.md](../README.md) — project overview, features, setup
- [architecture.md](../src/card_sorter/architecture.md) — pipeline & module layout
- [gui_wireframe.md](../src/card_sorter/gui_wireframe.md) — UI controls reference
