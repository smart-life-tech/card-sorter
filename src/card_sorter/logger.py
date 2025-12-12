import logging
import sys
from pathlib import Path


def setup_logging(log_dir: Path | str = None, level: int = logging.INFO) -> logging.Logger:
    log_dir = Path(log_dir) if log_dir else Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("card_sorter")
    logger.setLevel(level)

    if not logger.handlers:
        # Console handler - unbuffered
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.flush_interval = 1  # Flush every message
        console_fmt = logging.Formatter("[%(asctime)s] [%(levelname)-8s] %(message)s", datefmt="%H:%M:%S")
        console_handler.setFormatter(console_fmt)
        logger.addHandler(console_handler)
        
        # Force unbuffered output
        logger.propagate = True

        # File handler
        log_file = log_dir / "app.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_fmt = logging.Formatter("[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s")
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "card_sorter") -> logging.Logger:
    return logging.getLogger(name)
