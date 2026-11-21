"""Scan sessions on the machine itself.

A session has a name, a mode (Catalog: identify, sort and export CSVs; Sort: bins only) and its bin setup. Every
card the machine scans is saved with its photo. Stop ends the scanning; then the flagged cards can be reviewed
(on the touchscreen, or in any browser at http://sorter.local:8080) and Finish writes the CSVs.

On disk (~/sorter_data/sessions/<date time> <name>/):
    session.json      the session, every card and its review
    photos/0001.jpg   each card's photo
    <name> - ManaBox.csv, <name> - Moxfield.csv   written at Finish (Catalog sessions)
The Windows app copies finished sessions to the PC whenever it's running (its "Machine sessions" backup).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import threading
import zipfile

import rules
from identify import price_for

LANG_NAMES = {"en": "English", "ja": "Japanese", "de": "German", "fr": "French", "it": "Italian", "es": "Spanish",
              "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "zhs": "Chinese Simplified",
              "zht": "Chinese Traditional", "ph": "Phyrexian"}
CONDITIONS = ["Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"]


def safe_name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", s).strip() or "session"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Session:
    def __init__(self, folder: str, data: dict):
        self.folder = folder
        self.d = data
        self.lock = threading.RLock()

    # ------------------------------------------------------------ basics
    @property
    def id(self) -> str: return self.d["id"]
    @property
    def name(self) -> str: return self.d["name"]
    @property
    def catalog(self) -> bool: return self.d["mode"] == "Catalog"
    @property
    def cards(self) -> list[dict]: return self.d["cards"]
    @property
    def setup(self) -> dict: return self.d["bins"]

    def save(self) -> None:
        with self.lock:
            tmp = os.path.join(self.folder, "session.json.tmp")
            with open(tmp, "w") as f:
                json.dump(self.d, f, indent=1)
            os.replace(tmp, os.path.join(self.folder, "session.json"))

    def photo_path(self, n: int) -> str:
        return os.path.join(self.folder, "photos", f"{n:04d}.jpg")

    # ------------------------------------------------------------ cards
    def add_card(self, jpeg: bytes, ident: dict) -> dict:
        """Saves the photo and the identifier's answer, picks the bin. Returns the card record."""
        with self.lock:
            n = len(self.cards) + 1
            os.makedirs(os.path.join(self.folder, "photos"), exist_ok=True)
            with open(self.photo_path(n), "wb") as f:
                f.write(jpeg)
            c = {"n": n, "time": now(), "ident": {k: ident.get(k) for k in ("id", "source", "pinReason", "error")},
                 "noCard": bool(ident.get("noCard")), "offline": bool(ident.get("offline")),
                 "pinned": bool(ident.get("pinned")), "candidates": ident.get("candidates") or [],
                 "finishes": ident.get("finishes") or [], "finish": ident.get("finish") or "nonfoil",
                 "finishUnsure": bool(ident.get("finishUnsure")), "card": ident.get("card"),
                 "verdict": "", "note": "", "condition": "Near Mint", "bin": None, "dropped": None}
            self._decide(c, ident.get("flagReason"))
            self.cards.append(c)
            self.save()
            return c

    def _decide(self, c: dict, pc_flag: str | None = None) -> None:
        """Flagged? Then the bin. Reviewed cards are never flagged."""
        card = c.get("card")
        c["price"] = price_for(card, c["finish"])
        why = None
        if c["verdict"] in ("ok", "picked"):
            why = None
        elif c["noCard"]:
            why = "no card in the photo"
        elif not card:
            why = c["ident"].get("error") or "not identified"
        elif not c["pinned"]:
            why = pc_flag or "not sure of the printing"
        elif self.catalog and c["finishUnsure"]:
            why = "foil or not?"
        elif (card.get("setCode") or "").lower() in ("plst", "ulst") and c["price"] is None:
            why = "List card with no price"
        if c["verdict"] == "wrong":
            why = "marked wrong"
        c["flagged"] = why is not None
        c["flagReason"] = why
        facts = {"name": (card or {}).get("name", ""), "price": c["price"], "colors": (card or {}).get("colors", ""),
                 "typeLine": (card or {}).get("typeLine", ""), "rarity": (card or {}).get("rarity", ""),
                 "setCode": (card or {}).get("setCode", "")}
        choice = rules.choose(self.setup, facts, c["flagged"], why)
        if c.get("bin") is None:                     # the bin it physically went to never changes
            c["bin"] = choice["bin"]
        c["wanted"] = choice["wanted"]
        c["binLabel"] = choice["label"]
        c["binReason"] = choice["reason"]

    def mark_dropped(self, n: int, bin_no: int) -> None:
        with self.lock:
            c = self.cards[n - 1]
            c["dropped"] = bin_no
            self.save()

    def review(self, n: int, verdict: str, card: dict | None = None, finish: str | None = None,
               note: str | None = None, condition: str | None = None) -> dict:
        """verdict: ok (top match right), picked (chose another printing), wrong (not the card / not listed)."""
        with self.lock:
            c = self.cards[n - 1]
            c["verdict"] = verdict
            if card is not None:
                c["card"] = card
            if finish:
                c["finish"] = finish
                c["finishUnsure"] = False
            if note is not None:
                c["note"] = note
            if condition:
                c["condition"] = condition
            c["reviewedAt"] = now()
            self._decide(c)
            self.save()
            return c

    def replace_ident(self, n: int, ident: dict) -> dict:
        """A card identified again (e.g. it was scanned while the PC was off)."""
        with self.lock:
            c = self.cards[n - 1]
            c.update({"ident": {k: ident.get(k) for k in ("id", "source", "pinReason", "error")},
                      "noCard": bool(ident.get("noCard")), "offline": bool(ident.get("offline")),
                      "pinned": bool(ident.get("pinned")), "candidates": ident.get("candidates") or [],
                      "finishes": ident.get("finishes") or [], "finish": ident.get("finish") or "nonfoil",
                      "finishUnsure": bool(ident.get("finishUnsure")), "card": ident.get("card")})
            self._decide(c, ident.get("flagReason"))
            self.save()
            return c

    # ------------------------------------------------------------ summary
    def to_review(self) -> list[dict]:
        return [c for c in self.cards if c["flagged"] and not c["verdict"]]

    def summary(self) -> dict:
        cards = self.cards
        prices = [c["price"] for c in cards if c.get("price") is not None and c.get("card") and not c["noCard"]]
        counts: dict[int, int] = {}
        for c in cards:
            b = c.get("dropped") or c.get("bin")
            if b:
                counts[b] = counts.get(b, 0) + 1
        top = max((c for c in cards if c.get("price") is not None and c.get("card")), key=lambda c: c["price"], default=None)
        return {"id": self.id, "name": self.name, "mode": self.d["mode"], "state": self.d["state"],
                "started": self.d["started"], "ended": self.d.get("ended"), "cards": len(cards),
                "flagged": sum(1 for c in cards if c["flagged"]), "toReview": len(self.to_review()),
                "noCard": sum(1 for c in cards if c["noCard"]), "binCounts": counts,
                "total": round(sum(prices), 2), "top": card_brief(top) if top else None,
                "binLabels": rules.bin_labels(self.setup), "binsInUse": self.setup["binsInUse"],
                "exports": self.d.get("exports", []), "folder": os.path.basename(self.folder)}

    # ------------------------------------------------------------ export
    def export(self) -> list[str]:
        """ManaBox + Moxfield CSVs. Cards marked wrong with no printing picked, and photos with no card, are left
        out; flagged cards nobody reviewed go in as their best guess."""
        rows: dict[tuple, int] = {}
        keep: dict[tuple, dict] = {}
        for c in self.cards:
            card = c.get("card")
            if c["noCard"] or not card or c["verdict"] == "wrong":
                continue
            k = (card["id"], c["finish"], c["condition"])
            rows[k] = rows.get(k, 0) + 1
            keep[k] = c
        base = safe_name(self.name)
        files = []
        mb = io.StringIO()
        w = csv.writer(mb, lineterminator="\n")
        w.writerow(["Name", "Set code", "Set name", "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID",
                    "Scryfall ID", "Purchase price", "Misprint", "Altered", "Signed", "Condition", "Language", "Proxy",
                    "Purchase price currency"])
        for k, q in sorted(rows.items(), key=lambda kv: keep[kv[0]]["card"]["name"]):
            c = keep[k]; card = c["card"]
            cond = c["condition"].lower().replace(" ", "_")
            w.writerow([card["name"], card["setCode"].upper(), card.get("setName", ""), card["number"],
                        "normal" if c["finish"] == "nonfoil" else c["finish"], card.get("rarity", ""), q, "", card["id"],
                        "", "false", "false", "false", cond, card.get("lang") or "en", "false", ""])
        mx = io.StringIO()
        w = csv.writer(mx, lineterminator="\n", quoting=csv.QUOTE_ALL)
        w.writerow(["Count", "Tradelist Count", "Name", "Edition", "Condition", "Language", "Foil", "Tags",
                    "Last Modified", "Collector Number", "Alter", "Proxy", "Purchase Price"])
        for k, q in sorted(rows.items(), key=lambda kv: keep[kv[0]]["card"]["name"]):
            c = keep[k]; card = c["card"]
            foil = {"foil": "foil", "etched": "etched"}.get(c["finish"], "")
            tag = "needs-check" if c["flagged"] and not c["verdict"] else ""
            w.writerow([q, 0, card["name"], card["setCode"].lower(), c["condition"],
                        LANG_NAMES.get(card.get("lang") or "en", "English"), foil, tag, "", card["number"], "False", "False", ""])
        for suffix, text in (("ManaBox.csv", mb.getvalue()), ("Moxfield.csv", mx.getvalue())):
            p = os.path.join(self.folder, f"{base} - {suffix}")
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            files.append(os.path.basename(p))
        return files

    def finish(self) -> list[str]:
        with self.lock:
            self.d["state"] = "finished"
            self.d["ended"] = self.d.get("ended") or now()
            self.d["exports"] = self.export() if self.catalog else []
            self.save()
            return self.d["exports"]

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(self.folder):
                for fn in files:
                    if fn.endswith(".tmp"):
                        continue
                    p = os.path.join(root, fn)
                    z.write(p, os.path.relpath(p, self.folder))
        return buf.getvalue()


def card_brief(c: dict | None) -> dict | None:
    if not c:
        return None
    card = c.get("card") or {}
    return {"n": c["n"], "name": card.get("name") or ("No card" if c.get("noCard") else "Not identified"),
            "set": card.get("setName", ""), "setCode": (card.get("setCode") or "").upper(), "number": card.get("number", ""),
            "rarity": card.get("rarity", ""), "finish": c.get("finish"), "price": c.get("price"),
            "bin": c.get("dropped") or c.get("bin"), "binLabel": c.get("binLabel"), "binReason": c.get("binReason"),
            "flagged": c.get("flagged"), "flagReason": c.get("flagReason"), "verdict": c.get("verdict"),
            "cardId": card.get("id"), "imageUrl": card.get("imageUrl", "")}


class Store:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def new(self, name: str, mode: str, setup: dict) -> Session:
        t = dt.datetime.now()
        sid = t.strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.root, f"{t:%Y-%m-%d %H%M} {safe_name(name)}")
        os.makedirs(os.path.join(folder, "photos"), exist_ok=True)
        s = Session(folder, {"id": sid, "name": name, "mode": mode, "state": "running", "started": now(), "ended": None,
                             "bins": rules.normalize(setup), "cards": [], "exports": []})
        s.save()
        self._cache[sid] = s
        return s

    def all(self) -> list[Session]:
        out = []
        for d in sorted(os.listdir(self.root), reverse=True):
            p = os.path.join(self.root, d, "session.json")
            if not os.path.exists(p):
                continue
            try:
                data = json.load(open(p))
            except (OSError, ValueError):
                continue
            s = self._cache.get(data["id"])
            if s is None:
                s = Session(os.path.join(self.root, d), data)
                self._cache[data["id"]] = s
            out.append(s)
        return out

    def get(self, sid: str) -> Session | None:
        if sid in self._cache:
            return self._cache[sid]
        for s in self.all():
            if s.id == sid:
                return s
        return None

    def delete(self, sid: str) -> bool:
        s = self.get(sid)
        if not s:
            return False
        shutil.rmtree(s.folder, ignore_errors=True)
        self._cache.pop(sid, None)
        return True
