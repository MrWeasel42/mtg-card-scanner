"""Wall round every heat-set insert hole (and every M2 pilot): rays from the hole's axis outward, at several depths;
the material between the hole and the next surface is the wall. Flags walls under 1.2 mm (Ruthex wants ~1.6)."""
import sys, json, math, os
import numpy as np, trimesh
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from holes import holes
from sorter import placed, M3_INSERT, PILOT_M2
P = placed()
HERE = os.path.dirname(os.path.abspath(__file__))
rep = []
SKIP = ("door_",)                       # door barrels: 2.2 pin holes, not pilots
for name, shp in P.items():
    hs = [h for h in holes(shp.val()) if abs(h["r"] - M3_INSERT / 2) < 0.02 or abs(h["r"] - PILOT_M2 / 2) < 0.02]
    if name.startswith(("bin_side_back",)):
        hs = [h for h in hs if not (abs(h["r"] - PILOT_M2 / 2) < 0.02 and abs(h["d"][0]) > 0.99 and abs(h["t1"] - h["t0"]) > 50)]   # hinge pin bore
    if not hs:
        continue
    m = trimesh.load(os.path.join(HERE, "placed", name + ".stl"))
    for h in hs:
        d = np.asarray(h["d"]); a = np.cross(d, [0, 0, 1] if abs(d[2]) < 0.9 else [1, 0, 0]); a /= np.linalg.norm(a); b = np.cross(d, a)
        L = h["t1"] - h["t0"]
        walls = []
        for f in (0.15, 0.5, 0.85):
            c = h["p"] + d * (h["t0"] + f * L)
            for k in range(16):
                u = math.cos(2 * math.pi * k / 16) * a + math.sin(2 * math.pi * k / 16) * b
                o = c + u * (h["r"] - 0.05)          # just inside the hole wall
                locs, _, _ = m.ray.intersects_location([o], [u], multiple_hits=True)
                if len(locs) == 0:
                    continue
                ts = np.unique(np.round((locs - o) @ u, 3)); ts = ts[ts > 0.0]
                # the first hit must be the hole's own wall (0.05 away); otherwise this depth is outside the part
                if len(ts) >= 2 and ts[0] < 0.2:
                    walls.append(ts[1] - ts[0])
        if walls:
            w = float(np.min(walls))
            kind = "insert" if abs(h["r"] - M3_INSERT / 2) < 0.02 else "M2 pilot"
            rep.append(dict(part=name, kind=kind, at=[round(x, 1) for x in (h["p"] + d * (h["t0"] + h["t1"]) / 2)], wall=round(w, 2)))
bad = [r for r in rep if r["wall"] < 1.2]
json.dump(rep, open(os.path.join(HERE, "insert_walls.json"), "w"), indent=1)
seen = set()
for r in sorted(bad, key=lambda r: r["wall"]):
    k = (r["part"].split("_")[0] + r["part"].split("_")[1] if "_" in r["part"] else r["part"], r["kind"])
    print("THIN", r)
print(len(rep), "holes checked,", len(bad), "with walls under 1.2 mm")
