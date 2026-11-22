"""Hood cut in half (front wall removed) to show the inside: camera on its plate and hanger ribs, LED channel
ledges, the camera ribbon coming in low through the left wall and up under the L-rails."""
import json, os, sys
import cadquery as cq
from sorter import *
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/asm_cut"
os.makedirs(out, exist_ok=True)
items = []
def put(name, shape, kind):
    cq.exporters.export(shape, os.path.join(out, f"{name}.stl"), tolerance=0.15, angularTolerance=0.2)
    items.append({"file": f"{name}.stl", "kind": kind})
CUT_Y = -60.0                                         # everything in front of this is cut away
keep = box(-1e3, 1e3, CUT_Y, 1e3, -1e3, 1e3)
P = placed()
for k in ("hood", "hood_lid", "scan_floor", "scan_side_back", "scan_side_front", "feeder_base", "raw_tower", "bin_side_back_0",
          "bin_side_front_0", "tie_bar_0"):
    put(k, P[k].intersect(keep), "front" if k in ("hood", "hood_lid") else ("black" if k == "scan_floor" else "petg"))
put("camera_plate", camera_plate().translate((SCAN_X, 0, PATH + CAM_D + 44 - 4)), "fin")
put("camera", box(SCAN_X - 19, SCAN_X + 19, -19, 19, PATH + CAM_D + 44, PATH + CAM_D + 45.6), "servo")
put("lens", cyl_z(SCAN_X, 0, 15, PATH + CAM_D, PATH + CAM_D + 44).union(cyl_z(SCAN_X, 0, 18, PATH + CAM_D + 34, PATH + CAM_D + 44)), "alu")
put("led_back", box(HOOD_X0 + 4, HOOD_X1 - 4, 75 - 14 + 0.5, 75 - 3 - 0.5, PATH + LED_H, PATH + LED_H + 8), "alu")
put("led_strip", box(HOOD_X0 + 6, HOOD_X1 - 6, 75 - 14 + 4.5, 75 - 6, PATH + LED_H - 0.2, PATH + LED_H + 0.2), "accent")
put("card_scan", box(SCAN_X - 44, SCAN_X + 44, -31.5, 31.5, PATH, PATH + 0.6), "card")
put("ribbon", camera_ribbon()[0].intersect(keep), "card")
json.dump(items, open(os.path.join(out, "items.json"), "w"))
print(len(items), "parts")
