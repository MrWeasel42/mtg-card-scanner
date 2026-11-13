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
put("motor_track", box(TRACK_MOTOR_X - 21, TRACK_MOTOR_X + 21, 60, 108, TRACK_MOTOR_Z - 21, TRACK_MOTOR_Z + 21), "motor")
# belts: top run + return run each side
for s in (-1, 1):
    y0, y1 = sorted((s * BELT_Y0, s * BELT_Y1))
    put(f"belt_top_{s}", box(FIN_START_X, xe_end := BIN_X[1] + PITCH / 2 + 90, y0, y1, PATH + 4.6, PATH + 6.0), "belt")
    put(f"belt_ret_{s}", box(FIN_START_X, xe_end, y0, y1, PATH - 7.4, PATH - 6.0), "belt")
    for x in (FIN_START_X, xe_end):
        put(f"pulley_{s}_{int(x)}", cyl_y(x, PATH - 0.7, 6.4, y0 - 1, y1 + 1), "alu")
    # fins every pitch on the top run
    for i in range(5):
        fx = 128 + i * PITCH
        put(f"finv_{s}_{i}", box(fx, fx + 8, *sorted((s * 28.0, s * 47.0)), PATH + 0.6, PATH + 6.0), "fin")
# cards: in the hopper, under the camera, one dropping in bin 2
put("stack", box(TOWER_X0 + 0.7, TOWER_X0 + 88.7, -31.5, 31.5, PATH, PATH + 120), "stack")
put("card_scan", box(SCAN_X - 44, SCAN_X + 44, -31.5, 31.5, PATH, PATH + 0.6), "card")
put("card_bin1", box(BIN_X[0] - 44, BIN_X[0] + 44, -31.5, 31.5, PATH, PATH + 0.6), "card")
for i, h in enumerate((60, 25, 90)):
    put(f"cards_in_bin{i}", box(BIN_X[i] - 44, BIN_X[i] + 44, -31.5, 31.5, 2, 2 + h * 0.3), "stack")
# the 7 in display in its cradle (picture only)
put("display", box(SCAN_X - 94.7, SCAN_X + 94.7, -12, 0, 0, 120.3).rotate((0,0,0),(1,0,0),-20).translate((0, -62 - 8 - 4, PATH + HOOD_H + 19 - 7 + 2)), "screen")
# PSU on its side under the scanner
put("psu", box(SCAN_X0 + 8, SCAN_X0 + 8 + PSU_L, -PSU_H / 2, PSU_H / 2, RAIL_Z + 5, RAIL_Z + 5 + PSU_W), "alu")
# camera on the hood roof
put("camera", box(SCAN_X - 19, SCAN_X + 19, -19, 19, PATH + HOOD_H, PATH + HOOD_H + 25), "motor")
# servos on the back walls
for xb in BIN_X[:2]:
    put(f"servo_{int(xb)}", box(xb - 11.5, xb + 11.5, WALL_OUT + 4, WALL_OUT + 16, PATH - 44, PATH - 32), "servo")
json.dump(items, open(os.path.join(out, "items.json"), "w"))
print(len(items), "parts; length", L)
