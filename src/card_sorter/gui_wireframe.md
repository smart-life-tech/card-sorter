# GUI Wireframe Spec (text)

## Header
- Status badge: Ready / Working / Error
- Mode selector: Price | Color | Mixed (buttons)
- Price source toggle: Scryfall / TCGplayer

## Controls
- Price threshold slider + numeric field (default 0.25)
- Bin toggles: Price, Combined, W+U, B, R, G (disable → reroute to Combined)
- Test buttons per bin: moves servo open/close once
- Retry low-confidence toggle (on = one rescan)

## Main panel
- Last card summary: name, price, source, bin, flags (unrecognized, low_confidence, unpriced)
- Live counters: total processed, per-bin counts

## Footer
- Export CSV button (exports latest daily file)
- Settings saved toast/notice
- Error toasts for camera/servo/pricing failures

## Notes
- Touch-friendly sizing; run fullscreen on Pi display
- Persist settings on change to persistence file
- Keep it minimal; no camera preview required
