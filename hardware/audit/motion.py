"""Moving parts and install paths, swept in small steps against everything that is already in place.
Each move: the moving set (parts + bought bodies + screw heads), a list of poses, the static set; any overlap
(manifold boolean, mm^3) is a FAIL. Minimum clearance is estimated by also testing the moving set grown by the
required gap (offsetting is approximated by testing poses nudged +-gap along each axis)."""
import sys, json, math, os
import numpy as np, trimesh, manifold3d as m3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import *
from sorter import _stadium_yz, _lever_end
import cadquery as cq
HERE = os.path.dirname(os.path.abspath(__file__))
IDX = json.load(open(os.path.join(HERE, "placed", "index.json")))
_cache = {}
def T(name):
    if name not in _cache:
        _cache[name] = trimesh.load(os.path.join(HERE, "placed", name + ".stl"))
    return _cache[name]
def man(t):
    return m3.Manifold(m3.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
def cqmesh(shape):
    v, f = shape.val().tessellate(0.05, 0.2)
    return trimesh.Trimesh([(p.x, p.y, p.z) for p in v], f)
def union(ms):
    out = None
    for m in ms:
        out = m if out is None else out + m
    return out

def wires_mesh():
    import wiring
    tubes = []
    for r in wiring.runs():
        if not r.get("pts") or r.get("internal"):
            continue
        for a, b in zip(r["pts"], r["pts"][1:]):
            a, b = np.asarray(a, float), np.asarray(b, float)
            if np.linalg.norm(b - a) < 0.5:
                continue
            c = trimesh.creation.cylinder(radius=1.2, segment=[a, b], sections=8)
            tubes.append(man(c))
    return union(tubes)

RESULTS = []
def sweep(label, moving, poses, static_names, gap=0.0, extra_static=None, note=""):
    """moving: list of trimesh (at pose 0); poses: list of 4x4 transforms; static_names: placed names."""
    mv = union([man(m) for m in moving])
    st = union([man(T(n)) for n in static_names] + ([extra_static] if extra_static is not None else []))
    worst = (0.0, None)
    nudges = [np.eye(4)]
    if gap > 0:
        for ax in range(3):
            for sg in (-1, 1):
                N = np.eye(4); N[ax, 3] = sg * gap; nudges.append(N)
    for k, P in enumerate(poses):
        for N in nudges:
            M = N @ P
            v = (mv.transform(M[:3, :4]) ^ st).volume()
            if v > worst[0] + 1e-9:
                worst = (v, k)
    ok = worst[0] <= 0.02
    culprits = []
    if not ok:
        M = poses[worst[1]]
        for n in static_names:
            v = (mv.transform(M[:3, :4]) ^ man(T(n))).volume()
            if v > 0.02: culprits.append((n, round(v, 2)))
        if extra_static is not None:
            v = (mv.transform(M[:3, :4]) ^ extra_static).volume()
            if v > 0.02: culprits.append(("cables", round(v, 2)))
        # and without the clearance nudge
        culprits.append(("no-gap overlap", round((mv.transform(M[:3, :4]) ^ st).volume(), 2)))
    RESULTS.append(dict(label=label, ok=ok, overlap=round(worst[0], 2), at_pose=worst[1], gap=gap, n=len(poses), note=note, culprits=culprits))
    print(("PASS " if ok else "FAIL ") + f"{label:70s} poses {len(poses):3d} gap {gap} overlap {worst[0]:.2f}" + (f" at pose {worst[1]} {culprits}" if not ok else ""), flush=True)

def rot_x(deg, y, z):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    R = np.eye(4); R[1, 1], R[1, 2], R[2, 1], R[2, 2] = c, -s, s, c
    Tp = np.eye(4); Tp[1, 3], Tp[2, 3] = y, z
    Tn = np.eye(4); Tn[1, 3], Tn[2, 3] = -y, -z
    return Tp @ R @ Tn
def tr(dx=0, dy=0, dz=0):
    M = np.eye(4); M[:3, 3] = (dx, dy, dz); return M

def run():
    W = wires_mesh()
    every = [n for n in IDX if not n.startswith("v_")]
    # ---- doors + links + horns, 0 -> 65 degrees, against everything else (and every cable)
    for i in sorted({0, HUB_MODULE, BINS - 2}):
        x0 = BIN_X[i] - PITCH / 2
        door = T(f"door_{i}")
        static = [n for n in every if n not in (f"door_{i}", f"servo_link_{i}", f"horn_{i}")]
        sweep(f"bin {i+1} door closed (touching nothing)", [door], [rot_x(0, HINGE_Y, HINGE_Z)], static, gap=0.0, extra_static=W)
        sweep(f"bin {i+1} door 2 -> 65 deg vs all parts + cables, 0.3 mm clearance", [door], [rot_x(a, HINGE_Y, HINGE_Z) for a in range(2, 66, 3)],
              static, gap=0.3, extra_static=W, note="closed, the door's edges are 0.25 mm from the guide rails' webs (by design)")
        # link + horn move together: build each pose from the CAD
        heads = []
        poses_parts = []
        for a in list(range(0, 61, 5)) + [62, 63]:
            lk = cqmesh(link_placed(a).translate((x0, 0, 0)))
            le = (HINGE_Y + LEVER_R * math.cos(math.radians(LEVER_A0 + a)), HINGE_Z + LEVER_R * math.sin(math.radians(LEVER_A0 + a)))
            ht = (le[0] + SERVO_S[0] - HINGE_Y, le[1] + SERVO_S[1] - HINGE_Z)
            hd = cqmesh(cyl_x(le[0], le[1], 1.9, x0 + LINK_X[1], x0 + LINK_X[1] + 1.4).union(cyl_x(ht[0], ht[1], 1.9, x0 + LINK_X[0] - 1.4, x0 + LINK_X[0])))
            horn = cqmesh(_stadium_yz(SERVO_S, ht, 3.0, x0 + SERVO_TOP_X - 4.0, x0 + SERVO_TOP_X - 2.0))
            poses_parts.append((a, [lk, hd, horn]))
        st = [n for n in every if n not in (f"door_{i}", f"servo_link_{i}", f"horn_{i}", f"servo_{i}")]
        bad = []
        stat = union([man(T(n)) for n in st] + [W])
        for a, ms in poses_parts:
            v = (union([man(m) for m in ms]) ^ stat).volume()
            if v > 0.02:
                bad.append((a, round(v, 2)))
        RESULTS.append(dict(label=f"bin {i+1} link + horn + screw heads 0 -> 63 deg vs all parts + cables", ok=not bad, overlap=bad,
                            note="the lever end first touches the strip's notch at ~64 deg; travel is 60"))
        print(("PASS " if not bad else "FAIL ") + f"bin {i+1} link + horn + screw heads 0 -> 63 deg vs all parts + cables", bad)
    # ---- bins slide out the front
    for i in (0, HUB_MODULE, BINS - 1):
        sweep(f"bin {i+1} slides out the front (0 -> 130 mm)", [T(f"bin_{i}")], [tr(dy=-d) for d in range(0, 131, 5)],
              [n for n in every if not n.startswith("bin_") or n.startswith("bin_side")], gap=0.5, extra_static=W)
    # ---- electronics tray (with the SKR Pico + its plugs) slides out the front window (bay cover off)
    sweep("electronics tray + SKR Pico + plugs slide out the front (0 -> 140 mm)", [T("electronics_tray"), T("skr")],
          [tr(dy=-d) for d in range(0, 141, 5)], [n for n in every if n not in ("electronics_tray", "skr", "bay_cover", "bay_fan")], gap=0.0)
    # ---- tower lifts off; gate lifts in its track
    sweep("raw tower (+ gate + its screw) lifts straight off (0 -> 80 mm)", [T("raw_tower"), T("gate_plate")],
          [tr(dz=d) for d in range(0, 81, 4)], [n for n in every if n not in ("raw_tower", "gate_plate")], gap=0.0)
    sweep("gate lifts in its track (thick card) 0 -> 1.2 mm", [T("gate_plate")], [tr(dz=d / 10) for d in range(0, 13)],
          [n for n in every if n != "gate_plate"])
    # ---- pressure roller floats up (card under it): 0 -> 1.5 mm
    sweep("pressure roller + axle float up 0 -> 1.5 mm", [T("exit_roller_top"), T("shaft_pressure")], [tr(dz=d / 10) for d in range(0, 16)],
          [n for n in every if n not in ("exit_roller_top", "shaft_pressure", "exit_roller")])
    # ---- hood lid lifts off with the camera (ribbon unplugged at the camera)
    sweep("hood lid + camera + plate lift straight off (0 -> 120 mm)", [T("hood_lid"), T("camera"), T("camera_plate")],
          [tr(dz=d) for d in range(0, 121, 4)], [n for n in every if n not in ("hood_lid", "camera", "camera_plate")], gap=0.0)
    # ---- PSU slides in from the feeder end (scan module not yet beside the feeder base)
    sweep("PSU slides in from the feeder end over the cradles (feeder base not yet there)", [T("psu_body")],
          [tr(dx=-d) for d in range(0, 181, 5)], [n for n in every if n not in ("psu_body", "psu", "feeder_base", "iec_inlet")
                                                   and not n.startswith(("rail", "bay_", "electronics", "skr", "conv6", "hall", "card_clear",
                                                   "loop_", "shaft_feed", "shaft_exit", "feed_roller", "exit_roller", "idler", "nema_feed",
                                                   "motor_standoff_feed", "coupler_feed", "raw_tower", "gate_plate", "pressure", "screen", "pod", "conv5", "mount"))], gap=0.0)
    # ---- servo slides into its bracket (door, link not yet fitted)
    for i in (0,):
        sweep(f"bin {i+1} servo slides into its bracket from the hopper side (-24 -> 0 mm), door already hinged", [T(f"servo_{i}")],
              [tr(dx=-d) for d in range(0, 25, 1)], [n for n in every if not n.startswith(("servo_", "horn_", "hub_"))
                                                     and n not in (f"back_panel_{i}",)], note="body passes the bracket cut-out; horn goes on after")
    # ---- door goes in from below, then the pin from the module's open end
    for i in (0,):
        sweep(f"bin {i+1} door rises into place from below (-25 -> 0 mm, bin out)", [T(f"door_{i}")], [tr(dz=-d) for d in range(0, 26, 1)],
              [n for n in every if (not n.startswith(("door_", "servo_link_", "bin_" + str(i), "servo_", "horn_")) or n.startswith("bin_side"))],
              note="before the servo; barrels up into the strip notches (open underneath)")
        x0 = BIN_X[i] - PITCH / 2
        pin = cqmesh(cyl_x(HINGE_Y, HINGE_Z, 1.0, x0 + FRAME_KN[0][0], x0 + FRAME_KN[-1][1]))
        nxt = [f"bin_side_back_{i+1}", f"bin_side_front_{i+1}", f"tie_bar_{i+1}", f"joint_plate_f{i+1}", f"joint_plate_b{i+1}"]
        sweep(f"bin {i+1} hinge pin (2 x 100) pushed in from the module end (next module not on yet)", [pin], [tr(dx=d) for d in range(0, 111, 2)],
              [n for n in every if n not in nxt + [f"door_{i}"]])
    # ---- hub boards on the back panel go in through the window (panel moves in from 25 mm out)
    hubs = [T(n) for n in IDX if n.startswith("hub_")] + [T(f"back_panel_{HUB_MODULE}")]
    sweep("hub panel + boards go in through the module's window (25 -> 0 mm)", hubs, [tr(dy=d) for d in range(0, 26, 1)],
          [n for n in every if not n.startswith("hub_") and n != f"back_panel_{HUB_MODULE}" and not n.startswith(("joint_plate_b",))], gap=0.0)
    json.dump(RESULTS, open(os.path.join(HERE, "motion.json"), "w"), indent=1, default=str)

if __name__ == "__main__":
    run()
