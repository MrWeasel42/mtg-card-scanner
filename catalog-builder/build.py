"""Builds the downloadable catalog pack that the app uses.

    python build.py --model model.onnx --out pack/ [--previous prev_pack/]

Output (all in --out):
  catalog.sqlite         every English paper printing + per-set foil rules + prices
  fingerprints.bin       float16 little-endian, N x DIM, row i belongs to line i of the ids file
  fingerprint_ids.txt    one Scryfall card id per line
  manifest.json          versions, model preprocessing contract, file sizes and SHA-256 hashes

The model file itself is published separately (it rarely changes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from builder import db, fingerprints, foil_rules, scryfall

USER_AGENT = "MTGCardScanner/1.0 (+https://github.com/MrWeasel42/mtg-card-scanner)"
MODEL_VERSION = "dinov2s-224x308-v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_previous(prev: Path | None) -> dict[str, tuple[str, np.ndarray]]:
    """card_id -> (image_url, fingerprint) from the last published pack, if compatible."""
    if not prev or not (prev / "manifest.json").exists():
        return {}
    manifest = json.loads((prev / "manifest.json").read_text())
    if manifest.get("model", {}).get("version") != MODEL_VERSION:
        print("Previous catalog used a different model; rebuilding all fingerprints.")
        return {}
    dim = manifest["model"]["dim"]
    ids = (prev / "fingerprint_ids.txt").read_text().split()
    vecs = np.fromfile(prev / "fingerprints.bin", dtype="<f2").reshape(-1, dim)
    con = sqlite3.connect(prev / "catalog.sqlite")
    urls = dict(con.execute("SELECT id, image_url FROM cards"))
    con.close()
    return {cid: (urls.get(cid, ""), v) for cid, v in zip(ids, vecs)}


def local_or_http_fetcher():
    http = fingerprints.http_fetcher(USER_AGENT)

    def fetch(url: str) -> bytes:
        if url.startswith("file://"):
            return Path(url[7:]).read_bytes()
        return http(url)

    return fetch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--previous", type=Path)
    ap.add_argument("--bulk-file", type=Path, help="Use a local Scryfall bulk JSON (testing)")
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--overrides", type=Path, default=Path(__file__).parent / "foil_overrides.yaml")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)

    print("== Card data ==")
    if args.bulk_file:
        bulk, updated = args.bulk_file, "local"
    else:
        bulk, updated = scryfall.download_bulk(USER_AGENT, "default_cards", args.work / "bulk.json")

    print("== Database ==")
    db_path = args.out / "catalog.sqlite"
    db_path.unlink(missing_ok=True)
    con = db.connect(db_path)
    records = (r for r in map(scryfall.to_record, scryfall.iter_raw_cards(bulk)) if r)
    n_cards = db.replace_cards(con, records)
    print(f"{n_cards:,} printings")

    print("== Foil rules ==")
    print(foil_rules.build_rules(con, args.overrides))

    print("== Fingerprints ==")
    previous = load_previous(args.previous)
    rows = list(con.execute("SELECT id, image_url FROM cards ORDER BY id"))
    reused: dict[str, np.ndarray] = {}
    todo = []
    for r in rows:
        prev = previous.get(r["id"])
        if prev and prev[0] == r["image_url"]:
            reused[r["id"]] = prev[1]
        else:
            todo.append((r["id"], r["image_url"]))
    print(f"Reusing {len(reused):,}, computing {len(todo):,}")

    model = fingerprints.Model(str(args.model))
    new_ids, new_vecs, failed = fingerprints.build(todo, model, local_or_http_fetcher())
    fresh = dict(zip(new_ids, new_vecs))

    ids, vecs = [], []
    for r in rows:
        v = fresh.get(r["id"])
        if v is None:
            v = reused.get(r["id"])
        if v is not None:
            ids.append(r["id"])
            vecs.append(v)
    matrix = np.stack(vecs).astype("<f2")
    dim = int(matrix.shape[1])
    print(f"{len(ids):,} fingerprints ({len(failed):,} images failed)")

    # Safety net: never publish a catalog that lost a big chunk of cards.
    if len(previous) and len(ids) < 0.95 * len(previous):
        print(f"ERROR: fingerprint count fell from {len(previous):,} to {len(ids):,}. Not publishing.")
        return 1

    matrix.tofile(args.out / "fingerprints.bin")
    (args.out / "fingerprint_ids.txt").write_text("\n".join(ids) + "\n")

    now = datetime.now(timezone.utc)
    db.set_meta(con, "scryfall_updated_at", updated)
    db.set_meta(con, "built_at", now.isoformat(timespec="seconds"))
    con.execute("VACUUM")
    con.close()

    files = {}
    for name in ["catalog.sqlite", "fingerprints.bin", "fingerprint_ids.txt"]:
        p = args.out / name
        files[name] = {"size": p.stat().st_size, "sha256": sha256(p)}

    manifest = {
        "format": 1,
        "catalog_version": now.strftime("%Y.%m.%d.%H%M"),
        "built_at": now.isoformat(timespec="seconds"),
        "scryfall_updated_at": updated,
        "cards": n_cards,
        "fingerprints": len(ids),
        "model": {
            "version": MODEL_VERSION,
            "file": "model.onnx",
            "sha256": sha256(args.model),
            "size": args.model.stat().st_size,
            "input_name": "image",
            "output_name": "fingerprint",
            "width": fingerprints.WIDTH,
            "height": fingerprints.HEIGHT,
            "mean": fingerprints.MEAN,
            "std": fingerprints.STD,
            "resize": "bicubic",
            "dim": dim,
        },
        "files": files,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Catalog {manifest['catalog_version']} ready in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
