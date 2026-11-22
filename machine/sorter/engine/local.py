"""The machine's own identifier: the recognition engine on the Pi, answering exactly like the PC app does.

The PC app's answer to the machine (IdentifyViewModel.Machine.cs) is the recognizer's result plus the checks that
run once the candidates' catalog pictures are downloaded (ResultItemViewModel.LoadCoreAsync): straighten the crop
against the top match, read the ★/• mark off the picture, and the close-up detail compare between look-alike
printings. All of that is here too, in the same order, with the same 12 s cap.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import datetime as dt
import os
import threading
import time
import traceback
import urllib.request

import cv2
import numpy as np

from . import catalog as catalog_mod
from . import vision
from .recognizer import Recognizer, RecognitionResult

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OCR_DIR = os.path.join(REPO, "src", "CardScanner.Core", "OcrModels")
ASSETS_DIR = os.path.join(REPO, "src", "CardScanner.Core", "Assets")
CHECKS_CAP_S = 12.0
RARE_REPRINTS = {"sum", "ath", "brb", "btd", "dkm", "ced", "cei"}
DETAIL_PIN_REASON = "card details (set symbol, text box, artist line)"


def finish_options(card) -> list[dict]:
    out = []
    for k in card.finish_keys():
        label = {"nonfoil": "Non-foil", "etched": "Etched foil", "glossy": "Glossy"}.get(k, k)
        if k == "foil":
            label = f"Foil ({card.special_foil})" if card.special_foil else "Foil"
        out.append({"key": k, "label": label})
    return out


def shooting_star_era(card) -> bool:
    return card.frame == "1997" and "1999-02-15" <= card.released_at < "2003-07-01"


def detect_finish(card, collector_foil, shooting_star=None):
    """Finish.Detect: (key, reason, sure)."""
    keys = card.finish_keys()
    if len(keys) == 1:
        return keys[0], ("only made as non-foil" if keys[0] == "nonfoil" else "only made as foil"), True
    if shooting_star_era(card) and shooting_star is not None and "foil" in keys and "nonfoil" in keys:
        if shooting_star >= vision.SHOOTING_FOIL_AT:
            return "foil", "shooting star found", True
        if shooting_star < vision.SHOOTING_NONFOIL_BELOW:
            return "nonfoil", "no shooting star", True
    if collector_foil is True and "foil" in keys:
        return "foil", "★ in the collector line", True
    if collector_foil is True and "etched" in keys:
        return "etched", "★ in the collector line", True
    if collector_foil is False and "nonfoil" in keys:
        return "nonfoil", "• in the collector line", True
    return ("nonfoil" if "nonfoil" in keys else keys[0]), "couldn't tell from the photo — check it", False


class Pictures:
    """Catalog pictures from Scryfall ("large", falling back to "normal"), cached on the SD card."""

    def __init__(self, folder: str, timeout: float = 6.0):
        self.folder, self.timeout = folder, timeout
        os.makedirs(folder, exist_ok=True)
        self.pool = cf.ThreadPoolExecutor(4)

    def path(self, card) -> str | None:
        url = card.image_url or ""
        if not url.startswith("https://"):
            return None
        f = os.path.join(self.folder, card.id + "_large.jpg")
        if os.path.exists(f):
            return f
        for u in (url.replace("/normal/", "/large/"), url):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": catalog_mod.UA})
                data = urllib.request.urlopen(req, timeout=self.timeout).read()
                tmp = f + ".tmp"
                open(tmp, "wb").write(data)
                os.replace(tmp, f)
                return f
            except Exception:
                continue
        return None

    def paths(self, cards) -> list[str | None]:
        return list(self.pool.map(self.path, cards))


class Item:
    """One identified photo and the checks after it (the PC's ResultItemViewModel, minus the screen)."""

    def __init__(self, r: RecognitionResult, photo):
        self.r, self.photo = r, photo
        self.order = list(r.candidates)          # candidates, maybe re-ordered by the detail check
        self.paths: dict[str, str | None] = {}
        self.jpeg = r.card_jpeg
        self.mark_foil = None
        self.detail_pinned = False
        self.detail_note = None
        self.refresh_finish()

    @property
    def top(self):
        return self.order[0] if self.order else None

    @property
    def pinned(self) -> bool:
        return self.r.pinned or self.detail_pinned

    @property
    def pin_reason(self):
        return self.r.pin_reason if self.r.pinned else DETAIL_PIN_REASON if self.detail_pinned else None

    @property
    def flag_reason(self):
        return None if self.detail_pinned else self.r.flag_reason

    def refresh_finish(self):
        card = self.top.card if self.top else None
        if card is None:
            self.finish, self.finish_unsure, self.options, self.photo_unsure = "nonfoil", False, [], False
            return
        foil_mark = self.r.collector.foil if self.r.collector.foil is not None else self.mark_foil
        key, _, sure = detect_finish(card, foil_mark, self.r.shooting_star)
        self.options = finish_options(card)
        self.photo_unsure = not sure and len(self.options) > 1
        self.finish = next((o["key"] for o in self.options if o["key"] == key), self.options[0]["key"] if self.options else key)
        self.finish_unsure = not sure and len(self.options) > 1

    # -- the checks, in the PC's order
    def straighten(self, rec: Recognizer):
        top = self.top
        ref = self.paths.get(top.card.id) if top else None
        if not ref:
            return
        img = cv2.imread(ref, cv2.IMREAD_COLOR)
        if img is None:
            return
        jpeg = rec.refine_crop(self.photo, self.r, img)
        if jpeg:
            self.jpeg = jpeg

    def check_star(self):
        if self.r.collector.foil is not None or not self.photo_unsure:
            return
        foil = vision.star_mark_read(vision.star_mark_score(self.jpeg))
        if foil is None:
            return
        self.mark_foil = foil
        self.refresh_finish()

    def detail_check(self):
        top = self.top
        if top is None:
            return
        group = [c for c in self.order if c.card.name == top.card.name and self.paths.get(c.card.id)]
        if len(group) < 2:
            return
        scores = vision.detail_scores(self.jpeg, [(c.card.id, self.paths[c.card.id]) for c in group])
        if len(scores) < 2:
            return
        ranked = sorted(scores, key=lambda x: -x[1])
        by_id = {c.card.id: c for c in group}
        rare = lambda cid: by_id[cid].card.set_code in RARE_REPRINTS
        if rare(ranked[0][0]):
            nxt = next((x for x in ranked[1:] if not rare(x[0])), ("", 0.0))
            if ranked[0][1] - nxt[1] < vision.DETAIL_PIN_MARGIN:
                common = next((x for x in ranked if not rare(x[0])), None)
                if common is not None:
                    ranked.remove(common)
                    ranked.insert(0, common)
        pick = by_id[ranked[0][0]]
        margin = ranked[0][1] - ranked[1][1]
        printed_pin = self.r.pinned and (self.r.pin_reason or "").startswith("name + set + number")
        if printed_pin or margin < vision.DETAIL_REORDER_MARGIN:
            return
        if pick is not top:
            self.order = [pick] + [c for c in self.order if c is not pick]
            self.detail_note = (f"Close-up check preferred {pick.card.set_code.upper()} #{pick.card.collector_number} "
                                "over the picture match.")
        if margin >= vision.DETAIL_PIN_MARGIN and not self.r.pinned:
            self.detail_pinned = True
        self.refresh_finish()


class LocalIdentifier:
    """Same interface as identify.PcIdentifier. Loads in the background; `ready` once it can identify."""
    kind = "machine"
    label = "This machine"

    def __init__(self, data_dir: str, threads: int | None = None, catalog_dir: str | None = None,
                 auto_download: bool = True, log=print, recognizer: Recognizer | None = None,
                 pictures_dir: str | None = None):
        self.dir = catalog_dir or os.path.join(data_dir, "catalog")
        self.data_dir = data_dir
        self.threads = threads
        self.log = log
        self.rec: Recognizer | None = None
        self.state = "starting"            # starting | downloading | loading | ready | no catalog | error
        self.detail = ""
        self.last_ms = None
        self.avg_ms = None
        self.lock = threading.Lock()
        self.pictures = Pictures(pictures_dir or os.path.join(data_dir, "cache", "thumbs"))
        self.seq = 0
        self._ready = threading.Event()
        self.auto_download = auto_download
        if recognizer is not None:                # already loaded (tests, tools)
            self.rec, self.state, self.detail = recognizer, "ready", "Ready"
            self._ready.set()
        else:
            threading.Thread(target=self._load, daemon=True).start()

    # -- status
    @property
    def online(self) -> bool:
        return self.rec is not None

    @property
    def ready(self) -> bool:
        return self.rec is not None

    def connect(self) -> bool:
        return self.ready

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def status(self) -> dict:
        v = (self.rec.manifest.get("catalog_version") if self.rec else None) or ""
        return {"state": self.state, "detail": self.detail, "catalog": v, "lastMs": self.last_ms, "avgMs": self.avg_ms}

    def _load(self):
        try:
            if not catalog_mod.files_ready(self.dir):
                if not self.auto_download:
                    self.state, self.detail = "no catalog", "No card catalog on the machine yet."
                    return
                self.state, self.detail = "downloading", "Downloading the card catalog (about 220 MB, once)…"
                catalog_mod.update_catalog(self.dir, lambda t: setattr(self, "detail", t))
            self._open()
        except Exception as e:
            traceback.print_exc()
            self.state = "error" if catalog_mod.files_ready(self.dir) else "no catalog"
            self.detail = f"Couldn't get the machine's card reader ready: {e}"

    def _open(self):
        self.state, self.detail = "loading", "Loading the card catalog…"
        t = time.monotonic()
        rec = Recognizer(self.dir, OCR_DIR, ASSETS_DIR, self.threads)
        self.rec = rec
        self.state = "ready"
        self.detail = f"Ready (catalog {rec.manifest.get('catalog_version', '?')}, loaded in {time.monotonic() - t:.0f} s)"
        self.log(f"On-machine identifying ready: {self.detail}")
        self._ready.set()

    def update_catalog(self, busy=lambda: False) -> str:
        """Newer catalog published? Download it beside the old one, then switch when the machine isn't sorting."""
        try:
            import json
            remote = json.loads(catalog_mod._get(f"{catalog_mod.RELEASE_BASE}/catalog-latest/manifest.json", 30))
            have = (self.rec.manifest.get("catalog_version") if self.rec else None)
            if have == remote.get("catalog_version") and catalog_mod.files_ready(self.dir):
                return "up to date"
            new_dir = self.dir + ".new"
            os.makedirs(new_dir, exist_ok=True)
            for f in ("model.onnx", "catalog.sqlite", "fingerprints.bin", "fingerprint_ids.txt"):
                src, dst = os.path.join(self.dir, f), os.path.join(new_dir, f)
                if os.path.exists(src) and not os.path.exists(dst):
                    os.link(src, dst)           # unchanged files aren't downloaded again
            catalog_mod.update_catalog(new_dir)
            while busy():
                time.sleep(30)
            with self.lock:
                old = self.dir + ".old"
                if os.path.isdir(old):
                    import shutil
                    shutil.rmtree(old)
                os.replace(self.dir, old)
                os.replace(new_dir, self.dir)
                self._open()
            return "updated"
        except Exception as e:
            return f"catalog check failed: {e}"

    # -- identifying
    def identify(self, jpeg: bytes) -> dict:
        if self.rec is None:
            return {"ok": False, "offline": True, "error": f"The machine's card reader isn't ready ({self.detail})"}
        t0 = time.monotonic()
        try:
            with self.lock:
                rec = self.rec
                photo = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if photo is None:
                    raise ValueError("Couldn't open the photo.")
                r = rec.identify(photo, "machine")
            item = Item(r, photo)
            card = item.top.card if item.top else None
            if card is None or (not item.pinned and not (r.name_read or "").strip() and not r.collector.raw.strip()):
                return {"ok": False, "noCard": True, "error": "No card found in the photo.", "source": self.label}
            deadline = time.monotonic() + CHECKS_CAP_S
            try:
                cands = [c.card for c in item.order]
                for c, p in zip(cands, self.pictures.paths(cands)):
                    item.paths[c.id] = p
                for step in (lambda: item.straighten(rec), item.check_star, item.detail_check):
                    if time.monotonic() > deadline:
                        break
                    try:
                        step()
                    except Exception:
                        traceback.print_exc()
            except Exception:
                traceback.print_exc()
        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "noCard": True, "error": str(e) or "No card found in the photo.", "source": self.label}
        ms = int((time.monotonic() - t0) * 1000)
        self.last_ms = ms
        self.avg_ms = ms if self.avg_ms is None else int(self.avg_ms * 0.8 + ms * 0.2)
        self.seq += 1
        top = item.top.card
        return {"ok": True, "id": f"pi{self.seq}", "noCard": False, "pinned": item.pinned, "pinReason": item.pin_reason,
                "flagReason": item.flag_reason, "finish": item.finish, "finishUnsure": item.finish_unsure,
                "finishes": item.options, "card": top.json(), "candidates": [c.card.json() for c in item.order[:8]],
                "ms": ms, "source": self.label}

    # -- review helpers (the PC's /api/printings, /api/search, /api/card-image)
    def printings(self, name: str) -> list[dict]:
        if self.rec is None:
            return []
        return [c.json() for c in reversed(self.rec.catalog.printings_of(name))][:60]

    def search(self, text: str) -> list[dict]:
        return [c.json() for c in self.rec.catalog.search_names(text)] if self.rec else []

    def image(self, card_id: str) -> bytes | None:
        c = self.rec.catalog.get(card_id) if self.rec else None
        p = self.pictures.path(c) if c else None
        return open(p, "rb").read() if p else None

    def setup(self):
        return None

    def feedback(self, item: dict) -> None:
        """Reviews of cards the machine identified: kept on the machine (the PC keeps its own accuracy log)."""
        try:
            f = os.path.join(self.data_dir, "logs", "machine_identify_feedback.csv")
            os.makedirs(os.path.dirname(f), exist_ok=True)
            fresh = not os.path.exists(f)
            with open(f, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if fresh:
                    w.writerow(["time", "session", "id", "verdict", "card_id", "finish", "note"])
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"), item.get("session"), item.get("id"),
                            item.get("verdict"), item.get("cardId"), item.get("finish"), item.get("note")])
        except OSError:
            pass
