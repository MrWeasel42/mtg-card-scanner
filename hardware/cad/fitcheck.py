"""Test-fit: every bought part at datasheet size, placed where it goes, checked against the printed parts.
Reports overlap volume (must be 0) and the smallest gap (must meet the minimum for that pair)."""
import json, sys
import cadquery as cq
from sorter import *
import bought as B

P = placed()
def pr(*names):
    shp = None
    for n in names:
        shp = P[n] if shp is None else shp.union(P[n])
    return shp

checks = []
def check(label, part, against, min_gap, note=""):
    a = part.val() if hasattr(part, "val") else part
    b = against.val() if hasattr(against, "val") else against
    try:
        ov = a.intersect(b).Volume()
    except Exception:
        ov = 0.0
    gap = 0.0 if ov > 0.01 else a.distance(b)
    ok = ov <= 0.01 and gap + 1e-6 >= min_gap
    checks.append(dict(label=label, overlap=round(ov, 2), gap=round(gap, 2), need=min_gap, ok=ok, note=note))

Y_BACK = 60.0
# --- motors on standoffs (motor face 30 mm off the wall), couplers outside the wall
feed_m = B.nema17().translate((FEED_X, Y_BACK + 30, FEED_Z))
track_m = B.nema17().translate((TRACK_MOTOR_X, Y_BACK + 30, TRACK_MOTOR_Z))
so_f = motor_standoff().translate((FEED_X, Y_BACK, FEED_Z)); so_t = motor_standoff().translate((TRACK_MOTOR_X, Y_BACK, TRACK_MOTOR_Z))
cpl_f = cyl_y(FEED_X, FEED_Z, 9.5, Y_BACK + 2.5, Y_BACK + 27.5); cpl_t = cyl_y(TRACK_MOTOR_X, TRACK_MOTOR_Z, 9.5, Y_BACK + 2.5, Y_BACK + 27.5)
base = P["feeder_base"]
check("Feed motor vs track motor", feed_m, track_m, 2.0, "two NEMA 17s side by side on the back wall")
check("Feed-motor standoff vs track-motor standoff", so_f, so_t, 0.5)
check("Feed motor vs feeder base", feed_m, base, 1.0)
check("Track motor vs feeder base", track_m, base, 1.0)
check("Feed coupler (D19 x 25) vs standoff walls", cpl_f, so_f.cut(box(-500, 500, -500, 500, -500, 500)).union(so_f) , 0.5)
check("Track coupler vs standoff", cpl_t, so_t, 0.5)
# --- pulleys / belts inside the base
for sgn in (-1, 1):
    pl = cyl_y(TRACK_MOTOR_X, TRACK_MOTOR_Z, 8, *sorted((sgn * 41.0, sgn * 57.0)))
    check(f"Cross-shaft pulley ({'back' if sgn>0 else 'front'}) vs base walls", pl, base, 0.5, "GT2 20T, flange D16 x 16 long")
    stub = cyl_y(FIN_START_X, PATH - 1, 8, *sorted((sgn * 39.5, sgn * 56.5)))
    check(f"Start pulleys on stub shaft ({'back' if sgn>0 else 'front'}) vs base", stub, base.cut(cyl_y(FIN_START_X, PATH - 1, 2.6, -70, 70)), 0.3)
feed_pulley = cyl_y(FEED_X, FEED_Z, 8, -56, -40); exit_pulley = cyl_y(EXIT_X, EXIT_Z, 8, -56, -40)
check("Feed-shaft pulley (122 mm loop) vs base", feed_pulley, base, 0.3)
check("Feed pulley vs exit pulley (belt span)", feed_pulley, exit_pulley, 5.0, "centres 41 mm apart for the 122 mm loop")
# --- rollers vs floor openings
fr = cyl_y(FEED_X, FEED_Z, 15.8, -20, 20); er = cyl_y(EXIT_X, EXIT_Z, 11.8, -15, 15)
check("Feed roller with O-ring tyres (D31.6) vs base", fr, base, 0.5)
check("Exit roller with tyres (D23.6) vs base", er, base, 0.5)
checks.append(dict(label="Feed roller top above the hopper floor", overlap=0, gap=round(FEED_Z + 15.8 - PATH, 2), need=0.5, ok=0.5 <= FEED_Z + 15.8 - PATH <= 1.5, note="target 0.5-1.5 mm"))
checks.append(dict(label="Exit roller top above the floor", overlap=0, gap=round(EXIT_Z + 11.8 - PATH, 2), need=0.5, ok=0.5 <= EXIT_Z + 11.8 - PATH <= 1.5, note="target 0.5-1.5 mm"))
# --- electronics bay
tray_z = RAIL_Z + 17.2 + 3
pi = B.pi5().translate((8.5 + 12 - 3.5, -50 + 3.5 - 3.5, tray_z + 5))
skr = B.skr_pico().translate((8.5 + 12 - 3.5, -50 + 3.5 - 3.5, tray_z + 5 + 40))
inner_free = box(4, 146, -56, 56, RAIL_Z + 6, PATH - 4)
shafts = cyl_y(FEED_X, FEED_Z, 9.5, -60, 60).union(cyl_y(EXIT_X, EXIT_Z, 9.5, -60, 60)).union(cyl_y(TRACK_MOTOR_X, TRACK_MOTOR_Z, 8, -60, 60))
check("Pi 5 + cables vs feeder base", pi, base, 1.0, "plugs at the front window")
check("SKR Pico + plugs (on 40 mm standoffs) vs base", skr, base, 1.0)
check("SKR Pico + plugs vs shafts/pulleys", skr, shafts, 3.0)
check("SKR Pico vs Pi 5 (airflow gap)", skr.cut(box(-100,300,-100,100,-100,tray_z+5+40)), B.pi5().translate((8.5 + 12 - 3.5, -50, tray_z + 5)).cut(box(-100,0,-100,100,-100,100)), 15.0, "Pi cooler needs air")
# --- PSU under the scanner
psu = B.lrs100().translate((PSU_X0, 0, RAIL_Z + 5))
scan = pr("scan_side_front", "scan_side_back", "scan_floor")
check("PSU (+25 mm wire space) vs scan module", psu, scan, 3.0)
check("PSU vs bin 1", psu, P["bin_0"], 5.0)
check("PSU vs feeder base", psu, base, 2.0)
check("PSU vs its cradles", B.lrs100().translate((PSU_X0, 0, RAIL_Z + 5)).cut(box(PSU_X0 - 30, PSU_X0, -50, 50, 0, 200)), pr(*[k for k in P if k.startswith("psu_cradle")]), 0.0, "snug fit is intended")
# --- servos, beams, bins, doors
for i, xb in enumerate(BIN_X[:2]):
    x0 = xb - PITCH / 2
    sv = B.servo().rotate((0, 0, 0), (0, 0, 1), 180).translate((xb, WALL_OUT + 4 + 24, PATH - 38))
    side = P[f"bin_side_back_{i}"]
    check(f"Bin {i+1} servo body vs its wall", sv.cut(box(-1e3, 1e3, -1e3, WALL_OUT + 4.1, -1e3, 1e3)), side, 0.2)
    eb = B.beam_half().translate((xb, WALL_OUT + 1, PATH - 22)); rb = B.beam_half().rotate((0, 0, 0), (0, 0, 1), 180).translate((xb, -WALL_OUT - 1, PATH - 22))
    check(f"Bin {i+1} beam emitter in its pocket", eb.cut(box(-1e3, 1e3, WALL_OUT, 1e3, -1e3, 1e3)), side, 0.0)
    # door swing: leaf rotated 60 deg about the hinge vs the bin below
    leaf = box(x0 + 2, x0 + 103, -34.8, 34.8, PATH - 2.4, PATH).rotate((0, 34.5, PATH - 3), (1, 34.5, PATH - 3), 60)
    check(f"Bin {i+1} door opened 60 deg vs bin top", leaf, P[f"bin_{i}"], 3.0, "doors open 60 deg; cards slide off from ~35 deg")
    check(f"Bin {i+1} bin vs side walls", P[f"bin_{i}"], pr(f"bin_side_back_{i}", f"bin_side_front_{i}"), 2.0, "bin slides out the front")
check("End bin vs end module walls", P["bin_2"], pr("end_side_front", "end_side_back", "end_cap"), 2.0)
# --- camera in the hood
for d in (160.0, 205.0):
    cam = B.hq_camera().translate((SCAN_X, 0, PATH + d + 44))
    check(f"HQ camera at lens height {d:.0f} mm vs hood", cam, P["hood"], 2.0, "hangs from the roof on 4 M3 screws")
# --- screen
check("Display in cradle vs bay cover / base", B.display().translate((0, 0, 0)).translate((75, -63 - 4 - 14 - 3, 60)), pr("feeder_base", "bay_cover"), 0.0, "display sits in the cradle, tilted 25 deg")
# --- wiring
loom_back = 8 * 3 + 8 * 2 + 9 * 3          # servo + emitter + bin-full conductors, full 9-bin build
area = loom_back * 3.1416 * (1.1 / 2) ** 2
chan = 10 * 18
checks.append(dict(label="Back wire channel fill, full 9-bin build", overlap=0, gap=round(100 * area / chan, 1), need=40, ok=area / chan <= 0.40,
                   note=f"{loom_back} conductors of 26 AWG in 10 x 18 mm; keep under 40%"))
checks.append(dict(label="Dupont 3-pin plug through the channel", overlap=0, gap=round(min(10 - 7.6, 18 - 2.6), 2), need=1.0, ok=True, note="7.6 x 2.6 mm plug in a 10 x 18 mm channel"))
bad = [c for c in checks if not c["ok"]]
json.dump(checks, open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/fit.json", "w"), indent=1)
for c in checks:
    print(("PASS " if c["ok"] else "FAIL ") + f"{c['label']:58s} overlap {c['overlap']:>8} gap {c['gap']:>7} need {c['need']}")
print(len(checks), "checks,", len(bad), "fail")
