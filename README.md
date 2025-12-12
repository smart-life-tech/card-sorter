# Card Sorter

Magic: The Gathering card sorter running on Raspberry Pi 4 with PCA9685-driven servos.

## Features
- Offline card recognition (ONNX) with color identity lookup via card index
- Dual price sources (Scryfall primary, TCGplayer selectable) with caching and fallback
- Price, color, and mixed sorting modes; adjustable price threshold
- GUI (Tkinter) for mode/threshold/source selection, bin enable/disable, and servo test
- Continuous processing loop with pluggable trigger waiter (e.g., sensor/beam-break) or timed loop
- CSV logging per day with card metadata, price, source, bin, and flags
- State persistence for thresholds, sources, bin toggles, and last bin

## Hardware Assumptions
- Raspberry Pi 4
- PCA9685 servo driver, 6 servos (bins: price, combined, W+U, B, R, G) with future expansion channels reserved
- External 5–6V servo supply, common ground with Pi
- USB camera (default 1080p capture)

## Setup
1) Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2) Place model/index assets (adjust paths in config/default_config.yaml if needed):
   - models/card_recognizer.onnx
   - models/label_map.json (list indexed by model outputs → art_id)
   - models/card_index.json (array of objects: name, set_code, collector_number, art_id, colors, color_identity)
3) Export TCGplayer API keys if using that source:
   ```bash
   export TCGPLAYER_PUBLIC_KEY=your_public
   export TCGPLAYER_PRIVATE_KEY=your_private
   ```
4) Calibrate servo angles in config/default_config.yaml (servo_driver.angles) for each bin.

## Running
 - Ensure Python can find the `card_sorter` package:
    - On Windows (PowerShell): `$env:PYTHONPATH="src"`
    - On CMD: `set PYTHONPATH=src`
    - On Linux/macOS: `export PYTHONPATH=src`
 - Then from repo root:
    ```bash
    python -m card_sorter.main
    ```
 - GUI launches; use Start/Stop to control processing.
 - Mode buttons: Price, Color, Mixed.
 - Price threshold slider/entry adjusts USD threshold.
 - Price source dropdown toggles Scryfall/TCGplayer; fallback auto-sets to the other.
 - Bin checkboxes enable/disable bins (disabled bins reroute to combined).
 - Test button triggers a one-shot servo move for that bin.

## Model Assets
 - Place files (or update paths in config/default_config.yaml):
    - `models/card_recognizer.onnx` — offline classifier
    - `models/label_map.json` — array where index matches ONNX output index and value is `art_id`
    - `models/card_index.json` — array of objects: `{name, set_code, collector_number, art_id, colors, color_identity}`
 - Model format: expects 224x224 RGB float32 CHW input scaled 0–1 (adjust recognize.py if your model differs).

## Servo Angle Calibration
1) Set safe defaults in `config/default_config.yaml` under `hardware.servo_driver.angles`.
2) Launch GUI and use the **Test** buttons per bin. Adjust `open_deg` / `closed_deg` per bin until throw is correct.
3) Restart app to re-read config, or add a reload hook if desired.
4) Ensure common ground and powered servos during calibration.

## Pricing Keys
 - TCGplayer: set `TCGPLAYER_PUBLIC_KEY` and `TCGPLAYER_PRIVATE_KEY` environment variables (client credentials flow).
 - Scryfall: no key needed.


## Processing Flow
1) Capture: grab frame from camera at configured resolution.
2) Recognize: ONNX model infers art_id; card index resolves name/set/collector/color identity.
3) Price: primary source, then fallback (with cache TTL). TCGplayer client handles OAuth, retries, and backoff.
4) Route: price mode, color mode, or mixed; color identity drives color bins; multicolor/colorless → combined bin.
5) Actuate: map logical bin to PCA9685 channel and open/close angles.
6) Log: append to daily CSV with metadata, price/source, bin, and flags (unrecognized, low_confidence, unpriced, etc.).

## Custom Trigger Integration
- The GUI uses a default timed trigger. To use a sensor/beam-break, provide a callable `trigger_waiter` that blocks briefly and returns True when a card is present; pass it to `launch_gui(app, trigger_waiter=...)` in main.py.

## Notes
- If ONNXRuntime or model files are missing, recognition safely falls back (low confidence/unrecognized → combined bin).
- Ensure lighting and camera position are stable for best accuracy.
- Keep price cache TTL and thresholds tuned to your flow speed and desired price cutoff.
