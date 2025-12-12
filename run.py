#!/usr/bin/env python
"""
Simple standalone runner to test if the app starts without output buffering.
Run this if the normal runner shows no output.
"""
import sys
import os

# Force unbuffered mode
sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', buffering=1)

# Ensure PYTHONPATH includes src
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

print("=" * 60, flush=True)
print("Card Sorter - Unbuffered Launcher", flush=True)
print("=" * 60, flush=True)

try:
    from card_sorter.main import main
    print("[STARTUP] Importing main...", flush=True)
    print("[STARTUP] Starting application...", flush=True)
    main()
except Exception as e:
    print(f"[ERROR] {e}", flush=True)
    import traceback
    traceback.print_exc(file=sys.stdout)
