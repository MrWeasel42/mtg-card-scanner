"""Bin rules: the same rules as the Windows app (src/CardScanner.Core/Sorting/BinSorter.cs), so a setup made on
either one sorts the same way.

Bins are numbered from the feeder. Bins are tried in order (bin 1 first); the first bin whose rule fits gets the
card. The last bin in use is the end of the line: it takes Flagged cards and anything no other bin takes.

A setup is plain JSON (also what the Windows app saves):
    {"binsInUse": 3, "by": "Price", "priceBreaks": [1, 5, 10, 25, 50], "alphaRanges": ["A-F", ...],
     "setGroups": [], "rules": [ {rule for bin 1}, {bin 2}, ..., null, ... ]}
A rule: {"kind": "Price"|"Color"|"Letters"|"Rarity"|"Set"|"Type"|"Anything", "name": "", "min": 1, "max": 5,
         "colors": ["W", "U"], "letters": "A-F, Q", "rarities": ["rare"], "sets": ["MH3"], "types": ["Creature"]}
"""
from __future__ import annotations

import copy
import re
import unicodedata

MAX_BINS = 9
SORT_BY = ["Price", "Alphabet", "Color", "Rarity", "Set", "Type"]
KINDS = ["Price", "Color", "Letters", "Rarity", "Set", "Type", "Anything"]
COLOR_CODES = ["W", "U", "B", "R", "G", "M", "C", "L"]
COLOR_NAMES = ["White", "Blue", "Black", "Red", "Green", "Multicolor", "Colorless", "Lands"]
RARITY_CODES = ["common", "uncommon", "rare", "mythic", "special"]
TYPE_NAMES = ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker", "Land", "Battle"]


# Share of all paper Magic printings by first letter of the name (Scryfall, Nov 2026), in %. Alphabetical bins are
# split so each gets about the same number of cards; the machine's own scanned cards are mixed in as they build up.
LETTER_SHARE = {"A": 5.56, "B": 5.49, "C": 6.92, "D": 5.61, "E": 3.49, "F": 5.07, "G": 5.03, "H": 3.16, "I": 3.2,
                "J": 1.15, "K": 2.47, "L": 3.11, "M": 6.37, "N": 2.11, "O": 2.01, "P": 5.09, "Q": 0.35, "R": 5.0,
                "S": 13.18, "T": 7.29, "U": 1.46, "V": 2.39, "W": 3.39, "X": 0.09, "Y": 0.46, "Z": 0.54}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def alpha_split(groups: int, counts: dict | None = None) -> list[str]:
    """A-Z cut into `groups` runs of letters with as even a number of cards in each as possible.
    counts = cards seen per first letter on this machine; they count for more as they pile up."""
    seen = sum((counts or {}).values())
    w = [LETTER_SHARE[c] / 100 * 1000 + (counts or {}).get(c, 0) for c in LETTERS] if seen else [LETTER_SHARE[c] for c in LETTERS]
    groups = max(1, min(groups, 26))
    n = len(w)
    pre = [0.0]
    for x in w:
        pre.append(pre[-1] + x)
    INF = float("inf")
    # best[k][i]: smallest possible biggest group, splitting the first i letters into k groups
    best = [[INF] * (n + 1) for _ in range(groups + 1)]
    cut = [[0] * (n + 1) for _ in range(groups + 1)]
    best[0][0] = 0.0
    for k in range(1, groups + 1):
        for i in range(k, n + 1):
            for j in range(k - 1, i):
                v = max(best[k - 1][j], pre[i] - pre[j])
                if v < best[k][i] - 1e-9:
                    best[k][i], cut[k][i] = v, j
    out, i = [], n
    for k in range(groups, 0, -1):
        j = cut[k][i]
        out.append(LETTERS[j] if i - j == 1 else f"{LETTERS[j]}-{LETTERS[i - 1]}")
        i = j
    return out[::-1]


def _money(d: float) -> str:
    return f"${d:.0f}" if float(d) == int(d) else f"${d:.2f}".rstrip("0").rstrip(".")


def default_setup(bins_in_use: int = 3) -> dict:
    s = {"binsInUse": bins_in_use, "by": "Price", "priceBreaks": [1, 5, 10, 25, 50],
         "alphaRanges": ["A-F", "G-K", "L-R", "S-Z"], "setGroups": [], "rules": []}
    s["rules"] = preset_rules(s)
    return s


def normalize(s: dict | None, bins_in_use: int | None = None) -> dict:
    """Fills in anything missing (also accepts the Windows app's PascalCase JSON)."""
    s = copy.deepcopy(s or {})
    low = {k[:1].lower() + k[1:]: v for k, v in s.items()}
    out = default_setup()
    out.update({k: v for k, v in low.items() if k in out})
    out["rules"] = [_rule(r) for r in (low.get("rules") or [])]
    if not out["rules"]:
        out["rules"] = preset_rules(out)
    if bins_in_use is not None:
        out["binsInUse"] = bins_in_use
    out["binsInUse"] = max(2, min(MAX_BINS, int(out["binsInUse"])))
    return out


def _rule(r) -> dict | None:
    if not r:
        return None
    r = {k[:1].lower() + k[1:]: v for k, v in r.items()}
    kind = r.get("kind", "Price")
    if isinstance(kind, int):
        kind = KINDS[kind]
    return {"kind": kind, "name": r.get("name") or "", "min": r.get("min"), "max": r.get("max"),
            "colors": list(r.get("colors") or []), "letters": r.get("letters") or "",
            "rarities": list(r.get("rarities") or []), "sets": [x.upper() for x in (r.get("sets") or [])],
            "types": list(r.get("types") or [])}


def new_rule(kind: str = "Price") -> dict:
    return _rule({"kind": kind})


def preset_rules(s: dict, letter_counts: dict | None = None) -> list:
    by = s.get("by", "Price")
    rules: list = []
    if by == "Price":
        b = sorted({float(x) for x in s.get("priceBreaks", []) if float(x) > 0})
        if not b:
            rules.append(new_rule("Price"))
        else:
            rules.append(_rule({"kind": "Price", "max": b[0]}))
            for lo, hi in zip(b, b[1:]):
                rules.append(_rule({"kind": "Price", "min": lo, "max": hi}))
            rules.append(_rule({"kind": "Price", "min": b[-1]}))
    elif by == "Alphabet":
        # every bin but the end one gets a run of A-Z; names starting with a number go to the end bin
        s["alphaRanges"] = alpha_split(max(1, int(s.get("binsInUse", 3)) - 1), letter_counts)
        for r in s["alphaRanges"]:
            rules.append(_rule({"kind": "Letters", "letters": r}))
    elif by == "Color":
        for c in COLOR_CODES:
            rules.append(_rule({"kind": "Color", "colors": [c]}))
    elif by == "Rarity":
        for r in RARITY_CODES:
            rules.append(_rule({"kind": "Rarity", "rarities": [r]}))
    elif by == "Type":
        # one bin per card type, first match wins (an Artifact Creature goes to Creature)
        for t in TYPE_NAMES:
            rules.append(_rule({"kind": "Type", "types": [t]}))
    elif by == "Set":
        for g in s.get("setGroups", []):
            codes = []
            for x in g.replace(";", ",").replace("/", ",").replace(" ", ",").split(","):
                if x.strip() and x.strip().upper() not in codes:
                    codes.append(x.strip().upper())
            if codes:
                rules.append(_rule({"kind": "Set", "sets": codes}))
        rules.append(_rule({"kind": "Anything", "name": "Other sets"}))
    return rules[:MAX_BINS - 1]


def apply_preset(s: dict, by: str, letter_counts: dict | None = None) -> dict:
    s = copy.deepcopy(s)
    s["by"] = by
    s["rules"] = preset_rules(s, letter_counts)
    return s


def effective_rules(s: dict) -> list:
    rules = list(s.get("rules") or preset_rules(s))[:MAX_BINS - 1]
    return rules + [None] * (MAX_BINS - 1 - len(rules))


def letter_ranges(letters: str) -> list[str]:
    out = []
    for part in letters.upper().replace(";", ",").replace(" ", ",").split(","):
        p = "".join(ch for ch in part if ch.isalpha() or ch in "-#")
        if p:
            out.append(p)
    return out


def describe(r: dict | None) -> str:
    if r is None:
        return "(empty)"
    if (r.get("name") or "").strip():
        return r["name"].strip()
    k = r["kind"]
    if k == "Price":
        lo, hi = r.get("min"), r.get("max")
        if lo is None and hi is None:
            return "Any price"
        if lo is None:
            return f"Up to {_money(hi)}"
        if hi is None:
            return f"Over {_money(lo)}"
        return f"{_money(lo)}–{_money(hi)[1:]}"
    if k == "Color":
        cs = [COLOR_NAMES[i] for i, c in enumerate(COLOR_CODES) if c in r["colors"]]
        return " + ".join(cs) if cs else "No colors picked"
    if k == "Letters":
        parts = ["Numbers / symbols" if x == "#" else (f"{x[0]}–{x[2]}" if len(x) == 3 else x) for x in letter_ranges(r["letters"])]
        return ", ".join(parts) if parts else "No letters set"
    if k == "Rarity":
        rs = ["Special / bonus" if x == "special" else x.capitalize() for x in RARITY_CODES if x in r["rarities"]]
        return " + ".join(rs) if rs else "No rarity picked"
    if k == "Set":
        return ", ".join(x.upper() for x in r["sets"]) if r["sets"] else "No sets listed"
    if k == "Type":
        ts = [t for t in TYPE_NAMES if t in r["types"]]
        return " + ".join(ts) if ts else "No types picked"
    return "Everything else"


def flagged_bin(s: dict) -> int:
    return max(1, min(MAX_BINS, int(s["binsInUse"])))


def bin_labels(s: dict) -> list[str]:
    """Label for bins 1..binsInUse."""
    rules = effective_rules(s)
    end = flagged_bin(s)
    return ["Flagged + everything else" if b == end else describe(rules[b - 1]) for b in range(1, end + 1)]


def first_letter(name: str) -> str:
    name = name.replace("Æ", "AE").replace("æ", "ae").replace("Œ", "OE").replace("œ", "oe")
    for ch in unicodedata.normalize("NFD", name):
        if ch.isalpha():
            return ch.upper()
        if ch.isdigit():
            return ""
    return ""


def color_index(colors: str, type_line: str) -> int:
    """0 White .. 4 Green, 5 Multicolor, 6 Colorless, 7 Lands (front face)."""
    front = (type_line or "").split(" // ")[0]
    if "land" in front.lower():
        return 7
    cs = [c for c in "WUBRG" if c in (colors or "")]
    return 6 if not cs else ("WUBRG".index(cs[0]) if len(cs) == 1 else 5)


def _in_range(c: str, r: str) -> bool:
    if not c:
        return False
    parts = [p for p in r.split("-") if p]
    if not parts:
        return False
    lo, hi = parts[0][0], (parts[-1][0] if len(parts) > 1 else parts[0][-1])
    return lo <= c <= hi


def matches(r: dict, c: dict) -> bool:
    k = r["kind"]
    if k == "Price":
        p = c.get("price")
        return p is not None and (r.get("min") is None or p >= r["min"]) and (r.get("max") is None or p <= r["max"])
    if k == "Color":
        return COLOR_CODES[color_index(c.get("colors", ""), c.get("typeLine", ""))] in r["colors"]
    if k == "Letters":
        f = first_letter(c.get("name", ""))
        return any((f == "" if x == "#" else _in_range(f, x)) for x in letter_ranges(r["letters"]))
    if k == "Rarity":
        rr = (c.get("rarity") or "").lower()
        if rr not in ("common", "uncommon", "rare", "mythic"):
            rr = "special"
        return rr in r["rarities"]
    if k == "Set":
        return (c.get("setCode") or "").upper() in [x.upper() for x in r["sets"]]
    if k == "Type":
        front = (c.get("typeLine") or "").split(" // ")[0].split("—")[0].lower()
        return any(t.lower() in front for t in r["types"])
    return True


def _why(r: dict, c: dict) -> str:
    k = r["kind"]
    if k == "Price":
        return f"${c['price']:.2f}"
    if k == "Color":
        return COLOR_NAMES[color_index(c.get("colors", ""), c.get("typeLine", ""))]
    if k == "Letters":
        f = first_letter(c.get("name", ""))
        return f"starts with {f}" if f else "starts with a number / symbol"
    if k == "Rarity":
        return (c.get("rarity") or "").capitalize()
    if k == "Set":
        return (c.get("setCode") or "").upper()
    if k == "Type":
        return (c.get("typeLine") or "").split(" // ")[0]
    return describe(r)


def choose(s: dict, c: dict, flagged: bool = False, flag_reason: str | None = None) -> dict:
    """{bin, label, wanted, reason}; wanted 0 = Flagged."""
    end = flagged_bin(s)
    if flagged:
        return {"bin": end, "label": "Flagged", "wanted": 0, "reason": flag_reason or "flagged"}
    rules = effective_rules(s)
    for i, r in enumerate(rules):
        if r is None or not matches(r, c):
            continue
        wanted = i + 1
        why = _why(r, c)
        if wanted < end:
            return {"bin": wanted, "label": describe(r), "wanted": wanted, "reason": why}
        note = "shares the end bin with Flagged" if wanted == end else f"bin {wanted} is off"
        return {"bin": end, "label": describe(r), "wanted": wanted, "reason": f"{why} · {note}"}
    if c.get("price") is None and any(r and r["kind"] == "Price" for r in rules):
        return {"bin": end, "label": "Flagged", "wanted": 0, "reason": "no price"}
    return {"bin": end, "label": "Everything else", "wanted": end, "reason": "no bin's rule fits"}


def parse_sets(v) -> list[str]:
    """A set lock as typed ("HOB, hoc  spg") or a list -> ["hob", "hoc", "spg"] (blank = every set)."""
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[\s,;/]+", v)
    out = []
    for x in v:
        x = str(x).strip().lower()
        if x and x not in out:
            out.append(x)
    return out
