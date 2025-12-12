import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional


class CsvLogger:
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _file_for_today(self) -> Path:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return self.base_dir / f"cards_{today}.csv"

    def append(self, record: Dict[str, Optional[str]]) -> None:
        path = self._file_for_today()
        is_new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp",
                "name",
                "set_code",
                "collector_number",
                "art_id",
                "price_usd",
                "price_source",
                "bin",
                "flags",
            ])
            if is_new:
                writer.writeheader()
            writer.writerow(record)

    def export_latest(self) -> Path:
        path = self._file_for_today()
        if not path.exists():
            path.touch()
        return path
