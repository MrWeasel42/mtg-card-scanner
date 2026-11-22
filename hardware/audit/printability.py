"""Audit 1: every printed part on its own, in the orientation it's printed in.
Bed fit, islands (start in mid-air: need support), big overhangs, thin walls (< 2 extrusions), enclosed voids."""
import sys, json, math, os
import numpy as np, trimesh
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

STL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stl")
BED = (225.0, 225.0, 265.0)        # Neptune 4 Pro build volume
LH = 0.2
def R(axis, deg):
    return trimesh.transformations.rotation_matrix(math.radians(deg), {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis])
UP = np.eye(4)
PY_DOWN, NY_DOWN = R("x", -90), R("x", 90)          # +Y face on the bed / -Y face on the bed
PX_DOWN, NX_DOWN = R("y", 90), R("y", -90)
FLIP = R("y", 180)                                     # +Z face on the bed
ORIENT = {  # how each part sits on the bed (from the print notes)
    "back_panel": PY_DOWN, "back_panel_hub": PY_DOWN, "bay_cover": "auto_y", "belt_drill_jig": UP, "bin": UP,
    "bin_side_back": UP, "bin_side_front": NY_DOWN, "camera_plate": UP, "door": FLIP, "idler_slider": "auto_x", "joint_plate": "auto_y",
    "raw_tower": UP, "single_tower": UP, "double_tower": UP, "electronics_tray": UP, "end_cap": "auto_x",
    "end_ramp": "auto", "end_side_back": UP, "end_side_front": NY_DOWN, "exit_roller": PY_DOWN, "feed_roller": PY_DOWN,
    "feeder_base": UP, "fin": "auto_x", "fin_gauge": UP, "fit_coupon": UP, "gate_plate": PX_DOWN, "hood": UP, "hood_lid": FLIP,
    "inlet_plate": "auto_y", "motor_standoff": "auto_x", "mount_wall": "auto", "pod_cover": PY_DOWN, "polarizer_cap": UP,
    "pressure_bridge": FLIP, "psu_cradle": "auto_x", "scan_floor": FLIP, "scan_side_back": UP, "scan_side_front": UP,
    "screen_cradle": "auto_y", "servo_link": UP, "sheen_cap": PY_DOWN, "stack_weight": UP, "tie_bar": FLIP,
    "track_pulley_drive": NY_DOWN, "track_pulley_idler": PY_DOWN,
}
CANDS = {"auto": [UP, FLIP, PY_DOWN, NY_DOWN, PX_DOWN, NX_DOWN], "auto_x": [PX_DOWN, NX_DOWN], "auto_y": [PY_DOWN, NY_DOWN]}

def contact_area(m):
    z0 = m.bounds[0][2]
    f = m.triangles_center[:, 2] < z0 + 1e-3
    return m.area_faces[f & (m.face_normals[:, 2] < -0.99)].sum()

def place(name):
    m = trimesh.load(os.path.join(STL, name + ".stl"))
    o = ORIENT[name]
    if isinstance(o, str):
        best = None
        for T in CANDS[o]:
            mm = m.copy(); mm.apply_transform(T)
            a = contact_area(mm)
            if best is None or a > best[0]:
                best = (a, T)
        o = best[1]
    m.apply_transform(o)
    m.apply_translation(-m.bounds[0])
    return m

def to_polys(sec):
    if sec is None:
        return Polygon()
    polys = [p.buffer(0) for p in sec.polygons_full]
    return unary_union(polys) if polys else Polygon()

def audit(name):
    m = place(name)
    ext = m.bounds[1]
    res = {"part": name, "size": [round(float(x), 1) for x in ext], "watertight": bool(m.is_watertight)}
    res["fits_bed"] = bool(ext[0] <= BED[0] and ext[1] <= BED[1] and ext[2] <= BED[2]) or bool(ext[1] <= BED[0] and ext[0] <= BED[1] and ext[2] <= BED[2])
    shells = m.split(only_watertight=False)
    res["shells"] = len(shells)          # > 1: an enclosed void (or loose piece)
    zs = np.arange(LH / 2, ext[2], LH)
    secs = m.section_multiplane(plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], heights=list(zs))
    prev = None
    islands, overh, thin = [], [], []
    for z, s in zip(zs, secs):
        cur = to_polys(s)
        if cur.is_empty:
            prev = cur; continue
        if prev is not None and z > LH:
            sup = prev.buffer(LH * math.tan(math.radians(50)))       # 50 degree overhang is fine unsupported
            parts = list(cur.geoms) if isinstance(cur, MultiPolygon) else [cur]
            for p in parts:
                if p.area > 0.5 and not p.intersects(prev):
                    c = p.centroid; islands.append((round(z, 1), round(p.area, 1), round(c.x, 1), round(c.y, 1)))
            d = cur.difference(sup)
            if d.area > 2.0:
                for g in (d.geoms if hasattr(d, "geoms") else [d]):
                    if g.area > 2.0:
                        rr = g.minimum_rotated_rectangle
                        xy = np.array(rr.exterior.coords)[:4]
                        e = sorted([np.linalg.norm(xy[1] - xy[0]), np.linalg.norm(xy[2] - xy[1])])
                        c = g.centroid; overh.append((round(z, 1), round(g.area, 1), round(c.x, 1), round(c.y, 1), round(e[0], 1), round(e[1], 1)))
        # thin walls: anything narrower than 0.8 mm (2 lines of a 0.4 nozzle) vanishes under an opening
        op = cur.buffer(-0.38).buffer(0.38)
        lost = cur.difference(op)
        if lost.area > 0.3:
            for g in (lost.geoms if hasattr(lost, "geoms") else [lost]):
                if g.area > 0.3 and g.length > 2:
                    c = g.centroid; thin.append((round(z, 1), round(g.area, 2), round(c.x, 1), round(c.y, 1)))
        prev = cur
    res["islands"] = islands; res["overhangs"] = overh; res["thin"] = thin
    return res

if __name__ == "__main__":
    names = sys.argv[1:] or sorted(ORIENT)
    out = {}
    for n in names:
        r = audit(n); out[n] = r
        big = [o for o in r["overhangs"] if o[4] > 6.0]
        print(f"{n:20s} size {r['size']} bed {'ok' if r['fits_bed'] else 'NO'} shells {r['shells']} islands {len(r['islands'])} "
              f"overhang-regions {len(r['overhangs'])} wide(>6mm) {len(big)} max-span {max([o[4] for o in r['overhangs']] or [0])} thin {len(r['thin'])}", flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "printability.json"), "w"), indent=1)
