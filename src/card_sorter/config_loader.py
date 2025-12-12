import json
from pathlib import Path
from typing import Any, Dict

import yaml

from .models import AppConfig, ServoAngles


def _coerce_angles(raw_angles: Dict[str, Dict[str, float]]) -> Dict[str, ServoAngles]:
    return {name: ServoAngles(open_deg=vals["open_deg"], closed_deg=vals["closed_deg"]) for name, vals in raw_angles.items()}


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    app = raw["app"]
    hardware = raw["hardware"]
    recognition = raw.get("recognition", {})
    servo_driver = hardware["servo_driver"]
    routing = raw["routing"]

    return AppConfig(
        mode=app["mode"],
        mock_mode=app.get("mock_mode", False),
        price_threshold_usd=float(app["price_threshold_usd"]),
        price_primary=app["price_sources"]["primary"],
        price_fallback=app["price_sources"]["fallback"],
        price_cache_ttl_hours=int(app["price_sources"]["cache_ttl_hours"]),
        logging_dir=app["logging"]["csv_dir"],
        persistence_file=app["persistence_file"],
        recognition_model_path=recognition.get("model_path"),
        recognition_label_map=recognition.get("label_map_path"),
        recognition_card_index=recognition.get("card_index_path"),
        camera_resolution=list(hardware["camera"]["resolution"]),
        camera_device_index=int(hardware["camera"].get("device_index", 0)),
        servo_address=int(servo_driver["address"], 0) if isinstance(servo_driver["address"], str) else int(servo_driver["address"]),
        pwm_freq_hz=int(servo_driver["pwm_freq_hz"]),
        supply_voltage_v=float(servo_driver["supply_voltage_v"]),
        channel_map=servo_driver["channel_map"],
        angles=_coerce_angles(servo_driver["angles"]),
        routing_rules=routing,
    )


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = dict(state)
    if "disabled_bins" in serializable and isinstance(serializable["disabled_bins"], set):
        serializable["disabled_bins"] = list(serializable["disabled_bins"])
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "disabled_bins" in data and isinstance(data["disabled_bins"], list):
        data["disabled_bins"] = set(data["disabled_bins"])
    return data
