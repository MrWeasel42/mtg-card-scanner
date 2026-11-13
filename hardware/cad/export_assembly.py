import json, os, sys
import cadquery as cq
from sorter import *
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/asm"
os.makedirs(out, exist_ok=True)
items = []
def put(name, shape, kind):
    fn = f"{name}.stl"; cq.exporters.export(shape, os.path.join(out, fn), tolerance=0.2, angularTolerance=0.3)
    items.append({"file": fn, "kind": kind})
P = placed()
for k, v in P.items():
    kind = "black" if k in ("hood", "scan_floor") else ("bin" if k.startswith("bin_") and "side" not in k else "petg")
    put(k, v, kind)
# bought parts (for the picture only)
L = LENGTH
for y in (-RAIL_Y, RAIL_Y):
    put(f"rail_{int(y)}", box(-5, L + 5, y - 10, y + 10, 0, 20), "alu")
put("motor_feed", box(FEED_X - 21, FEED_X + 21, 60, 108, FEED_Z - 21, FEED_Z + 21), "motor")
put("motor_track", box(END_SHAFT_X - 21, END_SHAFT_X + 21, WALL_OUT + 30, WALL_OUT + 78, PUL_Z - 21, PUL_Z + 21), "motor")
put("standoff_feed", motor_standoff().translate((FEED_X, 60, FEED_Z)), "petg")
put("standoff_track", motor_standoff().translate((END_SHAFT_X, WALL_OUT, PUL_Z)), "petg")
put("track_shaft", cyl_y(END_SHAFT_X, PUL_Z, 2.5, -WALL_OUT, WALL_OUT + 30), "alu")
# 10 mm belts above the floor: bottom run pushes cards, top run returns; fins every 105 mm on the belt back
yc = (BELT_Y0 + BELT_Y1) / 2
for s in (-1, 1):
    y0, y1 = sorted((s * BELT_Y0, s * BELT_Y1))
    put(f"belt_low_{s}", box(FIN_START_X, END_SHAFT_X, y0, y1, BELT_BACK_LOW, BELT_BACK_LOW + 1.38), "belt")
    put(f"belt_high_{s}", box(FIN_START_X, END_SHAFT_X, y0, y1, PUL_Z + PUL_R - 0.9, PUL_Z + PUL_R + 0.45), "belt")
    for x, drv in ((FIN_START_X, False), (END_SHAFT_X, True)):
        pul = track_pulley(drv)
        if s < 0:
            pul = pul.rotate((0, 0, 0), (0, 0, 1), 180)
        put(f"pulley_{s}_{int(x)}", pul.translate((x, s * yc, PUL_Z)), "alu")
    fn = fin() if s > 0 else fin().mirror("XZ")
    for i in range(5):
        fx = FIN_START_X + 8 + i * PITCH
        put(f"fin_{s}_{i}", fn.translate((fx, s * yc, BELT_BACK_LOW)), "fin")
    for i in range(4):
        fx = FIN_START_X + 60 + i * PITCH
        put(f"finr_{s}_{i}", fn.mirror("XY").translate((fx, s * yc, PUL_Z + PUL_R + 0.45)), "fin")
# cards: in the hopper, under the camera, one dropping in bin 2
put("stack", box(TOWER_X0 + 0.7, TOWER_X0 + 88.7, -31.5, 31.5, PATH, PATH + 120), "stack")
put("card_scan", box(SCAN_X - 44, SCAN_X + 44, -31.5, 31.5, PATH, PATH + 0.6), "card")
put("card_bin1", box(BIN_X[0] - 44, BIN_X[0] + 44, -31.5, 31.5, PATH, PATH + 0.6), "card")
for i, h in enumerate((60, 25, 90)):
    put(f"cards_in_bin{i}", box(BIN_X[i] - 44, BIN_X[i] + 44, -31.5, 31.5, 2, 2 + h * 0.3), "stack")
# the 7 in display in its cradle (picture only)
bay_y = -63.0; bay_z = RAIL_Z + 6 + 66; piv = (75, bay_y - 4 - 14, bay_z)
disp = (box(-94.75, 94.75, -15, 0, -7, 113).translate((0, -3 - 12, -(SCREEN_H + 4) / 2))
        .rotate((0, 0, 0), (0, 0, 1), 180).rotate((0, 0, 0), (1, 0, 0), 25).translate(piv))
put("display", disp, "screen")
# PSU on its side under the scanner
put("psu", box(PSU_X0, PSU_X0 + PSU_L, -PSU_H / 2, PSU_H / 2, RAIL_Z + 5, RAIL_Z + 5 + PSU_W), "alu")
# camera on the hood roof
put("camera", box(SCAN_X - 19, SCAN_X + 19, -19, 19, PATH + CAM_D + 44, PATH + CAM_D + 56).union(cyl_z(SCAN_X, 0, 15, PATH + CAM_D, PATH + CAM_D + 44)), "motor")
# servos on the back walls
for xb in BIN_X[:2]:
    put(f"servo_{int(xb)}", box(xb - 11.5, xb + 11.5, WALL_OUT + 4, WALL_OUT + 16, PATH - 44, PATH - 32), "servo")
json.dump(items, open(os.path.join(out, "items.json"), "w"))
print(len(items), "parts; length", L)
