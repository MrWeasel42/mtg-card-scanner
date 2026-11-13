"""One STEP file of the whole 3-bin prototype: every printed part placed, plus the main bought parts
(as simple envelopes), each as a named, coloured body. Opens in Onshape, Fusion, FreeCAD."""
import sys
import cadquery as cq
from sorter import *
import bought as B

out = sys.argv[1] if len(sys.argv) > 1 else "../step/card_sorter_assembly.step"
P = placed()
A = cq.Assembly(name="card_sorter_3bin")
petg = cq.Color(0.24, 0.29, 0.36); black = cq.Color(0.08, 0.09, 0.1); white = cq.Color(0.9, 0.92, 0.93)
alu = cq.Color(0.72, 0.75, 0.78); teal = cq.Color(0.18, 0.83, 0.75); dark = cq.Color(0.12, 0.12, 0.13)
for k, v in P.items():
    col = black if k in ("hood", "scan_floor") else (white if k.startswith("bin_") and "side" not in k else petg)
    A.add(v, name=k, color=col)
# bought parts (envelopes, for fit)
A.add(box(-5, LENGTH + 5, RAIL_Y - 10, RAIL_Y + 10, 0, 20), name="rail_2020_back", color=alu)
A.add(box(-5, SCAN_X1, -RAIL_Y - 10, -RAIL_Y + 10, 0, 20), name="rail_2020_front", color=alu)
A.add(box(BIN_X[0] - PITCH / 2, BIN_X[1] + PITCH / 2, RAIL2_Y - 10, RAIL2_Y + 10, 0, 20), name="rail_2020_back_inner", color=alu)
A.add(B.nema17().translate((FEED_X, 90, FEED_Z)), name="motor_feed_NEMA17", color=dark)
A.add(B.nema17().translate((END_SHAFT_X, WALL_OUT + 30, PUL_Z)), name="motor_track_NEMA17", color=dark)
A.add(motor_standoff().translate((FEED_X, 60, FEED_Z)), name="motor_standoff_feed", color=petg)
A.add(motor_standoff().translate((END_SHAFT_X, WALL_OUT, PUL_Z)), name="motor_standoff_track", color=petg)
A.add(B.lrs100().translate((PSU_X0, 0, RAIL_Z + 5)), name="PSU_LRS-100-24_with_wire_space", color=alu)
A.add(B.hq_camera().translate((SCAN_X, 0, PATH + CAM_D + 44)), name="Pi_HQ_camera_6mm_lens", color=dark)
yc = (BELT_Y0 + BELT_Y1) / 2
for s in (-1, 1):
    y0, y1 = sorted((s * BELT_Y0, s * BELT_Y1))
    nm = "back" if s > 0 else "front"
    A.add(box(FIN_START_X, END_SHAFT_X, y0, y1, BELT_BACK_LOW, BELT_BACK_LOW + 1.38), name=f"belt_{nm}_bottom_run", color=dark)
    A.add(box(FIN_START_X, END_SHAFT_X, y0, y1, PUL_Z + PUL_R - 0.9, PUL_Z + PUL_R + 0.45), name=f"belt_{nm}_top_run", color=dark)
    for x, drv in ((FIN_START_X, False), (END_SHAFT_X, True)):
        # simplified pulley (teeth left out to keep the file small; the real part is track_pulley_*.step)
        pul = cyl_y(0, 0, PUL_R - 0.25, -5.5, 5.5).union(cyl_y(0, 0, 12, -6.5, -5.5)).union(cyl_y(0, 0, 12, 5.5, 6.5))
        A.add(pul.translate((x, s * yc, PUL_Z)), name=f"pulley_{'drive' if drv else 'idler'}_{nm}", color=alu)
    fn = fin() if s > 0 else fin().mirror("XZ")
    for i in range(5):
        A.add(fn.translate((FIN_START_X + 8 + i * PITCH, s * yc, BELT_BACK_LOW)), name=f"fin_{nm}_{i + 1}", color=teal)
A.add(cyl_y(END_SHAFT_X, PUL_Z, 2.5, -WALL_OUT, WALL_OUT + 30), name="track_drive_shaft_5mm", color=alu)
for i, xb in enumerate(BIN_X[:2]):
    A.add(B.servo().rotate((0, 0, 0), (0, 0, 1), 180).translate((xb, WALL_OUT + 4 + 24, PATH - 38)), name=f"servo_bin{i + 1}", color=cq.Color(0.17, 0.37, 0.68))
A.save(out, "STEP")
print("saved", out)
