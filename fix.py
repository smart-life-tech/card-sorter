import json
import requests
from tqdm import tqdm
from pathlib import Path

OUTPUT_DIR = Path("models")
OUTPUT_DIR.mkdir(exist_ok=True)

CARD_INDEX_PATH = OUTPUT_DIR / "card_index.json"
LABEL_MAP_PATH = OUTPUT_DIR / "label_map.json"


def download_scryfall_bulk():
    print("Downloading Scryfall bulk metadata...")
    bulk = requests.get("https://api.scryfall.com/bulk-data").json()
    default_cards = next(b for b in bulk["data"] if b["type"] == "default_cards")
    data = requests.get(default_cards["download_uri"]).json()
    return data


def build_indexes(cards):
    card_index = {}
    label_map = {}

    class_id = 0

    for card in tqdm(cards, desc="Processing cards"):
        # Skip non-paper cards
        if card.get("digital"):
            continue

        # Skip cards without images
        if "image_uris" not in card:
            continue

        key = f"{card['name']}|{card['set'].upper()}|{card['collector_number']}"

        # Avoid duplicates
        if key in card_index:
            continue

        price = 0.0
        prices = card.get("prices", {})
        for p in ["usd", "usd_foil", "usd_etched"]:
            if prices.get(p):
                price = float(prices[p])
                break

        card_index[key] = {
            "name": card["name"],
            "set": card["set"].upper(),
            "collector_number": card["collector_number"],
            "colors": card.get("color_identity", []),
            "is_land": "Land" in card.get("type_line", ""),
            "is_artifact": "Artifact" in card.get("type_line", ""),
            "is_colorless": len(card.get("color_identity", [])) == 0,
            "price": price,
            "image_uri": card["image_uris"]["large"],
        }

        label_map[str(class_id)] = key
        class_id += 1

    return card_index, label_map


def main():
    cards = download_scryfall_bulk()
    card_index, label_map = build_indexes(cards)

    with open(CARD_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(card_index, f, indent=2)

    with open(LABEL_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(label_map, f, indent=2)

    print(f"\nDone.")
    print(f"Saved {len(card_index)} cards.")
    print(f"- {CARD_INDEX_PATH}")
    print(f"- {LABEL_MAP_PATH}")


if __name__ == "__main__":
    main()
