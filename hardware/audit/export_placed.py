import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
os.environ.setdefault("SORTER_BINS", "9")
import cadquery as cq
from sorter import *
import bought as B
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "placed")
P = placed()
from extras import extras
E = extras()
import shutil; shutil.rmtree(out, ignore_errors=True); os.makedirs(out, exist_ok=True)
names = {}
for d in (P, E):
    for k, v in d.items():
        fn = os.path.join(out, k + ".stl")
        cq.exporters.export(v, fn, tolerance=0.05, angularTolerance=0.2)
        names[k] = "printed" if d is P else "extra"
json.dump(names, open(os.path.join(out, "index.json"), "w"), indent=0)
print(len(names))
