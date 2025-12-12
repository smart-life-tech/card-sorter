from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set

from .config_loader import load_state, save_state


@dataclass
class RuntimeState:
    mode: str
    price_threshold_usd: float
    price_source_primary: str
    price_source_fallback: str
    disabled_bins: Set[str] = field(default_factory=set)
    counts: Dict[str, int] = field(default_factory=dict)
    last_bin: str | None = None

    @classmethod
    def from_config(cls, config) -> "RuntimeState":
        return cls(
            mode=config.mode,
            price_threshold_usd=config.price_threshold_usd,
            price_source_primary=config.price_primary,
            price_source_fallback=config.price_fallback,
            disabled_bins=set(),
            counts={},
            last_bin=None,
        )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Dict:
        return load_state(self.path)

    def save(self, state: Dict) -> None:
        save_state(self.path, state)
