import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .actuate import ServoActuator
from .capture import CameraCapture
from .config_loader import load_config
from .gui import launch_gui
from .log_writer import CsvLogger
from .logger import get_logger, setup_logging
from .models import CardRecognitionResult
from .pricing import build_price_service
from .recognize import Recognizer
from .routing import Router
from .state import RuntimeState, StateStore

logger = get_logger(__name__)


class CardSorterApp:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = load_config(config_path)
        setup_logging(log_dir=Path(self.config.logging_dir).parent)
        logger.info("Initializing Card Sorter App")
        logger.info(f"mock_mode={self.config.mock_mode}")
        
        self.state_store = StateStore(Path(self.config.persistence_file))
        self.state = RuntimeState.from_config(self.config)
        self.state.__dict__.update(self.state_store.load())
        logger.info(f"Loaded state: mode={self.state.mode}, threshold=${self.state.price_threshold_usd:.2f}")

        # sync config with persisted state overrides
        self.config.price_threshold_usd = self.state.price_threshold_usd
        self.config.price_primary = self.state.price_source_primary
        self.config.price_fallback = self.state.price_source_fallback

        self.logger = CsvLogger(self.config.logging_dir)
        logger.info(f"CSV logging to {self.config.logging_dir}")
        
        mock_str = " (MOCK MODE)" if self.config.mock_mode else ""
        self.camera = CameraCapture(
            device_index=self.config.camera_device_index,
            resolution=tuple(self.config.camera_resolution),
            mock_mode=self.config.mock_mode
        )
        logger.info(f"Camera initialized: {self.config.camera_resolution[0]}x{self.config.camera_resolution[1]}{mock_str}")
        
        self.recognizer = Recognizer(
            model_path=self.config.recognition_model_path,
            label_map_path=self.config.recognition_label_map,
            card_index_path=self.config.recognition_card_index,
        )
        logger.info(f"Recognizer ready (model: {self.config.recognition_model_path})")
        
        self.price_service = build_price_service(
            primary_name=self.state.price_source_primary,
            fallback_name=self.state.price_source_fallback,
            ttl_hours=self.config.price_cache_ttl_hours,
        )
        logger.info(f"Price service: primary={self.state.price_source_primary}, fallback={self.state.price_source_fallback}")
        
        self.router = Router(config=self.config, disabled_bins=self.state.disabled_bins)
        logger.info(f"Router ready. Disabled bins: {self.state.disabled_bins or 'none'}")
        
        self.actuator = ServoActuator(
            channel_map=self.config.channel_map,
            angles=self.config.angles,
            address=self.config.servo_address,
            pwm_freq_hz=self.config.pwm_freq_hz,
            supply_voltage_v=self.config.supply_voltage_v,
            mock_mode=self.config.mock_mode,
        )
        logger.info(f"Servo actuator ready (PCA9685 @ 0x{self.config.servo_address:02x}){mock_str}")
        
        self._lock = threading.Lock()
        self._running = False

    def process_once(self) -> None:
        try:
            logger.info("--- Processing card ---")
            image_path = self.camera.capture()
            logger.debug(f"Captured image: {image_path}")
            
            recognition: CardRecognitionResult = self.recognizer.recognize(image_path)
            if recognition.name:
                logger.info(f"Recognized: {recognition.name} ({recognition.set_code}#{recognition.collector_number}) [conf={recognition.confidence:.2f}]")
            else:
                logger.warning(f"Unrecognized card [conf={recognition.confidence:.2f}]")

            price_quote = None
            if recognition.name:
                price_quote = self.price_service.get_price(
                    name=recognition.name,
                    set_code=recognition.set_code,
                    collector_number=recognition.collector_number,
                )
                if price_quote and price_quote.price_usd:
                    logger.info(f"Price: ${price_quote.price_usd:.2f} ({price_quote.source})")
                else:
                    logger.warning(f"No price found from {price_quote.source if price_quote else 'any source'}")

            price_usd = price_quote.price_usd if price_quote else None
            decision = self.router.route(card=recognition, price_usd=price_usd, mode=self.state.mode)
            logger.info(f"Routing: {decision.bin_name} ({decision.reason})")

            self.actuator.move(decision.bin_name, position="open")
            logger.debug(f"Servo actuation complete for {decision.bin_name}")

            flags = decision.flags[:]
            if price_quote and price_quote.price_usd is None:
                flags.append("unpriced")
            if price_quote is None:
                flags.append("no_price_lookup")

            self._bump_count(decision.bin_name)
            self.state.last_bin = decision.bin_name
            logger.info(f"Card {self.state.counts.get(decision.bin_name, 0)} → {decision.bin_name} (flags: {','.join(flags) if flags else 'none'})")

            self.logger.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "name": recognition.name,
                    "set_code": recognition.set_code,
                    "collector_number": recognition.collector_number,
                    "art_id": recognition.art_id,
                    "price_usd": price_usd,
                    "price_source": price_quote.source if price_quote else None,
                    "bin": decision.bin_name,
                    "flags": ";".join(flags),
                }
            )
            self._persist_state()
        except Exception as e:
            logger.error(f"Error processing card: {e}", exc_info=True)

    def process_loop(self, trigger_waiter: Callable[[], bool], stop_event: threading.Event) -> None:
        self._running = True
        logger.info("Starting processing loop")
        while not stop_event.is_set():
            if trigger_waiter():
                try:
                    self.process_once()
                except Exception as e:
                    logger.error(f"Loop error: {e}", exc_info=True)
                    time.sleep(0.1)
            else:
                time.sleep(0.05)
        logger.info("Processing loop stopped")
        self._running = False

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self.state.mode = mode
            logger.info(f"Mode changed to: {mode}")
            self._persist_state()

    def set_price_threshold(self, value: float) -> None:
        with self._lock:
            self.state.price_threshold_usd = value
            self.config.price_threshold_usd = value
            logger.info(f"Price threshold changed to: ${value:.2f}")
            self._persist_state()

    def set_price_sources(self, primary: str, fallback: str) -> None:
        with self._lock:
            self.state.price_source_primary = primary
            self.state.price_source_fallback = fallback
            self.price_service = build_price_service(
                primary_name=primary,
                fallback_name=fallback,
                ttl_hours=self.config.price_cache_ttl_hours,
            )
            logger.info(f"Price sources changed: primary={primary}, fallback={fallback}")
            self._persist_state()

    def toggle_bin(self, bin_name: str, enabled: bool) -> None:
        with self._lock:
            if not enabled:
                self.state.disabled_bins.add(bin_name)
                logger.warning(f"Bin disabled: {bin_name}")
            else:
                self.state.disabled_bins.discard(bin_name)
                logger.info(f"Bin enabled: {bin_name}")
            self.router.disabled_bins = self.state.disabled_bins
            self._persist_state()

    def test_bin(self, bin_name: str) -> None:
        print(f"[TEST] Moving servo for bin: {bin_name}", flush=True)
        logger.info(f"Testing bin: {bin_name}")
        self.actuator.move(bin_name, position="open")
        print(f"[TEST] Servo command sent for {bin_name}", flush=True)

    def _bump_count(self, bin_name: str) -> None:
        self.state.counts[bin_name] = self.state.counts.get(bin_name, 0) + 1

    def _persist_state(self) -> None:
        self.state_store.save(self.state.__dict__)

    def shutdown(self) -> None:
        logger.info("Shutting down Card Sorter")
        self.camera.release()
        self.actuator.release()
        logger.info("Shutdown complete")


def main() -> None:
    import sys
    import io
    
    # Force unbuffered output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    
    print("[START] Initializing...", flush=True)
    sys.stdout.flush()
    
    try:
        config_path = Path(__file__).resolve().parent.parent / "config" / "default_config.yaml"
        print(f"[START] Config path: {config_path}", flush=True)
        print(f"[START] Config exists: {config_path.exists()}", flush=True)
        
        setup_logging(log_dir=Path.cwd() / "logs")
        print("[START] Logging setup complete", flush=True)
        
        print("=" * 60, flush=True)
        print("Card Sorter Application Starting", flush=True)
        print("=" * 60, flush=True)
        
        logger.info("=" * 60)
        logger.info("Card Sorter Application Starting")
        logger.info("=" * 60)
        
        print("[START] Loading config...", flush=True)
        app = CardSorterApp(config_path)
        print(f"[START] mock_mode={app.config.mock_mode}", flush=True)
        print("[START] Config loaded, launching GUI...", flush=True)
        logger.info("Launching GUI...")
        
        launch_gui(app)
        
    except KeyboardInterrupt:
        print("[USER] Interrupted", flush=True)
        logger.info("Interrupted by user")
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        try:
            if 'app' in locals():
                print("[CLEANUP] Shutting down...", flush=True)
                app.shutdown()
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}", flush=True)


if __name__ == "__main__":
    main()
