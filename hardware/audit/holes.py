import os
"""Every cylindrical hole on every placed part: radius, axis line, extent along the axis, whether it goes
through the part's material (both ends open) — from the B-rep, merged across split faces."""
import sys, json, math, pickle
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
import numpy as np
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_REVERSED

def holes(shape):
    out = []
    for f in shape.Faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        if not ((f.wrapped.Orientation() == TopAbs_REVERSED) == cyl.Direct()):
            continue                                   # a boss / outside of a cylinder, not a hole
        ax = cyl.Axis(); d = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
        p = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
        k = int(np.argmax(np.abs(d)))
        if d[k] < 0: d = -d
        vs = np.array([[v.X, v.Y, v.Z] for v in f.Vertices()]) if f.Vertices() else None
        if vs is None or len(vs) == 0:
            bb = f.BoundingBox(); vs = np.array([[bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmax]])
        t = (vs - p) @ d
        # canonical axis point: closest point on the axis to the origin
        p0 = p - d * (p @ d)
        out.append(dict(r=cyl.Radius(), d=d, p=p0, t0=float(t.min() + p @ d), t1=float(t.max() + p @ d), area=f.Area()))
    merged = []
    for h in out:
        for g in merged:
            if abs(g["r"] - h["r"]) < 0.005 and abs(abs(g["d"] @ h["d"]) - 1) < 1e-5 and np.linalg.norm(g["p"] - h["p"]) < 0.05 \
               and h["t0"] <= g["t1"] + 0.05 and g["t0"] <= h["t1"] + 0.05:
                g["t0"] = min(g["t0"], h["t0"]); g["t1"] = max(g["t1"], h["t1"]); g["area"] += h["area"]; break
        else:
            merged.append(dict(h))
    for g in merged:
        g["full"] = g["area"] / (2 * math.pi * g["r"] * max(1e-6, g["t1"] - g["t0"]))   # 1 = full round hole, <1 = partial (slot end, cut by something)
    return merged

if __name__ == "__main__":
    from sorter import placed
    P = placed()
    H = {}
    for k, v in P.items():
        H[k] = [dict(r=round(h["r"], 3), d=[round(x, 4) for x in h["d"]], p=[round(x, 3) for x in h["p"]], t0=round(h["t0"], 3),
                     t1=round(h["t1"], 3), full=round(h["full"], 2)) for h in holes(v.val())]
    json.dump(H, open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "holes.json"), "w"))
    print(sum(len(v) for v in H.values()), "holes on", len(H), "parts")
