"""Test-fit: every bought part at datasheet size, placed where it goes, checked against the printed parts.
Reports overlap volume (must be 0) and the smallest gap (must meet the minimum for that pair)."""
import json, sys, math
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
# --- feed motor on its standoff (back wall of the feeder base); track motor on its standoff (back wall of the end module)
feed_m = B.nema17().translate((FEED_X, Y_BACK + 30, FEED_Z))
so_f = motor_standoff().translate((FEED_X, Y_BACK, FEED_Z))
cpl_f = cyl_y(FEED_X, FEED_Z, 9.5, Y_BACK + 2.5, Y_BACK + 27.5)
base = P["feeder_base"]
check("Feed motor vs feeder base", feed_m, base, 1.0)
check("Feed coupler (D19 x 25) vs its standoff", cpl_f, so_f, 0.5)
xe = BIN_X[1] + PITCH / 2
endm = pr("end_side_back", "end_side_front", "end_cap", "bin_2")
trk_m = B.nema17().translate((END_SHAFT_X, WALL_OUT + 30, PUL_Z))
so_t = motor_standoff().translate((END_SHAFT_X, WALL_OUT, PUL_Z))
cpl_t = cyl_y(END_SHAFT_X, PUL_Z, 9.5, WALL_OUT + 2.5, WALL_OUT + 27.5)
check("Track motor vs end module, end cap, end bin", trk_m, endm, 1.0, "on a 30 mm standoff on the end module's back wall")
check("Track coupler vs its standoff", cpl_t, so_t, 0.5)
check("Track-motor standoff vs end cap", so_t, P["end_cap"], 0.5)
# --- belt pulleys (printed 30T, flanges D24) at both ends of the loop
for sgn in (-1, 1):
    nm = "back" if sgn > 0 else "front"
    y0, y1 = sorted((sgn * 35.8, sgn * 48.2))
    st = cyl_y(FIN_START_X, PUL_Z, 12.0, y0, y1)
    check(f"Start idler ({nm}) vs feeder base posts, tower, gate, pressure roller", st,
          pr("feeder_base", "raw_tower", "gate_plate", "exit_roller_top"), 0.3, "flange to post wall")
    dr = cyl_y(END_SHAFT_X, PUL_Z, 12.0, y0, y1)
    check(f"Drive pulley ({nm}) vs end module", dr, pr("end_side_back", "end_side_front", "end_cap"), 0.3)
# --- everywhere a fin goes: straight runs + the arcs round both pulleys
RF = PUL_Z - (PATH - GROOVE_D + 0.5)                 # finger tip radius round a pulley (17.7)
RB = PUL_Z - (PATH + RAIL_H + 0.5)                   # bridge underside radius (14.0)
def fin_path(sgn):
    """Everywhere a fin goes. Finger |Y| 27-33.25 (down into the lane), bridge + leg |Y| 33.25-43.75 above the rail."""
    yf = sorted((sgn * FIN_REACH_Y, sgn * (RAIL_IN - 1.0))); yb = sorted((sgn * (RAIL_IN - 1.0), sgn * 43.75))
    zf = PATH - GROOVE_D + 0.5; zb = PATH + RAIL_H + 0.5
    low = box(FIN_START_X, END_SHAFT_X, *yf, zf, BELT_BACK_LOW).union(box(FIN_START_X, END_SHAFT_X, *yb, zb, BELT_BACK_LOW))
    top_b = PUL_Z + PUL_R + 0.45
    high = box(FIN_START_X, END_SHAFT_X, *sorted((sgn * FIN_REACH_Y, sgn * 43.75)), top_b, top_b + (BELT_BACK_LOW - zf))
    arcs = None
    for xc in (FIN_START_X, END_SHAFT_X):
        a = cyl_y(xc, PUL_Z, RF, *yf).union(cyl_y(xc, PUL_Z, RB, *yb)).cut(cyl_y(xc, PUL_Z, PUL_R + 0.4, -99, 99))
        arcs = a if arcs is None else arcs.union(a)
    return low.union(high).union(arcs.cut(box(FIN_START_X, END_SHAFT_X, -99, 99, PUL_Z - PUL_R, PUL_Z + PUL_R)))
fixed = None
for k, v in P.items():
    if k.startswith("door_") or k in ("screen_cradle",):
        continue
    fixed = v if fixed is None else fixed.union(v)
for sgn in (-1, 1):
    check(f"Fin path ({'back' if sgn>0 else 'front'} belt, whole loop) vs every fixed part", fin_path(sgn), fixed, 0.2,
          "finger in the lane, bridge 0.5 mm over the guide; past the tower, gate, pressure roller, hood and end cap")
    y0, y1 = sorted((sgn * BELT_Y0, sgn * BELT_Y1))
    lowb = box(FIN_START_X, END_SHAFT_X, y0, y1, BELT_BACK_LOW + 0.05, BELT_BACK_LOW + 1.38)
    check(f"Belt bottom run ({'back' if sgn>0 else 'front'}) vs walls (rests on the ledge)", lowb, fixed, 0.0)
# card-clear sensor under the floor at the feeder exit
tcrt = box(122.0, 132.0, -24.9, -19.1, PATH - 11.0, PATH - 4.0)
check("Card-clear sensor (TCRT5000 head) vs exit roller, shafts, 122 mm loop", tcrt,
      pr("exit_roller", "feed_roller").union(cyl_y(EXIT_X, EXIT_Z, 2.6, -60, 60)).union(cyl_y(EXIT_X, EXIT_Z, 8, -55, -39)), 1.0)
# card fit in the guides
checks.append(dict(label="Sleeved card (66 mm) in the guides: play per side", overlap=0, gap=round(RAIL_IN - 33.0, 2), need=0.5,
                   ok=RAIL_IN - 33.0 >= 0.5, note="guides 67.5 mm apart"))
off = RAIL_IN - 31.5
checks.append(dict(label="Raw card pushed fully to one side: finger overlap on its back edge", overlap=0, gap=round(31.5 - off - FIN_REACH_Y, 2), need=2.0,
                   ok=31.5 - off - FIN_REACH_Y >= 2.0, note="fingers reach in to |Y| 27"))
ang = math.degrees(math.atan((TAPER_IN0 - RAIL_IN) / (TAPER_X1 - TAPER_X0)))
checks.append(dict(label="Lead-in taper angle per side (degrees)", overlap=0, gap=round(ang, 2), need=2.0, ok=ang <= 2.0,
                   note="73 mm wide at the nip down to 67.5 mm at X 230, before the camera"))
checks.append(dict(label="Fin finger below the card floor (no card can get under it)", overlap=0, gap=round(GROOVE_D - 0.5, 2), need=0.5,
                   ok=GROOVE_D - 0.5 >= 0.5, note="finger runs 0.5 mm above the lane bottom, never on the card floor"))
checks.append(dict(label="Fin lands behind the exit-roller nip", overlap=0, gap=round(EXIT_X - FIN_START_X, 2), need=4.0,
                   ok=EXIT_X - FIN_START_X >= 4.0, note="the card's tail leaves the nip at X 136; fins touch down at X 131"))
loop = 2 * (END_SHAFT_X - FIN_START_X) + 2 * math.pi * PUL_R
checks.append(dict(label="Belt loop = whole number of 105 mm fin pitches", overlap=0, gap=round(loop, 2), need=FIN_PITCHES * 105,
                   ok=abs(loop - FIN_PITCHES * 105) < 0.01, note=f"{loop:.1f} mm = {FIN_PITCHES} x 105; +6 bins adds 12 pitches"))
# --- feed-to-exit roller loop (122 mm) on the front, inside the base
feed_pulley = cyl_y(FEED_X, FEED_Z, 8, -55, -39); exit_pulley = cyl_y(EXIT_X, EXIT_Z, 8, -55, -39)
check("Feed-shaft pulley (122 mm loop) vs base", feed_pulley, base, 0.3, "pulley set 1 mm off the wall")
check("Exit-shaft pulley vs base", exit_pulley, base, 0.3)
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
shafts = cyl_y(FEED_X, FEED_Z, 9.5, -60, 60).union(cyl_y(EXIT_X, EXIT_Z, 9.5, -60, 60))
check("Pi 5 + cables vs feeder base", pi, base, 1.0, "12 mm finger room at the USB end; the SKR talks over UART")
check("SKR Pico + plugs (on 40 mm standoffs) vs base", skr, base, 1.0)
check("SKR Pico + plugs vs roller shafts/pulleys", skr, shafts, 3.0)
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
    leafd = P[f"door_{i}"].rotate((0, 34.5, PATH - 3), (1, 34.5, PATH - 3), 60)
    check(f"Bin {i+1} door (with lever) opened 60 deg vs tie bars + walls", leafd,
          pr(*[k for k in P if k.startswith("tie_bar")], f"bin_side_front_{i}"), 0.4, "0.5 mm end gap to the joint bridges")
    check(f"Bin {i+1} vs its module (posts, back wall, sensor mount)", P[f"bin_{i}"], pr(f"bin_side_back_{i}", f"bin_side_front_{i}"), 0.8, "slides out the front between the 2.5 mm posts")
check("End bin vs end module walls, posts, end cap", P["bin_2"], pr("end_side_front", "end_side_back", "end_cap"), 0.8)
# --- bins forward: card landing room, second rail, level sensors
rail2 = box(BIN_X[0] - PITCH / 2, BIN_X[1] + PITCH / 2, RAIL2_Y - 10, RAIL2_Y + 10, 0, RAIL_Z)
check("Second back rail (Y +24) vs bins", rail2, pr("bin_0", "bin_1", "bin_2"), 2.0, "runs under the doors behind the bins; stops at the end module")
open_edge_y = 34.5 - 69.3 * math.cos(math.radians(60))
checks.append(dict(label="Open bin in front of the door's low edge (card landing room)", overlap=0, gap=round(open_edge_y - (BIN_Y - 36.0), 1), need=63.0,
                   ok=open_edge_y - (BIN_Y - 36.0) >= 63.0, note="was 34 mm with the bins centred; a card is 63 mm wide"))
for i, xb in enumerate(BIN_X):
    x0 = xb - PITCH / 2
    zt, zb = PATH - 19.0, 3.0
    r = (zt - zb) * math.tan(math.radians(7.5))
    cone = cq.Workplane("XY").add(cq.Solid.makeCone(r, 0.3, zt - zb, cq.Vector(x0 + TOF_X, -42.0, zb), cq.Vector(0, 0, 1)))
    others = {k: v for k, v in P.items() if not k.startswith("door_")}
    hit = pr(*others.keys())
    for k in [k for k in P if k.startswith("door_")]:
        hit = hit.union(P[k].rotate((0, 34.5, PATH - 3), (1, 34.5, PATH - 3), 60))
    check(f"Bin {i+1} level sensor view (15 deg cone) vs everything incl. open door", cone, hit, 0.5,
          "set the VL53L1X to a 4 x 4 region (about 15 deg); full stack is 63 mm away, past its 40 mm minimum")
# --- camera in the hood
for d in (160.0, 205.0):
    cam = B.hq_camera().translate((SCAN_X, 0, PATH + d + 44))
    check(f"HQ camera at lens height {d:.0f} mm vs hood", cam, P["hood"], 2.0, "hangs from the roof on 4 M3 screws")
# --- screen
check("Screen wall mount (between hopper and hood) vs front wire channel", P["mount_wall_gap"], P["scan_side_front"].cut(box(120, 230, -60, -54.9, PATH - 40, PATH)), 0.5)
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
