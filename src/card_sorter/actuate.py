import time
from typing import Dict

from .models import ServoAngles

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
except ImportError:  # pragma: no cover - hardware optional during dev
    board = None
    busio = None
    PCA9685 = None


class ServoActuator:
    def __init__(self, channel_map: Dict[str, int], angles: Dict[str, ServoAngles], address: int = 0x40, pwm_freq_hz: int = 50, supply_voltage_v: float = 5.5, mock_mode: bool = False) -> None:
        self.channel_map = channel_map
        self.angles = angles
        self.address = address
        self.pwm_freq_hz = pwm_freq_hz
        self.supply_voltage_v = supply_voltage_v
        self.mock_mode = mock_mode
        self._pca = None
        self._init_driver()

    def _init_driver(self) -> None:
        if self.mock_mode or PCA9685 is None:
            return
        i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(i2c, address=self.address)
        self._pca.frequency = self.pwm_freq_hz

    def _angle_to_duty(self, angle_deg: float) -> int:
        # Standard servo pulse: ~500-2500us over 0-180 deg
        min_pulse = 500
        max_pulse = 2500
        pulse = min_pulse + (max_pulse - min_pulse) * (angle_deg / 180.0)
        # PCA9685: 12-bit resolution over 20ms (for 50Hz), so 4096 steps for 20,000us
        duty = int((pulse / 20000.0) * 4095)
        return max(0, min(4095, duty))

    def move(self, bin_name: str, position: str = "open", dwell_s: float = 0.3) -> None:
        if self.mock_mode:
            print(f"[MOCK SERVO] Bin '{bin_name}' -> {position} (mock mode, no hardware)", flush=True)
            return
        if self._pca is None:
            return
        if bin_name not in self.channel_map or bin_name not in self.angles:
            return
        channel = self.channel_map[bin_name]
        angle = self.angles[bin_name].open_deg if position == "open" else self.angles[bin_name].closed_deg
        duty = self._angle_to_duty(angle)
        self._pca.channels[channel].duty_cycle = duty
        time.sleep(dwell_s)
        if position == "open":
            # close after dwell
            close_duty = self._angle_to_duty(self.angles[bin_name].closed_deg)
            self._pca.channels[channel].duty_cycle = close_duty

    def release(self) -> None:
        if self._pca:
            self._pca.deinit()
            self._pca = None
