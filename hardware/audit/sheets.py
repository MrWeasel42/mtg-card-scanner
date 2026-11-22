"""One sheet per printed part: iso, top, front and side views from the STL, with its size, quantity and print notes."""
import sys, os, json
import numpy as np, trimesh, vtk
from PIL import Image, ImageDraw, ImageFont
from viz import Scene, HERE
from sorter import PRINTED, STAGES
STL = os.path.join(HERE, "..", "mtg-card-scanner", "hardware", "stl") if len(sys.argv) < 2 else sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "sheets")
os.makedirs(OUT, exist_ok=True)
VIEWS = [("iso", (-1, -1.3, 0.9)), ("top", (0, 0, 1)), ("front", (0, -1, 0)), ("side", (1, 0, 0))]
try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20); FB = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
except Exception:
    F = FB = ImageFont.load_default()
meta = {}
for name, (fn, mat, note) in PRINTED.items():
    m = trimesh.load(os.path.join(STL, name + ".stl")); c = m.bounds.mean(0); ext = m.extents; R = np.linalg.norm(ext) * 1.6
    tiles = []
    for v, d in VIEWS:
        sc = Scene(600, 420, bg=(1, 1, 1)); sc.ren.GradientBackgroundOff()
        sc.add(name, m, kind="petg")
        d = np.asarray(d, float); d /= np.linalg.norm(d)
        up = (0, 0, 1) if v != "top" else (0, 1, 0)
        sc.camera(tuple(c + d * R * 2.2), tuple(c), up=up, angle=24)
        cam = sc.ren.GetActiveCamera(); cam.ParallelProjectionOn(); sc.ren.ResetCamera(); cam.SetParallelScale(cam.GetParallelScale() * 0.92)
        p = f"/tmp/sheet_{v}.png"; sc.png(p); tiles.append((v, Image.open(p)))
    W, H = 1200, 960
    im = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(im)
    for k, (v, t) in enumerate(tiles):
        x, y = (k % 2) * 600, 80 + (k // 2) * 420
        im.paste(t, (x, y)); dr.text((x + 12, y + 8), v, fill=(90, 90, 100), font=F)
    q = sum(STAGES[name])
    dr.text((20, 18), f"{name}   x{q}   {mat}", fill=(15, 20, 30), font=FB)
    dr.text((20, 905), f"{ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm ({ext[0]/25.4:.2f} x {ext[1]/25.4:.2f} x {ext[2]/25.4:.2f} in)   rev H   {note}"[:150], fill=(40, 40, 50), font=F)
    im.save(os.path.join(OUT, name + ".png"))
    meta[name] = dict(qty=q, stages=STAGES[name], mat=mat, note=note, x=round(float(ext[0]), 1), y=round(float(ext[1]), 1), z=round(float(ext[2]), 1))
    print(name, flush=True)
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
