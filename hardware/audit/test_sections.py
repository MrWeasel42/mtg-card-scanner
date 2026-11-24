"""Small 'fit test' pieces cut out of the long prints, so the fits that matter can be checked in an hour instead of
after a 19 h print (video tip: print just the section you're evaluating). Same orientation as the real part.
Writes hardware/stl/test_sections/*.stl"""
import os, sys
import numpy as np, trimesh, manifold3d as m3d
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import FEED_X, EXIT_X, FEED_Z, PATH, PUL_Z, SLIDER_POCKET_X, END_SHAFT_X, END_X0, WALL_OUT, PITCH, HINGE_Z, SERVO_TOP_X

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

def tear_gauge():
    """Upright plate with teardrop seats at 3 sizes each for the 685 (11 mm) and 625 (16 mm) bearings.
    Numbers are embossed under each hole (tenths over the bearing size: 1 = 11.15 / 16.0 ...)."""
    import cadquery as cq
    from sorter import tear_y, box
    sizes = [(11.15, 0), (11.25, 15), (11.35, 30), (16.0, 49), (16.1, 69), (16.2, 89)]
    g = box(-8, 99, 0, 5, 0, 26)
    for d, x in sizes:
        g = g.cut(tear_y(x, 13, d / 2, -1, 6))
    for i, (d, x) in enumerate(sizes):
        for k in range(i % 3 + 1):                    # 1, 2 or 3 small ticks under each hole = smallest .. largest
            g = g.union(box(x - 3 + 2.2 * k, x - 2 + 2.2 * k, -0.6, 0.01, 0.8, 3.0))
    p = os.path.join(OUT, "test_tear_gauge.stl"); cq.exporters.export(g, p); print("test_tear_gauge", p)

if __name__ == "__main__":
    tear_gauge()
    # feeder base back wall: both roller bearing seats (teardrops), the idler-slider pocket and the post top
    cut("feeder_base", (FEED_X - 18, 30, FEED_Z - 18), (SLIDER_POCKET_X[1] + 8, 80, 240), "test_feeder_seats_and_slider")
    # bin module back wall: hinge knuckles, door-rest, servo bracket, joint insert (one module end)
    cut("bin_side_back", (-1, 25, HINGE_Z - 30), (PITCH / 2 + 1, 70, HINGE_Z + 50), "test_bin_hinge")
    # bin module back wall, other end: the servo bracket and the pocket the servo slides into (ES08MA II)
    cut("bin_side_back", (SERVO_TOP_X - 8, 25, HINGE_Z - 52), (PITCH + 1, 70, HINGE_Z + 8), "test_servo_bracket")
    # feeder inner rib: the 685ZZ seat for the feed roller shaft (teardrop, prints upright)
    cut("feeder_base", (FEED_X - 16, 18, FEED_Z - 18), (FEED_X + 16, 31, FEED_Z + 16), "test_feeder_685_seat")
    # front end wall: 625 bearing seat with the 0.2 mm skin (flat print)
    xs = END_SHAFT_X - END_X0
    cut("end_side_front", (xs - 22, -WALL_OUT - 1, PUL_Z - 22), (xs + 22, -30, PUL_Z + 22), "test_end_bearing_seat")
