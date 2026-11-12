"""Makes a fingerprint for every card image using the ONNX model.

Images are streamed: download a chunk, fingerprint it, throw the pixels away. Nothing is
kept on disk, so a cloud runner never runs out of space. Fingerprints from the previous
catalog are reused for any card whose image hasn't changed, so weekly builds only process
new cards.

The preprocessing here is the contract the C# app must match exactly:
  RGB -> resize to WIDTH x HEIGHT (bicubic) -> /255 -> (x - MEAN) / STD -> CHW float32
"""

from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np
import onnxruntime as ort
import requests
from PIL import Image
from tqdm import tqdm

WIDTH, HEIGHT = 224, 308
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

_MEAN = np.array(MEAN, dtype=np.float32)
_STD = np.array(STD, dtype=np.float32)


def preprocess(img: Image.Image) -> np.ndarray:
    img = img.convert("RGB").resize((WIDTH, HEIGHT), Image.BICUBIC)
    arr = (np.asarray(img, dtype=np.float32) / 255.0 - _MEAN) / _STD
    return arr.transpose(2, 0, 1)


class Model:
    def __init__(self, path: str):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
        out = self.session.get_outputs()[0]
        self.dim = out.shape[1]

    def embed(self, batch: np.ndarray) -> np.ndarray:
        return self.session.run(None, {"image": batch.astype(np.float32)})[0]


def http_fetcher(user_agent: str) -> Callable[[str], bytes]:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "image/*"})
    session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8))

    def fetch(url: str) -> bytes:
        for attempt in range(5):
            try:
                r = session.get(url, timeout=30)
                if r.status_code == 429:
                    time.sleep(2 + 2 * attempt)
                    continue
                r.raise_for_status()
                return r.content
            except requests.RequestException:
                if attempt == 4:
                    raise
                time.sleep(1 + attempt)
        raise RuntimeError(f"could not download {url}")

    return fetch


def build(
    todo: list[tuple[str, str]],
    model: Model,
    fetch: Callable[[str], bytes],
    workers: int = 8,
    chunk: int = 256,
    batch: int = 32,
) -> tuple[list[str], np.ndarray, list[str]]:
    """todo: (card_id, image_url). Returns (ids, fingerprints, failed_ids)."""
    ids: list[str] = []
    vecs: list[np.ndarray] = []
    failed: list[str] = []

    def load(item):
        card_id, url = item
        try:
            with Image.open(io.BytesIO(fetch(url))) as im:
                return card_id, preprocess(im)
        except Exception:
            return card_id, None

    with ThreadPoolExecutor(max_workers=workers) as pool, tqdm(total=len(todo), unit="card", mininterval=10) as bar:
        for start in range(0, len(todo), chunk):
            loaded = list(pool.map(load, todo[start:start + chunk]))
            good = [(cid, arr) for cid, arr in loaded if arr is not None]
            failed += [cid for cid, arr in loaded if arr is None]
            for b in range(0, len(good), batch):
                part = good[b:b + batch]
                out = model.embed(np.stack([a for _, a in part]))
                ids += [cid for cid, _ in part]
                vecs.append(out.astype(np.float16))
            bar.update(len(loaded))

    dim = model.dim if isinstance(model.dim, int) else 0
    matrix = np.concatenate(vecs) if vecs else np.zeros((0, dim), dtype=np.float16)
    return ids, matrix, failed
