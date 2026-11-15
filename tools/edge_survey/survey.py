"""Which scan-floor colour contrasts best with the edges of every Magic card?

Downloads Scryfall's small image (146x204) of every paper printing (front face), samples the band 2-5% in from
each edge (the printed border, or the art on borderless cards; corners skipped), and scores candidate floor
colours by how many edge pixels are close to them in CIELAB (dE < 25: hard to tell apart under real lighting).
"""
import concurrent.futures as cf, io, json, sys, time, collections
import numpy as np, requests, cv2

import os, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "catalog-builder"))
from builder import scryfall   # same downloader as the catalog build (handles Scryfall's bulk-list quirks)

UA = {"User-Agent": "MTGCardScanner-edge-survey/1.0", "Accept": "*/*"}
s = requests.Session(); s.headers.update(UA)
bulk_path, _ = scryfall.download_bulk("MTGCardScanner-edge-survey/1.0", "default_cards", pathlib.Path("bulk.json"))
items = []
for c in scryfall.iter_raw_cards(bulk_path):
    if c.get("lang") not in ("en", None):
        continue
    if c.get("digital") or "paper" not in (c.get("games") or []) or c.get("layout") in ("art_series", "token", "double_faced_token", "emblem"):
        continue
    iu = c.get("image_uris") or ((c.get("card_faces") or [{}])[0].get("image_uris") or {})
    if iu.get("small"):
        items.append((iu["small"], c.get("border_color", ""), c.get("frame", ""), bool(c.get("full_art")), c.get("released_at", "")[:4]))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if limit: items = items[::max(1, len(items) // limit)]
print(f"{len(items):,} printings", flush=True)

def edge(url):
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200:
                im = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if im is None: return None
                im = cv2.resize(im, (146, 204), interpolation=cv2.INTER_AREA)
                H, W = im.shape[:2]; a, b = int(0.02 * W) or 1, int(0.05 * W) + 1; cy, cx = int(0.07 * H), int(0.07 * W)
                ring = np.concatenate([im[a:b, cx:W - cx].reshape(-1, 3), im[H - b:H - a, cx:W - cx].reshape(-1, 3),
                                       im[cy:H - cy, a:b].reshape(-1, 3), im[cy:H - cy, W - b:W - a].reshape(-1, 3)])
                return ring
            time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    return None

rings, meta = [], []
t0 = time.time()
with cf.ThreadPoolExecutor(12) as ex:
    for i, (ring, it) in enumerate(zip(ex.map(edge, [x[0] for x in items]), items)):
        if ring is not None:
            rings.append(ring[::3]); meta.append(it)
        if i % 5000 == 0: print(f"{i:,} / {len(items):,}  {time.time() - t0:.0f}s", flush=True)
print(f"measured {len(rings):,} cards", flush=True)

px = np.concatenate(rings).astype(np.uint8).reshape(-1, 1, 3)
lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
lab[:, 0] *= 100 / 255; lab[:, 1:] -= 128
hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV).reshape(-1, 3)
out = []
def p(line): print(line); out.append(line)
V = hsv[:, 2]
p(f"# Card edge colours across {len(rings):,} Scryfall printings\n")
p(f"Edge pixels: dark (V<60) {100*(V<60).mean():.1f}%, light (V>190) {100*(V>190).mean():.1f}%, in between {100*((V>=60)&(V<=190)).mean():.1f}%")
bc = collections.Counter(m[1] for m in meta)
p("Border colours: " + ", ".join(f"{k or '?'} {100*v/len(meta):.1f}%" for k, v in bc.most_common()))
p(f"Full-art / borderless share: {100*sum(m[3] or m[1]=='borderless' for m in meta)/len(meta):.1f}%\n")
H = hsv[:, 0].astype(int) * 2; S = hsv[:, 1]
sat = S > 90
names = ["red", "orange", "yellow", "yellow-green", "green", "green-cyan", "cyan", "azure", "blue", "violet", "magenta", "pink-red"]
hb = collections.Counter(((H[sat] + 15) // 30 % 12).tolist())
p("Saturated edge pixels by hue (% of all edge pixels): " + ", ".join(f"{names[k]} {100*hb.get(k,0)/len(H):.2f}%" for k in range(12)) + "\n")

def to_lab(rgb):
    c = cv2.cvtColor(np.uint8([[rgb[::-1]]]), cv2.COLOR_BGR2LAB).reshape(3).astype(np.float32)
    c[0] *= 100 / 255; c[1:] -= 128; return c
sample = lab[np.random.default_rng(1).choice(len(lab), min(len(lab), 3_000_000), replace=False)]
def score(rgb):
    d = np.sqrt(((sample - to_lab(rgb)) ** 2).sum(1))
    return 100 * (d < 25).mean(), 100 * (d < 40).mean(), float(np.percentile(d, 1))
named = {"#808080 mid grey": (128, 128, 128), "#A9A9A9 dark grey (light)": (169, 169, 169), "#FF00FF magenta": (255, 0, 255),
         "#C42EA0 matte magenta": (196, 46, 160), "#3D943E matte green": (61, 148, 62), "#00B140 chroma green": (0, 177, 64),
         "#0047BB chroma blue": (0, 71, 187), "#569BD2 sky blue": (86, 155, 210), "#E66E28 orange": (230, 110, 40),
         "#FFFFFF white": (255, 255, 255), "#000000 black": (0, 0, 0)}
p("| Floor colour | edge pixels within dE 25 | within dE 40 | closest 1% of edges (dE) |\n|---|---|---|---|")
for n, rgb in named.items():
    a, b, c = score(rgb); p(f"| {n} | {a:.2f}% | {b:.2f}% | {c:.1f} |")
best = []
for r in range(0, 256, 17):
    for g in range(0, 256, 17):
        for b2 in range(0, 256, 17):
            a, b, c = score((r, g, b2)); best.append((a, b, -c, (r, g, b2)))
best.sort()
p("\nBest colours on a full RGB grid (fewest edge pixels close to them):\n\n| Colour | within dE 25 | within dE 40 | closest 1% (dE) |\n|---|---|---|---|")
for a, b, c, rgb in best[:15]:
    p(f"| #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} | {a:.3f}% | {b:.2f}% | {-c:.1f} |")
open("edge_survey.md", "w").write("\n".join(out) + "\n")
