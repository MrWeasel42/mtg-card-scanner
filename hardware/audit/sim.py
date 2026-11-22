"""Card flow simulation: a raw, a single-sleeved and a double-sleeved card from the bottom of the hopper, under the
gate, through the exit nip, along the track behind a fin, under the camera, to a bin: down the opened door into
the bin. Every pose is checked against the real parts (manifold booleans); the gaps that matter (gate, nip, guides,
fin fingers, hood tunnel, door edge to bin) are measured. card_poses() is also what the video uses."""
import sys, os, json, math
import numpy as np, trimesh, manifold3d as m3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import *
HERE = os.path.dirname(os.path.abspath(__file__))

CARDS = {   # name: (length along X, width, thickness, tower, gate gap at its exit end)
    "raw":    (88.0, 63.0, 0.31, "raw", 0.45),
    "single": (91.0, 66.0, 0.51, "single", 0.70),   # Dragon Shield matte: ~0.10 mm a face
    "double": (91.0, 66.0, 0.62, "double", 0.85),   # + Perfect Fit inner: ~0.055 a face
}
PAD_Z0 = PATH + GATE      # pad's lowest point (raw setting)

def card_mesh(L, W, t):
    return trimesh.creation.box(extents=(L, W, t))

def poses(kind, bin_k=0, step_mm=4.0):
    """List of (phase, 4x4) for the card centre. Lying flat until the door, then on the door, then into the bin."""
    L, W, t, tower_k, gap = CARDS[kind]
    in_x = TOWERS[tower_k][0]
    x_tail0 = TOWER_EXIT_X - L - 0.5            # leading edge against the exit wall (the stack leans into that corner)
    out = []
    def flat(xc, z=None, y=0.0, phase=""):
        M = np.eye(4); M[:3, 3] = (xc, y, (PATH + t / 2 + 0.02) if z is None else z); out.append((phase, M))
    # 1. feed roller pulls it out under the gate and pushes it into the exit nip; feeds on until the card-clear
    #    sensor sees the tail go past, plus after_clear_mm
    x_tail_clear = CARD_CLEAR_X + 4.5 + 13.0
    x = x_tail0
    while x < x_tail_clear:
        flat(x + L / 2, phase="feed"); x += step_mm
    # 2. a fin comes round the start idler behind the card and pushes it one pitch: tail to 128 + 122
    x_tail_scan = 128.0 + PITCH
    while x < x_tail_scan:
        flat(x + L / 2, phase="to camera"); x += step_mm
    flat(x_tail_scan + L / 2, phase="scan")
    # 3. on to its bin (bin_k): the fin face lands at bin k's station
    xb = BIN_X[bin_k]
    x_tail_bin = x_tail_scan + PITCH * (bin_k + 1)
    x = x_tail_scan
    while x < x_tail_bin:
        flat(x + L / 2, phase="to bin"); x += step_mm
    xc = x_tail_bin + L / 2
    flat(xc, phase="at bin")
    # 4. the door opens under it: the card rides the door down to ~35 degrees, then slides off its low edge
    for a in range(0, 61, 3):
        M = trimesh.transformations.rotation_matrix(math.radians(a), [1, 0, 0], [0, HINGE_Y, HINGE_Z])
        C = np.eye(4); C[:3, 3] = (xc, 0.0, PATH + t / 2 + 0.02)
        out.append(("door opens", M @ C))
    # slide down the 60 degree door plane (card stays on the plane, moving toward -Y / down)
    M60 = trimesh.transformations.rotation_matrix(math.radians(60), [1, 0, 0], [0, HINGE_Y, HINGE_Z])
    for s in np.arange(0, 70, 3.0):
        C = np.eye(4); C[:3, 3] = (xc, -s, PATH + t / 2 + 0.02)
        out.append(("slides off", M60 @ C))
    # off the door's low edge it tips forward and drops: its back edge clears the bin's back wall (inner face Y -1),
    # then it falls flat to the bottom of the bin
    p_end = (M60 @ np.r_[xc, -70.0, PATH + t / 2, 1.0])[:3]
    land = np.array([xc, BIN_Y, 2.0 + t / 2])
    yb_clear = -1.0 - 1.0 - (W / 2) * math.cos(math.radians(60))     # centre Y with the back edge 1 mm in front of the wall
    for f in np.linspace(0, 1, 16):
        ang = math.radians(60 * (1 - f) + 75 * f)                       # it tumbles steeper as it drops
        p = np.array([xc, min(p_end[1], yb_clear) * (1 - f) + land[1] * f, p_end[2] * (1 - f) + 60.0 * f])
        R = trimesh.transformations.rotation_matrix(ang, [1, 0, 0]); R[:3, 3] = p
        out.append(("into the bin", R))
    for f in np.linspace(0, 1, 8):                                       # and settles flat on the stack
        ang = math.radians(75 * (1 - f))
        p = np.array([xc, land[1], 60.0 * (1 - f) + land[2] * f])
        R = trimesh.transformations.rotation_matrix(ang, [1, 0, 0]); R[:3, 3] = p
        out.append(("into the bin", R))
    return out

def run():
    idx = json.load(open(os.path.join(HERE, "placed", "index.json")))
    def man(t):
        return m3.Manifold(m3.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
    skip = ("v_", "rail", "hub_", "skr", "conv", "screen_block", "camera", "psu", "iec", "tof_", "beam_", "home_tcrt", "card_clear",
            "hall_leads", "bay_fan", "loop_", "led_channel", "nema", "coupler", "shaft_", "motor_standoff", "servo_", "horn_")
    names = [n for n in idx if not n.startswith(skip)]
    meshes = {n: trimesh.load(os.path.join(HERE, "placed", n + ".stl")) for n in names}
    report = {}
    for kind in CARDS:
        L, W, t, tk, gap = CARDS[kind]
        card = card_mesh(L, W, t)
        # this card's tower (and gate set for it)
        twr = cqm(tower(tk)) if tk != "raw" else meshes["raw_tower"]
        gate = meshes["gate_plate"].copy(); gate.apply_translation((0, 0, gap - GATE))
        static = {n: m for n, m in meshes.items() if n not in ("raw_tower", "gate_plate")}
        static["tower"] = twr; static["gate"] = gate
        rollers = ("feed_roller", "exit_roller", "exit_roller_top")   # the card is meant to touch these (nip)
        doors = [n for n in static if n.startswith("door_")]
        hits = {}
        P = poses(kind, bin_k=1)
        for ph, M in P:
            c = card.copy(); c.apply_transform(M)
            cm = man(c)
            lo, hi = c.bounds
            for n, m in static.items():
                if n in rollers:
                    continue
                if ph in ("door opens", "slides off", "into the bin") and n == "door_1":
                    continue     # riding on its own door
                if ph in ("door opens",) and n.startswith("door_1"):
                    continue
                b = m.bounds
                if np.any(lo > b[1] + 0.5) or np.any(hi < b[0] - 0.5):
                    continue
                v = (cm ^ man(m)).volume()
                if v > 0.01:
                    hits.setdefault(f"{ph}: {n}", 0.0); hits[f"{ph}: {n}"] = max(hits[f"{ph}: {n}"], round(v, 3))
        # gaps that matter
        gb = gate.bounds
        g = dict(
            gate_gap_exit_end=round(PATH + gap - PATH, 3), card_thickness=t,
            gate_margin_one_card=round(gap - t, 3), gate_blocks_two=bool(gap < 2 * t),
            tower_width_play_per_side=round((TOWERS[tk][1] - W) / 2, 2), tower_length_play=round(TOWERS[tk][0] - L, 2),
            guide_play_per_side=round(RAIL_IN - W / 2, 2), finger_overlap_on_card_edge=round(W / 2 - FIN_REACH_Y, 2),
            finger_overlap_card_pushed_to_one_side=round(W / 2 - (RAIL_IN - W / 2) - FIN_REACH_Y, 2),
            hood_tunnel_headroom=round(WALL_TOP + 0.5 - (PATH + t), 1),
            bin_inside_length_play=round(94 - L, 1), bin_inside_width_play=round(72 - W, 1))
        report[kind] = dict(hits=hits, gaps=g, poses=len(P))
        print(kind, "collisions:", hits or "none", "\n   ", g, flush=True)
    json.dump(report, open(os.path.join(HERE, "sim.json"), "w"), indent=1)

def cqm(shape):
    v, f = shape.val().tessellate(0.05, 0.2)
    return trimesh.Trimesh([(p.x, p.y, p.z) for p in v], f)

if __name__ == "__main__":
    run()
