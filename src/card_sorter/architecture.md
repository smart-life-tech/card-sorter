# Architecture Outline

## Pipeline
- capture: camera still at 1080p; push to queue
- recognize: offline model → {name, set_code, collector_number, art_id, confidence}; low confidence flagged
- price: cache both sources (scryfall, tcgplayer); choose primary then fallback; TTL 24h; unpriced flag
- route: apply mode (price/color/mixed), threshold, bin-disable map; resolve logical bin
- actuation: logical bin → PCA9685 channel/angles; open → dwell → close; retry limited; errors surfaced
- log: append to CSV (daily); fields: name, set, collector_number, art_id, price, source, bin, timestamp, flags
- gui: reads/writes state (mode, threshold, price source, bin enables); can trigger calibration/test per bin

## Modules (proposed)
- capture.py: Camera capture function/class
- recognize.py: wraps offline model
- pricing.py: fetch/cache prices from Scryfall/TCGplayer
- routing.py: applies rules to pick logical bin
- actuate.py: PCA9685 servo controller
- logging.py: CSV logger with daily rotation
- gui.py: Tkinter UI binding to state
- state.py: in-memory state + persistence to JSON
- main.py: orchestrates asyncio/threads for pipeline

## Data flow
capture → recognize → price → route → actuate → log → gui status update

## Concurrency
- Use asyncio or threads with queues; target 2–4s per card.
- Single actuation worker to avoid servo contention.

## Error handling
- Low confidence: one retry, then route to combined bin; flag.
- Disabled bin: reroute to combined bin; flag.
- Unpriced: combined bin; flag.
- Servo error: surface to GUI; pause or reroute to safe bin.

## Config
- YAML at config/default_config.yaml
- Runtime overrides saved to persistence file.

## Expansion
- Reserved PCA9685 channels 6–7 for future bins.
- Allow additional routing rules via config.
