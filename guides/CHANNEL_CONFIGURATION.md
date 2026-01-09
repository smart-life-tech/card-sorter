# PCA9685 Channel Configuration

Updated servo channel assignments to match your hardware setup.

---

## Your Hardware Setup

- **Channel 0**: Card hopper/dispenser servo
- **Channels 1-7**: Sorting bins

---

## Channel Assignments

| Channel | Function | Description |
|---------|----------|-------------|
| **0** | `hopper` | Card hopper/dispenser servo - feeds cards into the system |
| **1** | `price_bin` | High-value cards (above threshold) |
| **2** | `combined_bin` | Multi-color cards or low-value cards |
| **3** | `white_blue_bin` | White or Blue mono-color cards |
| **4** | `black_bin` | Black mono-color cards |
| **5** | `red_bin` | Red mono-color cards |
| **6** | `green_bin` | Green mono-color cards |
| **7** | `extra_bin` | Reserved for future use |
| 8-15 | (unused) | Available for expansion |

---

## Updated Files

Both sorter versions have been updated with the new channel configuration:

### 1. `mtg_sorter_fixed.py` (GUI version)
```python
@dataclass
class ServoConfig:
    hopper: int = 0              # Card hopper/dispenser servo
    price_bin: int = 1           # High-value cards bin
    combined_bin: int = 2        # Multi-color/low-value cards bin
    white_blue_bin: int = 3      # White/Blue mono-color bin
    black_bin: int = 4           # Black mono-color bin
    red_bin: int = 5             # Red mono-color bin
    green_bin: int = 6           # Green mono-color bin
    extra_bin: int = 7           # Extra bin (future use)
    pulse_open_us: int = 2000    # ~90 degrees
    pulse_close_us: int = 1000   # ~0 degrees
    hopper_dispense_us: int = 1500  # Hopper dispense position
    hopper_rest_us: int = 1000      # Hopper rest position
    pca_address: int = 0x40
```

### 2. `mtg_sorter_cli.py` (CLI version)
Same configuration as above.

---

## Testing Your Setup

### Test Individual Bins

```bash
# Test price bin (channel 1)
python3 mtg_sorter_cli.py test-servo --bin price

# Test combined bin (channel 2)
python3 mtg_sorter_cli.py test-servo --bin combined

# Test white/blue bin (channel 3)
python3 mtg_sorter_cli.py test-servo --bin white_blue

# Test black bin (channel 4)
python3 mtg_sorter_cli.py test-servo --bin black

# Test red bin (channel 5)
python3 mtg_sorter_cli.py test-servo --bin red

# Test green bin (channel 6)
python3 mtg_sorter_cli.py test-servo --bin green
```

### Test All Bins at Once

```bash
python3 mtg_sorter_cli.py test-all
```

This will test channels 1-6 in sequence (skipping channel 0 hopper).

---

## Hopper Control

The hopper servo (channel 0) is not currently integrated into the automatic sorting workflow, but you can control it manually if needed.

### Adding Hopper Control

If you want to add automatic card dispensing from the hopper, you can add a function like this:

```python
def dispense_card(pca, servo_cfg, mock: bool):
    """Dispense one card from the hopper"""
    if mock or pca is None:
        print(f"[HOPPER] Dispensing card (ch {servo_cfg.hopper})")
        time.sleep(0.5)
        return
    
    # Move to dispense position
    dispense_val = int(servo_cfg.hopper_dispense_us * 4096 / 20000.0)
    rest_val = int(servo_cfg.hopper_rest_us * 4096 / 20000.0)
    
    try:
        print(f"[HOPPER] Dispensing card...")
        pca.channels[servo_cfg.hopper].duty_cycle = dispense_val
        time.sleep(0.3)  # Wait for card to drop
        pca.channels[servo_cfg.hopper].duty_cycle = rest_val
        time.sleep(0.2)  # Wait for servo to return
    except Exception as e:
        print(f"[ERROR] Hopper dispense failed: {e}")
```

Then call this before each card detection cycle in the `run_sorter()` function.

---

## Pulse Width Settings

### Bin Servos (Channels 1-7)
- **Open**: 2000µs (~90 degrees) - Gate opens to let card through
- **Close**: 1000µs (~0 degrees) - Gate closes to block cards

### Hopper Servo (Channel 0)
- **Dispense**: 1500µs (~45 degrees) - Position to release one card
- **Rest**: 1000µs (~0 degrees) - Holding position

**Note**: You may need to adjust these values based on your specific servo models and mechanical setup.

---

## Calibration

If servos don't move to the correct positions:

1. **Test each servo individually** to see current behavior
2. **Adjust pulse widths** in `ServoConfig`:
   - Increase `pulse_open_us` for more rotation
   - Decrease `pulse_close_us` for less rotation
3. **Re-test** until gates open/close properly

Example adjustments:
```python
pulse_open_us: int = 2200    # More open (increase by 100-200µs)
pulse_close_us: int = 900     # More closed (decrease by 100µs)
```

---

## Wiring Verification

Ensure your servos are connected to the correct PCA9685 channels:

```
PCA9685 Board:
┌─────────────────────────────────┐
│ CH0  CH1  CH2  CH3  CH4  CH5   │
│  │    │    │    │    │    │    │
│  ↓    ↓    ↓    ↓    ↓    ↓    │
│ Hop  Pri  Com  W/B  Blk  Red   │
│                                 │
│ CH6  CH7  CH8  CH9  ...  CH15  │
│  │    │                         │
│  ↓    ↓                         │
│ Grn  Ext                        │
└─────────────────────────────────┘

Legend:
Hop = Hopper
Pri = Price bin
Com = Combined bin
W/B = White/Blue bin
Blk = Black bin
Red = Red bin
Grn = Green bin
Ext = Extra bin
```

---

## Summary

✅ **Channel 0** reserved for hopper (not used in current sorting logic)
✅ **Channels 1-6** mapped to sorting bins
✅ **Channel 7** available for future expansion
✅ Both GUI and CLI versions updated
✅ Ready to test with your hardware!

Test your setup with:
```bash
python3 mtg_sorter_cli.py test-all
