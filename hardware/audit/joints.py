"""Fastener audit: every screw in the machine, placed on its real axis, checked against the real meshes.

For each screw instance:
  seat    the head's bearing face is found by casting along the axis (first material in the clamp part)
  head    nothing may occupy the head's cylinder (D x H) behind the seat
  shank   the clamped parts must have a clearance hole (no material inside 0.47 d of the axis)
  thread  engagement inside the threaded part: insert (5.7 mm from the insert's mouth), pilot (material at the
          thread crest radius), nut (given), T-nut (grip vs the slot), motor (4.5 mm deep holes)
  tip     past the thread, the screw may not run into anything (blind hole bottom, another part)
  tool    straight clear length behind the head for a hex key / driver (rays at 1.4 mm round the axis)
Install-time: every part listed in `present` (parts already fitted when this screw goes in) is in the scene, the
others are not, so a screw that's only reachable before something else goes on is caught.
"""
import sys, json, math, os
import numpy as np, trimesh
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
import sorter as S
from sorter import *

HERE = os.path.dirname(os.path.abspath(__file__))
MESH = {}
def mesh(name):
    if name not in MESH:
        MESH[name] = trimesh.load(os.path.join(HERE, "placed", name + ".stl"))
    return MESH[name]
ALL = [l.strip() for l in json.load(open(os.path.join(HERE, "placed", "index.json")))]

HEAD = {"shcs": {2: (3.8, 2.0), 3: (5.5, 3.0), 5: (8.5, 5.0)}, "pan": {2: (3.8, 1.4), 3: (5.6, 2.1)}}
INSERT_L = 5.7

def intervals(m, o, d, tmax):
    """Inside-material intervals of mesh m along the ray o + t d, 0 <= t <= tmax."""
    locs, idx, _ = m.ray.intersects_location([o], [d], multiple_hits=True)
    if len(locs) == 0:
        return []
    t = np.sort(np.dot(locs - o, d))
    t = np.unique(np.round(t, 4))
    if len(t) % 2:     # grazing hit: drop the last
        t = t[:-1]
    return [(a, b) for a, b in zip(t[0::2], t[1::2]) if a < tmax]

def ring(d, r, n=8):
    d = np.asarray(d, float); a = np.cross(d, [0, 0, 1] if abs(d[2]) < 0.9 else [1, 0, 0]); a /= np.linalg.norm(a)
    b = np.cross(d, a)
    return [r * (math.cos(2 * math.pi * k / n) * a + math.sin(2 * math.pi * k / n) * b) for k in range(n)]

def material(names, o, d, r, tmax, n=8):
    """Per part: union of inside intervals over rays at radius r round the axis (r=0: the axis itself)."""
    out = {}
    offs = [np.zeros(3)] if r == 0 else ring(d, r, n)
    for nm in names:
        m = mesh(nm)
        lo, hi = m.bounds
        # quick reject: segment bbox vs mesh bbox
        p0, p1 = o, o + d * tmax
        if np.any(np.minimum(p0, p1) - r - 1 > hi) or np.any(np.maximum(p0, p1) + r + 1 < lo):
            continue
        iv = []
        for off in offs:
            iv += intervals(m, o + off, d, tmax)
        if iv:
            out[nm] = sorted(iv)
    return out

def first(ivs):
    return min(a for a, b in ivs) if ivs else None

def overlap(ivs, a, b):
    return sum(max(0.0, min(y, b) - max(x, a)) for x, y in ivs)

def check(j):
    if j.get("per_point_dir") or j.get("clamp_by_side") or j["thread"][0] == "insert_any":
        out = []
        for p in j["pts"]:
            jj = dict(j); jj["pts"] = [p]; jj.pop("per_point_dir", None); jj.pop("clamp_by_side", None)
            if j["dir"] is None:
                jj["dir"] = (0, -math.copysign(1, p[1]), 0)
            if j.get("clamp_by_side"):
                fr = p[1] < 0
                jj["clamp"] = [c for c in j["clamp"] if (("front" in c) or c.endswith(tuple(f"_f{k}" for k in range(20)))) == fr]
            if j["thread"][0] == "insert_any":
                d = np.asarray(jj["dir"], float); d /= np.linalg.norm(d)
                o = np.asarray(p, float) - d * 3.0
                cand = material([n for n in jj.get("present", ALL) if n not in jj["clamp"]], o, d, M3_INSERT / 2 + 0.6, 200)
                best = None
                for nm, iv in cand.items():
                    t = first(iv)
                    if t > 3.0 - 1 and (best is None or t < best[0]):
                        best = (t, nm)
                jj["thread"] = ("insert", best[1] if best else "?")
            out += check(jj)
        return out
    d = np.asarray(j["dir"], float); d /= np.linalg.norm(d)
    dia, L = j["screw"]
    kind = j.get("head", "shcs")
    hd, hh = HEAD[kind][dia]
    res = []
    scene = [n for n in j.get("present", ALL)]
    for p in j["pts"]:
        p = np.asarray(p, float)
        BACK = 3.0
        o = p - d * BACK          # the point given is at the head's seat (or just outside it)
        tmax = BACK + 3 * L + 30
        r_cr = dia / 2 * 0.94     # thread crest
        r_core = dia / 2 * 0.62   # inside the core: a pilot / clearance hole is open here
        # seat: first material of the clamp stack (or thread part if nothing is clamped) on an annulus just outside the screw
        first_part = j["clamp"][0] if j["clamp"] else j["thread"][1]
        if first_part == "?":
            res.append(dict(pt=p.round(2).tolist(), ok=False, msg="no insert found on this axis")); continue
        ann = material([first_part], o, d, (dia / 2 + hd / 2) / 2 + 0.3, tmax)
        if first_part not in ann:
            res.append(dict(pt=p.round(2).tolist(), ok=False, msg=f"no seat: {first_part} not on this axis")); continue
        ts = first(ann[first_part])
        r = dict(pt=p.round(2).tolist(), seat=round(ts - BACK, 2), into=j["thread"][1] if len(j["thread"]) > 1 and isinstance(j["thread"][1], str) else j["thread"][0])
        probs = []
        # head volume (behind the seat)
        hv = material(scene, o, d, hd / 2 - 0.15, tmax, n=12)
        hv0 = material(scene, o, d, 0, tmax)
        for nm, iv in list(hv.items()) + list(hv0.items()):
            ov = overlap(iv, ts - hh, ts - 0.05)
            if ov > 0.05:
                probs.append(f"head hits {nm} ({ov:.1f} mm)")
        # shank
        crest = material(scene, o, d, r_cr, tmax)
        core = material(scene, o, d, r_core, tmax)
        tip = ts + L
        th_kind, th_part = j["thread"][0], (j["thread"][1] if len(j["thread"]) > 1 else None)
        eng = 0.0
        for nm in set(crest) | set(core):
            c_iv = core.get(nm, []); k_iv = crest.get(nm, [])
            if nm == th_part or any(nm.startswith(x) for x in j.get("ignore", ())):
                continue
            ovk = overlap(k_iv, ts, tip)
            if nm in j["clamp"]:
                if ovk > 0.15 and not nm.startswith("v_"):
                    probs.append(f"no clearance hole in {nm} ({ovk:.1f} mm of material on the screw)")
            elif ovk > 0.15:
                probs.append(f"screw runs into {nm} ({ovk:.1f} mm)")
        grip = None
        if th_kind == "insert":
            # insert mouth = where the thread part starts along the axis at a radius just outside the insert hole
            mouth_iv = material([th_part], o, d, M3_INSERT / 2 + 0.6, tmax).get(th_part, [])
            hole_core = core.get(th_part, [])
            m0 = None
            for a, b in sorted(mouth_iv):
                if b > ts - 0.01:
                    m0 = max(a, ts); break
            if m0 is None:
                probs.append("insert part not on the axis")
            else:
                eng = max(0.0, min(tip, m0 + INSERT_L) - m0)
                bottom = overlap(hole_core, m0, tip)
                if bottom > 0.1:
                    probs.append(f"tip bottoms out in the insert hole ({bottom:.1f} mm too long)")
                grip = m0 - ts
        elif th_kind == "pilot":
            # boss material just outside the drawn pilot (the printed pilot comes out ~0.45 mm small, so the
            # thread cuts into it); the drawn pilot must be the tuned PILOT size
            pr_iv = material([th_part], o, d, dia / 2 * 1.2, tmax).get(th_part, [])
            c_iv = core.get(th_part, [])
            eng = overlap(pr_iv, ts, tip)
            if overlap(c_iv, ts, tip) > 0.1:
                probs.append(f"pilot too short / blind: core hits {th_part} ({overlap(c_iv, ts, tip):.1f} mm)")
        elif th_kind in ("nut", "motor", "tnut", "fixed"):
            # given: start of the threaded element along the axis (distance from the seat) and its length
            t0, tl = j["thread"][1], j["thread"][2]
            eng = max(0.0, min(tip, ts + t0 + tl) - (ts + t0))
            grip = t0
            if th_kind == "motor" and tip > ts + t0 + tl + 0.01:
                probs.append(f"too long for the motor's {tl} mm holes ({tip - ts - t0 - tl:.1f} mm)")
            if th_kind == "tnut" and tip > ts + t0 + tl + 0.01:
                probs.append(f"bottoms in the rail slot ({tip - ts - t0 - tl:.1f} mm)")
        need = j.get("min_eng", 2.4 if th_kind == "nut" else 3.0)
        if eng + 1e-6 < need:
            probs.append(f"thread engagement {eng:.1f} mm < {need}")
        # tool access: straight back from the head top
        hk = 1.4 if dia >= 3 else 0.8
        back = []
        top = o + d * (ts - hh - 0.05)
        far = top - d * 120.0
        near_parts = [nm for nm in scene if not (np.any(np.minimum(top, far) - 3 > mesh(nm).bounds[1]) or
                                                  np.any(np.maximum(top, far) + 3 < mesh(nm).bounds[0]))]
        for off in [np.zeros(3)] + ring(d, hk, 6):
            ht = top + off
            hits = []
            for nm in near_parts:
                m = mesh(nm)
                locs, _, _ = m.ray.intersects_location([ht], [-d], multiple_hits=False)
                if len(locs):
                    hits.append(np.linalg.norm(locs[0] - ht))
            back.append(min(hits) if hits else 120.0)
        clear = min(back)
        r.update(eng=round(eng, 1), grip=None if grip is None else round(grip, 1), tool=round(min(clear, 999), 1))
        if clear < j.get("min_tool", 12.0):
            probs.append(f"tool access only {clear:.1f} mm straight behind the head")
        r["ok"] = not probs
        r["msg"] = "; ".join(probs)
        res.append(r)
    return res

if __name__ == "__main__":
    from joint_table import JOINTS
    want = sys.argv[1:]
    report = []
    for j in JOINTS:
        if want and not any(w in j["name"] for w in want):
            continue
        rs = check(j)
        ok = all(r["ok"] for r in rs)
        report.append(dict(name=j["name"], screw=f"M{j['screw'][0]} x {j['screw'][1]}", n=len(rs), ok=ok, results=rs))
        print(("PASS " if ok else "FAIL ") + f"{j['name']:46s} M{j['screw'][0]}x{j['screw'][1]:<3} x{len(rs):<3}",
              "eng", sorted(set(r.get('eng') for r in rs if 'eng' in r)), "tool", min([r.get('tool', 0) for r in rs] or [0]),
              "" if ok else " | " + " / ".join(sorted(set(r["msg"] for r in rs if not r["ok"])))[:400])
    json.dump(report, open(os.path.join(HERE, "joints_report.json"), "w"), indent=1)
    print(sum(r["ok"] for r in report), "/", len(report), "joints pass")
