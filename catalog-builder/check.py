"""Accuracy check on a freshly built catalog: downloads random card images, roughens them
like a camera would (tilt, blur, lighting, JPEG), and checks the right printing comes back.

    python check.py --pack pack/ --model model.onnx --count 300
"""

from __future__ import annotations

import argparse
import io
import os
import random
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from build import USER_AGENT
from builder import fingerprints


def roughen(img: Image.Image, rng: random.Random) -> Image.Image:
    img = img.convert("RGB")
    img = img.rotate(rng.uniform(-2, 2), resample=Image.BICUBIC, fillcolor=(30, 30, 30))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.85, 1.15))
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.85, 1.15))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 1.2)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=rng.randint(60, 90))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--count", type=int, default=300)
    args = ap.parse_args()

    dim = None
    import json
    manifest = json.loads((args.pack / "manifest.json").read_text())
    dim = manifest["model"]["dim"]
    ids = (args.pack / "fingerprint_ids.txt").read_text().split()
    vecs = np.fromfile(args.pack / "fingerprints.bin", dtype="<f2").reshape(-1, dim).astype(np.float32)
    con = sqlite3.connect(args.pack / "catalog.sqlite")
    info = {r[0]: r[1:] for r in con.execute("SELECT id, name, set_code, collector_number, image_url FROM cards")}

    rng = random.Random(42)
    sample = rng.sample(ids, min(args.count, len(ids)))
    model = fingerprints.Model(str(args.model))
    fetch = fingerprints.http_fetcher(USER_AGENT)

    exact = same_name = 0
    misses = []
    for cid in sample:
        img = roughen(Image.open(io.BytesIO(fetch(info[cid][3]))), rng)
        q = model.embed(fingerprints.preprocess(img)[None])[0]
        best = ids[int(np.argmax(vecs @ q))]
        if best == cid:
            exact += 1
        elif info[best][0] == info[cid][0]:
            same_name += 1
        else:
            misses.append((cid, best))

    n = len(sample)
    lines = [
        f"### Accuracy check ({n} random cards, simulated camera blur/tilt/lighting)",
        f"- Exact printing: **{exact}/{n} ({100 * exact / n:.1f}%)**",
        f"- Right card, different printing: {same_name}/{n} (the collector-number reader fixes most of these)",
        f"- Wrong card: {len(misses)}/{n}",
    ]
    for cid, best in misses[:15]:
        a, b = info[cid], info[best]
        lines.append(f"  - {a[0]} ({a[1].upper()} #{a[2]}) → {b[0]} ({b[1].upper()} #{b[2]})")
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
