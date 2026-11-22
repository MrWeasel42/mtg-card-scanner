"""Fake photos of real cards for the Pi-engine parity check (CI).

    python make_photos.py <catalog.sqlite> <out dir> [count]

Random real printings (fixed seed) plus some that exercise the special rules (white borders, The List, old frames,
Secret Lair), each pasted into a photo: the machine's view (green scan floor, nearly straight, 4056 x 3040) and
phone-style photos (tilted, dark or light table, some upside down).
"""
import json
import os
import random
import sqlite3
import sys
import urllib.request

import cv2
import numpy as np

UA = "MTGCardScanner-CI/1.0 (+https://github.com/MrWeasel42/mtg-card-scanner)"


def picks(db, n, rng):
    con = sqlite3.connect(db)
    base = "SELECT id, name, set_code, collector_number, image_url FROM cards WHERE layout NOT IN ('token','double_faced_token','emblem','art_series') AND image_url LIKE 'https://%'"
    rows = con.execute(base).fetchall()
    rng.shuffle(rows)
    out = rows[:n]
    for extra in ("border_color = 'white'", "set_code = 'plst'", "frame = '1997'", "set_code = 'sld'", "frame = '1993'"):
        some = con.execute(base + " AND " + extra).fetchall()
        rng.shuffle(some)
        out += some[:max(2, n // 10)]
    return out


def paste(card, size, bg, angle, scale, upside_down, rng):
    W, H = size
    photo = np.empty((H, W, 3), np.uint8)
    photo[:] = bg
    noise = rng.normal(0, 4, photo.shape)
    photo = np.clip(photo + noise, 0, 255).astype(np.uint8)
    if upside_down:
        card = cv2.rotate(card, cv2.ROTATE_180)
    ch = H * scale
    cw = ch * 63 / 88
    cx, cy = W / 2 + rng.uniform(-0.04, 0.04) * W, H / 2 + rng.uniform(-0.04, 0.04) * H
    a = np.deg2rad(angle)
    ux, uy = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
    c = np.array([cx, cy])
    dst = np.array([c - ux * cw / 2 - uy * ch / 2, c + ux * cw / 2 - uy * ch / 2,
                    c + ux * cw / 2 + uy * ch / 2, c - ux * cw / 2 + uy * ch / 2], np.float32)
    src = np.array([[0, 0], [card.shape[1] - 1, 0], [card.shape[1] - 1, card.shape[0] - 1], [0, card.shape[0] - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(card, m, (W, H), flags=cv2.INTER_CUBIC)
    mask = cv2.warpPerspective(np.full(card.shape[:2], 255, np.uint8), m, (W, H))
    photo[mask > 127] = warped[mask > 127]
    return cv2.GaussianBlur(photo, (3, 3), 0)


def main():
    db, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    rng = random.Random(42)
    nrng = np.random.default_rng(42)
    os.makedirs(out, exist_ok=True)
    truth = {}
    k = 0
    for cid, name, setc, num, url in picks(db, n, rng):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url.replace("/normal/", "/large/"), headers={"User-Agent": UA}), timeout=30).read()
        except Exception:
            continue
        card = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if card is None:
            continue
        k += 1
        kind = k % 4
        if kind == 0:     # the machine: green floor, nearly straight, full HQ-camera size
            photo = paste(card, (4056, 3040), (60, 120, 70), rng.uniform(-2, 2), 0.78, rng.random() < 0.5, nrng)
        elif kind == 1:   # dark table
            photo = paste(card, (2000, 1500), (40, 38, 45), rng.uniform(-15, 15), 0.75, False, nrng)
        elif kind == 2:   # light table
            photo = paste(card, (2000, 1500), (205, 210, 215), rng.uniform(-12, 12), 0.72, False, nrng)
        else:             # upside down on wood
            photo = paste(card, (2000, 1500), (60, 95, 140), rng.uniform(-10, 10), 0.75, True, nrng)
        f = f"p{k:03d}.jpg"
        cv2.imwrite(os.path.join(out, f), photo, [cv2.IMWRITE_JPEG_QUALITY, 90])
        truth[f] = {"id": cid, "name": name, "set": setc, "number": num, "kind": ["machine", "dark", "light", "upside down"][kind]}
        print(f, name, setc, num, truth[f]["kind"], flush=True)
    json.dump(truth, open(os.path.join(out, "truth.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
