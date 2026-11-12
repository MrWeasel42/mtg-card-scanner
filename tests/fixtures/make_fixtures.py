"""Builds a tiny catalog pack for the C# tests, using the real Python catalog builder.

The C# tests then identify these cards, which proves the C# preprocessing and matching
agree with the Python side that builds the real catalog.

    python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "catalog-builder"))

import build  # noqa: E402
from tests.test_build import export_tiny_model, make_card  # noqa: E402

OUT = ROOT / "tests" / "CardScanner.Core.Tests" / "Fixtures"


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        imgs = OUT / "cards"
        if OUT.exists():
            shutil.rmtree(OUT)
        imgs.mkdir(parents=True)
        cards = [make_card(i + 1, f"Test Card {i}", "tst", str(i + 1), "2024-01-01", imgs) for i in range(8)]
        for c in cards:  # store PNG so the C# test reads exactly what Python fingerprinted
            src = Path(c["image_uris"]["normal"][7:])
            png = src.with_suffix(".png")
            from PIL import Image
            Image.open(src).save(png)
            src.unlink()
            c["image_uris"]["normal"] = f"file://{png}"
        bulk = tmp / "bulk.json"
        bulk.write_text(json.dumps(cards))
        model = OUT / "model.onnx"
        export_tiny_model(model)
        build.main(["--model", str(model), "--out", str(OUT), "--bulk-file", str(bulk), "--work", str(tmp)])
        # The test manifest records the tiny model's real hash; image URLs point at local files.
        print("Fixtures written to", OUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
