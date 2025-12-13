import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Any

from .models import CardMetadata


@dataclass
class CardIndex:
    records: Dict[str, CardMetadata]

    @classmethod
    def load(cls, path: Path) -> "CardIndex":
        raw = json.loads(path.read_text(encoding="utf-8"))
        records: Dict[str, CardMetadata] = {}

        def coerce_row(art_id: str, row: Dict[str, Any]) -> None:
            meta = CardMetadata(
                name=row.get("name"),
                set_code=row.get("set_code") or row.get("set"),
                collector_number=row.get("collector_number"),
                art_id=art_id,
                colors=row.get("colors", []),
                color_identity=row.get("color_identity", row.get("colors", [])),
            )
            records[meta.art_id] = meta

        if isinstance(raw, list):
            for row in raw:
                art_id = row.get("art_id") or row.get("id")
                if not art_id:
                    continue
                coerce_row(art_id, row)
        elif isinstance(raw, dict):
            for art_id, row in raw.items():
                if isinstance(row, dict):
                    coerce_row(art_id, row)

        return cls(records=records)

    def get_by_art_id(self, art_id: str) -> Optional[CardMetadata]:
        return self.records.get(art_id)
