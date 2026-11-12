"""End-to-end test of the catalog build using fake cards, local images and a randomly
initialised model (no internet needed).

    cd catalog-builder && python -m tests.test_build
"""

from __future__ import annotations

import json
import random
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from builder import fingerprints  # noqa: E402


DIM = 3 * 8 * 8


def export_tiny_model(path: Path) -> None:
    import torch

    class Tiny(torch.nn.Module):
        def forward(self, x):
            v = torch.nn.functional.avg_pool2d(x, kernel_size=(38, 28), stride=(38, 28))[:, :, :8, :8].flatten(1)
            v = v - v.mean(dim=1, keepdim=True)
            return v / (v.norm(dim=1, keepdim=True) + 1e-8)

    torch.onnx.export(Tiny(), torch.zeros(1, 3, 308, 224), str(path), input_names=["image"],
                      output_names=["fingerprint"], opset_version=17, dynamo=False,
                      dynamic_axes={"image": {0: "batch"}, "fingerprint": {0: "batch"}})


def make_card(i, name, set_code, num, released, img_dir, frame="2015",
              finishes=("nonfoil", "foil"), promo=(), lang="en", digital=False, layout="normal"):
    cid = f"{i:08d}-0000-4000-8000-000000000000"
    img = img_dir / f"{cid}.jpg"
    rng = random.Random(i)
    im = Image.new("RGB", (488, 680), tuple(rng.randint(0, 255) for _ in range(3)))
    d = ImageDraw.Draw(im)
    for _ in range(30):
        x, y = rng.randint(0, 440), rng.randint(0, 640)
        d.ellipse([x, y, x + rng.randint(20, 200), y + rng.randint(20, 200)],
                  fill=tuple(rng.randint(0, 255) for _ in range(3)))
    im.save(img, "JPEG", quality=92)
    return {
        "id": cid, "oracle_id": f"o-{name}", "name": name, "lang": lang, "digital": digital,
        "games": ["paper"], "layout": layout, "set": set_code, "set_name": set_code.upper(),
        "set_type": "expansion", "collector_number": num, "released_at": released,
        "rarity": "common", "type_line": "Instant", "colors": ["U"], "color_identity": ["U"],
        "frame": frame, "border_color": "black", "full_art": False, "finishes": list(finishes),
        "promo_types": list(promo), "prices": {"usd": "0.10", "usd_foil": "0.50"},
        "image_status": "highres_scan", "image_uris": {"normal": f"file://{img}"},
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="catalog_test_"))
    try:
        imgs = tmp / "imgs"; imgs.mkdir()
        cards, i = [], 0
        for n in range(6):
            i += 1; cards.append(make_card(i, f"Old {n}", "3ed", str(n + 1), "1994-04-01", imgs, "1993", ("nonfoil",)))
        for n in range(6):
            i += 1; cards.append(make_card(i, f"New {n}", "ltr", str(n + 1), "2023-06-23", imgs))
        i += 1; cards.append(make_card(i, "Island", "ltr", "715", "2023-06-23", imgs, finishes=("foil",), promo=("surgefoil",)))
        i += 1; cards.append(make_card(i, "Island", "ltr", "274", "2023-06-23", imgs, lang="ja"))   # kept (Japanese-only printing)
        i += 1; cards.append(make_card(i, "Island", "ltr", "275", "2023-06-23", imgs, lang="de"))   # skipped
        bulk = tmp / "bulk.json"
        bulk.write_text(json.dumps(cards))

        # The real model is verified separately (export once, ONNX check in the workflow).
        # A random-weight ViT outputs near-identical vectors, so the test uses a tiny
        # stand-in model with the same inputs/outputs: an 8x8 colour thumbnail.
        model = tmp / "model.onnx"
        export_tiny_model(model)

        # Build 1: from scratch
        pack1 = tmp / "pack1"
        assert build.main(["--model", str(model), "--out", str(pack1), "--bulk-file", str(bulk),
                           "--work", str(tmp / "work")]) == 0
        m = json.loads((pack1 / "manifest.json").read_text())
        assert m["cards"] == 14 and m["fingerprints"] == 14, m
        assert m["model"]["dim"] == DIM

        # Build 2: with one new card; everything else must be reused
        i += 1; cards.append(make_card(i, "Brand New", "ltr", "800", "2023-06-23", imgs))
        bulk.write_text(json.dumps(cards))
        pack2 = tmp / "pack2"
        assert build.main(["--model", str(model), "--out", str(pack2), "--bulk-file", str(bulk),
                           "--previous", str(pack1), "--work", str(tmp / "work")]) == 0
        m2 = json.loads((pack2 / "manifest.json").read_text())
        assert m2["fingerprints"] == 15

        # Reused fingerprints must equal the originals exactly
        ids1 = (pack1 / "fingerprint_ids.txt").read_text().split()
        ids2 = (pack2 / "fingerprint_ids.txt").read_text().split()
        v1 = np.fromfile(pack1 / "fingerprints.bin", dtype="<f2").reshape(-1, DIM)
        v2 = np.fromfile(pack2 / "fingerprints.bin", dtype="<f2").reshape(-1, DIM)
        for cid, v in zip(ids1, v1):
            assert np.array_equal(v, v2[ids2.index(cid)])

        # Matching: each catalog image must find itself (real blur robustness needs real weights;
        # the cloud build checks that)
        mdl = fingerprints.Model(str(model))
        hits = 0
        for cid in ids2:
            with Image.open(imgs / f"{cid}.jpg") as im:
                q = mdl.embed(fingerprints.preprocess(im)[None])[0]
            best = ids2[int(np.argmax(v2.astype(np.float32) @ q))]
            hits += best == cid
        print(f"Self-match (tiny test model, exact image): {hits}/{len(ids2)}")
        assert hits == len(ids2)

        con = sqlite3.connect(pack2 / "catalog.sqlite")
        assert con.execute("SELECT special_foil FROM cards WHERE collector_number='715'").fetchone()[0] == "Surge Foil"
        rules = dict(con.execute("SELECT set_code, indicator FROM set_foil_rules"))
        assert rules == {"3ed": "nonfoil_only", "ltr": "collector_star"}, rules
        con.close()
        print("ALL BUILD TESTS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
