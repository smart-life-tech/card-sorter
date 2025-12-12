from pathlib import Path
from typing import Optional, Tuple

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None


class CameraCapture:
    def __init__(self, device_index: int = 0, resolution: Tuple[int, int] = (1920, 1080), output_dir: Path | str = "captures") -> None:
        self.device_index = device_index
        self.resolution = resolution
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._cap: Optional["cv2.VideoCapture"] = None

    def _ensure_camera(self) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV is required for camera capture but is not installed.")
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.device_index)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        if not self._cap.isOpened():
            raise RuntimeError("Camera failed to open.")

    def capture(self, filename: Optional[str] = None) -> Path:
        self._ensure_camera()
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Camera read failed.")
        if filename is None:
            filename = "card.jpg"
        path = self.output_dir / filename
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError("Failed to write captured image.")
        return path

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
