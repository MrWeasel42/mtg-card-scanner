"""Downloads Scryfall's bulk card data and turns each printing into a clean record."""

from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path
from typing import Iterator

import requests
from tqdm import tqdm

BULK_INDEX_URL = "https://api.scryfall.com/bulk-data"

# Special foil treatments Scryfall records in "promo_types".
SPECIAL_FOILS = {
    "surgefoil": "Surge Foil",
    "galaxyfoil": "Galaxy Foil",
    "halofoil": "Halo Foil",
    "textured": "Textured Foil",
    "gilded": "Gilded Foil",
    "confettifoil": "Confetti Foil",
    "doublerainbow": "Double Rainbow Foil",
    "rainbowfoil": "Rainbow Foil",
    "raisedfoil": "Raised Foil",
    "neonink": "Neon Ink Foil",
    "oilslick": "Oil Slick Foil",
    "stepandcompleat": "Step-and-Compleat Foil",
    "silverfoil": "Silver Foil",
    "ripplefoil": "Ripple Foil",
    "fracturefoil": "Fracture Foil",
    "manafoil": "Mana Foil",
    "firstplacefoil": "First Place Foil",
    "dragonscalefoil": "Dragonscale Foil",
    "singularityfoil": "Singularity Foil",
    "cosmicfoil": "Cosmic Foil",
    "chocobotrackfoil": "Chocobo Track Foil",
}

# Layouts that aren't real playable/collectible card faces we want to match.
SKIP_LAYOUTS = {"art_series"}


def _session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept": "application/json;q=0.9,*/*;q=0.8"})
    return s


def get_bulk_info(user_agent: str, bulk_type: str) -> dict:
    """Ask Scryfall where today's bulk file lives and when it was last updated."""
    r = _session(user_agent).get(BULK_INDEX_URL, timeout=30)
    r.raise_for_status()
    for item in r.json()["data"]:
        if item["type"] == bulk_type:
            return item
    raise RuntimeError(f"Scryfall bulk type '{bulk_type}' not found")


def download_bulk(user_agent: str, bulk_type: str, dest: Path) -> tuple[Path, str]:
    """Download the bulk JSON if Scryfall has a newer one. Returns (path, updated_at)."""
    info = get_bulk_info(user_agent, bulk_type)
    updated_at = info["updated_at"]
    stamp = dest.with_suffix(".updated_at")
    if dest.exists() and stamp.exists() and stamp.read_text().strip() == updated_at:
        print(f"Card data already up to date ({updated_at}).")
        return dest, updated_at

    print(f"Downloading Scryfall card data ({info.get('size', 0) / 1e6:.0f} MB)...")
    tmp = dest.with_suffix(".part")
    s = _session(user_agent)
    for attempt in range(3):
        try:
            with s.get(info["download_uri"], stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0)) or None
                with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True) as bar:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        bar.update(len(chunk))
            break
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"Download hiccup ({e}); retrying...")
            time.sleep(5)
    tmp.replace(dest)
    stamp.write_text(updated_at)
    return dest, updated_at


def iter_raw_cards(bulk_path: Path) -> Iterator[dict]:
    """Stream cards out of the (large) bulk file without loading it all into memory."""
    try:
        import ijson

        with open(bulk_path, "rb") as f:
            yield from ijson.items(f, "item", use_float=True)
    except ImportError:  # pragma: no cover - fallback if ijson is missing
        with open(bulk_path, "r", encoding="utf-8") as f:
            yield from json.load(f)


def sort_name(name: str) -> str:
    """Name used for alphabetical sorting: front face only, 'Æ' -> 'Ae', accents removed."""
    front = name.split(" // ")[0]
    front = front.replace("Æ", "Ae").replace("æ", "ae")
    front = unicodedata.normalize("NFKD", front)
    front = "".join(c for c in front if not unicodedata.combining(c))
    return front.strip()


def _price(prices: dict, key: str) -> float | None:
    v = (prices or {}).get(key)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def to_record(card: dict, language: str = "en") -> dict | None:
    """Convert a raw Scryfall card into the record we store. Returns None to skip it."""
    if card.get("lang") != language:
        return None
    if card.get("digital") or "paper" not in (card.get("games") or []):
        return None
    if card.get("layout") in SKIP_LAYOUTS:
        return None

    faces = card.get("card_faces") or []
    front = faces[0] if faces else {}

    image_uris = card.get("image_uris") or front.get("image_uris") or {}
    image_url = image_uris.get("normal") or image_uris.get("large")
    if not image_url:
        return None

    colors = card.get("colors")
    if colors is None:
        colors = front.get("colors", [])
    type_line = card.get("type_line") or front.get("type_line") or ""

    promo_types = card.get("promo_types") or []
    special = [SPECIAL_FOILS[p] for p in promo_types if p in SPECIAL_FOILS]
    finishes = card.get("finishes") or []
    prices = card.get("prices") or {}

    return {
        "id": card["id"],
        "oracle_id": card.get("oracle_id") or front.get("oracle_id"),
        "name": card["name"],
        "sort_name": sort_name(card["name"]),
        "set_code": card["set"],
        "set_name": card.get("set_name", ""),
        "set_type": card.get("set_type", ""),
        "collector_number": card["collector_number"],
        "released_at": card.get("released_at", ""),
        "rarity": card.get("rarity", ""),
        "layout": card.get("layout", ""),
        "type_line": type_line,
        "colors": "".join(colors),
        "color_identity": "".join(card.get("color_identity") or []),
        "frame": card.get("frame", ""),
        "border_color": card.get("border_color", ""),
        "full_art": int(bool(card.get("full_art"))),
        "finishes": ",".join(finishes),
        "promo_types": ",".join(promo_types),
        "special_foil": ",".join(special),
        "price_usd": _price(prices, "usd"),
        "price_usd_foil": _price(prices, "usd_foil"),
        "price_usd_etched": _price(prices, "usd_etched"),
        "image_url": image_url,
        "image_status": card.get("image_status", ""),
    }
