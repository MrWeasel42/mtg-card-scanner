"""Every cable route (cad/wiring.py) against the real parts: a route may only pass through openings, never through
material. Rays along each segment; any stretch inside a printed part (or a bought body) is reported."""
import sys, json, os, math
import numpy as np, trimesh
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
import wiring
HERE = os.path.dirname(os.path.abspath(__file__))
idx = json.load(open(os.path.join(HERE, "placed", "index.json")))
SOLID = ["psu_body"] + [n for n in idx if n != "psu_body" and not n.startswith(("v_", "rail", "hub_", "skr", "conv", "screen_block", "camera", "tof_", "beam_",
                                            "home_tcrt", "card_clear", "psu", "iec_inlet", "hall_leads", "bay_fan", "loop_", "led_channel"))]
M = {n: trimesh.load(os.path.join(HERE, "placed", n + ".stl")) for n in SOLID}

def inside(o, d, L):
    out = {}
    for n, m in M.items():
        lo, hi = m.bounds
        p1 = o + d * L
        if np.any(np.minimum(o, p1) > hi + 1) or np.any(np.maximum(o, p1) < lo - 1):
            continue
        locs, _, _ = m.ray.intersects_location([o], [d], multiple_hits=True)
        if not len(locs):
            continue
        t = np.unique(np.round(np.sort((locs - o) @ d), 4))
        # inside test at the start
        ins = bool(m.contains([o + d * 1e-3])[0])
        pts = [0.0] + [x for x in t if 0 < x < L] + [L]
        tot, state = 0.0, ins
        for a, b in zip(pts, pts[1:]):
            if state:
                tot += b - a
            state = not state
        if tot > 0.3:
            out[n] = round(tot, 1)
    return out

def check():
    rep = []
    for r in wiring.runs():
        pts = r.get("pts")
        if not pts or r.get("internal"):
            continue
        hits = {}
        segs = list(zip(pts, pts[1:]))
        for k, (a, b) in enumerate(segs):
            a, b = np.asarray(a, float), np.asarray(b, float)
            L = np.linalg.norm(b - a)
            if L < 1e-6:
                continue
            d = (b - a) / L
            # skip 4 mm at the very ends of the route (the plug sits in its board / sensor pocket)
            a0 = a + d * (4.0 if k == 0 else 0.0); L0 = L - (4.0 if k == 0 else 0.0) - (4.0 if k == len(segs) - 1 else 0.0)
            if L0 <= 0:
                continue
            for n, v in inside(a0, d, L0).items():
                hits.setdefault(n, []).append((k, v))
        rep.append(dict(cable=r["cable"], hits=hits))
        print(("OK   " if not hits else "HIT  ") + f"{r['cable'][:60]:60s}", "" if not hits else hits)
    return rep

if __name__ == "__main__":
    json.dump(check(), open(os.path.join(HERE, "wires.json"), "w"), indent=1)
