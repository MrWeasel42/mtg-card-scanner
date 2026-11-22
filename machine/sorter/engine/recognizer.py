"""Photo in, ranked catalog printings out: a line-for-line copy of src/CardScanner.Core/Recognition/Recognizer.cs.

  1. Find the card in the photo and straighten it.
  2. Read the card's name (OCR). That decides which card it is.
  3. Read the collector line (set code + number + ★/•). That pins down the printing.
  4. Compare the picture against every printing of that card to break remaining ties.
Weights and rules are the PC app's (tuned on real phone photos, docs/recognition.md). Keep the two in step.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import detector, vision
from .catalog import CardCatalog, CardIndex, CardInfo, FingerprintIndex, Fingerprinter, PrintingKey, normalize
from .collector import EMPTY, CollectorLine
from .ocr import CardTextReader, TextLine

IMAGE_WEIGHT = 2.0
NUMBER_BONUS, SET_BONUS, BOTH_BONUS = 0.30, 0.20, 0.50
UNLIKELY_PENALTY = 0.20
PICTURE_CANDIDATES = 5
LIST_BONUS, LIST_PENALTY = 0.60, 0.30
MIN_PIN_SIMILARITY = 0.65
BORDER_PENALTY, YEAR_BONUS, SIZE_BONUS = 0.40, 0.25, 0.25
MIN_NAME_SCORE, MIN_FALLBACK_NAME_SCORE = 0.85, 0.90
MIN_IMAGE_SIMILARITY = 0.50
HI_W, HI_H = detector.WIDTH * 2, detector.HEIGHT * 2

RULES_WORDS = {"flying", "trample", "haste", "vigilance", "reach", "deathtouch", "lifelink", "first strike",
               "double strike", "flash", "defender", "menace", "hexproof", "indestructible", "ward", "prowess",
               "flanking", "banding", "shroud", "fear", "intimidate", "regenerate", "enchant creature", "equip"}

F32 = np.float32


@dataclass
class Candidate:
    card: CardInfo
    score: float
    image_similarity: float
    name_matched: bool
    number_matched: bool
    set_matched: bool


@dataclass
class RecognitionResult:
    source: str
    candidates: list
    card_jpeg: bytes
    outline_found: bool
    outline_method: str
    corners: np.ndarray | None
    corners_text: str
    upside_down: bool
    elapsed: float
    name_read: str | None
    border: str | None
    collector: CollectorLine
    pinned: bool
    shooting_star: float
    list_symbol: float
    pin_reason: str | None
    flag_reason: str | None
    file_path: str | None = None

    @property
    def best(self):
        return self.candidates[0] if self.candidates else None


@dataclass
class _Scored:
    p: PrintingKey
    score: float
    sim: float
    name: bool
    num: bool
    set: bool
    border_mismatch: bool
    year: bool
    size: bool


def _resize(src, w, h):
    return cv2.resize(src, (w, h), interpolation=cv2.INTER_AREA if src.shape[1] > w else cv2.INTER_CUBIC)


def _fmt_price(p: float) -> str:
    """C# {p:0.##}"""
    s = f"{p:.2f}".rstrip("0").rstrip(".")
    return s or "0"


def _group(p: PrintingKey) -> str:
    return p.set_code + "|" + p.number.rstrip("★")


def _split2(number: str):
    parts = number.split("-")
    return parts if len(parts) == 2 else None


class Recognizer:
    def __init__(self, catalog_dir: str, ocr_dir: str, assets_dir: str, threads: int | None = None):
        threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.manifest = json.load(open(os.path.join(catalog_dir, "manifest.json")))
        m = self.manifest["model"]
        self.index = FingerprintIndex(os.path.join(catalog_dir, "fingerprints.bin"),
                                      os.path.join(catalog_dir, "fingerprint_ids.txt"), int(m.get("dim", 384)))
        self.catalog = CardCatalog(os.path.join(catalog_dir, "catalog.sqlite"))
        self.fp = Fingerprinter(os.path.join(catalog_dir, m.get("file", "model.onnx")), m, threads)
        self.cards = CardIndex(os.path.join(catalog_dir, "catalog.sqlite"))
        self.ocr = CardTextReader(ocr_dir, threads)
        self.marks = vision.Marks(assets_dir)
        self.clahe = cv2.createCLAHE(2.5, (8, 8))
        self.set_lock: set[str] | None = None

    # ------------------------------------------------------------------ public
    def identify_jpeg(self, jpeg: bytes, source: str = "", top_k: int = 8, force_upside_down=None) -> RecognitionResult:
        photo = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if photo is None or photo.size == 0:
            raise ValueError("Couldn't open the photo.")
        return self.identify(photo, source, top_k, force_upside_down)

    @staticmethod
    def refine_crop(photo, result: RecognitionResult, reference) -> bytes | None:
        """Re-straighten by lining the photo up with a candidate's catalog image (Recognizer.RefineCrop)."""
        if not result.corners_text:
            return None
        corners = np.array([[float(v) for v in xy.split(",")] for xy in result.corners_text.split()], F32)
        better = vision.crop_refine(photo, corners, reference, result.upside_down)
        if better is None:
            return None
        card = detector.warp(photo, better, HI_W, HI_H)
        if result.upside_down:
            card = cv2.rotate(card, cv2.ROTATE_180)
        return cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()

    # ------------------------------------------------------------------ the pipeline
    def identify(self, photo, source: str = "", top_k: int = 8, force_upside_down=None) -> RecognitionResult:
        t0 = time.monotonic()
        det = detector.detect(photo)
        hi_up = detector.warp(photo, det.corners, HI_W, HI_H) if det.found else _resize(photo, HI_W, HI_H)
        hi_down = cv2.rotate(hi_up, cv2.ROTATE_180)
        hi = [hi_up, hi_down]
        small_up = _resize(hi_up, detector.WIDTH, detector.HEIGHT)
        small_down = _resize(hi_down, detector.WIDTH, detector.HEIGHT)
        vecs = self.fp.embed_batch([small_up, small_down])
        views = [1] if force_upside_down is True else [0] if force_upside_down is False else [0, 1]
        cards = self.cards
        coll_cache: dict = {}

        def read_collector(v, img=None, upscale=2.0):
            key = (v, upscale) if img is None else None
            if key is not None and key in coll_cache:
                return coll_cache[key]          # same image, same read: the C# reads it twice, the answer is the same
            c = self._read_collector(hi[v] if img is None else img, upscale)
            if key is not None:
                coll_cache[key] = c
            return c

        # 1. the name, from the top of the card, both ways up
        hits = []
        for v in views:
            hits += self._read_names(hi[v], v, True, MIN_NAME_SCORE)
        if not any(h[1] >= 0.9 for h in hits):
            for v in views:
                hits += self._read_names(self._enhance(hi[v]), v, True, MIN_NAME_SCORE)
        if not hits:
            for v in views:
                whole = _resize(hi[v], 732, 1020)
                hits += [h for h in self._read_names(whole, v, False, MIN_FALLBACK_NAME_SCORE) if len(h[0]) >= 5]

        # 2. which way up
        view = views[0]
        if len(views) == 2:
            def best_of(v):
                vals = [h[1] + IMAGE_WEIGHT * self._best_similarity(h[0], vecs[v]) for h in hits if h[3] == v]
                return max(vals) if vals else IMAGE_WEIGHT * self.index.search(vecs[v], 1)[0][1]
            view = 1 if best_of(1) > best_of(0) else 0

            def readable(v):
                c = read_collector(v)
                return any(cards.printings_at(sc, n) for sc in c.set_codes for n in c.numbers)
            up, down = readable(0), readable(1)
            if up != down:
                r = 0 if up else 1
                strong_other = any(h[3] != r and h[1] >= 0.99 and len(h[2]) >= 6 for h in hits)
                if not strong_other:
                    view = r
        vec = vecs[view]
        view_hits = [h for h in hits if h[3] == view]
        view_hits = [h for h in view_hits if not any(o[0] != h[0] and o[1] >= 0.9 and f" {h[0]} " in f" {o[0]} "
                                                     for o in view_hits)]

        # 3. collector line and border
        collector = read_collector(view)
        sharp = None

        def sharp_view():
            nonlocal sharp
            if sharp is None:
                s = detector.warp(photo, det.corners, HI_W * 2, HI_H * 2)
                sharp = cv2.rotate(s, cv2.ROTATE_180) if view == 1 else s
            return sharp
        if det.found and collector.set_codes and (
                collector.foil is None
                or not any(cards.printings_at(sc, n) for sc in collector.set_codes for n in collector.numbers)):
            collector = collector.merged(read_collector(view, sharp_view(), 1))
        if det.found and not collector.set_codes:
            collector = collector.with_copyright_numbers(self._read_copyright_line(sharp_view()))
        border = vision.border_classify(hi[view]) if det.found else None
        list_score = self.marks.list.score(hi[view])
        list_seen, list_absent = list_score >= vision.LIST_SEEN_AT, list_score < vision.LIST_ABSENT_BELOW

        # 4. score every printing the name or the collector line points at
        name_score: dict[str, float] = {}
        for h in view_hits:
            name_score[h[0]] = max(name_score.get(h[0], 0.0), h[1])
        pool: dict[str, PrintingKey] = {}
        lock = self.set_lock if self.set_lock else None
        allowed = (lambda p: True) if lock is None else (lambda p: p.set_code.lower() in lock)
        for key in name_score:
            for p in cards.printings_of_name(key):
                if allowed(p):
                    pool[p.id] = p
        for s in collector.set_codes:
            for n in collector.numbers:
                for p in cards.printings_at(s, n):
                    if allowed(p):
                        pool[p.id] = p
        picture_ids = set()
        if lock is None:
            for cid, _ in self.index.search(vec, PICTURE_CANDIDATES):
                p = cards.by_id_get(cid)
                if p is not None and cid not in pool:
                    pool[cid] = p
                    picture_ids.add(cid)
        else:
            close = [p for s in lock for p in cards.printings_in_set(s) if self.index.contains(p.id) and p.id not in pool]
            close = sorted(((p, self.index.similarity(vec, p.id)) for p in close), key=lambda t: -t[1])[:PICTURE_CANDIDATES]
            for p, _ in close:
                pool[p.id] = p
                picture_ids.add(p.id)
        outside_lock = None
        if lock is not None:
            strong = next((k for k, v in name_score.items() if v >= 0.95 and cards.printings_of_name(k)
                           and not any(allowed(p) for p in cards.printings_of_name(k))), None)
            other_set = next((sc for sc in collector.set_codes if sc not in lock
                              and any(cards.printings_at(sc, n) for n in collector.numbers)), None)
            if strong is not None:
                outside_lock = f"Not from the locked sets: the name reads as {cards.printings_of_name(strong)[0].name}."
            elif other_set is not None and not any(sc in lock for sc in collector.set_codes):
                outside_lock = f"Not from the locked sets: the set code reads {other_set.upper()}."

        cs = collector.set_codes

        def set_hit(p):
            sp = _split2(p.number)
            return (p.set_code.lower() in cs or ("prm" in cs and p.set_type == "promo")
                    or (p.set_code in ("plst", "ulst") and sp is not None and sp[0].lower() in cs))
        no_set_code = len(cs) == 0 or not any(set_hit(p) for p in pool.values())

        def sizes_of(p):
            sp = _split2(p.number)
            code = sp[0] if p.set_code in ("plst", "ulst") and sp is not None else p.set_code
            return self.catalog.set_sizes.get(code.lower())

        scored: list[_Scored] = []
        for p in pool.values():
            if not self.index.contains(p.id):
                continue
            sim = self.index.similarity(vec, p.id)
            ns = max(name_score.get(normalize(k), 0.0) for k in p.name.split(" // ") + [p.name])
            num = (p.number.lower().lstrip("0") in collector.numbers
                   or (no_set_code and collector.copyright_digits_contain(p.number)))
            st = p.set_code.lower() in cs or ("prm" in cs and p.set_type == "promo")
            is_list = p.set_code in ("plst", "ulst")
            sp = _split2(p.number)
            if is_list and sp is not None:
                num = num or sp[1].lower().lstrip("0") in collector.numbers or (no_set_code and collector.copyright_digits_contain(sp[1]))
                st = st or sp[0].lower() in cs
            pinned_by_collector = num and st
            bm = (p.border_color in ("black", "gold")) if border == "white" else (p.border_color == "white") if border == "black" else False
            year_match = collector.copyright_year is not None and p.release_year == collector.copyright_year
            sz = sizes_of(p)
            size_match = num and bool(collector.set_totals) and sz is not None and bool(sz & collector.set_totals)
            score = (IMAGE_WEIGHT * sim + ns + (NUMBER_BONUS if num else 0) + (SET_BONUS if st else 0)
                     + (BOTH_BONUS if pinned_by_collector else 0)
                     + (YEAR_BONUS if year_match and not pinned_by_collector else 0)
                     + (SIZE_BONUS if size_match and not pinned_by_collector else 0)
                     - (UNLIKELY_PENALTY if p.is_unlikely and not pinned_by_collector else 0)
                     - (BORDER_PENALTY if bm and not pinned_by_collector else 0)
                     + (LIST_BONUS if is_list and list_seen else 0)
                     - (LIST_PENALTY if is_list and list_absent else 0)
                     - (0.05 if is_list and not list_seen and not list_absent else 0)
                     - (LIST_PENALTY if not is_list and list_seen else 0))
            scored.append(_Scored(p, score, sim, ns > 0, num, st, bm and not pinned_by_collector, year_match, size_match))

        flag = None
        if not scored:
            for cid, s in self.index.search(vec, top_k):
                scored.append(_Scored(PrintingKey(cid), IMAGE_WEIGHT * s, s, False, False, False, False, False, False))
            flag = "Couldn't read the card's name or collector number — matched by picture only."
            if lock is not None and outside_lock is None:
                outside_lock = "Not from the locked sets: nothing in them looks like this card."
        scored.sort(key=lambda t: -t.score)
        shown = [t for i, t in enumerate(scored) if i == 0 or t.p.id not in picture_ids or t.num or t.sim >= 0.85]
        top = (shown[:1] + [t for t in shown[1:] if not t.border_mismatch] + [t for t in shown[1:] if t.border_mismatch])[:top_k]
        infos = self.catalog.get_many([t.p.id for t in top])
        candidates = [Candidate(infos[t.p.id], float(F32(t.score)), t.sim, t.name, t.num, t.set) for t in top if t.p.id in infos]

        best = candidates[0] if candidates else None
        if flag is None and best is not None:
            if not best.name_matched and not (best.number_matched and best.set_matched):
                flag = "Couldn't read the card's name — matched by collector line and picture."
            elif best.image_similarity < MIN_IMAGE_SIMILARITY and not (best.name_matched and best.number_matched and best.set_matched):
                flag = "The picture doesn't look much like the catalog image."
        pinned = best is not None and best.name_matched and best.number_matched and best.set_matched
        pin_reason = "name + set + number agree" if pinned else None
        best_is_list = best is not None and best.card.is_list_reprint
        if pinned and best_is_list:
            pin_reason = "name + set + number + List symbol"
        if best_is_list and not list_seen:
            pinned, pin_reason = False, None

        def list_doubt_for(name):
            return (not best_is_list and not list_absent
                    and any(c.card.is_list_reprint and c.card.name == name for c in candidates))
        list_doubt = best is not None and list_doubt_for(best.card.name)

        def list_fits(p):
            return (not list_absent) if p.set_code in ("plst", "ulst") else (not list_seen)

        def first_per_group(items):
            seen, out = set(), []
            for t in items:
                g = _group(t.p)
                if g not in seen:
                    seen.add(g)
                    out.append(t)
            return out

        if not pinned and best is not None and best.name_matched and best.number_matched and no_set_code:
            same = first_per_group([t for t in scored if t.name and t.num and t.p.name == best.card.name
                                    and (list_fits(t.p) or t.p.id == best.card.id)])
            best_group = _group(next(t for t in scored if t.p.id == best.card.id).p)
            mine = next((t for t in same if _group(t.p) == best_group), None)
            if len(same) == 1:
                pinned, pin_reason = True, "name + number (no set code printed)"
            elif sum(1 for t in same if t.year) == 1 and mine is not None and mine.year:
                pinned, pin_reason = True, "name + number + copyright year"
        if (not pinned and best is not None and best.name_matched and best.number_matched and collector.set_totals
                and (not best_is_list or list_seen)):
            same = first_per_group([t for t in scored if t.name and t.num and t.p.name == best.card.name
                                    and (list_fits(t.p) or t.p.id == best.card.id)])
            sized = [t for t in same if t.size]
            if len(sized) == 1 and sized[0].p.id == best.card.id and not list_doubt_for(best.card.name):
                pinned = True
                pin_reason = f"name + number + set size (/{'/'.join(str(x) for x in collector.set_totals)})"
        if (not pinned and best is not None and best.name_matched and no_set_code and collector.copyright_year is not None
                and (not best_is_list or list_seen)):
            named = first_per_group([t for t in scored if t.name and t.p.name == best.card.name and list_fits(t.p)])
            year_ones = [t for t in named if t.year]
            if len(year_ones) == 1 and year_ones[0].p.id == best.card.id and not list_doubt_for(best.card.name):
                pinned, pin_reason = True, "name + copyright year (the only printing from that year)"
        if (not pinned and best is not None and best.name_matched and no_set_code and collector.has_copyright_text
                and (not best_is_list or list_seen)):
            possible = first_per_group([t for t in scored if t.name and t.p.name == best.card.name and list_fits(t.p)
                                        and not t.border_mismatch and not t.p.is_unlikely and t.p.release_year >= 1995])
            if len(possible) == 1 and possible[0].p.id == best.card.id and not list_doubt_for(best.card.name):
                pinned, pin_reason = True, "name + copyright line (the only printing since 1995 with this border)"
        if (not pinned and best_is_list and list_seen and best.name_matched
                and sum(1 for t in scored if t.p.name == best.card.name and t.p.set_code in ("plst", "ulst")) == 1):
            pinned, pin_reason = True, "name + List symbol (its only List printing)"
        if not pinned and border is not None and best is not None and best.name_matched:
            possible = [t for t in scored if t.name and t.p.name == best.card.name and not t.border_mismatch
                        and not t.p.is_unlikely and t.p.border_color in ("white", "black")]
            if len(possible) == 1 and possible[0].p.id == best.card.id:
                pinned, pin_reason = True, f"name + {border} border (the only {border}-bordered printing)"
        if (not pinned and best is not None and best.number_matched and best.set_matched and not best.name_matched
                and best.image_similarity >= MIN_PIN_SIMILARITY):
            pinned, pin_reason = True, "set + number + picture (name not readable)"
            if flag is not None and flag.startswith("Couldn't read the card's name"):
                flag = None
        if not pinned and best is not None and best.number_matched and best.set_matched:
            fp = next((t.p for t in scored if t.p.id == best.card.id), None)
            if fp is not None and fp.lang != "en" and (fp.lang == "ja" or collector.foreign_language):
                pinned = True
                pin_reason = f"set + number + {collector.language or fp.lang.upper()} marker ({best.card.language_name} printing)"
                if flag is not None and flag.startswith("Couldn't read the card's name"):
                    flag = None

        if list_doubt:
            pinned, pin_reason = False, None
        if outside_lock is not None:
            pinned, pin_reason, flag = False, None, outside_lock
        if (flag is None and best is not None and not pinned and not list_seen and not list_absent
                and any(c.card.is_list_reprint and c.card.name == best.card.name for c in candidates)):
            flag = "Might be a List reprint — check the bottom-left corner for the List symbol."
        if flag is None and best is not None and not pinned:
            rival = next((c for c in candidates[1:] if c.card.name == best.card.name), None)
            p1 = _price(best.card)
            p2 = 0.0 if rival is None else _price(rival.card)
            hi_p, lo_p = max(p1, p2), max(min(p1, p2), 0.01)
            if rival is not None and hi_p >= 20 and hi_p / lo_p >= 2 and best.score - rival.score < F32(0.15):
                flag = (f"Look-alike printings with very different prices ({best.card.set_code.upper()} ${_fmt_price(p1)} vs "
                        f"{rival.card.set_code.upper()} ${_fmt_price(p2)}) — double-check the edition.")

        jpeg = cv2.imencode(".jpg", hi[view], [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
        name_read = max(view_hits, key=lambda h: h[1])[2] if view_hits else None
        return RecognitionResult(
            source=source, candidates=candidates, card_jpeg=jpeg, outline_found=det.found, outline_method=det.method,
            corners=det.corners, corners_text=" ".join(f"{c[0]:.1f},{c[1]:.1f}" for c in det.corners) if det.found else "",
            upside_down=view == 1, elapsed=time.monotonic() - t0, name_read=name_read, border=border,
            collector=collector, pinned=pinned, shooting_star=self.marks.shooting.score(hi[view]), list_symbol=list_score,
            pin_reason=pin_reason, flag_reason=flag)

    # ------------------------------------------------------------------ helpers
    def _best_similarity(self, key, vec) -> float:
        best = 0.0
        for p in self.cards.printings_of_name(key):
            best = max(best, self.index.similarity(vec, p.id))
        return best

    def _read_names(self, card, view, top_only, min_score):
        """[(name key, score, raw text, view)]"""
        region = card[0:int(card.shape[0] * 0.20), 0:int(card.shape[1] * 0.85)] if top_only else card
        found = []
        for text in _line_texts(self.ocr.read(region)):
            m = self.cards.match_name(text, min_score)
            if m is not None and not (m[1] < 1 and normalize(text) in RULES_WORDS):
                found.append((m[0], m[1], text, view))
        return found

    def _read_collector(self, card, upscale=2.0) -> CollectorLine:
        y0 = int(card.shape[0] * 0.88)
        bottom = card[y0:, 0:int(card.shape[1] * 0.62)]
        big = cv2.resize(bottom, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC) if upscale > 1 else bottom.copy()
        lines = sorted(self.ocr.read(big), key=lambda l: l.top)
        return CollectorLine.parse(" ".join(l.text for l in lines))

    def _read_copyright_line(self, card) -> str:
        y0 = int(card.shape[0] * 0.88)
        bottom = card[y0:, 0:int(card.shape[1] * 0.95)]
        max_left = card.shape[1] * F32(0.70)
        lines = [l for l in self.ocr.read(bottom) if l.box[:, 0].min() < max_left]
        return " ".join(l.text for l in sorted(lines, key=lambda l: l.top))

    def _enhance(self, bgr):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(self.clahe.apply(gray), cv2.COLOR_GRAY2BGR)


def _price(c: CardInfo) -> float:
    for v in (c.price_usd, c.price_usd_foil, c.price_usd_etched):
        if v is not None:
            return v
    return 0.0


def _line_texts(lines: list[TextLine]):
    """Each OCR line, plus words on the same row joined together ("Lightning" + "Bolt")."""
    out = [l.text for l in lines]
    rows: list[list[TextLine]] = []
    for l in sorted(lines, key=lambda l: l.top):
        h = float(l.box[:, 1].max()) - l.top
        row = next((r for r in rows if abs(r[0].top - l.top) < h * 0.5), None)
        if row is None:
            rows.append([l])
        else:
            row.append(l)
    for row in rows:
        if len(row) > 1:
            out.append(" ".join(l.text for l in sorted(row, key=lambda l: l.left)))
    return out
