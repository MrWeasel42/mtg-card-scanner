"""The card catalog, the AI fingerprints and the name index: copies of src/CardScanner.Core/Catalog/*.cs and
Recognition/{CardIndex,FingerprintIndex,Fingerprinter}.cs. Same files as the Windows app: the published
catalog-latest release (catalog.sqlite, fingerprints.bin, fingerprint_ids.txt, manifest.json) + model-v1."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import urllib.request
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort
from rapidfuzz.distance import LCSseq
from rapidfuzz.process import cdist

F32 = np.float32
RELEASE_BASE = "https://github.com/MrWeasel42/mtg-card-scanner/releases/download"
MODEL_TAGS = {"dinov2s-224x308-v1": "model-v1"}
UA = "MTGCardScanner-Pi/1.0 (+https://github.com/MrWeasel42/mtg-card-scanner)"

LANGUAGE_NAMES = {"en": "English", "ja": "Japanese", "de": "German", "fr": "French", "it": "Italian", "es": "Spanish",
                  "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "zhs": "Chinese Simplified",
                  "zht": "Chinese Traditional", "ph": "Phyrexian", "kl": "Klingon", "qkl": "Klingon", "tlh": "Klingon",
                  "qya": "Quenya", "la": "Latin"}


# ------------------------------------------------------------------------------------------------ files
def files_ready(d: str) -> bool:
    try:
        m = json.load(open(os.path.join(d, "manifest.json")))
    except (OSError, ValueError):
        return False
    return os.path.exists(os.path.join(d, "model.onnx")) and all(os.path.exists(os.path.join(d, f)) for f in m["files"])


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _get(url: str, timeout=60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()


def update_catalog(d: str, progress=lambda text: None) -> dict:
    """Downloads whatever is missing or out of date (each file checked against its SHA-256), like the PC app's
    CatalogUpdater. Nothing replaces the working files until everything has downloaded and checked out."""
    os.makedirs(d, exist_ok=True)
    remote = json.loads(_get(f"{RELEASE_BASE}/catalog-latest/manifest.json"))
    model = remote["model"]
    tag = MODEL_TAGS.get(model["version"])
    if tag is None:
        raise RuntimeError(f"This machine software doesn't know model '{model['version']}': press Update.")
    jobs = []
    if not (os.path.exists(os.path.join(d, model["file"])) and sha256(os.path.join(d, model["file"])) == model["sha256"]):
        jobs.append((model["file"], f"{RELEASE_BASE}/{tag}/{model['file']}", model["sha256"], model["size"]))
    for name, info in remote["files"].items():
        p = os.path.join(d, name)
        if not (os.path.exists(p) and sha256(p) == info["sha256"]):
            jobs.append((name, f"{RELEASE_BASE}/catalog-latest/{name}", info["sha256"], info["size"]))
    staging = os.path.join(d, "staging")
    os.makedirs(staging, exist_ok=True)
    total, done = sum(j[3] for j in jobs) or 1, 0
    for name, url, sha, size in jobs:
        tmp = os.path.join(staging, name)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                progress(f"Downloading the card catalog: {done * 100 // total}%")
        if sha256(tmp) != sha:
            raise RuntimeError(f"{name} was corrupted during download. Try again.")
    for name, *_ in jobs:
        os.replace(os.path.join(staging, name), os.path.join(d, name))
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(remote, f, indent=1)
    return remote


# ------------------------------------------------------------------------------------------------ card info
@dataclass
class CardInfo:
    id: str
    name: str
    set_code: str
    set_name: str
    collector_number: str
    released_at: str
    frame: str
    finishes: str
    promo_types: str
    special_foil: str
    price_usd: float | None
    price_usd_foil: float | None
    price_usd_etched: float | None
    image_url: str
    rarity: str = ""
    colors: str = ""
    type_line: str = ""
    lang: str = "en"

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES.get(self.lang, self.lang)

    @property
    def is_list_reprint(self) -> bool:
        return self.set_code in ("plst", "ulst")

    def finish_keys(self) -> list[str]:
        k = [x.strip() for x in self.finishes.split(",") if x.strip()]
        return k or ["nonfoil", "foil"]

    def json(self) -> dict:
        """The same card JSON the PC app answers the machine with (IdentifyViewModel.Machine.cs CardJson)."""
        return {"id": self.id, "name": self.name, "setCode": self.set_code, "setName": self.set_name,
                "number": self.collector_number, "rarity": self.rarity, "colors": self.colors, "typeLine": self.type_line,
                "lang": self.lang, "finishes": [x.strip() for x in self.finishes.split(",") if x.strip()],
                "prices": {"nonfoil": self.price_usd, "foil": self.price_usd_foil, "etched": self.price_usd_etched},
                "imageUrl": self.image_url}


_BASE_COLUMNS = ("id, name, set_code, set_name, collector_number, released_at, frame, finishes, promo_types, "
                 "special_foil, price_usd, price_usd_foil, price_usd_etched, image_url, rarity, colors, type_line")


def _connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return con


class CardCatalog:
    def __init__(self, db_path: str):
        self._con = _connect(db_path)
        has = lambda sql: self._con.execute(sql).fetchone() is not None
        self._cols = _BASE_COLUMNS + (", lang" if has("SELECT 1 FROM pragma_table_info('cards') WHERE name = 'lang'") else ", 'en'")
        self.set_sizes: dict[str, set[int]] = {}
        if has("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'set_info'"):
            for code, size in self._con.execute("SELECT set_code, printed_size FROM set_info WHERE printed_size > 0"):
                self.set_sizes.setdefault(code.lower(), set()).add(int(size))

    @staticmethod
    def _read(r) -> CardInfo:
        s = lambda v: "" if v is None else str(v)
        f = lambda v: None if v is None else float(v)
        return CardInfo(r[0], r[1], r[2], r[3], r[4], s(r[5]), s(r[6]), s(r[7]), s(r[8]), s(r[9]), f(r[10]), f(r[11]),
                        f(r[12]), s(r[13]), s(r[14]), s(r[15]), s(r[16]), s(r[17]) or "en")

    def get_many(self, ids) -> dict[str, CardInfo]:
        ids = list(ids)
        if not ids:
            return {}
        q = f"SELECT {self._cols} FROM cards WHERE id IN ({','.join('?' * len(ids))})"
        return {c.id: c for c in map(self._read, self._con.execute(q, ids))}

    def get(self, cid: str) -> CardInfo | None:
        return self.get_many([cid]).get(cid)

    def printings_of(self, name: str) -> list[CardInfo]:
        return [self._read(r) for r in self._con.execute(
            f"SELECT {self._cols} FROM cards WHERE name = ? ORDER BY released_at", (name,))]

    def search_names(self, text: str, limit: int = 12) -> list[CardInfo]:
        text = (text or "").strip()
        if not text:
            return []
        out, seen = [], set()
        for r in self._con.execute(f"SELECT {self._cols} FROM cards WHERE name LIKE ? ORDER BY (name LIKE ?) DESC, "
                                   "length(name), released_at DESC", (f"%{text}%", f"{text}%")):
            c = self._read(r)
            if c.name.lower() not in seen:
                seen.add(c.name.lower())
                out.append(c)
                if len(out) >= limit:
                    break
        return out


# ------------------------------------------------------------------------------------------------ name index
_SPACES = re.compile(" {2,}")


def normalize(s: str) -> str:
    """Lowercase, Æ -> ae, accents and punctuation removed, single spaces (CardIndex.Normalize)."""
    s = unicodedata.normalize("NFD", s.replace("Æ", "Ae").replace("æ", "ae"))
    out = []
    for ch in s:
        if unicodedata.category(ch) == "Mn":
            continue
        c = ch.lower()
        if len(c) == 1 and ("a" <= c <= "z" or "0" <= c <= "9" or c == " "):
            out.append(c)
    return _SPACES.sub(" ", "".join(out)).strip()


def similarity(a: str, b: str) -> float:
    """2 * LCS / (len a + len b), same as rapidfuzz's fuzz.ratio / 100."""
    if not a and not b:
        return 1.0
    return 2.0 * LCSseq.similarity(a, b) / (len(a) + len(b))


def collector_key(set_code: str, number: str) -> str:
    return set_code.lower() + "|" + number.lower().lstrip("0")


@dataclass(frozen=True)
class PrintingKey:
    id: str
    name: str = ""
    set_code: str = ""
    number: str = ""
    layout: str = ""
    set_type: str = ""
    border_color: str = ""
    release_year: int = 0
    lang: str = "en"

    @property
    def is_unlikely(self) -> bool:
        return self.set_type == "memorabilia" or self.set_code in ("sum", "ath", "brb", "btd", "dkm")


NOT_REAL_CARDS = {"token", "double_faced_token", "emblem", "art_series"}


class CardIndex:
    def __init__(self, db_path: str):
        con = _connect(db_path)
        has_lang = con.execute("SELECT 1 FROM pragma_table_info('cards') WHERE name = 'lang'").fetchone() is not None
        rows = con.execute("SELECT id, name, set_code, collector_number, layout, set_type, border_color, released_at"
                           + (", lang" if has_lang else ", 'en'") + " FROM cards")
        self.by_name: dict[str, list[PrintingKey]] = {}
        self.by_collector: dict[str, list[PrintingKey]] = {}
        self.by_id: dict[str, PrintingKey] = {}
        self.by_set: dict[str, list[PrintingKey]] = {}
        n = 0
        for r in rows:
            rel = r[7] or ""
            year = int(rel[:4]) if len(rel) >= 4 and rel[:4].isdigit() else 0
            p = PrintingKey(r[0], r[1], r[2], r[3], r[4] or "", r[5] or "", r[6] or "", year, r[8] or "en")
            n += 1
            self.by_id[p.id] = p
            if p.layout not in NOT_REAL_CARDS and p.lang == "en":
                faces = p.name.split(" // ") + [p.name]
                for face in dict.fromkeys(faces):
                    key = normalize(face)
                    if key:
                        self.by_name.setdefault(key, []).append(p)
            self.by_set.setdefault(p.set_code.lower(), []).append(p)
            self.by_collector.setdefault(collector_key(p.set_code, p.number), []).append(p)
        con.close()
        self.count = n
        names = list(self.by_name)
        # Fuzzy matching goes through names by length, then in catalog order (the C# loop): the first best wins.
        order = sorted(range(len(names)), key=lambda i: (len(names[i]), i))
        self._names = [names[i] for i in order]
        self._lens = np.array([len(x) for x in self._names])

    def by_id_get(self, cid: str) -> PrintingKey | None:
        return self.by_id.get(cid)

    def printings_in_set(self, code: str) -> list[PrintingKey]:
        return self.by_set.get(code.lower(), [])

    def printings_of_name(self, key: str) -> list[PrintingKey]:
        return self.by_name.get(key, [])

    def printings_at(self, set_code: str, number: str) -> list[PrintingKey]:
        return self.by_collector.get(collector_key(set_code, number), [])

    def match_name(self, text: str, min_score: float = 0.8):
        q = normalize(text)
        if len(q) < 3:
            return None
        if q in self.by_name:
            return q, 1.0
        import math
        lo = int(math.ceil(len(q) * min_score / (2 - min_score)))
        hi = int(math.floor(len(q) * (2 - min_score) / min_score))
        a, b = np.searchsorted(self._lens, lo, "left"), np.searchsorted(self._lens, hi, "right")
        if a >= b:
            return None
        cand = self._names[a:b]
        lcs = cdist([q], cand, scorer=LCSseq.similarity, dtype=np.int32)[0]
        scores = 2.0 * lcs / (len(q) + self._lens[a:b])
        i = int(np.argmax(scores))                         # first maximum, like the C# "s > best" loop
        if scores[i] > min_score:
            return cand[i], float(scores[i])
        return None


# ------------------------------------------------------------------------------------------------ fingerprints
class FingerprintIndex:
    def __init__(self, bin_path: str, ids_path: str, dim: int):
        ids = [l for l in open(ids_path, encoding="utf-8").read().splitlines() if l]
        v = np.fromfile(bin_path, dtype="<f2").astype(F32)
        if v.size != len(ids) * dim:
            raise ValueError(f"Fingerprint file has {v.size // max(dim, 1)} rows but {len(ids)} ids")
        self.ids = ids
        self.vectors = v.reshape(len(ids), dim)
        self.row = {cid: i for i, cid in enumerate(ids)}
        self.dim = dim

    def contains(self, cid: str) -> bool:
        return cid in self.row

    def similarity(self, q: np.ndarray, cid: str) -> float:
        r = self.row.get(cid)
        return 0.0 if r is None else float(np.dot(self.vectors[r], q))

    def search(self, q: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        scores = self.vectors @ q
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.lexsort((top, -scores[top]))]
        return [(self.ids[i], float(scores[i])) for i in top]


class Fingerprinter:
    """RGB, bicubic resize, /255, (x - mean) / std, CHW: must match catalog-builder/builder/fingerprints.py."""

    def __init__(self, model_path: str, info: dict, threads: int):
        o = ort.SessionOptions()
        o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        o.intra_op_num_threads = threads
        self._s = ort.InferenceSession(model_path, o, providers=["CPUExecutionProvider"])
        self.w, self.h = int(info.get("width", 224)), int(info.get("height", 308))
        self.mean = np.array(info.get("mean", [0.485, 0.456, 0.406]), F32)
        self.std = np.array(info.get("std", [0.229, 0.224, 0.225]), F32)
        self.input = info.get("input_name", "image")
        self.dim = int(info.get("dim", 384))

    def embed_batch(self, cards) -> np.ndarray:
        batch = []
        for c in cards:
            r = cv2.resize(c, (self.w, self.h), interpolation=cv2.INTER_CUBIC)
            rgb = r[:, :, ::-1].astype(F32)
            batch.append(((rgb / F32(255) - self.mean) / self.std).transpose(2, 0, 1))
        out = self._s.run(None, {self.input: np.ascontiguousarray(np.stack(batch))})[0]
        return out[:, :self.dim].astype(F32)
