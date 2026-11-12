"""The SQLite card catalog: one row per printing, plus per-set foil rules."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

CARD_COLUMNS = [
    "id", "oracle_id", "name", "sort_name", "set_code", "set_name", "set_type",
    "collector_number", "released_at", "rarity", "layout", "type_line", "colors",
    "color_identity", "frame", "border_color", "full_art", "finishes", "promo_types",
    "special_foil", "price_usd", "price_usd_foil", "price_usd_etched", "image_url",
    "image_status",
]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS cards (
    {", ".join(c + (" TEXT PRIMARY KEY" if c == "id" else "") for c in CARD_COLUMNS)}
);
CREATE INDEX IF NOT EXISTS idx_cards_set_num ON cards(set_code, collector_number);
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);

CREATE TABLE IF NOT EXISTS set_foil_rules (
    set_code TEXT PRIMARY KEY,
    set_name TEXT,
    released_at TEXT,
    indicator TEXT,      -- what on the card tells you it's foil (see foil_rules.py)
    verified INTEGER,    -- 1 = checked against real cards, 0 = best guess
    note TEXT
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def replace_cards(con: sqlite3.Connection, records: Iterable[dict]) -> int:
    """Swap in a fresh set of cards (prices and new printings change daily)."""
    placeholders = ", ".join("?" for _ in CARD_COLUMNS)
    con.execute("DELETE FROM cards")
    n = 0
    batch = []
    for rec in records:
        batch.append(tuple(rec[c] for c in CARD_COLUMNS))
        if len(batch) >= 5000:
            con.executemany(f"INSERT OR REPLACE INTO cards VALUES ({placeholders})", batch)
            n += len(batch)
            batch.clear()
    if batch:
        con.executemany(f"INSERT OR REPLACE INTO cards VALUES ({placeholders})", batch)
        n += len(batch)
    con.commit()
    return n


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
    con.commit()


def get_meta(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def all_card_ids(con: sqlite3.Connection) -> list[str]:
    return [r["id"] for r in con.execute("SELECT id FROM cards ORDER BY id")]
