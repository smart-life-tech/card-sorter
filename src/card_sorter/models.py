from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CardRecognitionResult:
    name: Optional[str]
    set_code: Optional[str]
    collector_number: Optional[str]
    art_id: Optional[str]
    confidence: float
    colors: Optional[List[str]] = None
    color_identity: Optional[List[str]] = None
    image_path: Optional[str] = None


@dataclass
class CardMetadata:
    name: str
    set_code: str
    collector_number: str
    art_id: str
    colors: List[str]
    color_identity: List[str]


@dataclass
class PriceQuote:
    price_usd: Optional[float]
    source: str
    fetched_at: datetime


@dataclass
class RoutingDecision:
    bin_name: str
    reason: str
    flags: List[str] = field(default_factory=list)


@dataclass
class ServoAngles:
    open_deg: float
    closed_deg: float


@dataclass
class AppConfig:
    mode: str
    price_threshold_usd: float
    price_primary: str
    price_fallback: str
    price_cache_ttl_hours: int
    logging_dir: str
    persistence_file: str
    recognition_model_path: Optional[str]
    recognition_label_map: Optional[str]
    recognition_card_index: Optional[str]
    camera_resolution: List[int]
    servo_address: int
    pwm_freq_hz: int
    supply_voltage_v: float
    channel_map: Dict[str, int]
    angles: Dict[str, ServoAngles]
    routing_rules: Dict[str, str]
