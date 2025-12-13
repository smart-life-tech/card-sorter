import json
from math import exp
from pathlib import Path
from typing import List, Optional

import numpy as np

try:  # pragma: no cover - optional heavy deps
    import onnxruntime as ort
    import cv2
except ImportError:  # pragma: no cover - optional heavy deps
    ort = None
    cv2 = None

from .card_index import CardIndex
from .logger import get_logger
from .models import CardMetadata, CardRecognitionResult


logger = get_logger(__name__)


class Recognizer:
    def __init__(self, model_path: Optional[Path], label_map_path: Optional[Path], card_index_path: Optional[Path]) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.label_map_path = Path(label_map_path) if label_map_path else None
        self.card_index_path = Path(card_index_path) if card_index_path else None

        self.session = self._load_session()
        self.label_map: List[str] = self._load_label_map()
        self.card_index: Optional[CardIndex] = self._load_index()

    def _load_session(self):
        if self.model_path and self.model_path.exists() and ort:
            return ort.InferenceSession(str(self.model_path))
        if not self.model_path:
            logger.warning("No recognition model path configured; running in recognition-disabled mode")
        elif not self.model_path.exists():
            logger.warning(f"Recognition model not found at {self.model_path}; running in recognition-disabled mode")
        elif ort is None:
            logger.warning("onnxruntime not installed; running in recognition-disabled mode")
        return None

    def _load_label_map(self) -> List[str]:
        if self.label_map_path and self.label_map_path.exists():
            data = json.loads(self.label_map_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                try:
                    # Convert mapping of index->art_id to ordered list by numeric key
                    items = sorted(data.items(), key=lambda kv: int(kv[0]))
                    return [v for _, v in items]
                except Exception:
                    return list(data.values())
            return []
        if self.label_map_path and not self.label_map_path.exists():
            logger.warning(f"Label map not found at {self.label_map_path}")
        return []

    def _load_index(self) -> Optional[CardIndex]:
        if self.card_index_path and self.card_index_path.exists():
            return CardIndex.load(self.card_index_path)
        if self.card_index_path and not self.card_index_path.exists():
            logger.warning(f"Card index not found at {self.card_index_path}")
        return None

    def recognize(self, image_path: Path) -> CardRecognitionResult:
        if not self.session or cv2 is None:
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.0,
                image_path=str(image_path),
            )

        try:
            input_tensor = self._preprocess(image_path)
            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]
            probs = self._softmax(logits)
            top_idx = int(np.argmax(probs))
            confidence = float(probs[top_idx])
            art_id = self._art_id_from_idx(top_idx)
            meta = self._meta_from_art(art_id)
            if meta:
                return CardRecognitionResult(
                    name=meta.name,
                    set_code=meta.set_code,
                    collector_number=meta.collector_number,
                    art_id=meta.art_id,
                    confidence=confidence,
                    colors=meta.colors,
                    color_identity=meta.color_identity,
                    image_path=str(image_path),
                )
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=art_id,
                confidence=confidence,
                colors=None,
                color_identity=None,
                image_path=str(image_path),
            )
        except Exception:
            return CardRecognitionResult(
                name=None,
                set_code=None,
                collector_number=None,
                art_id=None,
                confidence=0.0,
                image_path=str(image_path),
            )

    def _preprocess(self, image_path: Path) -> np.ndarray:
        img = cv2.imread(str(image_path))
        if img is None:
            raise RuntimeError("Failed to read image for recognition")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (224, 224))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # CHW
        img = np.expand_dims(img, axis=0)
        return img

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        m = np.max(logits)
        exps = np.exp(logits - m)
        return exps / np.sum(exps)

    def _art_id_from_idx(self, idx: int) -> Optional[str]:
        if 0 <= idx < len(self.label_map):
            return self.label_map[idx]
        return None

    def _meta_from_art(self, art_id: Optional[str]) -> Optional[CardMetadata]:
        if not art_id or not self.card_index:
            return None
        return self.card_index.get_by_art_id(art_id)
