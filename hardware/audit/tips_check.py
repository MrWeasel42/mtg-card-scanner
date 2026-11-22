"""Checks taken from the 'Everything I know about 3D Printing' tips, run on every printed part in its print orientation:
  1. sideways holes (axis flat on the bed) >= 5 mm across that are plain round (no teardrop / pointed roof)
  2. downward steps: a wider hole below a narrower coaxial one (counterbore / pocket opening toward the bed) -> the
     narrower hole starts in mid-air; wants a 0.2 mm sacrificial bridge layer
  3. convex round-over on the first layer (fillet at the bed edge) -> should be a chamfer
  4. tall parts on a small footprint -> brim / mouse ears
"""
import os, sys, json, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
import numpy as np, trimesh
from printability import ORIENT, CANDS, contact_area, STL
import printability as P
from holes import holes
from sorter import PRINTED

def orient(name):
    m = trimesh.load(f"{STL}/{name}.stl")
    o = ORIENT[name]
    if isinstance(o, str):
        best = None
        for T in CANDS[o]:
            mm = m.copy(); mm.apply_transform(T); a = contact_area(mm)
            if best is None or a > best[0]: best = (a, T)
        o = best[1]
    m.apply_transform(o); off = -m.bounds[0]; m.apply_translation(off)
    T = o.copy(); T[:3, 3] += off
    return m, T

out = {}
for name in ORIENT:
    if name not in PRINTED: continue
    m, T = orient(name)
    shape = PRINTED[name][0]()
    shape = shape.val() if hasattr(shape, "val") else shape
    R = T[:3, :3]
    hs = []
    for h in holes(shape):
        d = R @ h["d"]; p = R @ h["p"] + T[:3, 3]
        hs.append(dict(r=h["r"], d=d, a=p + d * h["t0"] if True else None, b=p + d * h["t1"], full=h["full"]))
        # note: 'a','b' = axis end points in print frame (p is the axis point closest to origin in part frame)
    res = {"side_round": [], "steps": [], "bed_fillet": None, "tall": None}
    # 1. sideways holes
    for h in hs:
        if abs(h["d"][2]) < 0.05 and h["r"] >= 2.5 and h["full"] > 0.5:
            mid = (h["a"] + h["b"]) / 2
            probe = mid + np.array([0, 0, h["r"] + 0.4])
            if m.contains([probe])[0]:       # material right above the round roof -> plain round hole, no teardrop
                res["side_round"].append(dict(d=round(2 * h["r"], 2), at=[round(x, 1) for x in mid], len=round(float(np.linalg.norm(h["b"] - h["a"])), 1)))
    # 2. downward steps on vertical holes
    vert = [h for h in hs if abs(abs(h["d"][2]) - 1) < 1e-3]
    for h in vert:
        lo, hi = sorted([h["a"][2], h["b"][2]])
        for g in vert:
            if g is h or g["r"] <= h["r"] + 0.3: continue
            if np.linalg.norm((g["a"] - h["a"])[:2]) > 0.05: continue
            glo, ghi = sorted([g["a"][2], g["b"][2]])
            if abs(ghi - lo) < 0.05:          # wide hole ends exactly where the narrow one starts, wide one below
                res["steps"].append(dict(narrow=round(2 * h["r"], 2), wide=round(2 * g["r"], 2), z=round(lo, 2),
                                         at=[round(float(x), 1) for x in h["a"][:2]]))
    # 3. first-layer round-over: faces in the bottom 1.5 mm whose normal points down-and-out at 50..85 degrees, curved
    z = m.triangles_center[:, 2]; n = m.face_normals
    band = (z < 1.5) & (z > 0.05) & (n[:, 2] < -0.17) & (n[:, 2] > -0.94)
    a = m.area_faces[band].sum()
    res["bed_fillet"] = round(float(a), 1) if a > 3 else 0
    # 4. tall on a small footprint
    ext = m.bounds[1]; foot = contact_area(m)
    res["tall"] = dict(h=round(float(ext[2]), 1), foot=round(float(foot), 0), ratio=round(float(ext[2]) / max(1, math.sqrt(foot)), 2))
    out[name] = res
    print(f"{name:20s} side_round {len(res['side_round'])} steps {len(res['steps'])} bed_fillet {res['bed_fillet']} h/sqrt(foot) {res['tall']['ratio']}")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tips_check.json"), "w"), indent=1, default=float)
