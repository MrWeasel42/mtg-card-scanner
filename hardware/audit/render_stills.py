import os, sys, os, math, json
import numpy as np, trimesh
from viz import *
OUT = os.path.join(HERE, "renders")
L = END_X0 + END_L
def base_scene(w=1600, h=900, skip=()):
    sc = Scene(w, h)
    sc.load(skip=tuple(skip))
    fm = fin_meshes()
    for k in range(int(LOOP // PITCH)):
        for sg in (1, -1):
            sc.add(f"fin_{sg}_{k}", fm[sg], kind="fin", M=fin_pose(k * PITCH + 40))
    sc.add("belts", belt_meshes(), kind="belt")
    # a stack of raw cards in the hopper (leaning with the tower), cards in a few bins
    st = trimesh.creation.box(extents=(88, 63, 120)); st.apply_translation((TOWER_EXIT_X - 44.5, 0, PATH + 60.5))
    st.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-TOWER_LEAN), [1, 0, 0], [0, 0, PATH]))
    st.apply_transform(trimesh.transformations.rotation_matrix(math.radians(TOWER_LEAN_X), [0, 1, 0], [TOWER_EXIT_X, 0, PATH]))
    sc.add("stack", st, kind="stack")
    for i, hgt in enumerate((40, 15, 70, 25, 55, 10, 35, 20, 60)[:BINS]):
        b = trimesh.creation.box(extents=(88, 63, hgt)); b.apply_translation((BIN_X[i] + BIN_DX, BIN_Y, 2 + hgt / 2))
        sc.add(f"binstack_{i}", b, kind="stack")
    return sc
def everything_but(sc, keep_prefix):
    return [n for n in sc.actors if not n.startswith(keep_prefix)]
def shot(sc, name, pos, foc, angle=30, up=(0, 0, 1)):
    sc.camera(pos, foc, up=up, angle=angle); sc.png(os.path.join(OUT, name + ".png")); print(name, flush=True)

if __name__ == "__main__":
    sc = base_scene()
    shot(sc, "01_iso_front", (L * 0.15, -1250, 900), (L * 0.45, 0, 150), 32)
    shot(sc, "02_iso_back", (L * 0.85, 1300, 800), (L * 0.45, 0, 150), 32)
    shot(sc, "03_top", (L * 0.5, 0, 2600), (L * 0.5, 0, 150), 32, up=(0, 1, 0))
    # feeder: section through the middle (Y = 0), seen from the front
    names = [n for n in sc.actors if not n.startswith(("screen_", "pod_", "conv5", "mount_wall"))]
    sc.clip(names, (0, 0.0, 0), (0, 1, 0))
    for n in ("screen_cradle", "pod_cover", "pod_standoff", "screen_block", "conv5", "mount_wall_gap"):
        sc.show(n, False)
    shot(sc, "04_feeder_section", (90, -420, 230), (90, 0, 200), 34)
    shot(sc, "05_gate_closeup", (112, -75, 212), (114, 0, 207), 30)
    shot(sc, "06_scan_section", (300, -620, 300), (300, 0, 230), 38)
    shot(sc, "07_bin_section", (480, -330, 170), (480, 0, 150), 40)
    sc.unclip()
    # bin module from inside: door, servo, link (cut at Y = 30 from the front, looking back)
    sc.clip([n for n in sc.actors], (0, 20.0, 0), (0, 1, 0))
    shot(sc, "08_door_servo", (470, -160, 175), (465, 35, 180), 34)
    sc.unclip()
    # electronics bay: front wall + bay cover off
    sc.clip([n for n in sc.actors if n in ("feeder_base",)], (0, -55.0, 0), (0, 1, 0))
    sc.show("bay_cover", False); sc.show("bay_fan", True)
    shot(sc, "09_bay", (75, -330, 120), (75, 0, 70), 40)
    sc.unclip(); sc.show("bay_cover", True)
    # under the scanner: PSU, IEC inlet (front wall cut away)
    sc.clip([n for n in sc.actors if n.startswith(("scan_side_front", "scan_floor"))], (0, -46.0, 0), (0, 1, 0))
    shot(sc, "10_psu_iec", (250, -360, 100), (250, 0, 90), 40)
    sc.unclip()
    shot(sc, "11_end_module", (END_X0 + 300, -420, 420), (END_X0 + 60, 0, 180), 38)
    shot(sc, "12_back_channel", (500, 420, 120), (420, 60, 60), 40)
