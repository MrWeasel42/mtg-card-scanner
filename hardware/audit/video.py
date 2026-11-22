"""How it works: an explainer video rendered from the real CAD (audit/placed) with the card poses from sim.py.
Segments: overview, feeding, the gate, the fins, scanning, sorting into a bin, the three card types.
Writes renders/how_it_works.mp4 (+ one clip per segment)."""
import os, sys, os, math, subprocess, json
import numpy as np, trimesh
from viz import *
import sim
from sorter import _lever_end
OUT = os.path.join(HERE, "renders")
W, H, FPS = 1280, 720, 24
L_ALL = END_X0 + END_L

def smooth(u):
    u = min(1.0, max(0.0, u)); return u * u * (3 - 2 * u)
def lerp(a, b, u):
    return tuple(np.asarray(a, float) * (1 - u) + np.asarray(b, float) * u)

class Film:
    def __init__(self):
        self.sc = Scene(W, H)
        sc = self.sc
        sc.load(skip=("hall_leads", "loop_", "led_channel_", "screen_block"))
        for n in ("led_channel_f", "led_channel_b"):
            sc.add(n, trimesh.load(os.path.join(PL, n + ".stl")), kind="led")
        self.fm = fin_meshes()
        self.nf = int(round(LOOP / PITCH))
        for k in range(self.nf):
            for sg in (1, -1):
                sc.add(f"fin_{sg}_{k}", self.fm[sg], kind="fin")
        sc.add("belts", belt_meshes(), kind="belt")
        st = trimesh.creation.box(extents=(88, 63, 100)); st.apply_translation((TOWER_EXIT_X - 44.5, 0, PATH + 0.31 + 50.2))
        st.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-TOWER_LEAN), [1, 0, 0], [0, 0, PATH]))
        st.apply_transform(trimesh.transformations.rotation_matrix(math.radians(TOWER_LEAN_X), [0, 1, 0], [TOWER_EXIT_X, 0, PATH]))
        sc.add("stack", st, kind="stack")
        for i, hgt in enumerate((40, 15, 70, 25, 55, 10, 35, 20, 60)[:BINS]):
            b = trimesh.creation.box(extents=(88, 63, hgt)); b.apply_translation((BIN_X[i] + BIN_DX, BIN_Y, 2 + hgt / 2))
            sc.add(f"binstack_{i}", b, kind="stack")
        # cards (one of each kind; only one shown at a time)
        self.cards = {}
        for kind in sim.CARDS:
            names = []
            for j, (kk, m) in enumerate(card_parts(kind)):
                nm = f"card_{kind}_{j}"; sc.add(nm, m, kind=kk); names.append(nm); sc.show(nm, False)
            self.cards[kind] = names
        # break-beam line, camera view pyramid, ToF cone (shown when they matter)
        xb = BIN_X[1]
        beam = trimesh.creation.cylinder(radius=0.8, segment=[(xb, -WALL_IN, PATH - 22), (xb, WALL_IN, PATH - 22)])
        sc.add("beam", beam, kind="accent", color=(1.0, 0.1, 0.1)); sc.show("beam", False)
        zc = PATH + CAM_D
        fov = trimesh.Trimesh([(SCAN_X, 0, zc), (SCAN_X - 50, -38, PATH + 0.5), (SCAN_X + 50, -38, PATH + 0.5), (SCAN_X + 50, 38, PATH + 0.5), (SCAN_X - 50, 38, PATH + 0.5)],
                              [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (1, 3, 2), (1, 4, 3)])
        sc.add("fov", fov, kind="glass", color=(1.0, 1.0, 0.7), opacity=0.25); sc.show("fov", False)
        x0 = BIN_X[1] - PITCH / 2
        cone = trimesh.creation.cone(radius=(PATH - 22) * math.tan(math.radians(7.5)), height=PATH - 22)
        cone.apply_translation((x0 + TOF_X, -42.0, PATH - 19 - (PATH - 22)))   # apex at the sensor, widening DOWN into the bin
        sc.add("tof_cone", cone, kind="glass", color=(0.3, 1.0, 0.4), opacity=0.25); sc.show("tof_cone", False)
        self.ffmpeg = None
        self.frames = 0
        self.marks = []
        self.link0 = {}
        self.set_fins(40.0)

    # ---------------------------------------------------------------- state
    def set_fins(self, s):
        for k in range(self.nf):
            for sg in (1, -1):
                self.sc.move(f"fin_{sg}_{k}", fin_pose(s + k * PITCH))
    def show_card(self, kind, M):
        for k, names in self.cards.items():
            for n in names:
                self.sc.show(n, k == kind)
                if k == kind:
                    self.sc.move(n, M)
    def hide_cards(self):
        for names in self.cards.values():
            for n in names: self.sc.show(n, False)
    def roll(self, ang_feed, ang_exit, lift=0.0):
        R = lambda a, x, z: trimesh.transformations.rotation_matrix(a, [0, 1, 0], [x, 0, z])
        self.sc.move("feed_roller", R(ang_feed, FEED_X, FEED_Z))
        self.sc.move("exit_roller", R(ang_exit, EXIT_X, EXIT_Z))
        self.sc.move("exit_roller_top", trimesh.transformations.translation_matrix((0, 0, lift)) @ R(-ang_exit, EXIT_X, PR_Z))
        self.sc.move("shaft_pressure", trimesh.transformations.translation_matrix((0, 0, lift)))
    def door(self, i, a):
        """Door i at angle a (deg): door, horn turn about their axes; the link translates (parallelogram)."""
        x0 = BIN_X[i] - PITCH / 2
        self.sc.move(f"door_{i}", trimesh.transformations.rotation_matrix(math.radians(a), [1, 0, 0], [0, HINGE_Y, HINGE_Z]))
        self.sc.move(f"horn_{i}", trimesh.transformations.rotation_matrix(math.radians(a), [1, 0, 0], [0, SERVO_S[0], SERVO_S[1]]))
        e0, e1 = _lever_end(LEVER_A0), _lever_end(LEVER_A0 + a)
        self.sc.move(f"servo_link_{i}", trimesh.transformations.translation_matrix((0, e1[0] - e0[0], e1[1] - e0[1])))

    # ---------------------------------------------------------------- output
    def start(self, path):
        self.path = path
        self.ffmpeg = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                                        "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    def frame(self):
        self.ffmpeg.stdin.write(self.sc.frame_bytes()); self.frames += 1
    def finish(self):
        self.ffmpeg.stdin.close(); self.ffmpeg.wait()
    def caption(self, title, body):
        sc = self.sc
        sc.text(title, 30, 82, size=30, bold=True, color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
        sc.text(body, 30, 22, size=21, color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
    def chapter(self, name):
        self.marks.append((name, self.frames / FPS))

# ======================================================================================== the film
def main():
    F = Film(); sc = F.sc
    F.start(os.path.join(OUT, "how_it_works.mp4"))
    every = list(sc.actors)
    pod = ("screen_cradle", "pod_cover", "pod_standoff", "conv5", "mount_wall_gap")
    cam_over = ((L_ALL * 0.12, -1300, 880), (L_ALL * 0.45, 0, 160), 32)
    F.roll(0, 0); [F.door(i, 0) for i in range(BINS - 1)]

    # ---- 0. title
    F.chapter("Overview")
    sc.camera(*cam_over[:2], angle=cam_over[2])
    sc.text("  MTG card sorter: how it works  ", W / 2, H - 120, size=46, bold=True, just="center", color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
    sc.text("  rendered from the CAD after the design audit (rev H): every part is the real model  ", W / 2, H - 165, size=22, just="center", color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
    for _ in range(int(3.0 * FPS)): F.frame()
    sc.clear_text()
    # ---- 1. overview orbit with the main parts named
    labels = [("Hopper (tower + gate)", (65, 0, 330)), ("Feeder base\n(rollers, motor, electronics bay)", (75, -60, 120)),
              ("Scanner hood\n(camera + lights)", (HOOD_X0 + 70, -75, PATH + 150)), ("Track: 2 belts with pusher fins", (700, -50, WALL_TOP + 5)),
              ("9 bins (trapdoor over each)", (BIN_X[3], -75, 120)), ("Touch screen + Pi 5", (200, -110, PATH + 40))]
    n = int(9 * FPS)
    for k in range(n):
        u = smooth(k / n)
        a = math.radians(-70 + 50 * u)
        R = 1550
        pos = (L_ALL * 0.45 + R * math.cos(a) * 0.9, R * math.sin(a), 900 - 150 * u)
        sc.camera(pos, (L_ALL * 0.42, 0, 170), angle=34)
        if k == int(0.8 * FPS):
            offs = [(-60, 90), (-260, -40), (40, 90), (40, 80), (30, -110), (-300, 40)]
            for (t, p), (dx, dy) in zip(labels, offs):
                sc.callout(t, p, dx=dx, dy=dy)
            F.caption("The machine", "Cards go in the hopper on the left, get photographed under the hood, ride the track and drop into one of 9 bins.")
        F.frame()
    sc.clear_text()

    # ---- 2. feeding (front half cut away)
    F.chapter("Feeding")
    for p in pod: sc.show(p, False)
    keep = [n for n in every if not n.startswith(("card_", "fov", "beam", "tof_cone"))]
    sc.clip(keep, (0, 0, 0), (0, 1, 0))
    P = sim.poses("raw", bin_k=1, step_mm=1.2)
    feed = [M for ph, M in P if ph == "feed"]
    cam_a = ((80, -330, 240), (95, 0, 215), 36); cam_b = ((114, -95, 212), (116, 0, 207), 30)
    ang = 0.0
    n = int(18 * FPS)
    for k in range(n):
        u = k / n
        i = min(len(feed) - 1, int(len(feed) * smooth((u - 0.12) / 0.8)))
        M = feed[i]; F.show_card("raw", M)
        xc = M[0, 3]
        ang += 0.12
        lift = 0.31 if (xc + 44 > EXIT_X - 3 and xc - 44 < EXIT_X) else 0.0
        F.roll(ang, ang, lift)
        if u < 0.35: cpos = cam_a
        elif u < 0.45: v = smooth((u - 0.35) / 0.1); cpos = (lerp(cam_a[0], cam_b[0], v), lerp(cam_a[1], cam_b[1], v), 36 - 6 * v)
        elif u < 0.7: cpos = cam_b
        elif u < 0.8: v = smooth((u - 0.7) / 0.1); cpos = (lerp(cam_b[0], cam_a[0], v), lerp(cam_b[1], cam_a[1], v), 30 + 6 * v)
        else: cpos = cam_a
        sc.camera(*cpos[:2], angle=cpos[2])
        if k in (0, int(0.36 * n), int(0.71 * n)):
            sc.clear_text()
            if k == 0:
                F.caption("1. Feeding", "The feed roller (3 rubber O-rings) under the stack drags the bottom card toward the exit wall.")
                sc.callout("Feed roller", (FEED_X, 0, FEED_Z - 12), dx=-160, dy=-90); sc.callout("Exit rollers\n(top one floats on the card)", (EXIT_X, 0, PR_Z + 12), dx=60, dy=70)
                sc.callout("Gate", (119, 0, PATH + 30), dx=-40, dy=110); sc.callout("Card-clear sensor (IR)", (CARD_CLEAR_X, 0, PATH - 9), dx=40, dy=-120)
            elif k == int(0.36 * n):
                F.caption("The gate", f"Its foot hangs {GATE:.2f} mm above the floor: one raw card (0.31) slides under, two (0.62) can't. One M3 screw sets the gap.")
                sc.callout("silicone pad", (113, 0, PATH + 1.4), dx=-320, dy=140); sc.callout("bottom card", (100, 0, PATH + 0.2), dx=-260, dy=-160)
            else:
                F.caption("Into the exit nip", "The exit rollers pull it out; when the card-clear sensor sees the tail go by, the feeder stops 13 mm later.")
        F.frame()
    sc.clear_text(); sc.unclip()

    # ---- 3. the fins push it to the camera (front walls cut away)
    F.chapter("Fins and belts")
    sc.clip([n for n in every if not n.startswith(("card_", "fin_", "belts", "fov", "beam", "tof_cone"))], (0, -36.0, 0), (0, 1, 0))
    move = [M for ph, M in P if ph in ("feed",)][-1:] + [M for ph, M in P if ph == "to camera"]
    tail0 = move[0][0, 3] - 44.0
    n = int(14 * FPS)
    cam3a = ((120, -230, 255), (160, 0, 212), 40); cam3b = ((235, -330, 290), (250, 0, 212), 40)
    for k in range(n):
        u = k / n
        v = smooth((u - 0.15) / 0.75)
        tail = tail0 + (128.0 + PITCH - tail0) * v
        M = move[0].copy(); M[0, 3] = tail + 44.0
        F.show_card("raw", M)
        # the pushing fin: lands at X 131, then its face rides at the card's tail
        face = 128.0 + PITCH * v if v > 0 else 128.0 - 30 * (1 - smooth(u / 0.15))
        F.set_fins(face - FIN_START_X)
        c = (lerp(cam3a[0], cam3b[0], smooth(u)), lerp(cam3a[1], cam3b[1], smooth(u)), 38 + 2 * u)
        sc.camera(*c[:2], angle=c[2])
        if k == 0:
            F.caption("2. Belts and fins", "Two 10 mm belts run above the floor; a fin every 122 mm comes down behind the card and pushes it one station.")
            sc.callout("start idler (fins come down here)", (FIN_START_X, -42, PUL_Z + 12), dx=-40, dy=90)
            sc.callout("belt (10 mm GT2)", (200, -42, BELT_BACK_LOW + 1), dx=40, dy=110)
        F.frame()
    sc.clear_text(); sc.unclip()
    scan_M = M.copy()

    # ---- 4. scanning (hood cut in half)
    F.chapter("Scanning")
    sc.clip([n for n in every if not n.startswith(("card_", "fov", "beam", "tof_cone"))], (0, 0.0, 0), (0, 1, 0))
    n = int(10 * FPS)
    for k in range(n):
        u = k / n
        sc.camera((SCAN_X - 60, -560, 420), (SCAN_X, 0, PATH + 90), angle=38)
        on = 0.25 < u < 0.85
        F.sc.glow("led_channel_b", on); F.sc.glow("led_channel_f", on)
        sc.show("fov", 0.45 < u < 0.6)
        if k == 0:
            F.caption("3. Scanning", "The card stops under the hood. The LED strips light it, the Pi HQ camera takes the photo, the Pi identifies the card.")
            sc.callout("Pi HQ camera, 115 mm above the card\n(slides 100-135 mm on the lid)", (SCAN_X + 15, 0, PATH + CAM_D + 50), dx=90, dy=40)
            sc.callout("LED strip (low on the wall:\nglare reflects away from the lens)", (SCAN_X - 40, 64, PATH + LED_H + 4), dx=-380, dy=60)
            sc.callout("sheen LED (low angle: shows foil)", (SCAN_X + 20, 72, SHEEN_Z), dx=120, dy=-40)
            sc.callout("card", (SCAN_X + 20, 0, PATH + 0.5), dx=120, dy=-90)
        F.frame()
    F.sc.glow("led_channel_b", False); F.sc.glow("led_channel_f", False); sc.show("fov", False)
    sc.clear_text(); sc.unclip()

    # ---- 5. sorting: on to bin 2, the door opens, the card slides in (seen from inside, behind)
    F.chapter("Sorting into a bin")
    bk = 1
    x0 = BIN_X[bk] - PITCH / 2
    seq = [M for ph, M in P if ph in ("to bin", "at bin")]
    drop = [(ph, M) for ph, M in P if ph in ("door opens", "slides off", "into the bin")]
    sc.clip([n for n in every if not n.startswith(("card_", "fin_", "belts", "fov", "beam", "tof_cone"))], (0, -36.0, 0), (0, 1, 0))
    n1 = int(5 * FPS)
    for k in range(n1):
        u = smooth(k / n1)
        tail = 128.0 + PITCH + PITCH * (bk + 1) * u
        M = scan_M.copy(); M[0, 3] = tail + 44
        F.show_card("raw", M); F.set_fins(tail - FIN_START_X)
        sc.camera((x0 - 60, -520, 330), (x0 + 40, 0, 190), angle=40)
        if k == 0:
            F.caption("4. Sorting", "The Pi picks the bin. The fins carry the card along the closed doors to its bin's station.")
        F.frame()
    sc.clear_text(); sc.unclip()
    # view from the front, inside the module, looking at the door mechanism
    sc.clip([n for n in every if not n.startswith(("card_", "beam", "tof_cone", "fin_", "belts"))], (0, -34.0, 0), (0, 1, 0))
    for nm in [f"bin_side_front_{bk}"]: sc.show(nm, False)
    nd = len(drop); n2 = int(10 * FPS)
    for k in range(n2):
        u = k / n2
        j = min(nd - 1, int(nd * smooth((u - 0.1) / 0.6)))
        ph, M = drop[j]
        a = min(60.0, 60.0 * smooth((u - 0.1) / 0.25)) if u < 0.8 else 60.0 * (1 - smooth((u - 0.8) / 0.15))
        F.door(bk, a); F.show_card("raw", M)
        sc.show("beam", ph == "into the bin" and j < nd - 4)
        sc.show("tof_cone", u > 0.75)
        sc.camera((x0 + 25, -175, 120), (x0 + 75, 30, 175), angle=46)
        if k == 0:
            F.caption("The trapdoor", "The servo turns its horn 60 degrees; the link and the door's lever form a parallelogram, so the door turns exactly 60 too.")
            sc.callout("servo", (x0 + SERVO_TOP_X + 12, SERVO_S[0] - 6, SERVO_S[1] - 10), dx=60, dy=-80)
            sc.callout("horn + link + lever\n(a parallelogram)", (x0 + 90, 28, 172), dx=-60, dy=150)
            sc.callout("door hinge (2 mm pin)", (x0 + 40, HINGE_Y - 3, HINGE_Z), dx=-280, dy=120)
        if k == int(0.45 * n2):
            sc.clear_text()
            F.caption("Into the bin", "The card slides off the open door into the bin; it crosses the break beam on the way, which confirms the drop.")
            sc.callout("break beam (emitter back, receiver front)", (BIN_X[bk] + 20, 0, PATH - 22), dx=40, dy=140)
        if k == int(0.78 * n2):
            sc.clear_text()
            F.caption("Door shuts, bin is watched", "The servo closes the door; a time-of-flight sensor under the front strip measures how full the bin is.")
            sc.callout("bin-level sensor (VL53L1X)", (x0 + TOF_X, -40, PATH - 19), dx=-300, dy=100)
        F.frame()
    F.door(bk, 0); sc.show("beam", False); sc.show("tof_cone", False); sc.show(f"bin_side_front_{bk}", True)
    sc.clear_text(); sc.unclip()

    # ---- 6. the three kinds of card under the gate
    F.chapter("Raw, sleeved, double-sleeved")
    sc.clip([n for n in every if not n.startswith(("card_",))], (0, 0, 0), (0, 1, 0))
    for kind, label in (("raw", "Raw card: 0.31 mm thick, 63 x 88. Raw tower, gate 0.45 mm"),
                        ("single", "Sleeved (Dragon Shield matte): ~0.51 mm, 66 x 91. Single-sleeve tower, gate 0.70 mm"),
                        ("double", "Double-sleeved (+ Perfect Fit): ~0.62 mm, 66 x 91. Double tower, gate 0.85 mm")):
        gap = sim.CARDS[kind][4]
        sc.move("gate_plate", trimesh.transformations.translation_matrix((0, 0, gap - GATE)))
        PP = [M for ph, M in sim.poses(kind, 1, step_mm=1.0) if ph == "feed"]
        n = int(5 * FPS)
        for k in range(n):
            i = min(len(PP) - 1, int(len(PP) * smooth(k / n) * 0.55))
            F.show_card(kind, PP[i]); F.roll(k * 0.12, k * 0.12, sim.CARDS[kind][2] if PP[i][0, 3] + 44 > EXIT_X - 3 else 0)
            sc.camera((114, -110, 213), (114, 0, 207), angle=30)
            if k == 0:
                sc.clear_text(); F.caption("5. Three kinds of card", label)
                sc.callout(f"gap {gap:.2f} mm under the pad", (121, 0, PATH + gap / 2 + 0.3), dx=60, dy=160)
            F.frame()
    sc.move("gate_plate", np.eye(4)); sc.clear_text(); sc.unclip(); F.hide_cards()

    # ---- 7. outro
    F.chapter("Checks")
    for p in pod: sc.show(p, True)
    n = int(6 * FPS)
    for k in range(n):
        sc.camera(*cam_over[:2], angle=cam_over[2])
        if k == 0:
            sc.text("  What was checked (all pass)  ", 40, 640, size=30, bold=True, color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
            lines = ["every part vs every other part: no overlaps", "every screw: hole lines up, length, thread, tool reaches it (51 joint groups)",
                     "every cable route: through openings only, clear of the doors", "doors, links, bins, tray, tower, lid, PSU: moved through their range",
                     "raw / sleeved / double-sleeved card: every pose, no collisions", "every printed part: fits the bed, no unsupported islands"]
            for i, l in enumerate(lines):
                sc.text("  - " + l + "  ", 40, 590 - 34 * i, size=21, color=(1, 1, 1), bg=(0.12, 0.12, 0.15))
        F.frame()
    F.finish()
    json.dump(F.marks, open(os.path.join(OUT, "chapters.json"), "w"))
    print("frames", F.frames, "seconds", F.frames / FPS, F.marks)

if __name__ == "__main__":
    main()
