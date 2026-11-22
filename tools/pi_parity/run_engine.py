"""The Pi's engine (machine/sorter/engine) on a folder of photos, writing the same JSON as tools/CardScanner.Parity.

    python run_engine.py <catalog dir> <photos dir> <catalog pictures dir> <out.json>
"""
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "machine", "sorter"))
from engine import local, vision  # noqa: E402
from engine.recognizer import Recognizer  # noqa: E402


def main():
    cat, photos, pics, out = sys.argv[1:5]
    t = time.monotonic()
    rec = Recognizer(cat, local.OCR_DIR, local.ASSETS_DIR)
    load_s = time.monotonic() - t
    results, machine = [], []
    machine_id = local.LocalIdentifier(os.path.dirname(os.path.abspath(out)), recognizer=rec, pictures_dir=pics)
    for f in sorted(glob.glob(os.path.join(photos, "*.jpg"))):
        jpeg = open(f, "rb").read()
        photo = cv2.imread(f, cv2.IMREAD_COLOR)
        r = rec.identify(photo, os.path.basename(f))
        top = r.best
        pic = lambda c: (p if os.path.exists(p := os.path.join(pics, c.id + "_large.jpg")) else None)
        refine = None
        card_jpeg = r.card_jpeg
        if top is not None and pic(top.card) and r.outline_found:
            ref = cv2.imread(pic(top.card), cv2.IMREAD_COLOR)
            corners = np.array([[float(v) for v in xy.split(",")] for xy in r.corners_text.split()], np.float32)
            better = vision.crop_refine(photo, corners, ref, r.upside_down)
            refine = None if better is None else better.tolist()
            j = rec.refine_crop(photo, r, ref)
            if j:
                card_jpeg = j
        star = list(vision.star_mark_score(card_jpeg))
        detail = None
        if top is not None:
            group = [(c.card.id, pic(c.card)) for c in r.candidates if c.card.name == top.card.name and pic(c.card)]
            if len(group) >= 2:
                detail = [{"id": i, "score": s} for i, s in vision.detail_scores(card_jpeg, group)]
        c = r.collector
        results.append({
            "file": os.path.basename(f), "ms": int(r.elapsed * 1000), "outline": r.outline_found, "method": r.outline_method,
            "corners": r.corners_text, "upsideDown": r.upside_down, "nameRead": r.name_read,
            "collector": {"raw": c.raw, "numbers": sorted(c.numbers), "sets": sorted(c.set_codes), "foil": c.foil,
                          "year": c.copyright_year, "lang": c.language, "totals": sorted(c.set_totals)},
            "border": r.border, "list": r.list_symbol, "shootingStar": r.shooting_star, "pinned": r.pinned,
            "pinReason": r.pin_reason, "flagReason": r.flag_reason,
            "candidates": [{"id": x.card.id, "name": x.card.name, "set": x.card.set_code, "number": x.card.collector_number,
                            "score": x.score, "sim": x.image_similarity, "nameMatched": x.name_matched,
                            "numberMatched": x.number_matched, "setMatched": x.set_matched} for x in r.candidates],
            "refine": refine, "star": star, "detail": detail})
        # and the whole answer the machine acts on (recognizer + checks), timed like a real card
        t = time.monotonic()
        a = machine_id.identify(jpeg)
        machine.append({"file": os.path.basename(f), "ms": int((time.monotonic() - t) * 1000), "ok": a.get("ok"),
                        "card": (a.get("card") or {}).get("id"), "pinned": a.get("pinned"), "pinReason": a.get("pinReason"),
                        "flagReason": a.get("flagReason"), "finish": a.get("finish"), "finishUnsure": a.get("finishUnsure")})
        print(f"{os.path.basename(f)}: {top.card.name if top else None} {top.card.set_code if top else ''} "
              f"#{top.card.collector_number if top else ''}{' PIN' if r.pinned else ''} {int(r.elapsed * 1000)} ms", flush=True)
    json.dump({"catalog": rec.manifest.get("catalog_version"), "loadSeconds": round(load_s, 1), "results": results,
               "machine": machine}, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
