import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # avoid circular import at runtime
    from .main import CardSorterApp


class SorterGUI:
    def __init__(self, app: "CardSorterApp", trigger_waiter: Optional[Callable[[], bool]] = None) -> None:
        self.app = app
        self.trigger_waiter = trigger_waiter or self._default_trigger
        self.root = tk.Tk()
        self.root.title("Card Sorter")
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None

        self.mode_var = tk.StringVar(value=self.app.state.mode)
        self.price_var = tk.DoubleVar(value=self.app.state.price_threshold_usd)
        self.source_var = tk.StringVar(value=self.app.state.price_source_primary)

        self.status_var = tk.StringVar(value="Ready")
        self.last_bin_var = tk.StringVar(value="-")
        self.counts_var = tk.StringVar(value="{}")

        self._build_layout()
        self._schedule_status_update()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Mode buttons
        ttk.Label(frame, text="Mode").grid(row=0, column=0, sticky="w")
        for idx, mode in enumerate(["price", "color", "mixed"]):
            ttk.Radiobutton(frame, text=mode.capitalize(), variable=self.mode_var, value=mode, command=self._on_mode).grid(row=1, column=idx, sticky="w")

        # Price threshold
        ttk.Label(frame, text="Price threshold ($)").grid(row=2, column=0, sticky="w")
        ttk.Scale(frame, from_=0.0, to=5.0, orient="horizontal", variable=self.price_var, command=lambda _: self._on_price()).grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Entry(frame, textvariable=self.price_var, width=8).grid(row=3, column=3, sticky="w")

        # Price source
        ttk.Label(frame, text="Price source").grid(row=4, column=0, sticky="w")
        tk.OptionMenu(frame, self.source_var, self.source_var.get(), "scryfall", "tcgplayer").grid(row=5, column=0, sticky="w")
        self.source_var.trace_add("write", lambda *_: self._on_source())

        # Bin toggles and tests
        ttk.Label(frame, text="Bins").grid(row=6, column=0, sticky="w")
        bins = [
            ("price_bin", "Price"),
            ("combined_bin", "Combined"),
            ("white_blue_bin", "W+U"),
            ("black_bin", "B"),
            ("red_bin", "R"),
            ("green_bin", "G"),
        ]
        for i, (key, label) in enumerate(bins):
            row = 7 + i
            var = tk.BooleanVar(value=key not in self.app.state.disabled_bins)
            chk = ttk.Checkbutton(frame, text=label, variable=var, command=lambda k=key, v=var: self._on_bin_toggle(k, v.get()))
            chk.grid(row=row, column=0, sticky="w")
            ttk.Button(frame, text="Test", command=lambda k=key: self.app.test_bin(k)).grid(row=row, column=1, sticky="w")

        # Controls
        ttk.Button(frame, text="Start", command=self.start_processing).grid(row=20, column=0, pady=5, sticky="w")
        ttk.Button(frame, text="Stop", command=self.stop_processing).grid(row=20, column=1, pady=5, sticky="w")

        # Status
        ttk.Label(frame, textvariable=self.status_var).grid(row=21, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Last bin:").grid(row=22, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.last_bin_var).grid(row=22, column=1, sticky="w")
        ttk.Label(frame, text="Counts:").grid(row=23, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.counts_var).grid(row=23, column=1, sticky="w")

    def _on_mode(self) -> None:
        self.app.set_mode(self.mode_var.get())

    def _on_price(self) -> None:
        try:
            self.app.set_price_threshold(float(self.price_var.get()))
        except ValueError:
            pass

    def _on_source(self, *_args) -> None:
        primary = self.source_var.get()
        fallback = "tcgplayer" if primary == "scryfall" else "scryfall"
        self.app.set_price_sources(primary, fallback)

    def _on_bin_toggle(self, bin_name: str, enabled: bool) -> None:
        self.app.toggle_bin(bin_name, enabled)

    def _default_trigger(self) -> bool:
        time.sleep(0.1)
        return False  # Don't auto-process; wait for user to click Start

    def start_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.worker = threading.Thread(target=self.app.process_loop, args=(self.trigger_waiter, self.stop_event), daemon=True)
        self.worker.start()
        self.status_var.set("Processing")

    def stop_processing(self) -> None:
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=0.1)
        self.status_var.set("Stopped")

    def _schedule_status_update(self) -> None:
        self.counts_var.set(str(self.app.state.counts))
        self.last_bin_var.set(self.app.state.last_bin or "-")
        self.root.after(500, self._schedule_status_update)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        self.stop_processing()
        self.root.destroy()


def launch_gui(app: "CardSorterApp", trigger_waiter: Optional[Callable[[], bool]] = None) -> None:
    gui = SorterGUI(app, trigger_waiter=trigger_waiter)
    gui.run()
