"""Per-set foil rules: what (if anything) printed on a card tells you it's foil.

The recognizer uses this to decide how much to trust each clue:

  nonfoil_only        The set was never printed in foil (e.g. everything before Urza's Legacy).
                      Any card matched to it is automatically non-foil.
  foil_only           Every card in the set is foil.
  separate_printings  Foil and non-foil versions are different printings in Scryfall's data
                      (e.g. black-bordered 7th Edition foils), so the image match decides.
  shooting_star       Old-frame foils (Urza's Legacy to Scourge era) carry a shooting-star
                      stamp in the lower-left of the text box.
  collector_star      Newer cards print a star (foil) or dot (non-foil) in the collector line,
                      e.g. "LTR ★ EN" vs "LTR • EN".
  none                Foils exist but nothing printed marks them; the lighting check must decide.

Rules marked verified=0 are best guesses from the data and should be confirmed against real
cards. Fix any set by hand in config/foil_overrides.yaml (it always wins).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import yaml

# Assumption: the star/dot separator arrived with the Magic 2015 collector-line redesign.
# UNVERIFIED - confirm with real cards and adjust here or in foil_overrides.yaml.
COLLECTOR_STAR_FROM = "2014-07-18"

OLD_FRAMES = {"1993", "1997"}


def _classify(cards: list[sqlite3.Row]) -> tuple[str, str]:
    has_foil = [("foil" in c["finishes"].split(",") or "etched" in c["finishes"].split(",")) for c in cards]
    has_nonfoil = ["nonfoil" in c["finishes"].split(",") for c in cards]

    if not any(has_foil):
        return "nonfoil_only", "No foil printings exist in this set."
    if not any(has_nonfoil):
        return "foil_only", "Every printing in this set is foil."

    # Same card name appearing as a foil-only printing AND a nonfoil-only printing.
    by_name = defaultdict(set)
    for c, f, n in zip(cards, has_foil, has_nonfoil):
        if f != n:
            by_name[c["name"]].add("foil" if f else "nonfoil")
    split = sum(1 for kinds in by_name.values() if len(kinds) == 2)
    if split and split >= 0.5 * len({c["name"] for c in cards}):
        return "separate_printings", "Foils are their own printings; the image match tells them apart."

    frames = {c["frame"] for c in cards}
    released = min(c["released_at"] for c in cards if c["released_at"]) if cards else ""
    if frames & OLD_FRAMES:
        return "shooting_star", "Old-frame foil: look for the shooting star in the text box."
    if released >= COLLECTOR_STAR_FROM:
        return "collector_star", "Star (foil) or dot (non-foil) in the collector line."
    return "none", "No printed foil marker; relies on the lighting check."


def build_rules(con: sqlite3.Connection, overrides_path: Path) -> dict[str, int]:
    cards_by_set = defaultdict(list)
    for row in con.execute("SELECT name, set_code, set_name, released_at, frame, finishes FROM cards"):
        cards_by_set[row["set_code"]].append(row)

    overrides = {}
    if overrides_path.exists():
        overrides = (yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}).get("sets", {}) or {}

    con.execute("DELETE FROM set_foil_rules")
    counts: dict[str, int] = defaultdict(int)
    for set_code, cards in cards_by_set.items():
        indicator, note = _classify(cards)
        verified = 1 if indicator in {"nonfoil_only", "foil_only", "separate_printings"} else 0
        if set_code in overrides:
            o = overrides[set_code]
            indicator = o.get("indicator", indicator)
            note = o.get("note", "Set by hand in foil_overrides.yaml")
            verified = 1
        released = min((c["released_at"] for c in cards if c["released_at"]), default="")
        con.execute(
            "INSERT INTO set_foil_rules VALUES (?, ?, ?, ?, ?, ?)",
            (set_code, cards[0]["set_name"], released, indicator, verified, note),
        )
        counts[indicator] += 1
    con.commit()
    return dict(counts)
