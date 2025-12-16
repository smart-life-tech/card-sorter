# MTG Card Sorter - CLI Usage Guide

Command-line interface for testing and running the card sorter over SSH without GUI.

---

## Quick Start

### 1. Make the script executable:
```bash
chmod +x mtg_sorter_cli.py
```

### 2. Test I2C connection:
```bash
python3 mtg_sorter_cli.py test-i2c
```

### 3. Test a single servo:
```bash
python3 mtg_sorter_cli.py test-servo --bin price
```

### 4. Test all servos:
```bash
python3 mtg_sorter_cli.py test-all
```

### 5. Test camera:
```bash
python3 mtg_sorter_cli.py test-camera
```

### 6. Run the sorter:
```bash
python3 mtg_sorter_cli.py run --mode price --count 10
```

---

## Commands

### `test-i2c`
Test I2C connection and detect PCA9685.

**Usage:**
```bash
python3 mtg_sorter_cli.py test-i2c
```

**Output:**
```
[TEST] Testing I2C...
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- -- 
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
70: -- -- -- -- -- -- -- --                         
[TEST] ✓ PCA9685 detected at 0x40
```

---

### `test-servo`
Test a single servo bin.

**Usage:**
```bash
python3 mtg_sorter_cli.py test-servo --bin <bin_name>
```

**Available bins:**
- `price` - High-value cards bin
- `combined` - Multi-color/low-value cards bin
- `white_blue` - White/Blue mono-color bin
- `black` - Black mono-color bin
- `red` - Red mono-color bin
- `green` - Green mono-color bin

**Examples:**
```bash
# Test price bin
python3 mtg_sorter_cli.py test-servo --bin price

# Test in mock mode
python3 mtg_sorter_cli.py test-servo --bin price --mock

# Test with hardware
python3 mtg_sorter_cli.py test-servo --bin price --no-mock
```

**Output:**
```
[TEST] Testing price_bin (channel 0)...
[SERVO] price_bin (ch 0) -> OPEN (2000µs) ... CLOSE (1000µs)
[TEST] Complete
```

---

### `test-all`
Test all servo bins in sequence.

**Usage:**
```bash
python3 mtg_sorter_cli.py test-all
```

**Output:**
```
[TEST] Testing all servos...

[TEST] Testing price_bin (channel 0)...
[SERVO] price_bin (ch 0) -> OPEN (2000µs) ... CLOSE (1000µs)
[TEST] Complete

[TEST] Testing combined_bin (channel 1)...
[SERVO] combined_bin (ch 1) -> OPEN (2000µs) ... CLOSE (1000µs)
[TEST] Complete

... (continues for all 6 bins)
```

---

### `test-camera`
Test camera capture and verify it's working.

**Usage:**
```bash
python3 mtg_sorter_cli.py test-camera
```

**Output:**
```
[TEST] Testing camera...
[CAMERA] ✓ Opened device 0 at 1280x720
[TEST] Capturing 5 frames...
  Frame 1/5: ✓ (720, 1280, 3)
  Frame 2/5: ✓ (720, 1280, 3)
  Frame 3/5: ✓ (720, 1280, 3)
  Frame 4/5: ✓ (720, 1280, 3)
  Frame 5/5: ✓ (720, 1280, 3)
[TEST] Camera test complete
```

---

### `run`
Run the card sorter to process cards.

**Usage:**
```bash
python3 mtg_sorter_cli.py run [OPTIONS]
```

**Options:**
- `--mode <price|color>` - Sorting mode (default: price)
- `--count <N>` - Number of cards to process (default: 10)
- `--threshold <USD>` - Price threshold in dollars (default: 0.25)
- `--mock` - Force mock mode (no hardware)
- `--no-mock` - Force hardware mode

**Examples:**

```bash
# Sort 10 cards by price (threshold $0.25)
python3 mtg_sorter_cli.py run

# Sort 20 cards by price with $1.00 threshold
python3 mtg_sorter_cli.py run --count 20 --threshold 1.00

# Sort by color instead of price
python3 mtg_sorter_cli.py run --mode color --count 15

# Test in mock mode
python3 mtg_sorter_cli.py run --mock --count 5
```

**Output:**
```
[SORTER] Starting in price mode...
[SORTER] Will process 10 card(s)
[SORTER] Threshold: $0.25
[SORTER] Press Ctrl+C to stop

[1/10] Waiting for card... DETECTED!
  [OCR] Reading card name... 'Lightning Bolt'
  [SCRYFALL] Looking up... $0.50 (R)
  [ROUTE] → price_bin
[SERVO] price_bin (ch 0) -> OPEN ... CLOSE

[2/10] Waiting for card... DETECTED!
  [OCR] Reading card name... 'Forest'
  [SCRYFALL] Looking up... $0.05 (G)
  [ROUTE] → combined_bin
[SERVO] combined_bin (ch 1) -> OPEN ... CLOSE

... (continues)

[SORTER] Complete! Processed 10 card(s)
```

**To stop early:** Press `Ctrl+C`

---

## Common Usage Patterns

### Initial Hardware Setup Test
```bash
# 1. Check I2C
python3 mtg_sorter_cli.py test-i2c

# 2. Test camera
python3 mtg_sorter_cli.py test-camera

# 3. Test all servos
python3 mtg_sorter_cli.py test-all
```

### Calibrate Individual Servos
```bash
# Test each bin to verify servo angles
python3 mtg_sorter_cli.py test-servo --bin price
python3 mtg_sorter_cli.py test-servo --bin combined
python3 mtg_sorter_cli.py test-servo --bin white_blue
python3 mtg_sorter_cli.py test-servo --bin black
python3 mtg_sorter_cli.py test-servo --bin red
python3 mtg_sorter_cli.py test-servo --bin green
```

### Production Sorting
```bash
# Sort 100 cards by price ($0.50 threshold)
python3 mtg_sorter_cli.py run --mode price --count 100 --threshold 0.50

# Sort by color (for organizing collection)
python3 mtg_sorter_cli.py run --mode color --count 50
```

### Troubleshooting
```bash
# Test in mock mode (no hardware required)
python3 mtg_sorter_cli.py test-all --mock
python3 mtg_sorter_cli.py run --mock --count 3

# Force hardware mode (even if not detected as Pi)
python3 mtg_sorter_cli.py test-servo --bin price --no-mock
```

---

## Mock Mode vs Hardware Mode

### Mock Mode (Default on non-Pi systems)
- No hardware required
- Prints simulated servo movements
- Useful for testing logic without hardware
- Enable with `--mock` flag

### Hardware Mode (Default on Raspberry Pi)
- Requires PCA9685 and servos connected
- Actually moves servos
- Requires camera for `run` command
- Enable with `--no-mock` flag

**Auto-detection:**
- On Raspberry Pi with hardware libraries: Hardware mode
- On other systems: Mock mode
- Override with `--mock` or `--no-mock`

---

## Exit Codes

- `0` - Success
- `1` - Error (check output for details)

---

## Tips for SSH Usage

### 1. Run in background with nohup:
```bash
nohup python3 mtg_sorter_cli.py run --count 100 > sorter.log 2>&1 &
```

### 2. Monitor progress:
```bash
tail -f sorter.log
```

### 3. Use screen/tmux for persistent sessions:
```bash
# Start screen session
screen -S sorter

# Run sorter
python3 mtg_sorter_cli.py run --count 100

# Detach: Ctrl+A, then D
# Reattach: screen -r sorter
```

### 4. Quick servo test loop:
```bash
# Test each servo 3 times
for bin in price combined white_blue black red green; do
  for i in 1 2 3; do
    echo "Test $i for $bin"
    python3 mtg_sorter_cli.py test-servo --bin $bin
    sleep 1
  done
done
```

---

## Troubleshooting

### "Camera failed to open"
```bash
# Check camera device
ls /dev/video*

# If camera is on different device:
# Edit mtg_sorter_cli.py and change:
# camera_device_index: int = 0  # Change to 1, 2, etc.
```

### "PCA9685 not found"
```bash
# Check I2C is enabled
sudo raspi-config
# Interface Options → I2C → Enable

# Reboot
sudo reboot

# Test again
python3 mtg_sorter_cli.py test-i2c
```

### "Permission denied" on I2C
```bash
# Add user to i2c group
sudo usermod -a -G i2c $USER

# Log out and back in, or:
newgrp i2c
```

### Servo angles wrong
Edit `mtg_sorter_cli.py` and adjust:
```python
pulse_open_us: int = 2000    # Increase for more rotation
pulse_close_us: int = 1000   # Decrease for less rotation
```

Test with:
```bash
python3 mtg_sorter_cli.py test-servo --bin price
```

---

## Comparison: CLI vs GUI

| Feature | CLI | GUI |
|---------|-----|-----|
| SSH Compatible | ✅ Yes | ❌ Requires X11 forwarding |
| Headless Operation | ✅ Yes | ❌ No |
| Interactive Testing | ✅ Command-based | ✅ Button-based |
| Real-time Status | ✅ Console output | ✅ Status label |
| Background Running | ✅ Easy with nohup | ❌ Difficult |
| Scripting | ✅ Easy | ❌ Not possible |
| Visual Feedback | ❌ Text only | ✅ GUI elements |

**Recommendation:** Use CLI for SSH/remote testing, GUI for local desktop use.

---

## Next Steps

1. **Test hardware:** Run through all test commands
2. **Calibrate servos:** Adjust pulse widths if needed
3. **Test sorting:** Run with `--count 5` first
4. **Production use:** Increase count and run in background

For GUI version, see `mtg_sorter_fixed.py` and run on desktop with display.
