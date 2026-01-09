# MTG Card Sorter - Wiring Guide (PCA9685)

Complete wiring reference for Raspberry Pi 4, PCA9685 16-channel servo driver, USB webcam, 6 servo bins, and power distribution.

## Table of Contents
1. [Component List](#component-list)
2. [Power Requirements](#power-requirements)
3. [Raspberry Pi GPIO Pinout](#raspberry-pi-gpio-pinout)
4. [Servo Connections](#servo-connections)
5. [Camera Connection](#camera-connection)
6. [Wiring Diagram](#wiring-diagram)
7. [Assembly Checklist](#assembly-checklist)

---

## Component List

| Component | Quantity | Notes |
|-----------|----------|-------|
| Raspberry Pi 4 (2GB+) | 1 | Running the sorter application |
| USB Webcam (1080p+) | 1 | Card capture; any USB 2.0/3.0 compatible |
| PCA9685 16-Channel Servo Driver | 1 | I2C-based PWM controller; default address 0x40 |
| MG90S Metal Servo | 6 | Servo motors for bin actuation; 5-6V rated |
| Micro Servo | 0-10 | Optional future expansion (uses channels 6-15 on PCA9685) |
| USB Power Supply (5V/3A+) | 1 | Raspberry Pi power |
| Servo Power Supply (5-6V) | 1 | Dedicated power for all servos; 2A+ recommended |
| Jumper Wires (M/F, M/M) | ~20 | I2C (SDA/SCL), servo signal, power, ground |
| USB Cable (A→Micro B) | 1 | Pi ↔ power supply |
| Breadboard (optional) | 1 | I2C and power distribution |

---

## Power Requirements

### Raspberry Pi
- **Input**: 5V DC via USB-C
- **Current**: ~600 mA (idle) to 1.2 A (full load)
- **Recommended PSU**: 5V/3A or 5V/4A

### Servos (MG90S)
- **Voltage**: 4.8–6.0 V (nominal 5.5 V with battery voltage sag)
- **Stall Current**: ~900 mA per servo (peak)
- **No-Load Current**: ~50 mA per servo (idle)
- **Total for 6 servos**: ~2–5 A continuous (depends on load/movement)
- **Recommended PSU**: 5.5 V / 2 A minimum; 5.5 V / 3 A preferred

### Ground Connection
- **Critical**: Connect Pi GND to servo PSU GND (common ground reference)
- The PWM signal goes from GPIO pin → servo signal line; ground must be shared

---

## Raspberry Pi I2C Connection

### Overview
```
Pi 4 Header (GPIO pin numbers in BCM naming):

Pin 1  (3.3V)    ████  Pin 2  (5V)
Pin 3  (GPIO 2)  ████  Pin 4  (5V)      ↑ I2C SDA (data line)
Pin 5  (GPIO 3)  ████  Pin 6  (GND)     ↑ I2C SCL (clock line)
Pin 7  (GPIO 4)  ████  Pin 8  (GPIO 14)
Pin 9  (GND)     ████  Pin 10 (GPIO 15)
...
```

### I2C Pins (for PCA9685)

| Signal | GPIO | Physical Pin | PCA9685 Pin | Description |
|--------|------|--------------|-------------|-------------|
| **SDA** | GPIO 2 | Pin 3 | SDA | I2C Data line (bidirectional) |
| **SCL** | GPIO 3 | Pin 5 | SCL | I2C Clock line (bidirectional) |
| **GND** | GND | Pin 6, 9, 14, 20, 30, 34, 39 | GND | Ground reference (common with servo PSU) |
| **VCC** | 5V (opt.) | Pin 2, 4 | VCC | Power to PCA9685 (optional; can use servo PSU 5V) |

### PCA9685 Channel Assignments

| Channel | Purpose | Pulse Open | Pulse Close | Notes |
|---------|---------|------------|-------------|-------|
| `Ch0` | Hopper / feeder servo | 2000 µs | 1000 µs | Channel 0 — card hopper (feed) |
| `Ch1` | `price_bin` | 2000 µs | 1000 µs | |
| `Ch2` | `combined_bin` | 2000 µs | 1000 µs | |
| `Ch3` | `white_blue_bin` | 2000 µs | 1000 µs | |
| `Ch4` | `black_bin` | 2000 µs | 1000 µs | |
| `Ch5` | `red_bin` | 2000 µs | 1000 µs | |
| `Ch6` | `green_bin` | 2000 µs | 1000 µs | |
| `Ch7` | `extra_bin` (optional) | 2000 µs | 1000 µs | Optional 7th bin if wired |
| **Reserved** | 8–15 | — | — | Available for future expansion |

### I2C Address
- **Default**: 0x40 (configurable via address pins on PCA9685)
- To change: solder jumpers on PCA9685 board (A0, A1, A2)

---

## Servo Connections

### Signal Connection (PCA9685 → Servo)
Each servo has three wires:
- **Orange/Yellow** (Signal) → PCA9685 channel pin (CH0–CH5)
- **Red** (Power) → +5–6V from servo PSU
- **Brown/Black** (Ground) → Common ground (GND)

### Example: price_bin Servo (Channel 0)
```
PCA9685 Channel 0 PWM output ────── Orange/Yellow wire (Signal)
Servo PSU +5.5V ──────────────────── Red wire (Power)
Servo PSU GND (common with Pi GND) - Brown/Black wire (Ground)
                                       ↓
                              MG90S Servo Motor
```

### Example Wiring for Hopper + 7 Bins

| Servo | PCA9685 Channel | Signal (O/Y) | Power (Red) | Ground (Br/Blk) |
|-------|------------------|--------------|-------------|-----------------|
| hopper (feeder) | Ch0 | Ch0 | +5.5V PSU | GND Rail |
| price | Ch1 | Ch1 | +5.5V PSU | GND Rail |
| combined | Ch2 | Ch2 | +5.5V PSU | GND Rail |
| white_blue | Ch3 | Ch3 | +5.5V PSU | GND Rail |
| black | Ch4 | Ch4 | +5.5V PSU | GND Rail |
| red | Ch5 | Ch5 | +5.5V PSU | GND Rail |
| green | Ch6 | Ch6 | +5.5V PSU | GND Rail |
| extra | Ch7 | Ch7 | +5.5V PSU | GND Rail |

### Ground Rail
- Connect all servo **brown/black** wires to a common **GND rail**
- Connect PCA9685 **GND** to the same rail
- Connect that rail to a **GND pin on the Pi** (e.g., Pin 6, 9, 14, 20, etc.)
- **Critical**: All devices (Pi, PCA9685, servo PSU) must share common ground

---

## Camera Connection

### USB Webcam
- **Connection**: USB A→USB Micro/USB-C (depending on camera)
- **Port**: Any USB 2.0 or 3.0 port on Raspberry Pi
- **Device Index**: `/dev/video0` (usually; configure in app if multiple cameras)
- **Power**: Drawn from Pi's USB bus (5V)
- **Current**: ~200–500 mA depending on resolution/frame rate

### Camera Framing
- Position camera to capture card front-on
- Adjust lighting to minimize glare on card surface
- The app warps the largest detected 4-corner contour (card outline) to a standard 720×1024 px image
- OCR reads the **top 8–22%** of warped image (name ROI)

---

## Wiring Diagram

### Simplified Block Diagram
```─┐
│                  Raspberry Pi 4 (5V/3A PSU)                     │
│                                                                  │
│  GPIO 2 (SDA) ──→ I2C Data line                                │
│  GPIO 3 (SCL) ──→ I2C Clock line                               │
│         ↓                     ↓                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  PCA9685 I2C Servo Driver (0x40)                   │       │
│  │  Ch0–5 (6× PWM outputs to servos)                  │       │
│  │  Ch6–15 (reserved for expansion)                   │       │
│  └─────────────────────────────────────────────────────┘       │
│   ↓ ↓ ↓ ↓ ↓ ↓                                                    │
│  Ch0 Ch1 Ch2 Ch3 Ch4 Ch5                                        │
│   ↓   ↓   ↓   ↓   ↓   ↓                                          │
│ [S0] [S1] [S2] [S3] [S4] [S5]                                   │
│ price combined white black red green                            │
│                                                                  │
│  USB Port → [USB Webcam]                                        │
└──────────────────────────────────────────────────────────────────┘
                           ↓ (GND common)
    ┌─────────────────────────────────────────┐
    │  Servo Power Supply (5.5V / 2–3A)      │
    │  ├─ +5.5V ──→ All 6 servo red wires    │
    │  └─ GND ────→ All 6 servo black wires  │
    │              & Pi GPIO GND              │
    │              & PCA9685 GND              │
    └─────────────────────────────────────────┘
```

### Detailed Pin Connection Table

| Device | Pin | Type | Connection | Notes |
|--------|-----|------|-----------|-------|
| **Pi USB-C** | 5V, GND | Power In | 5V/3A PSU | Pi power |
| **Pi GPIO 2** | Pin 3 | I2C | PCA9685 SDA | I2C data line (pull-up optional) |
| **Pi GPIO 3** | Pin 5 | I2C | PCA9685 SCL | I2C clock line (pull-up optional) |
| **Pi GND** | Pin 6/9/14/20/30/34/39 | Ground | PCA9685 GND, servo PSU GND, all servo black | Common reference |
| **PCA9685 Ch0–Ch7** | Ch0–Ch7 | PWM Out | Servo signal wires (orange/yellow) | hopper (Ch0) + bins Ch1–Ch7 |
| **PCA9685 VCC** | VCC | Power | +5.5V from servo PSU (optional) | Can also use Pi 5V |
| **PCA9685 GND** | GND | Ground | Common GND rail | Must connect to Pi GND |
| **Servo PSU** | 5.5V, GND | Power Out | All servo red wires & PCA9685 | 2–3A minimum |
| **Webcam USB** | USB 2.0/3.0 | Data+Power | Any USB port on Pi | /dev/video0
| **Servo PSU** | 5.5V, GND | Power Out | All servo power & ground | 2–3A minimum |

---

## Assembly Checklist

- [ ] **Power P+ servo PSU ready (separate from Pi PSU)
  - [ ] All PSUs unplugged before assembly

- [ ] **I2C Setup**
  - [ ] Pi GPIO 2 (SDA, Pin 3) and GPIO 3 (SCL, Pin 5) enabled and available
  - [ ] PCA9685 address confirmed (default 0x40; check solder jumpers if changed)
  - [ ] I2C pull-up resistors checked (often included on PCA9685 board)

- [ ] **PCA9685 Wiring**
  - [ ] PCA9685 SDA connected to Pi GPIO 2 (Pin 3)
  - [ ] PCA9685 SCL connected to Pi GPIO 3 (Pin 5)
  - [ ] PCA9685 GND connected to common ground rail
  - [ ] PCA9685 VCC connected to +5.5V from servo PSU (or Pi 5V)

- [ ] **Servo Wiring**
  - [ ] 6× servo signal wires (orange/yellow) connected to correct PCA9685 channels (Ch0–Ch5)
  - [ ] 6× servo power wires (red) connected to +5.5V rail
  - [ ] 6× servo ground wires (brown/black) connected to ground rail
  - [ ] Common ground rail connected to Pi GPIO GND and PCA9685 GND
  - [ ] All connections secure (no loose strands)

- [ ] **Camera**
  - [ ] USB webcam connected to any Pi USB port
  - [ ] Camera positioned and focused on card drop zone
  - [ ] Lighting set up to minimize glare

- [ ] **Software**
  - [ ] `mtg_sorter.py` downloaded/updated (PCA9685 version)
  - [ ] Python packages installed: `opencv-python`, `pytesseract`, `requests`, `adafruit-circuitpython-pca9685`, `adafruit-blinka`
  - [ ] Tesseract OCR installed on Pi: `sudo apt-get install tesseract-ocr`
  - [ ] I2C enabled on Pi: `sudo raspi-config` → Interfacing Options → I2C

- [ ] **Testing**
  - [ ] Pi boots normally with all hardware connected
  - [ ] I2C device detected: `i2cdetect -y 1` should show `0x40`
- [ PCA9685 Not Detected
```bash
# Test I2C connection
i2cdetect -y 1
# Should show address 0x40 (or custom address if changed)
```
- Verify I2C enabled: `raspi-config` → Interfacing Options → I2C
- Check SDA/SCL wires securely connected to Pi pins 3 and 5
- Try different I2C address if board has address jumpers soldered
- Check for 4.7 kΩ pull-up resistors on SDA/SCL (often included on PCA9685 board)

### Servo Not Responding
- Verify PCA9685 address in `mtg_sorter.py` matches hardware: `ServoConfig.pca_address = 0x40`
- Check channel number matches `ServoConfig` (0–5 for 6 bins)
- Verify power supply delivering 5–6V to servo PSU **and** PCA9685
- Test with manual `i2cset` command to move servo:
  ```bash
  i2cset -y 1 0x40 0x08 0x0F 0x07  # Set channel 0 to ~2000 µs
  ```
- Swap servo to different channel to rule out hardware defect

### Camera Not Detected
- Verify USB connection: `lsusb | grep -i video`
- Check device index (try `/dev/video0`, `/dev/video1`, etc.)
- Update `capture_resolution` if camera doesn't support 1280×720

### OCR Returns Empty/Incorrect Text
- Check name ROI bounds in `AppConfig.name_roi` (default: `0.08, 0.08, 0.92, 0.22`)
- Improve lighting and camera focus
- Try adjusting Tesseract config in `ocr_name_from_image()`
Configuration Reference

If you need to **change PCA9685 channels or pulse widths**, edit `ServoConfig` in `mtg_sorter.py`:

```python
@dataclass
class ServoConfig:
    # PCA9685 channel assignments (0-15)
    price_bin: int = 0           # ← Change channel if needed
    combined_bin: int = 1        # ← Change channel if needed
    white_blue_bin: int = 2      # ← Change channel if needed
    black_bin: int = 3           # ← Change channel if needed
    red_bin: int = 4             # ← Change channel if needed
    green_bin: int = 5           # ← Change channel if needed
    
    # Servo pulse widths (in microseconds)
    pulse_open_us: int = 2000    # ~90 degrees (typical)
    pulse_close_us: int = 1000   # ~0 degrees (typical)
    
    # PCA9685 I2C address (default 0x40)
    pca_address: int = 0x40      # Change if solder jumpers changed
```

### Calibrating Servo Angles
If your servos don't open/close to the angles you want:
1. Adjust `pulse_open_us` and `pulse_close_us` in `ServoConfig`
2. Typical servo range: **1000 µs (0°) to 2000 µs (90°)**
3. Find the microseconds needed for your bin mechanism
4. Test in GUI with "Test" buttons to verify before full runeparate power and signal wires if running long distances

### Scryfall Lookup Fails
- Test network: `ping -c 1 api.scryfall.com`
- Check if card name is exact match (e.g., "Lightning Bolt", not "lightning bolt")
- Verify `pytesseract` is extracting clean text

---

## Pin Configuration Reference

If you need to **change GPIO pins**, edit `ServoConfig` in `mtg_sorter.py`:

```python
@dataclass
class ServoConfig:
    price_bin: int = 17          # ← Change this
    combined_bin: int = 27       # ← Change this
    white_blue_bin: int = 22     # ← Change this
    black_bin: int = 23          # ← Change this
    red_bin: int = 24            # ← Change this
    green_bin: int = 25          # ← Change this
    open_dc: float = 7.5         # PWM duty cycle (%) for servo "open"
    close_dc: float = 5.0        # PWM duty cycle (%) for servo "close"
    freq_hz: int = 50            # PWM frequency (Hz)
```

---

## Safety Notes

⚠️ **Always**:
- Power down Pi and servos before rewiring
- Double-check polarity (GND = black, Power = red)
- Use a separate PSU for servos if total current exceeds 1.5A
- Never exceed 3.3V or 5V on GPIO pins (servos are 5V-safe; PWM signal is 3.3V)
- Keep power and signal wires separated if possible to reduce noise

---

## Next Steps

1. Wire up according to the pinout table above
2. Power on Pi and verify no smoke/sparks
3. Run `mtg_sorter.py` and test each bin with the GUI "Test" buttons
4. Adjust servo angles if needed: modify `open_dc` and `close_dc` in `ServoConfig`
5. Calibrate camera framing and OCR ROI for your setup
6. Deploy and enjoy!
