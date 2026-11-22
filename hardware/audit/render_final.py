"""The pictures for hardware/renders (README + design page), from the audited meshes."""
import os, sys, os, math
import numpy as np, trimesh
from viz import *
from render_stills import base_scene
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "renders")
os.makedirs(OUT, exist_ok=True)
L = END_X0 + END_L
def shot(sc, name, pos, foc, angle=30, up=(0, 0, 1)):
    sc.camera(pos, foc, up=up, angle=angle); sc.png(os.path.join(OUT, name + ".png")); print(name, flush=True)
sc = base_scene(1600, 1000)
V, F, _ = ribbon_strip(); sc.add("ribbon", trimesh.Trimesh(V, F), kind="wire", color=(0.85, 0.65, 0.2))
everything = list(sc.actors)
pod = ("screen_cradle", "pod_cover", "pod_standoff", "screen_block", "conv5", "mount_wall_gap")
shot(sc, "asm_iso", (L * 0.12, -1300, 880), (L * 0.45, 0, 160), 32)
shot(sc, "asm_back", (L * 0.85, 1300, 800), (L * 0.45, 0, 150), 32)
shot(sc, "asm_screen", (60, -560, 420), (200, -40, 260), 40)
shot(sc, "ribbon_route", (120, -420, 560), (215, 0, 330), 42)
# feeder section
for p in pod: sc.show(p, False)
sc.clip([n for n in everything if n not in pod], (0, 0.0, 0), (0, 1, 0))
shot(sc, "feeder", (85, -430, 250), (90, 0, 190), 38)
shot(sc, "hood_cutaway", (SCAN_X - 40, -640, 360), (SCAN_X, 0, PATH + 90), 38)
shot(sc, "hood_cutaway_iso", (SCAN_X - 260, -520, 600), (SCAN_X, 0, PATH + 80), 38)
sc.unclip()
for p in pod: sc.show(p, True)
# door + servo from inside the module (front half cut away)
sc.clip(everything, (0, 20.0, 0), (0, 1, 0))
x0 = BIN_X[0] - PITCH / 2
shot(sc, "door_servo", (x0 + 30, -120, 150), (x0 + 80, 35, 185), 44)
sc.unclip()
# bin hub: from behind, back panel off
xh = BIN_X[HUB_MODULE] - PITCH / 2
sc.show(f"back_panel_{HUB_MODULE}", False)
shot(sc, "bin_hub", (xh + 61, 330, 110), (xh + 61, 40, 100), 40)
sc.show(f"back_panel_{HUB_MODULE}", True)
# lid off with the camera hanging from it
for n in ("hood_lid", "camera", "camera_plate"):
    sc.move(n, trimesh.transformations.translation_matrix((0, 0, 130)))
shot(sc, "hood_lid_off", (SCAN_X - 380, -520, 620), (SCAN_X, 0, PATH + 200), 40)
