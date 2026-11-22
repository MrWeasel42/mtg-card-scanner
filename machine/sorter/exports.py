"""The export formats: the same files, columns and values as the Windows app (src/CardScanner.App/CsvExport.cs).

Each format writes one file for a session's cards. Cards marked wrong or "printing not listed" and photos with no
card are left out of the collection formats; flagged cards nobody reviewed go in as their best guess (Moxfield tags
them needs-check, ROCA marks them REJECT).
"""
from __future__ import annotations

import csv
import io

LANG_NAMES = {"en": "English", "ja": "Japanese", "de": "German", "fr": "French", "it": "Italian", "es": "Spanish",
              "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "zhs": "Chinese Simplified",
              "zht": "Chinese Traditional", "ph": "Phyrexian"}

# key, title, description, file suffix: the same list as CsvExport.Formats
FORMATS = [
    ("ManaBox", "ManaBox", "Exact printing by Scryfall ID, with finish, condition and language. Import in ManaBox: "
                           "Collection → Import → CSV.", "ManaBox.csv"),
    ("Moxfield", "Moxfield", "Moxfield collection import (Collection → Import → CSV). Unreviewed flagged cards are "
                             "tagged needs-check.", "Moxfield.csv"),
    ("Deckbox", "Deckbox", "Deckbox inventory import (also read by many other collection sites).", "Deckbox.csv"),
    ("TCGplayer", "TCGplayer list", "A Mass Entry list (1 Card Name [SET]) to paste at tcgplayer.com/massentry to "
                                    "price or buy the cards.", "TCGplayer Mass Entry.txt"),
    ("Roca", "ROCA / TCGplayer", "Same columns as a ROCA Sorter export: one row per scan with TCGplayer product ID, "
                                 "bin, REJECT for flagged cards, confidence and photo.", "ROCA style.csv"),
    ("General", "General CSV", "One row per scanned card with everything: printing, finish, price, colors, type, bin, "
                               "why it was flagged.", "All details.csv"),
]
KEYS = [f[0] for f in FORMATS]
DEFAULT = ["ManaBox", "Moxfield"]
LEFT_OUT = ("wrong", "notlisted")


def _usable(c: dict) -> bool:
    return bool(c.get("card")) and not c.get("noCard") and c.get("verdict") not in LEFT_OUT


def _unchecked(c: dict) -> bool:
    return bool(c.get("flagged")) and not c.get("verdict")


def _rows(cards: list[dict]) -> list[dict]:
    """Same printing, finish, condition and tags = one row with a quantity."""
    groups: dict[tuple, dict] = {}
    for c in cards:
        if not _usable(c):
            continue
        card = c["card"]
        k = (card["id"], c.get("finish") or "nonfoil", c.get("condition") or "Near Mint", bool(c.get("altered")),
             bool(c.get("misprint")), _unchecked(c))
        g = groups.setdefault(k, {"card": card, "finish": k[1], "condition": k[2], "altered": k[3], "misprint": k[4],
                                  "unchecked": k[5], "qty": 0})
        g["qty"] += 1
    return sorted(groups.values(), key=lambda r: r["card"]["name"])


def _mana_cond(c: str) -> str:
    return {"Lightly Played": "lightly_played", "Moderately Played": "moderately_played",
            "Heavily Played": "heavily_played", "Damaged": "damaged"}.get(c, "near_mint")


def _tf(b) -> str:
    return "true" if b else "false"


def _lang(card) -> str:
    return LANG_NAMES.get(card.get("lang") or "en", card.get("lang") or "English")


def _writer(buf, quote_all=False):
    return csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL)


def manabox(rows) -> str:
    b = io.StringIO(); w = _writer(b)
    w.writerow(["Name", "Set code", "Set name", "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID",
                "Scryfall ID", "Purchase price", "Misprint", "Altered", "Signed", "Condition", "Language", "Proxy",
                "Purchase price currency"])
    for r in rows:
        c = r["card"]
        w.writerow([c["name"], c["setCode"].upper(), c.get("setName", ""), c["number"],
                    "normal" if r["finish"] == "nonfoil" else r["finish"], c.get("rarity", ""), r["qty"], "", c["id"],
                    "", _tf(r["misprint"]), _tf(r["altered"]), "false", _mana_cond(r["condition"]),
                    c.get("lang") or "en", "false", ""])
    return b.getvalue()


def moxfield(rows) -> str:
    b = io.StringIO(); w = _writer(b, True)
    w.writerow(["Count", "Tradelist Count", "Name", "Edition", "Condition", "Language", "Foil", "Tags",
                "Last Modified", "Collector Number", "Alter", "Proxy", "Purchase Price"])
    for r in rows:
        c = r["card"]
        w.writerow([r["qty"], 0, c["name"], c["setCode"].lower(), r["condition"], _lang(c),
                    {"foil": "foil", "etched": "etched"}.get(r["finish"], ""), "needs-check" if r["unchecked"] else "",
                    "", c["number"], "True" if r["altered"] else "False", "False", ""])
    return b.getvalue()


def deckbox(rows) -> str:
    b = io.StringIO(); w = _writer(b)
    w.writerow(["Count", "Tradelist Count", "Name", "Edition", "Card Number", "Condition", "Language", "Foil", "Signed",
                "Artist Proof", "Altered Art", "Misprint", "Promo", "Textless", "My Price"])
    for r in rows:
        c = r["card"]
        w.writerow([r["qty"], 0, c["name"], c.get("setName", ""), c["number"], r["condition"], _lang(c),
                    "" if r["finish"] == "nonfoil" else "foil", "", "", "altered" if r["altered"] else "",
                    "misprint" if r["misprint"] else "", "", "", ""])
    return b.getvalue()


def tcgplayer(rows) -> str:
    """Mass Entry: "2 Lightning Bolt [M11]". Double-faced cards go by their front face's name."""
    out: dict[tuple, int] = {}
    for r in rows:
        k = (r["card"]["name"].split(" // ")[0], r["card"]["setCode"].upper())
        out[k] = out.get(k, 0) + r["qty"]
    return "".join(f"{q} {n} [{s}]\n" for (n, s), q in out.items())


def roca(cards: list[dict]) -> str:
    """ROCA Sorter Max export: rejects first (Sequence ID 0, bin REJECT), then sorted cards numbered 1, 2, 3..."""
    b = io.StringIO(); w = _writer(b)
    w.writerow(["Sequence ID", "Output Bin ID", "Rejected", "TCGp Product ID", "OmniChannel ID", "Product Line",
                "Set Name", "Card Name", "Number", "Rarity", "Condition ID", "Condition", "Finish", "TCG Market Price",
                "Confidence", "Image Path"])
    rejected = lambda c: not _usable(c) or _unchecked(c)
    seq = 0
    for c in sorted(cards, key=lambda c: (not rejected(c), c["n"])):
        rej = rejected(c)
        card = c["card"] if _usable(c) else None
        fin = c.get("finish") or "nonfoil"
        tcg = "" if card is None else (card.get("tcgplayerEtchedId") if fin == "etched" and card.get("tcgplayerEtchedId")
                                      else card.get("tcgplayerId") or "Unavailable")
        cond = c.get("condition") or "Near Mint"
        rar = (card or {}).get("rarity") or ""
        rar = {"common": "C", "uncommon": "U", "rare": "R", "mythic": "M", "special": "S"}.get(rar, rar[:1].upper())
        if not rej:
            seq += 1
        w.writerow(["0" if rej else seq, "REJECT" if rej else (c.get("dropped") or c.get("bin") or ""), "Y" if rej else "N",
                    tcg, "", "" if card is None else "Magic", (card or {}).get("setName", ""), (card or {}).get("name", ""),
                    (card or {}).get("number", ""), rar,
                    {"Lightly Played": 2, "Moderately Played": 3, "Heavily Played": 4, "Damaged": 5}.get(cond, 1), cond,
                    "" if card is None else {"foil": "Foil", "etched": "Etched"}.get(fin, "Normal"),
                    f"{c.get('price') or 0:.2f}".rstrip("0").rstrip("."), "None" if card is None else
                    ("FAIR" if c.get("flagged") else "GOOD"), f"photos/{c['n']:04d}.jpg"])
    return b.getvalue()


def general(cards: list[dict]) -> str:
    b = io.StringIO(); w = _writer(b)
    w.writerow(["Scan", "Name", "Set code", "Set name", "Collector number", "Finish", "Rarity", "Language", "Condition",
                "Altered", "Misprint", "Price USD", "Colors", "Type", "Bin", "Bin label", "Bin reason", "Pinned by",
                "Flagged", "Reviewed", "Scryfall ID", "Photo"])
    for c in sorted(cards, key=lambda c: c["n"]):
        if not _usable(c):
            continue
        card = c["card"]
        w.writerow([c["n"], card["name"], card["setCode"].upper(), card.get("setName", ""), card["number"],
                    c.get("finish") or "nonfoil", card.get("rarity", ""), _lang(card), c.get("condition") or "Near Mint",
                    _tf(c.get("altered")), _tf(c.get("misprint")),
                    "" if c.get("price") is None else f"{c['price']:.2f}", card.get("colors", ""),
                    card.get("typeLine", ""), c.get("dropped") or c.get("bin") or "", c.get("binLabel") or "",
                    c.get("binReason") or "", (c.get("ident") or {}).get("pinReason") or "",
                    c.get("flagReason") or "" if c.get("flagged") else "", _tf(bool(c.get("verdict"))), card["id"],
                    f"photos/{c['n']:04d}.jpg"])
    return b.getvalue()


def write(cards: list[dict], formats: list[str]) -> list[tuple[str, str]]:
    """[(file suffix, text)] for the chosen formats (any unknown key is ignored)."""
    rows = _rows(cards)
    if not rows:
        return []
    make = {"ManaBox": lambda: manabox(rows), "Moxfield": lambda: moxfield(rows), "Deckbox": lambda: deckbox(rows),
            "TCGplayer": lambda: tcgplayer(rows), "Roca": lambda: roca(cards), "General": lambda: general(cards)}
    return [(suffix, make[key]()) for key, _, _, suffix in FORMATS if key in formats]
