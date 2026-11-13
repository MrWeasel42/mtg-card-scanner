import os, re, json, sys
import cadquery as cq
from sorter import PRINTED
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
views = {"iso": (-1, 1.2, -0.9), "top": (0, 0, 1), "front": (0, -1, 0), "side": (1, 0, 0)}
meta = {}
for name, (fn, qty, mat, note) in PRINTED.items():
    s = fn(); bb = s.val().BoundingBox()
    s = s.rotate((0, 0, 0), (1, 0, 0), 180)   # CadQuery's SVG export draws Z down; flip so drawings read upright
    meta[name] = dict(qty=qty, mat=mat, note=note, x=round(bb.xlen, 1), y=round(bb.ylen, 1), z=round(bb.zlen, 1))
    for v, d in views.items():
        f = os.path.join(out, f"{name}_{v}.svg")
        cq.exporters.export(s, f, opt={"width": 420, "height": 300, "marginLeft": 10, "marginTop": 10, "showAxes": False,
                                       "projectionDir": d, "strokeWidth": 0.6 if v == "iso" else 0.5, "strokeColor": (20, 33, 43),
                                       "hiddenColor": (150, 160, 170), "showHidden": v != "iso"})
json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=1)
print(len(meta))
