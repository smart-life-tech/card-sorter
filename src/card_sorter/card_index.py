import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .models import CardMetadata


@dataclass
class CardIndex:
    records: Dict[str, CardMetadata]

    @classmethod
    def load(cls, path: Path) -> "CardIndex":
        data = json.loads(path.read_text(encoding="utf-8"))
        records: Dict[str, CardMetadata] = {}
        for row in data:
            meta = CardMetadata(
                name=row["name"],
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                art_id=row["art_id"],
                colors=row.get("colors", []),
                color_identity=row.get("color_identity", []),
            )
            records[meta.art_id] = meta
        return cls(records=records)

    def get_by_art_id(self, art_id: str) -> Optional[CardMetadata]:
        return self.records.get(art_id)
