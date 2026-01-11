#!/usr/bin/env python3
"""Apply fixes to mtg_sorter.py"""

import re

# Read the file
with open('mtg_sorter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Return both decision and rec from process_once
content = content.replace(
    '        print(decision)\n        return decision\n\n    def start_loop(self, on_update):',
    '        print(decision)\n        return decision, rec\n\n    def start_loop(self, on_update):'
)

# Fix 2: Update _loop to pass rec
content = content.replace(
    '    def _loop(self, on_update):\n        while not self._stop_event.is_set():\n            try:\n                decision = self.process_once()\n                on_update(decision)\n            except Exception as exc:\n                on_update(f"Error: {exc}")',
    '    def _loop(self, on_update):\n        while not self._stop_event.is_set():\n            try:\n                decision, rec = self.process_once()\n                on_update(decision, rec)\n            except Exception as exc:\n                on_update(f"Error: {exc}", None)'
)

# Fix 3: Update _on_update to accept rec and display card info
old_on_update = '''    def _on_update(self, msg):
        if isinstance(msg, RoutingDecision):
            self.status_var.set(f"{msg.bin_name} ({msg.reason})")
        else:
            self.status_var.set(str(msg))'''

new_on_update = '''    def _on_update(self, msg, rec=None):
        if isinstance(msg, RoutingDecision):
            self.status_var.set(f"{msg.bin_name} ({msg.reason})")
            # Update card info display with recognized card
            if rec and rec.name:
                self.ocr_text_var.set(rec.name)
                info_text = f"Name: {rec.name}\\nSet: {rec.set_code or 'N/A'}\\nCollector #: {rec.collector_number or 'N/A'}\\nConfidence: {rec.confidence:.2f}"
                if rec.colors:
                    info_text += f"\\nColors: {', '.join(rec.colors)}"
                self.card_info_text.config(state=tk.NORMAL)
                self.card_info_text.delete(1.0, tk.END)
                self.card_info_text.insert(1.0, info_text)
                self.card_info_text.config(state=tk.DISABLED)
            else:
                self.ocr_text_var.set("[No card detected]")
        else:
            self.status_var.set(str(msg))'''

content = content.replace(old_on_update, new_on_update)

# Write back
with open('mtg_sorter.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixes applied successfully!")
