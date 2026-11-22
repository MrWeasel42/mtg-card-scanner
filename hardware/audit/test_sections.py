"""Small 'fit test' pieces cut out of the long prints, so the fits that matter can be checked in an hour instead of
after a 19 h print (video tip: print just the section you're evaluating). Same orientation as the real part.
Writes hardware/stl/test_sections/*.stl"""
import os, sys
import numpy as np, trimesh, manifold3d as m3d
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import FEED_X, EXIT_X, FEED_Z, PATH, PUL_Z, SLIDER_POCKET_X, END_SHAFT_X, END_X0, WALL_OUT, PITCH, HINGE_Z

STL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stl")
OUT = os.path.join(STL, "test_sections"); os.makedirs(OUT, exist_ok=True)

def man(t):
    return m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))

def cut(name, lo, hi, out):
    t = trimesh.load(f"{STL}/{name}.stl")
    b = trimesh.creation.box(bounds=[lo, hi])
    r = (man(t) ^ man(b)).to_mesh()
    res = trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)
    res.export(f"{OUT}/{out}.stl")
    print(f"{out:34s} from {name:16s} {np.round(res.extents, 1)} mm  {res.volume / 1000:.1f} cm3  bounds {np.round(t.bounds, 0).tolist()}")

if __name__ == "__main__":
    # feeder base back wall: both roller bearing seats (teardrops), the idler-slider pocket and the post top
    cut("feeder_base", (FEED_X - 18, 30, FEED_Z - 18), (SLIDER_POCKET_X[1] + 8, 80, 240), "test_feeder_seats_and_slider")
    # bin module back wall: hinge knuckles, door-rest, servo bracket, joint insert (one module end)
    cut("bin_side_back", (-1, 25, HINGE_Z - 30), (PITCH / 2 + 1, 70, HINGE_Z + 50), "test_bin_hinge_and_servo")
    # front end wall: 625 bearing seat with the 0.2 mm skin (flat print)
    xs = END_SHAFT_X - END_X0
    cut("end_side_front", (xs - 22, -WALL_OUT - 1, PUL_Z - 22), (xs + 22, -30, PUL_Z + 22), "test_end_bearing_seat")
