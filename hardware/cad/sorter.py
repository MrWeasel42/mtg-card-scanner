"""
MTG card sorter, 3-bin prototype: parametric CAD (CadQuery).

Coordinates (mm): X along the card path (left -> right), Y across (front = -Y, back = +Y), Z up from the desk.
The card slides face up on the track floor at Z = PATH. Cards travel long edge first (88 mm along X).

Run:  python sorter.py            -> exports STL + STEP for every printable part into ../stl and ../step
      python sorter.py --assembly -> also writes assembly.glb-ready STLs (placed) into ../assembly
"""
import math, os, sys
import cadquery as cq

# ----------------------------------------------------------------------------- key dimensions
PATH = 205.0          # track floor height above the desk (top of the 2020 rails is Z=20)
RAIL_Z = 20.0         # 2020 extrusion lying on the desk
RAIL_Y = 62.0         # extrusion centre lines at Y = +-62
PITCH = 122.0         # one bin / one belt-fin step: 61 belt teeth (factory 1220 mm closed loop / 10 fins)
CH = 70.0             # channel width between the side strips (Y -35..35)
STRIP_IN, STRIP_OUT = 35.0, 47.0   # side strip (floor edge + belt guide) Y range
WALL_IN, WALL_OUT = 47.0, 55.0     # side wall Y range
BELT_Y0, BELT_Y1 = 37.0, 47.0      # 10 mm GT2 belt, vertical loop ABOVE the floor, Y range
WALL_IN_UP = 48.5                  # inner face of the side walls above the floor (room for the pulley flanges)
WALL_TOP = PATH + 40.0             # side walls rise 40 mm above the floor and hide the belts
PUL_T = 30                         # printed GT2 pulleys, 30 teeth: pitch diameter 19.10 mm
PUL_R = PUL_T * 2.0 / math.pi / 2  # 9.55 pitch radius
PUL_Z = PATH + 17.0                # all belt pulley shafts: bottom (card-pushing) run back face 7 mm above the floor
BELT_BACK_LOW = PUL_Z - PUL_R - 0.45   # underside of the bottom run (belt back), ~PATH + 7
BELT_TEETH_HIGH = PUL_Z + PUL_R - 1.0  # underside of the top run (tooth tips), ~PATH + 25.5
FIN_OUT_Y = 32.25                  # fingers' outer edge (the lanes on doors/floors stop at 32.6, leaving a 0.9 mm lip)
FIN_REACH_Y = 27.0                 # fin fingers reach in to |Y| = 27 (raw card edge 31.5, or 29.25 when it sits off-centre)
GROOVE_Y1 = 32.6                   # lanes on the doors, tie bars and scan floor stop 0.9 short of the edge (fingers reach 32.25)
GROOVE_Y0, GROOVE_D = 26.5, 1.2    # fin lanes: groove from |Y| 26.5 out to the floor edge, 1.2 mm deep
RAIL_IN, RAIL_W, RAIL_H = 33.75, 2.0, 2.5   # side guides: 67.5 mm apart (sleeved card 66 + 0.75 a side), 2.5 tall
FLOOR_W = 33.5                     # doors, scan floor and end ramp stop at |Y| 33.5, just inside the guide rails' webs
TAPER_X0, TAPER_X1, TAPER_IN0 = 136.0, 230.0, 36.5   # lead-in: 73 mm wide at the exit-roller nip, 67.5 mm by X 230 (1.7 deg a side)
TOWER_LEAN_X = 3.0                 # the L-shaped hopper also leans 3 degrees toward the exit wall
BINS = int(os.environ.get("SORTER_BINS", "9"))   # the machine is the 9-bin one; SORTER_BINS=3 draws the first test build
                                   # (feeder, scanner, bin modules 1-2, end module; the end module moves out when 3-8 go in)
FIN_PITCHES = 2 * BINS + 4         # belt loop in fin pitches: 3 bins = 10 x 122 = 1220 mm (factory loop),
                                   # 9 bins = 22 x 122 = 2684 mm (welded loop). One fin every 122 mm (61 teeth).
CARD_L, CARD_W = 88.0, 63.0
SCAN_X = 128.0 + PITCH + CARD_L / 2   # card centre when photographed (294): fin face lands at 128, one pitch on
BIN_X = [SCAN_X + PITCH * (k + 1) for k in range(BINS)]   # bin centres (416, 538, ... 1392): the last is the end-of-line bin
HUB_MODULE = 1                     # the bin hub (back panel with the servo board etc.) is on bin module 2
# Hole sizes tuned on the PETG fit coupon (Neptune 4 Pro, 0.4 nozzle, flow 0.95). Measured: a printed hole comes
# out about 0.07 + 0.78/d mm under size (16 mm: -0.12, 5 mm: -0.23, 4 mm: -0.27, 2 mm: -0.46).
M5 = 5.6; M3 = 3.6; M3_INSERT = 4.7   # clearance (prints 3.3) / heat-set insert (prints 4.45: 4.32 lead drops in, 5.04 knurl melts)
SEAT_685 = 11.3; SEAT_625 = 16.3      # bearing seats (11 / 16 mm OD): firm hand press
PILOT_M2, PILOT_M25 = 2.1, 2.5        # self-tapping pilots: print ~1.66 (M2 core 1.57) and ~2.12 (M2.5 core 2.01)
M2 = 2.2
FIN_START_X = 131.0   # start idlers (stub shafts in the posts on the feeder base); fins land here, 5 mm behind the exit nip
END_SHAFT_X = FIN_START_X + (FIN_PITCHES * PITCH - 2 * math.pi * PUL_R) / 2   # drive shaft in the end module (711)
NEMA = 42.3; NEMA_HOLES = 31.0; NEMA_BOSS = 22.5
SLIDER_POCKET_X = (124.0, 139.0)   # start-idler slider pocket in each post top (the slider is 8 long: +-3.5 travel)
SLIDER_Y = (50.0, 58.5)            # |Y| of the slider (post walls 1.3 mm either side)
SLIDER_YC = sum(SLIDER_Y) / 2
SLIDER_SCREW_Z = 222.0 + 6.5       # tension screw axis (1.6 mm above the stub hole)
CARD_CLEAR_X = 124.5               # card-clear TCRT5000 under the floor at the feeder exit
TRAY_X = (14.0, 136.0)             # electronics tray, world X (front window is 12..138)
TRAY_SCREW_X, TRAY_SCREW_Y = (18.0, 132.0), -44.0
SKR_X = 24.5                       # SKR Pico's first mounting hole, world X (board X 21..106)   # 2 x M3 x 8 hold the tray down on the ledge inserts

# towers: raw, single-sleeved and double-sleeved. All share the exit wall (inside face at X 109.5, where the gate is),
# the base screws and the tower-ID magnets, so any of them drops onto the same feeder base.
TOWER_EXIT_X = 109.5
TOWERS = {"raw": (89.5, 64.5), "single": (92.5, 67.5), "double": (93.5, 68.5)}   # inside X x Y
TOWER_IN_X, TOWER_IN_Y = TOWERS["raw"]
TOWER_X0 = TOWER_EXIT_X - TOWER_IN_X  # inside face of the entry side (open) for the raw tower: 20
TOWER_SKIRT_X0 = 2.0              # every tower's base skirt starts here
TOWER_SCREW = [(9.0, -45.0), (9.0, 45.0)]   # 2 x M3 thumb screws into heat-set inserts in the feeder base
HALL = [(9.0, -30.0), (9.0, 30.0)]          # tower-ID: A3144 hall sensors in the base, 6 x 3 mm magnets in the skirt
TOWER_MAGNETS = {"raw": (0,), "single": (1,), "double": (0, 1)}   # which HALL positions get a magnet
TOWER_H = 185.0
GATE = 0.45                       # raw-card gate opening, set with the adjuster
TOWER_LEAN = 3.0                  # degrees the hopper leans back (+Y)
PSU_L, PSU_W, PSU_H = 129.0, 97.0, 30.0   # Mean Well LRS-100-24 (L x W x H); terminal block on one 97 mm end
PSU_X0 = 180.0                    # PSU case starts here; its terminals face -X with 25 mm for the wires
CAM_D = 115.0                     # lens front to card (4.5 in; Eric's test: sharp from ~4 in, card fills the frame).
                                  # Adjustable 100-135 mm. The lens's barrel distortion is taken out in software (lens calibration).
CHAN_Z0, CHAN_Z1 = 28.0, 56.0     # back wire channel: 10 x 24 mm inside (the whole 9-bin loom at ~32% fill)
TOP_INSERT_Y = 53.0                # wall-top inserts (hood feet), |Y|
TIE_X = 4.0                        # tie-bar screw axis, from the module start (bar ends are 7 mm thick)
JOINT_Z = PATH - 6.0              # joint plates: just under the floor line (8 mm wall), above the back panels and tie-bar heads
CHAN_GAP = 20.0                   # channel gap at each back rail screw (head 8.5 + 2 x 4 mm slot travel + play)
END_BIN_D = 113.0; END_BIN_Y = -18.5   # end bin: Y +38 .. -75
BIN_Y = -37.0                     # bins sit forward: inner back wall at Y -1, right under the open door's low edge
BIN_DX = 0.75                      # bins sit 0.75 mm toward +X of the station: raw (88) and sleeved (91) cards both clear their walls
BAY_TOP = 140.0                   # front wall is open below this between 2.5 mm posts so the bins slide out the front
POST_T = 2.5
RAIL2_Y = 24.0                    # second back rail (under the doors) replaces the front rail under the bin modules
TOF_X = PITCH / 2 - 19.5           # bin-level ToF sensor (Pololu VL53L1X carrier, 13 x 18 mm) position in each module

FEED_X, FEED_Z, FEED_R = 95.0, PATH - 11.0, 12.0     # feed roller: same O-rings, size and height as the exit roller,
                                                      # so both move the card at the same speed (same 20T pulleys)
EXIT_X, EXIT_Z, EXIT_R = 136.0, PATH - 11.0, 12.0    # exit roller pair; 122 mm GT2 closed loop from the feed shaft

def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))

def cyl_y(x, z, r, y0, y1):
    return cq.Workplane("XZ").center(x, z).circle(r).extrude(-(y1 - y0)).translate((0, y0, 0))

def cyl_x(y, z, r, x0, x1):
    return cq.Workplane("YZ").center(y, z).circle(r).extrude(x1 - x0).translate((x0, 0, 0))

def cyl_z(x, y, r, z0, z1):
    return cq.Workplane("XY").center(x, y).circle(r).extrude(z1 - z0).translate((0, 0, z0))

def tear_y(x, z, r, y0, y1):
    """A hole along Y with a 45 degree pointed roof (teardrop): for bearing seats and shaft holes in parts that print
    upright, where a round hole's top would sag. The bearing still sits on the round lower 3/4."""
    k = r / math.sqrt(2)
    roof = cq.Workplane("XZ").polyline([(x - k, z + k), (x, z + r * math.sqrt(2)), (x + k, z + k), (x, z)]).close().extrude(-(y1 - y0)).translate((0, y0, 0))
    return cyl_y(x, z, r, y0, y1).union(roof)

def nema_face_y(x, z, y_face, depth=6, sign=-1):
    """Pocket pattern for a NEMA 17 bolted to a wall whose face is at y_face (motor body outside)."""
    s = cyl_y(x, z, NEMA_BOSS / 2 + 0.5, y_face - depth if sign < 0 else y_face, y_face if sign < 0 else y_face + depth)
    for dx in (-1, 1):
        for dz in (-1, 1):
            s = s.union(cyl_y(x + dx * NEMA_HOLES / 2, z + dz * NEMA_HOLES / 2, M3 / 2,
                              y_face - depth if sign < 0 else y_face, y_face if sign < 0 else y_face + depth))
    return s

def rail_slots(part, x0, x1, ys=(-RAIL_Y, RAIL_Y), z=RAIL_Z, n=2):
    """M5 slots in a foot so the part bolts to the 2020 rails with T-nuts (slots allow +-4 mm adjustment)."""
    xs = [x0 + (x1 - x0) * (i + 1) / (n + 1) for i in range(n)]
    for y in ys:
        for x in xs:
            slot = cq.Workplane("XY").center(x, y).slot2D(M5 + 8, M5, 0).extrude(12).translate((0, 0, z - 1))
            part = part.cut(slot)
            # counterbore for the head: 4 mm of foot under it, so an M5 x 10 reaches 4.2 mm into the T-nut
            part = part.cut(cq.Workplane("XY").center(x, y).slot2D(M5 + 8 + 4.0, 9.6, 0).extrude(20).translate((0, 0, z + 4)))
    return part

def rail_in(x):
    """Inner face of the side guide (|Y|) at track position x: tapered lead-in, then parallel."""
    if x <= TAPER_X0:
        return TAPER_IN0
    if x >= TAPER_X1:
        return RAIL_IN
    return TAPER_IN0 - (TAPER_IN0 - RAIL_IN) * (x - TAPER_X0) / (TAPER_X1 - TAPER_X0)

def guide_rail(x0, x1, side, chamfer=True, xoff=0.0):
    """Side guide from x0 to x1 on one side (+1 back / -1 front), following rail_in(), with 1 x 4 mm
    chamfered lead-ins on the inner face at each end so a card corner can't catch on a module joint."""
    ri = lambda x: rail_in(x + xoff)
    xs = sorted(set([x0, x1] + [x - xoff for x in (TAPER_X0, TAPER_X1) if x0 < x - xoff < x1]))
    inner = [(x, ri(x)) for x in xs]
    if chamfer:
        inner = [(x0, ri(x0) + 1.0), (x0 + 4.0, ri(x0 + 4.0))] + [p for p in inner if x0 + 4.0 < p[0] < x1 - 4.0] + \
                [(x1 - 4.0, ri(x1 - 4.0)), (x1, ri(x1) + 1.0)]
    outer = [(x, ri(x) + RAIL_W) for x, _ in reversed(inner)]
    pts = [(x, side * y) for x, y in inner] + [(x, side * y) for x, y in outer]
    # solid down to 1.5 mm under the floor line: the part over the floor-edge gap (inside |Y| 35) hangs off the strip
    # as a web, so the rail is one piece with the wall (it used to float 0.15 mm above the strip). Doors and floors
    # stop at |Y| 33.5, 0.25 mm inside it.
    r = cq.Workplane("XY").polyline(pts).close().extrude(RAIL_H + 1.5).translate((0, 0, PATH - 1.5))
    return r

def fin_groove(x0, x1, y_out):
    """Both fin lanes (|Y| GROOVE_Y0..y_out, GROOVE_D deep) to cut from a floor part."""
    g = None
    for sg in (-1, 1):
        y0, y1 = sorted((sg * GROOVE_Y0, sg * y_out))
        b = box(x0, x1, y0, y1, PATH - GROOVE_D, PATH + 1)
        g = b if g is None else g.union(b)
    return g

# ============================================================================ FEEDER (head unit)
X1_BASE = 150.0

def feeder_base():
    """Head unit: hopper floor, feed roller, exit roller, both motors, start of the edge belts.
    Footprint 150 x 130 mm (5.9 x 5.1 in), 185 mm (7.3 in) tall, prints upright without supports
    (window openings and the hopper floor are bridged; parts hanging under the floor have 45 degree webs). Walls 4 mm."""
    X0, X1, Y0, Y1 = 0.0, 150.0, -60.0, 60.0
    shell = box(X0, X1, Y0, Y1, RAIL_Z, PATH)
    inner = box(X0 + 4, X1 - 4, Y0 + 4, Y1 - 4, RAIL_Z + 6, PATH - 4)
    b = shell.cut(inner)
    # feet over the rails
    b = b.union(box(X0, X1, -RAIL_Y - 10, -RAIL_Y + 10, RAIL_Z, RAIL_Z + 6)).union(box(X0, X1, RAIL_Y - 10, RAIL_Y + 10, RAIL_Z, RAIL_Z + 6))
    b = rail_slots(b, X0, X1)
    # the rail screws (M5 x 10, head D8.5) sit right at the foot of the 4 mm walls (rail centre Y 62, wall face Y 60):
    # notch the wall's outer face round each slot so the head (and its +-4 mm of slot travel) fits and a key reaches it
    for y in (-RAIL_Y, RAIL_Y):
        for x in (X0 + (X1 - X0) / 3, X0 + 2 * (X1 - X0) / 3):
            yn0, yn1 = sorted((math.copysign(57.0, y), math.copysign(61.0, y)))
            b = b.cut(box(x - 9.5, x + 9.5, yn0, yn1, RAIL_Z + 4, RAIL_Z + 11))
    # electronics bay windows: front (service, covered by bay_cover) and back (cables); kept below the motor bolts.
    # The front window is wider than the electronics tray (124 mm), so the tray slides in through it.
    b = b.cut(box(X0 + 12, X1 - 12, Y0 - 1, Y0 + 5, RAIL_Z + 15, RAIL_Z + 95))
    b = b.cut(box(X0 + 30, X1 - 30, Y1 - 5, Y1 + 1, RAIL_Z + 15, RAIL_Z + 60))
    # the back wire channel starts here (x 115..150), lined up with the modules' channel (inside Y 55..65): the
    # base's wall is cut away behind it, so the looms go straight from the bay into the channel
    b = b.union(box(X1 - 35, X1, Y1, WALL_OUT + 12, RAIL_Z + 6, CHAN_Z1))
    b = b.cut(box(X1 - 35, X1 + 1, WALL_OUT + 0.01, WALL_OUT + 10, CHAN_Z0 + 2, CHAN_Z1 - 2))
    b = b.cut(box(X1 - 35, X1 - 4, WALL_OUT - 1.0, Y1 + 0.01, CHAN_Z0 + 2, CHAN_Z1 - 2))
    # tray ledges: the tray (x 14..136) rests on two ledges that reach in from the side walls past the window edges.
    # Each ledge is a 3 mm shelf bridged from the wall to a 4 mm rib standing on the floor (prints upright, no
    # support); an M3 insert near the front of each ledge takes the tray's screw.
    for (xa, xb, xr0, xr1) in ((X0 + 3, X0 + 22, X0 + 18, X0 + 22), (X1 - 22, X1 - 3, X1 - 22, X1 - 18)):
        b = b.union(box(xa, xb, Y0 + 3, Y1 - 3, RAIL_Z + 14, RAIL_Z + 17))
        b = b.union(box(xr0, xr1, Y0 + 10, Y1 - 10, RAIL_Z + 5, RAIL_Z + 14))
    for x in TRAY_SCREW_X:
        b = b.union(box(x - 5, x + 5, TRAY_SCREW_Y - 5, TRAY_SCREW_Y + 5, RAIL_Z + 5, RAIL_Z + 17))
        b = b.cut(cyl_z(x, TRAY_SCREW_Y, M3_INSERT / 2, RAIL_Z + 9, RAIL_Z + 17.1))
    # cover screw inserts beside the front window
    for (x, z) in ((X0 + 7, RAIL_Z + 30), (X1 - 7, RAIL_Z + 30), (X0 + 7, RAIL_Z + 90), (X1 - 7, RAIL_Z + 90)):
        b = b.cut(cyl_y(x, z, M3_INSERT / 2, Y0 - 1, Y0 + 6))
    # wiring pass-through into the space under the scanner (24 V in, sensor and servo looms out)
    b = b.cut(box(X1 - 5, X1 + 1, -25, 25, RAIL_Z + 18, RAIL_Z + 48))
    # hopper floor openings: feed roller, exit roller, fin slots where the fins rise around the start pulleys
    b = b.cut(box(FEED_X - 18, FEED_X + 18, -21, 21, PATH - 6, PATH + 1))
    b = b.cut(box(EXIT_X - 14, EXIT_X + 14, -17, 17, PATH - 6, PATH + 1))
    b = b.cut(box(X1 - 5, X1 + 1, -17, 17, EXIT_Z - 14, PATH - 4))
    b = b.cut(box(FEED_X - 10, EXIT_X + 10, -56, -38, PATH - 4.1, PATH - 2.2))   # recess over both pulleys + the loop (122 mm loop)   # exit roller (D23.6) reaches past the end wall's inner face
    # feed roller shaft: 685ZZ bearings (11 mm OD x 5) in inner ribs at |Y| 24..29 (small enough to stay under the floor)
    # The ribs hang from the hopper floor, so they're tied to a wall at 45 degrees and the base still prints
    # upright with no support inside the closed box. Back rib: two 3 mm webs out to the back wall (clear of the
    # feed shaft). Front rib: its underside slopes down toward -X and runs on as a 5 mm strut to the left wall
    # (the front side is taken by the 122 mm loop and its pulleys).
    zr0, ztop, yw = FEED_Z - 14, PATH - 4, 60.0 - 4
    rib = (cq.Workplane("XZ").polyline([(FEED_X - 8, zr0), (FEED_X + 8, zr0), (FEED_X + 12, zr0 + 4),
                                        (FEED_X + 12, ztop), (FEED_X - 12, ztop), (FEED_X - 12, zr0 + 4)])
           .close().extrude(-5).translate((0, 24, 0)))
    b = b.union(rib)
    for xw in (FEED_X - 8, FEED_X + 5):
        prof = [(24.0, zr0), (yw + 1, zr0 - (yw + 1 - 24.0)), (yw + 1, ztop), (24.0, ztop)]
        b = b.union(cq.Workplane("YZ").polyline(prof).close().extrude(3).translate((xw, 0, 0)))
    xr1, xw0 = FEED_X + 12, X0 + 3                       # front rib right edge, left inner wall (+1 overlap)
    k = (zr0 + 2) - xr1                                  # underside line z = x + k through the rib's low corner
    front = [(xw0, xw0 + k), (xr1, xr1 + k), (xr1, ztop), (FEED_X - 12, ztop), (FEED_X - 12, FEED_X - 12 + k + 8), (xw0, xw0 + k + 8)]
    b = b.union(cq.Workplane("XZ").polyline(front).close().extrude(-5).translate((0, -29, 0)))
    b = b.cut(tear_y(FEED_X, FEED_Z, SEAT_685 / 2, -30, 30))      # (teardrops: the base prints upright)
    b = b.cut(tear_y(FEED_X, FEED_Z, 3.0, Y0 - 1, Y1 + 1))
    # exit roller shaft through both walls
    # exit roller bearings sit in slots (+-2 mm along X) so the 122 mm belt can be tensioned
    for yy in ((Y0 - 1, Y0 + 5), (Y1 - 5, Y1 + 1)):
        b = b.cut(tear_y(EXIT_X - 2, EXIT_Z, SEAT_625 / 2, *yy)).cut(tear_y(EXIT_X + 2, EXIT_Z, SEAT_625 / 2, *yy)).cut(box(EXIT_X - 2, EXIT_X + 2, yy[0], yy[1], EXIT_Z - SEAT_625 / 2, EXIT_Z + SEAT_625 / 2 * 1.2))
    # feed motor on the back wall at the feed shaft (on a 30 mm standoff). The standoff's square is centred on the
    # shaft, so its upper screws land above the hopper floor: a tab rises there (behind the tower skirt), and the
    # wall is thickened to 8 mm inside so every insert is fully buried (5.7 mm insert in a 7.5 mm hole).
    b = b.union(box(FEED_X - 23, FEED_X + 23, Y1 - 8, Y1 - 3.9, FEED_Z - 23, PATH - 3.9))
    b = b.union(box(FEED_X - 23, FEED_X + 21, Y1 - 8.5, Y1, PATH - 0.1, FEED_Z + 23))
    b = b.cut(tear_y(FEED_X, FEED_Z, 3.0, Y1 - 9, Y1 + 1))
    for (x, z) in ((FEED_X, FEED_Z),):
        b = b.cut(tear_y(x, z, SEAT_625 / 2, Y1 - 5, Y1 + 1))     # 625 bearing seat in the wall; shaft passes out to the coupler
        for dx in (-1, 1):
            for dz in (-1, 1):
                b = b.cut(cyl_y(x + dx * NEMA_HOLES / 2, z + dz * NEMA_HOLES / 2, M3_INSERT / 2, Y1 - 6.5, Y1 + 1))
    # two webs under the hopper floor (Y +-22.5, V-shaped underside at 45 degrees from the end walls) so the
    # floor prints as 32 / 42 / 32 mm bridges instead of one 112 mm bridge
    for yc in (-22.5, 22.5):
        web = (cq.Workplane("XZ").polyline([(X0 + 3, PATH - 3.9), (X1 - 3, PATH - 3.9), (X1 - 3, PATH - 10), ((X0 + X1) / 2, PATH - 10 - (X1 - X0 - 6) / 2),
                                            (X0 + 3, PATH - 10)]).close().extrude(1.25, both=True).translate((0, yc, 0)))
        web = web.cut(cyl_y(FEED_X, FEED_Z, 3.5, -60, 60)).cut(cyl_y(EXIT_X, EXIT_Z, 13.5, -60, 60))
        web = web.cut(box(CARD_CLEAR_X - 9, CARD_CLEAR_X + 18, -30, -14, 0, 400))    # card-clear sensor housing (and no sliver by the roller)
        b = b.union(web)
    # posts on top of the base carry the start idlers above the floor (they continue the track side walls)
    for sg in (-1, 1):
        y0p, y1p = sorted((sg * WALL_IN_UP, sg * 60.0))
        b = b.union(box(FIN_START_X - 16, X1, y0p, y1p, PATH, WALL_TOP))
        # 5 mm stub in a +-3.5 mm slot along X. It is pressed into idler_slider, a block that drops into a pocket in
        # the post top; an M3 x 20 from the post's hopper-side face (X 115, easy to reach over the floor) threads into
        # the slider's insert and pulls it back to tension the belt. (v3 had the screw in the end face, which the
        # scan module's wall covers.)
        b = b.cut(box(FIN_START_X - 3.5, FIN_START_X + 3.5, y0p - 1, y1p + 1, PUL_Z - 2.6, PUL_Z + 2.6))
        b = b.cut(cyl_y(FIN_START_X - 3.5, PUL_Z, 2.6, y0p - 1, y1p + 1)).cut(cyl_y(FIN_START_X + 3.5, PUL_Z, 2.6, y0p - 1, y1p + 1))
        yk0, yk1 = sorted((sg * SLIDER_Y[0], sg * SLIDER_Y[1]))
        b = b.cut(box(SLIDER_POCKET_X[0], SLIDER_POCKET_X[1], yk0 - 0.2, yk1 + 0.2, PUL_Z - 8.2, WALL_TOP + 1))
        b = b.cut(cyl_x(sg * SLIDER_YC, SLIDER_SCREW_Z, M3 / 2, FIN_START_X - 17, SLIDER_POCKET_X[0] + 0.5))
        # outer ledges the belt rides on (same as the track walls), and the heat-set inserts for the lid
        yl0, yl1 = sorted((sg * 44.0, sg * WALL_IN_UP))
        b = b.union(box(FIN_START_X + 12, X1, yl0, yl1, BELT_BACK_LOW - 2, BELT_BACK_LOW))
        b = b.cut(cyl_z(X1 - 6, sg * 54.0, M3_INSERT / 2, WALL_TOP - 7, WALL_TOP + 1))
    # fin lanes where the fins come down round the start idlers, and the start of the tapered side guides
    b = b.cut(fin_groove(FIN_START_X - 7, X1 + 1, 40.0))
    for sg in (-1, 1):
        b = b.union(guide_rail(TAPER_X0, X1, sg, chamfer=False))   # solid down into the lane (fins stop at |Y| 32.75)
    # card-clear sensor (TCRT5000 reflective IR) under a slot in the floor at X 127, |Y| 22: the track only
    # steps once the card's tail has left it, so a fin can't come down on a card
    # (centred at X 124.5: its housing ends at X 130.7, clear of the exit shaft even with the shaft slid 2 mm back to
    # tension the 122 mm loop)
    xc = CARD_CLEAR_X
    b = b.cut(box(xc - 4.5, xc + 4.5, -24.0, -20.0, PATH - 5, PATH + 1))
    b = b.cut(box(xc - 5.2, xc + 5.2, -25.0, -19.0, PATH - 12, PATH - 3.9))
    b = b.union(box(xc - 7.2, xc + 6.2, -27.0, -17.0, PATH - 13, PATH - 4).cut(box(xc - 5.2, xc + 5.2, -25.0, -19.0, PATH - 14, PATH - 3.9)))
    # (this pocket hangs under the floor: the only spot on the base that needs printed support)
    # The hopper floor is flat and clear from the entry side to the exit roller: nothing stands on it in the card's
    # way (v2 had a locating bar under the exit wall that the bottom card ran into). Any tower sits flat on its skirt,
    # held and located by 2 M3 thumb screws in heat-set inserts. Each insert gets a boss tied to the left wall at
    # 45 degrees underneath, so it prints without support.
    for (x, y) in TOWER_SCREW:
        g = (cq.Workplane("XZ").polyline([(0.0, PATH - 4.0), (x + 5.0, PATH - 4.0), (x + 5.0, PATH - 9.0), (0.0, PATH - 9.0 - (x + 5.0))])
             .close().extrude(-10.0).translate((0, y - 5.0, 0)))
        b = b.union(g)
        b = b.cut(cyl_z(x, y, M3_INSERT / 2, PATH - 8, PATH + 1))
    # tower-ID hall sensors (A3144, flat, branded face up) in 6.2 mm pockets 3.2 deep; leads go down a 3 mm hole into
    # the bay. The tower's magnets sit right above them in its skirt.
    for (x, y) in HALL:
        b = b.cut(cyl_z(x, y, 3.1, PATH - 3.2, PATH + 1)).cut(cyl_z(x, y, 1.5, PATH - 6, PATH))
    return b

def tower(kind="raw"):
    """L-shaped open hopper: back wall (+Y) and exit wall (+X) only. Raw: inside 89.5 x 64.5 mm (~550 cards);
    single-sleeved 92.5 x 67.5; double-sleeved 93.5 x 68.5. The exit wall's inside face is always at X 109.5 (the
    gate), so the stack lines up with the feed roller and the guides whatever is fitted. Leans 3 degrees back and
    3 degrees toward the exit, so the stack rests in that corner, square against the gate; front and entry sides are
    open for loading. The bottom card lies flat on the floor; the skirt keeps the bottom few cards in on the open
    sides. Skirt: sits flat on the floor, 2 x M3 thumb screws, and the tower-ID magnets (6 x 3 mm, pressed in from
    underneath, SOUTH pole down: the A3144 only switches on a south pole) in the positions that say which tower it is."""
    in_x, in_y = TOWERS[kind]
    x0 = TOWER_EXIT_X - in_x
    t = 3.5
    xo0, xo1 = x0 - t, TOWER_EXIT_X + t
    yo0, yo1 = -in_y / 2 - t, in_y / 2 + t
    xi1, yi1 = TOWER_EXIT_X, in_y / 2
    back = box(x0 + 6, xo1, yi1, yo1, PATH - 6, PATH + TOWER_H)          # back wall
    exitw = box(xi1, xo1, yo0 + 6, yo1, PATH - 6, PATH + TOWER_H)        # exit wall (carries the gate)
    for sg in (-1, 1):   # 1 mm relief on the outside, low down beside the gate track: the fins sweep past here
        exitw = exitw.cut(box(xi1 + 2.5, xo1 + 1, *sorted((sg * 22.0, sg * 50.0)), PATH - 7, PATH + 40))
    walls = back.union(exitw)
    # stiffening stays OUTSIDE the card space: a top rim and a rib along each free edge, on the outer faces
    walls = walls.union(box(x0 + 6, xo1 + 3, yo1, yo1 + 3, PATH + TOWER_H - 8, PATH + TOWER_H))         # back rim
    walls = walls.union(box(xo1, xo1 + 3, yo0 + 6, yo1 + 3, PATH + TOWER_H - 8, PATH + TOWER_H))       # exit rim
    walls = walls.union(box(x0 + 6, x0 + 10, yo1, yo1 + 4, PATH + 12, PATH + TOWER_H))                 # back wall free edge
    walls = walls.union(box(xo1, xo1 + 4, yo0 + 6, yo0 + 10, PATH + 42, PATH + TOWER_H))               # exit wall free edge
    # gate track on the exit face (+X): a closed slot the gate slides in from below (it can't tip out), the underside
    # sloped at 45 degrees so it prints without support, and a boss on top. The gate HANGS on one M3 x 12 cap screw:
    # head on the boss (clearance hole), threaded into the insert in the gate's top. Turn it to set the gap; an M3
    # nut on top of the boss locks it. The gate can lift (a thick card pushes it up) but never drop below the setting.
    gx = xo1
    trk = (cq.Workplane("XZ").polyline([(gx, PATH + 6), (gx, PATH + 40), (gx + GATE_TRACK_D, PATH + 40),
                                        (gx + GATE_TRACK_D, PATH + 6 + GATE_TRACK_D)]).close().extrude(20, both=True))
    walls = walls.union(trk)
    walls = walls.cut(box(gx + 0.8, gx + 1.2 + GATE_T, -GATE_W / 2 - 0.4, GATE_W / 2 + 0.4, PATH + 5, PATH + 41))   # 0.2 / 0.4 play
    walls = walls.union(box(gx, gx + GATE_TRACK_D, -6, 6, PATH + 40, PATH + 46))
    walls = walls.cut(cyl_z(gx + 1 + GATE_T / 2, 0, M3 / 2, PATH + 39, PATH + 47))
    # lean: back about the X axis through the floor line, then toward the exit about the Y axis through the exit wall foot
    walls = walls.rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN)
    walls = walls.rotate((xi1, 0, PATH), (xi1, 1, PATH), TOWER_LEAN_X)
    # walls stop 3 mm above the floor (on the skirt); the exit wall leaves 6 mm across the card width (the gate sets it)
    walls = walls.cut(box(xo0 - 20, xo1 + 20, -80, 80, PATH - 20, PATH + 3))
    walls = walls.cut(box(xi1 - 1, xo1 + 1, -in_y / 2, in_y / 2, PATH - 1, PATH + 7))
    # skirt: flat on the floor, round the open sides and under the walls; stops at the exit wall so the fins clear it
    skirt = box(TOWER_SKIRT_X0, xo1 + 1, -50, 50, PATH + 0.2, PATH + 9)
    skirt = skirt.cut(box(x0, xo1 + 2, -in_y / 2, in_y / 2 + 1.0, PATH, PATH + 10))   # +1 at the back: the stack leans that way
    for (x, y) in TOWER_SCREW:
        skirt = skirt.cut(cyl_z(x, y, M3 / 2, PATH, PATH + 12))
    for i in TOWER_MAGNETS[kind]:
        x, y = HALL[i]
        skirt = skirt.cut(cyl_z(x, y, 3.15, PATH, PATH + 3.2 + 0.2))      # 6 x 3 magnet, press fit, flush underneath
    # the kind, embossed on the skirt top so the three towers can't be mixed up
    lbl = {"raw": "RAW", "single": "1 SLV", "double": "2 SLV"}[kind]
    skirt = skirt.union(cq.Workplane("XY").text(lbl, 6.0, 0.6, halign="center", valign="center", kind="bold")
                        .rotate((0, 0, 0), (0, 0, 1), 90).translate(((TOWER_SKIRT_X0 + x0) / 2, 0.0, PATH + 9)))
    return walls.union(skirt)

def raw_tower():
    return tower("raw")

GATE_T, GATE_W, GATE_H, GATE_FOOT = 8.0, 27.6, 35.5, 2.5   # gate body thickness (X), width, height, foot thickness
GATE_PAD = 1.5                                            # silicone pad under the foot (modelled in the assembly)
GATE_TRACK_D = GATE_T + 3.0                               # track depth off the exit wall

def gate_plate():
    """v4. Hangs in the tower's exit track on an M3 x 12 (heat-set insert in its top), so turning the screw sets the
    gap and the gate can't fall or tip out. Foot reaches back over the card path under the exit wall; 1.5 mm
    silicone pad glued under the foot. No pause, no nut. Fits all three towers. Prints on its outer (+X) face."""
    g = box(0, GATE_T, -GATE_W / 2, GATE_W / 2, -2, GATE_H)
    g = g.union(box(-4, GATE_T, -GATE_W / 2, GATE_W / 2, -2, GATE_FOOT))   # foot over the card path
    g = g.cut(gate_floor(0.0))
    g = g.cut(cyl_z(GATE_T / 2, 0, M3_INSERT / 2, GATE_H - 7, GATE_H + 1))
    return g

def gate_floor(dz):
    """Everything below the gate's underside, in the gate's (tower) frame. The tower leans 3 degrees back, which
    would tip a flat foot 1.4 mm across the card's width (two cards could slip under the high side), so the
    underside is cut 3 degrees the other way: level with the floor across the card. Along the card it keeps the
    3 degree slope toward the exit (a lead-in; the gap is set at the exit end)."""
    return box(-60, 60, -60, 60, -60, 0).rotate((0, 0, 0), (1, 0, 0), TOWER_LEAN).translate((0, 0, dz))

def o_ring_roller(r_hub, width, grooves=3, bore=5.0, d_flat=0.5):
    """Printed hub with grooves for nitrile O-ring tyres. D-shaft bore 5 mm with flat."""
    hub = cq.Workplane("XZ").circle(r_hub).extrude(width / 2, both=True)
    pitch = width / grooves
    for i in range(grooves):
        y = -width / 2 + pitch * (i + 0.5)
        groove = cq.Workplane("XZ").circle(r_hub + 1).circle(r_hub - 1.6).extrude(1.6, both=True).translate((0, y, 0))
        hub = hub.cut(groove)
    bore_s = cq.Workplane("XZ").circle(bore / 2 + 0.1).extrude(width, both=True)
    hub = hub.cut(bore_s)
    flat = box(-3, 3, -width, width, bore / 2 - d_flat, bore / 2 + 0.5)
    hub = hub.union(flat.intersect(cq.Workplane("XZ").circle(bore / 2 + 0.2).extrude(width / 2, both=True)))
    # M3 grub screw boss
    hub = hub.cut(cq.Workplane("XY").circle(1.4).extrude(r_hub + 1).translate((0, 0, 0)))
    return hub

def feed_roller():   # OD with tyres ~24 mm: three 16 x 3.5 mm O-rings (same as the exit rollers)
    return o_ring_roller(10.0, 40.0, 3)

def exit_roller():   # OD with tyres ~24 mm: two 16 x 3.5 mm O-rings (print 2: driven + pressure)
    return o_ring_roller(10.0, 30.0, 2)

PR_Z = PATH + 13.0      # pressure roller axle when it rests on the exit roller (both D23.6 with their O-rings)

def pressure_bridge():
    """Holds the top (pressure) roller over the exit roller. A beam across the tops of the feeder base's two posts
    (2 x M3 x 10 into the inserts already there) with two hangers that come down beside the roller, inside the fins'
    reach (|Y| 16-20; fins never come inside |Y| 27). The roller's 5 mm axle (40 mm of the 5 mm shaft, roller grub-
    screwed to it, a collar outside each hanger) floats in vertical slots: it rests on the exit roller by its own
    weight and lifts for the card. For more grip, loop a small O-ring from each axle end down to the hook under the
    slot. Prints beam down, no supports."""
    x0b, x1b = EXIT_X - 6.0, X1_BASE
    b = box(x0b, x1b, -59.0, 59.0, WALL_TOP, WALL_TOP + 5)
    for sg in (-1, 1):
        b = b.cut(cyl_z(X1_BASE - 6, sg * 54.0, M3 / 2, WALL_TOP - 1, WALL_TOP + 6))
        y0, y1 = sorted((sg * 16.0, sg * 20.0))
        h = box(EXIT_X - 7.0, EXIT_X + 7.0, y0, y1, PR_Z - 6.0, WALL_TOP + 0.01)
        h = h.cut(box(EXIT_X - 2.7, EXIT_X + 2.7, y0 - 1, y1 + 1, PR_Z - 1.3, PR_Z + 4.0)).cut(cyl_y(EXIT_X, PR_Z - 1.3, 2.7, y0 - 1, y1 + 1)) \
             .cut(cyl_y(EXIT_X, PR_Z + 4.0, 2.7, y0 - 1, y1 + 1))
        hk = (cq.Workplane("YZ").polyline([(sg * 20.0, PR_Z - 6.0), (sg * 23.0, PR_Z - 6.0), (sg * 23.0, PR_Z - 3.0), (sg * 20.0, PR_Z)])
              .close().extrude(4.0).translate((EXIT_X - 2, 0, 0)))
        h = h.union(hk)   # O-ring hook, 45 degree top: prints beam down without support
        # web from the hanger out along the beam (stiff against the card pushing on the roller)
        h = h.union(box(EXIT_X - 7.0, EXIT_X + 7.0, *sorted((sg * 16.0, sg * 26.0)), WALL_TOP - 8.0, WALL_TOP + 0.01))
        b = b.union(h)
    return b

def idler_slider():
    """Carries a start idler's 5 mm stub (pressed in, 21 mm of the 5 mm shaft) in the post-top pocket. M3 insert in
    its hopper-side face for the tension screw (M3 x 20 from the post's face). World frame, back post (mirror for
    the front). Prints on its side (X down)."""
    x0 = FIN_START_X - 4.0
    k = box(x0, x0 + 8.0, SLIDER_Y[0], SLIDER_Y[1], PUL_Z - 8.0, PUL_Z + 10.5)
    k = k.cut(cyl_y(FIN_START_X, PUL_Z, 2.55, SLIDER_Y[0] - 1, SLIDER_Y[1] + 1))
    k = k.cut(cyl_x(SLIDER_YC, SLIDER_SCREW_Z, M3_INSERT / 2, x0 - 1, x0 + 8.1))
    return k

def stack_weight():
    """Rides on top of the stack so the last few cards still feed. Pocket for 4 x M8 washers."""
    w = box(0, 86, -30.5, 30.5, 0, 12)
    w = w.cut(box(8, 78, -22, 22, 3, 13))
    w = w.union(box(38, 48, -6, 6, 3, 40))        # handle (stands on the pocket floor)
    return w

def fin():
    """Pusher fin on the BACK (smooth side) of the 10 mm belt, so it can go round the pulleys. One M2 x 6
    button-head screw from the tooth side through a 2 mm hole in the belt's centre line threads into the leg;
    the head runs in the groove round the middle of every pulley.
    Shape: leg down from the belt, bridge over the side guide (0.5 mm above it), finger down into the fin lane
    (0.7 mm below the card floor, 0.5 mm above the groove bottom) so no card can get under it and it never
    touches the surface cards slide on. A 3 x 3 mm square of the 1.5 mm silicone sheet glued in the pocket on
    the pushing face is the soft tip. Frame: bottom run, belt back at z = 0 facing down, belt centre y = 0,
    inward = -y. Print on its side; mirror for the front belt."""
    yc = (BELT_Y0 + BELT_Y1) / 2                        # 42
    z_floor = PATH - BELT_BACK_LOW                      # floor level in this frame (~ -7.05)
    zb0, zb1 = z_floor + RAIL_H + 0.5, z_floor + RAIL_H + 2.1   # bridge 0.5 over the rail top
    yf0, yf1 = -(yc - FIN_REACH_Y), -(yc - FIN_OUT_Y)          # finger |Y| 27 .. 32.25 (clears the hinge knuckles)
    f = box(0, 5, -1.75, 1.75, zb0, 0)                                  # leg
    f = f.union(box(0, 5, yf0, 1.75, zb0, zb1))                         # bridge
    f = f.union(box(1.5, 5, yf0, yf1, z_floor - (GROOVE_D - 0.5), zb0))  # finger (pushing face at x = 5)
    f = f.cut(box(4.0, 5.1, yf0 + 1.5, yf0 + 4.5, z_floor - 0.2, z_floor + 2.8))   # pad pocket, 1 mm deep
    f = f.cut(cyl_z(2.0, 0, PILOT_M2 / 2, -4.5, 0.1))                    # pilot for the M2 self-tapping screw
    return f

def belt_drill_jig():
    """Clamps on a straight run of the 10 mm belt, teeth down on printed GT2 ridges, so every fin hole is drilled
    on the belt's centre line at a tooth. Guide holes 61 teeth (122 mm) apart: drill one, slide the jig on until
    its first hole sits over the last hole drilled, drill the next. 10 fins on each factory 1220 mm loop."""
    L = 130.0
    j = box(0, L, -9, 9, 0, 6)
    j = j.cut(box(-1, L + 1, -5.1, 5.1, 3, 7))               # belt channel (10.2 wide)
    for k in range(int(L / 2)):
        j = j.union(box(2 * k + 0.6, 2 * k + 1.4, -5.1, 5.1, 3, 3.75))   # tooth ridges at 2 mm pitch
    for x in (2.0 + 1.0, 2.0 + 1.0 + PITCH):
        j = j.cut(cyl_z(x, 0, 1.25, -1, 8))    # 2 mm drill guide (prints ~2.1)
    j = j.union(box(0, L, -9, -5.1, 6, 9)).union(box(0, L, 5.1, 9, 6, 9))  # lips; a strip of tape holds the belt
    return j

def fin_gauge():
    """Squares the fins: sits across the side rails; both fins of a pair must drop into its two notches at the
    same time. If not, loosen one drive pulley's grub screw, turn it until they do, tighten."""
    g = box(0, 12, -(RAIL_IN + RAIL_W + 6), RAIL_IN + RAIL_W + 6, PATH + RAIL_H, PATH + RAIL_H + 6)
    g = g.union(box(0, 12, -(RAIL_IN + RAIL_W + 6), -(RAIL_IN + RAIL_W), PATH, PATH + RAIL_H))
    g = g.union(box(0, 12, RAIL_IN + RAIL_W, RAIL_IN + RAIL_W + 6, PATH, PATH + RAIL_H))
    for sg in (-1, 1):
        y0, y1 = sorted((sg * 39.9, sg * 44.1))
        g = g.cut(box(5.5, 10.5, y0, y1, PATH, PATH + RAIL_H + 7))      # notch for the fin leg (5 wide)
    return g

def track_pulley(drive=False):
    """Printed 30-tooth GT2 pulley for the 10 mm belt, with a 4.5 x 2 mm groove round the middle for the fin
    screw heads. Idler: two 685ZZ bearings (5 x 11 x 5) pressed in, spins on a fixed 5 mm stub.
    Drive: 5 mm bore, inner hub with an M3 x 4 grub screw (captive nut). Axis along Y, centred at the origin."""
    r_od = PUL_R - 0.254                               # GT2 outside radius
    face = 11.0
    p = cyl_y(0, 0, r_od, -face / 2, face / 2)
    # GT2 grooves: 0.555 mm radius tooth root, 0.75 deep, with a straight-sided neck
    for k in range(PUL_T):
        a = 2 * math.pi * k / PUL_T
        cx, cz = (r_od - 0.195) * math.cos(a), (r_od - 0.195) * math.sin(a)
        g = cyl_y(cx, cz, 0.555, -face, face)
        neck = (box(-0.5, 0.5, -face, face, 0, 1.2).rotate((0, 0, 0), (0, 1, 0), -math.degrees(a) + 90)
                .translate((cx, 0, cz)))
        p = p.cut(g).cut(neck)
    p = p.cut(cyl_y(0, 0, r_od + 1, -2.25, 2.25).cut(cyl_y(0, 0, r_od - 2.0, -3, 3)))   # screw-head groove
    for sgn in (-1, 1):                                 # flanges
        y0f, y1f = sorted((sgn * face / 2, sgn * (face / 2 + 1.0)))
        p = p.union(cyl_y(0, 0, 12.0, y0f, y1f))
    if drive:
        # hub on the inner side (it would hit the 625 bearing seat in the end wall on the outer side). Fins
        # ride round with the pulley, and the hub (r 8) stays inside the bridge's 14 mm radius.
        yh0, yh1 = -(face / 2 + 8.0), -(face / 2 + 1.0)
        p = p.union(cyl_y(0, 0, 8.0, yh0, yh1))
        p = p.cut(cyl_y(0, 0, 2.55, -20, 20))
        yg = (yh0 + yh1) / 2
        p = p.cut(cyl_z(0, yg, 1.6, 0, 9))                                   # M3 x 4 grub, sits below the hub surface
        p = p.cut(box(-2.9, 2.9, yh0 - 1, yg + 1.3, 3.0, 5.6))               # M3 nut slides in from the hub end
    else:
        p = p.cut(cyl_y(0, 0, SEAT_685 / 2, -10, 10)).union(cyl_y(0, 0, SEAT_685 / 2, -0.5, 0.5).cut(cyl_y(0, 0, 4.0, -1, 1)))
    return p

def sensor_clip():
    """Holds one break-beam half (20 x 10 x 8 housing) with a 4 mm window for the beam. M3 to a wall insert."""
    c = box(0, 26, 0, 12, 0, 16)
    c = c.cut(box(2.8, 23.2, 2, 12.1, 2.8, 13.2))
    c = c.cut(cyl_y(13, 8, 2.0, -1, 3))
    c = c.union(box(26, 36, 0, 3, 0, 16)).cut(cyl_y(31, 8, M3 / 2, -1, 4))
    return c

def motor_standoff():
    """Holds a NEMA 17 30 mm off the wall so the 5x5 coupler sits outside the wall. Two 4 mm plates joined by
    side walls, open top and bottom: an L-key reaches every screw head and the coupler set screws from above.
    Motor face plate: 4 x M3 x 8 into the motor. Wall plate: 4 x M3 x 10 into the wall's heat-set inserts.
    Frame in its own coordinates: wall side at y=0, motor face at y=30."""
    L, T = 30.0, 4.0
    m = box(-21.15, 21.15, 0, L, -21.15, 21.15)
    m = m.cut(box(-18.4, 18.4, T, L - T, -22, 22))            # open top + bottom between the plates
    m = m.cut(tear_y(0, 0, 11.5, -1, L + 1))                  # motor boss / shaft / coupler (teardrop: prints open side down)
    for dx in (-15.5, 15.5):
        for dz in (-15.5, 15.5):
            m = m.cut(cyl_y(dx, dz, M3 / 2, -1, L + 1))       # short screws, heads inside
    # fillets between the side walls and the plates
    for sx in (-1, 1):
        for yy in (T, L - T):
            m = m.union(box(*sorted((sx * 18.4, sx * 15.4)), yy - 3 if yy > T else yy, yy + 3 if yy == T else yy, -21.15, -18.8))
            m = m.union(box(*sorted((sx * 18.4, sx * 15.4)), yy - 3 if yy > T else yy, yy + 3 if yy == T else yy, 18.8, 21.15))
    return m

def fit_coupon():
    """Print this first (PETG, ~1 h). Every hole size the machine depends on, at the design value (marked *)
    and a step either side, so the CAD can be matched to this printer before the long prints.
    Rows (front to back): M3 heat-set insert holes · 685ZZ seats (idler pulleys) · 625 seats (shaft bearings) ·
    5 mm shaft holes + M2 fin-screw pilots. Back rib: horizontal 2 mm hinge-pin and 5 mm shaft holes (walls print
    upright, so those holes print sideways) and the M3 nut trap from the drive-pulley hub."""
    W, D, T = 112.0, 80.0, 6.0
    c = box(0, W, 0, D, 0, T)
    labels = []
    def row(y, dias, design, depth, push=None, x0=10.0, dx=None):
        n = len(dias); dx = dx or (W - 2 * x0) / (n - 1)
        for i, d in enumerate(dias):
            x = x0 + i * dx
            nonlocal c
            c = c.cut(cyl_z(x, y, d / 2, T - depth, T + 1))
            if push: c = c.cut(cyl_z(x, y, push / 2, -1, T))
            labels.append((x, y - (max(dias) / 2 + 3.2), f"{d:g}" + ("*" if abs(d - design) < 1e-6 else "")))
    row(10.0, [4.5, 4.6, 4.7, 4.8, 4.9], M3_INSERT, 5.5)
    row(27.0, [11.2, 11.3, 11.4], SEAT_685, 5.0, push=7.0, x0=16.0)
    row(48.0, [16.2, 16.3, 16.4], SEAT_625, 5.0, push=10.0, x0=16.0)
    row(68.0, [5.1, 5.3, 5.5], 5.5, T + 1, x0=8.0, dx=11.0)
    row(68.0, [1.9, 2.1, 2.3], PILOT_M2, T + 1, x0=50.0, dx=8.0)
    # back rib with horizontal holes (hinge pin 2.0/2.1/2.2, frame vs door; shaft 5.5) and the nut trap
    rib = box(0, W, D, D + 8, 0, 16)
    for x, d in ((12, 2.0), (24, 2.1), (36, 2.2), (54, 5.3), (70, 5.5)):
        rib = rib.cut(cyl_y(x, 9.0, d / 2, D - 1, D + 9))
        star = "*" if d in (2.1, 5.5) else ""
        labels.append((x, D - 2.6, f"{d:g}{star}"))
    rib = rib.cut(box(84, 89.8, D - 1, D + 9, 7.0, 9.6))                           # M3 nut trap 5.8 x 2.6
    rib = rib.cut(cyl_z(86.9, D + 4, M3 / 2, 0, 17))
    c = c.union(rib)
    labels.append((86.9, D - 2.6, "nut"))
    for (x, y, t) in labels:
        c = c.union(cq.Workplane("XY").text(t, 4.0, 0.6, halign="center", valign="center", kind="bold").translate((x, y, T)))   # raised: reads better than cut
    return c

# ============================================================================ SCANNER
SCAN_X0, SCAN_X1 = 150.0, BIN_X[0] - PITCH / 2  # scan module footprint along X (150..355, under the hood)
HOOD_X0, HOOD_X1 = SCAN_X - 77.0, SCAN_X + 78.0
CAM_RIB_X0 = 34.6    # camera hanger ribs at |X - SCAN_X| 34.6..38.6
CAM_HOLE_DZ = 5.0    # tab insert centre, above the camera PCB's underside
CAM_D_MIN, CAM_D_MAX = 100.0, 135.0
CAM_SLOT_Z0 = PATH + 44 + CAM_D_MIN + CAM_HOLE_DZ   # lens tip is 44 below the PCB underside
CAM_SLOT_Z1 = PATH + 44 + CAM_D_MAX + CAM_HOLE_DZ
HOOD_H = 198.0        # lens-to-card 100-135 mm, camera plate under the lid's roof at the top setting
CAM_CABLE_Z = PATH + HOOD_H - 15.0  # camera connector level (roughly)
SHEEN_Z = WALL_TOP + 6.0            # sheen LED port in the back wall, under the back LED ledge
LED_H = 55.0                        # LED strips this far above the card
LID_Z = PATH + HOOD_H - 12.0        # the hood's removable lid starts here
LID_KEY_X = SCAN_X + 40.0           # lid key on the back side, off-centre: the lid only goes on one way
RIB_CONN_Z = PATH + CAM_D + 44 + 2.0   # camera connector height (default lens height)
RIB_X = HOOD_X0 - 8.5               # the ribbon rises here, flat, just outside the hood's left wall (in the gap)
RIB_RUN_Z = WALL_TOP + 7.0          # height of the run back across the gap (just above the conveyor walls) from the pod
RIB_TWIST_Z = (RIB_RUN_Z + 16.0, RIB_CONN_Z - 36.0)   # the ribbon rolls 90 deg over this rise (~64 mm, 4 x its width)
RIB_RAIL_Z0 = RIB_CONN_Z - 34.0     # one pair of L-rails on the outside of the left wall holds the flat top part
SCREEN_TILT = 15.0                  # screen leans back this many degrees

WIN_X0, WIN_X1, WIN_Z0, WIN_ZR = 12.0, PITCH - 12.0, RAIL_Z + 20.0, 125.0   # back window (module x): rectangle to
# Z 125, then a 45 degree roof to a point at Z 174 (no long bridge when the wall prints upright)
MOUNT_X = 203.0                    # screen wall mount centre (on the scan module's front wall)
CRADLE_XC = (PSU_X0 + 6.0, PSU_X0 + PSU_L - 17.0)    # PSU cradle centres (186, 292): the first clears the IEC inlet

def back_window(x0, x1, s, xa=WIN_X0, xb=WIN_X1, z0=WIN_Z0, zr=WIN_ZR):
    """The window through a back wall: a rectangle with a 45 degree roof, so the wall prints upright without a long
    bridge (the roof meets in a point)."""
    w = xb - xa
    pts = [(x0 + xa, z0), (x0 + xb, z0), (x0 + xb, zr), (x0 + xa + w / 2, zr + w / 2), (x0 + xa, zr)]
    y0, y1 = sorted((s * (WALL_IN - 1), s * (WALL_OUT + 1)))
    return cq.Workplane("XZ").polyline(pts).close().extrude(-(y1 - y0)).translate((0, y0, 0))

GUSSET_IN = 38.0   # the gusset under the strip stops at |Y| 38: the door barrels pass up beside it (2.6 mm of strip overhangs)

def strip_gusset(x0, x1, s, notches=()):
    """45 degree gusset under the strip (wall face to the strip's inner edge) so the walls print UPRIGHT: the 12 mm
    strip would otherwise be a flat overhang. notches: (xa, xb) ranges left open (tie bar ends, lever swing...)."""
    yw, yi = s * WALL_IN, s * GUSSET_IN
    zt = PATH - 12.0
    g = (cq.Workplane("YZ").polyline([(yw, zt - (WALL_IN - GUSSET_IN)), (yw, zt + 0.01), (yi, zt + 0.01)]).close()
         .extrude(x1 - x0).translate((x0, 0, 0)))
    for xa, xb in notches:
        g = g.cut(box(xa, xb, -99, 99, 0, 400))
    return g

def side_frame(x0, x1, side, bin_opening=True, rails=True, bay=False, tie_hole=True, top_inserts=None,
               bosses=None, gusset_notches=()):
    """One side of a track module (side = -1 front, +1 back). Wall + top strip with belt run + foot. Prints UPRIGHT
    (foot down; 225 mm tall, under the Neptune 4 Pro's 265): the strip has a 45 degree gusset under it, windows
    have pointed roofs. Floor edge is at |Y| = 35; belt loop at |Y| 37..47 above the floor.
    top_inserts: X positions of wall-top inserts (default both ends); bosses: X positions of the outer-face M3
    inserts at Z PATH-25 (joint plates; default both ends)."""
    s = side
    yw0, yw1 = sorted((s * WALL_IN, s * WALL_OUT))
    ys0, ys1 = sorted((s * STRIP_IN, s * WALL_IN))
    zb = BAY_TOP if (bay and s < 0) else RAIL_Z                  # front walls of bin modules start above the bay
    f = box(x0, x1, yw0, yw1, zb, PATH)                          # wall below the floor
    yu0, yu1 = sorted((s * WALL_IN_UP, s * WALL_OUT))
    f = f.union(box(x0, x1, yu0, yu1, PATH, WALL_TOP))          # wall above the floor hides the belt
    f = f.union(box(x0, x1, ys0, ys1, PATH - 12, PATH))         # strip: floor edge
    f = f.union(strip_gusset(x0, x1, s, gusset_notches))
    # ledges under the belt's outer 3 mm (bottom run rests on its back, top run on its tooth tips)
    yl0, yl1 = sorted((s * 44.0, s * WALL_IN_UP))
    f = f.union(box(x0, x1, yl0, yl1, BELT_BACK_LOW - 2, BELT_BACK_LOW))
    f = f.union(box(x0, x1, yl0, yl1, BELT_TEETH_HIGH - 2, BELT_TEETH_HIGH))
    if rails:
        f = f.union(guide_rail(x0, x1, s, xoff=0.0 if x0 > 0 else 1e4))   # bin modules (built at x 0) are past the taper
    for xc in (top_inserts if top_inserts is not None else (x0 + 8, x1 - 8)):   # hood inserts in the wall top
        # the wall is only 6.5 mm up here: a boss on the outer face (45 degree underside) and the insert moved out
        # to Y 53 leaves 2 mm of wall either side of it
        bz = (cq.Workplane("YZ").polyline([(s * WALL_OUT, WALL_TOP - 18), (s * (WALL_OUT + 3), WALL_TOP - 15), (s * (WALL_OUT + 3), WALL_TOP),
                                           (s * WALL_OUT, WALL_TOP)]).close().extrude(10.0).translate((xc - 5, 0, 0)))
        f = f.union(bz)
        f = f.cut(cyl_z(xc, s * TOP_INSERT_Y, M3_INSERT / 2, WALL_TOP - 7, WALL_TOP + 1))
    slot_xs = []
    if not (bay and s < 0):
        # foot over the rail; M5 x 10 + T-nut in the rail's top slot
        yf0, yf1 = sorted((s * WALL_IN, s * (RAIL_Y + 10)))
        f = f.union(box(x0, x1, yf0, yf1, RAIL_Z, RAIL_Z + 6))
        f = rail_slots(f, x0, x1, ys=(s * RAIL_Y,))
        slot_xs = [x0 + (x1 - x0) * (i + 1) / 3 for i in range(2)]
    # wire channel on the outside face of the back walls (servo, sensor and LED looms): a closed 10 x 24 mm duct
    # standing on the foot, open at both ends so it runs through every module. It stops short either side of each
    # rail screw (gap = head + slot travel), so a key reaches the screws and the looms can be fed in there.
    if s > 0:
        cz0, cz1 = CHAN_Z0, CHAN_Z1
        ch = box(x0, x1, WALL_OUT, WALL_OUT + 12, RAIL_Z + 6, cz1)
        ch = ch.cut(box(x0 - 1, x1 + 1, WALL_OUT + 0.01, WALL_OUT + 10, cz0 + 2, cz1 - 2))
        for xs in slot_xs:
            ch = ch.cut(box(xs - CHAN_GAP / 2, xs + CHAN_GAP / 2, WALL_OUT + 0.01, WALL_OUT + 13, RAIL_Z + 5, cz1 + 1))
        f = f.union(ch)
    # window through the back wall (wiring, the bin hub), pointed roof
    if bin_opening and s > 0:
        f = f.cut(back_window(x0, x1, s))
    for xc in (bosses if bosses is not None else (x0 + 8, x1 - 8)):   # outer-face inserts: joint plates
        f = f.cut(cyl_y(xc, JOINT_Z, M3_INSERT / 2, s * WALL_OUT - (6 if s > 0 else 0), s * WALL_OUT + (6 if s < 0 else 0)))
    if tie_hole:
        f = f.cut(cyl_y(x0 + TIE_X, PATH - 17.5, M3 / 2, yw0 - 1, yw1 + 1))     # tie-bar screw
    if bay and s < 0:
        # two fingers under the wall's bottom edge either side of the bin's top: they put the bin in the right place
        # along X as it slides in (1.5 mm play a side)
        for xs in (-1, 1):
            xf = x0 + PITCH / 2 + BIN_DX + xs * (49.0 + 1.5 + 1.0)
            f = f.union(box(xf - 1.0, xf + 1.0, -WALL_OUT, -WALL_IN, BAY_TOP - 10.0, BAY_TOP + 0.01))
        # the front wall stops at BAY_TOP: the bin slides out underneath. It hangs from the tie bar at its start and
        # a joint plate to the next module at its end (no posts down to the desk any more: they made the part too
        # tall for the bed and stopped it lying flat).
        # bin-level sensor: VL53L1X carrier slides into a pocket under the strip, looking straight down at
        # Y -42 (into the stack); its wires come out of the open inner end of the pocket
        tb = box(x0 + TOF_X - 11, x0 + TOF_X + 11, -WALL_IN, -35.5, PATH - 19, PATH - 12)
        f = f.union(tb)
        f = f.cut(box(x0 + TOF_X - 9.2, x0 + TOF_X + 9.2, -48.6, -35.4, PATH - 17.2, PATH - 14.8))
        f = f.cut(cyl_z(x0 + TOF_X, -42.0, 4.5, PATH - 40, PATH - 17))       # view shaft down through the gusset
        # bevel the wall's inner bottom edge under the sensor so its 15 degree cone clears the wall (front wall now
        # ends at Z 140 right beside the view)
        f = f.cut(cq.Workplane("YZ").polyline([(-WALL_IN + 0.01, BAY_TOP + 16.0), (-WALL_IN - 5.0, BAY_TOP - 0.01), (-WALL_IN + 0.01, BAY_TOP - 0.01)])
                  .close().extrude(24.0).translate((x0 + TOF_X - 12.0, 0, 0)))
    if bay and s > 0:
        # foot reaching in to the second back rail under the doors
        f = f.union(box(x0, x1, RAIL2_Y - 10, WALL_IN, RAIL_Z, RAIL_Z + 6))
        f = rail_slots(f, x0, x1, ys=(RAIL2_Y,))
    return f

HOME_X, HOME_Y = SCAN_X0 + 10.0, 39.5   # belt home sensor (TCRT5000 looking up at the fins, back side)

def scan_common(s):
    """Both scan-module walls: hood insert in the wall top at the hood's left feet (its right feet use bin module
    1's), a ledge along the strip's inner edge that the scan floor's ribs rest on, the PSU cradle screws."""
    f = side_frame(SCAN_X0, SCAN_X1, s, bin_opening=False, tie_hole=False, top_inserts=(HOOD_X0 + 11.0, SCAN_X1 - 6.0), bosses=(),
                   gusset_notches=((HOME_X - 7.0, HOME_X + 33.5),) if s > 0 else ())
    f = f.union(box(SCAN_X0, SCAN_X1, *sorted((s * 33.0, s * STRIP_IN + s * 0.01)), PATH - 12, PATH - 10))
    zc = PSU_SCREW_Z[0] if s < 0 else PSU_SCREW_Z[1]
    for xc in CRADLE_XC:
        f = f.cut(cyl_y(xc, zc, M3 / 2, -WALL_OUT - 1, WALL_OUT + 1))
    return f

def scan_side_front():
    """Front wall of the scan module: the screen wall mount's 2 inserts (Z PATH-21, 89 mm apart round MOUNT_X)."""
    f = scan_common(-1)
    for x in (MOUNT_X - 44.5, MOUNT_X + 44.5):
        f = f.cut(cyl_y(x, PATH - 21, M3_INSERT / 2, -WALL_OUT - 1, -WALL_OUT + 6))
    return f

def scan_side_back():
    """Back wall of the scan module: the IEC inlet window and the cable hole (teardrop), covered by the inlet plate."""
    f = scan_common(1)
    f = f.cut(box(SCAN_X0 + 42, SCAN_X0 + 100, WALL_IN - 1, WALL_OUT + 1, RAIL_Z + 52, RAIL_Z + 94))
    xg, zg = SCAN_X0 + 124, RAIL_Z + 73
    f = f.cut(cyl_y(xg, zg, 10.0, WALL_IN - 1, WALL_OUT + 1))
    f = f.cut(cq.Workplane("XZ").polyline([(xg - 7.07, zg + 7.07), (xg, zg + 14.14), (xg + 7.07, zg + 7.07)]).close()
              .extrude(-(WALL_OUT - WALL_IN + 2)).translate((0, WALL_IN - 1, 0)))
    for x in (SCAN_X0 + 36, SCAN_X0 + 144):
        for z in (RAIL_Z + 43, RAIL_Z + 103):
            f = f.cut(cyl_y(x, z, M3_INSERT / 2, WALL_OUT - 6, WALL_OUT + 1))
    # belt home sensor: a spare TCRT5000 module under the strip looks up through a window at the fin bridges
    # going past on the bottom run (3 mm above the window; with no fin it sees the black belt 7 mm up).
    # Cards never reach |Y| 37. Module screws to an insert in the strip's underside (M3 x 6 from the kit).
    xh, yh = HOME_X, HOME_Y
    f = f.cut(box(xh - 4.5, xh + 4.5, yh - 2.0, yh + 2.0, PATH - 5, PATH + 1))          # window
    f = f.cut(box(xh - 5.2, xh + 5.2, yh - 2.9, yh + 2.9, PATH - 13, PATH - 3.9))       # head pocket
    f = f.cut(cyl_z(xh + 23.0, yh, M3_INSERT / 2, PATH - 13, PATH - 6))                  # module mounting hole
    f = f.cut(cyl_y(xh + 30.0, PATH - 18, 3.0, WALL_IN - 1, WALL_OUT + 1))              # wires out to the back
    return f

def scan_floor():
    """Solid matte-green floor under the camera (green stands out best against black, white and borderless card edges), between the strips (Y -35..35). Slots let the fins pass."""
    x0, x1 = SCAN_X0, SCAN_X1
    fl = box(x0 + 0.5, x1 - 5.5, -FLOOR_W, FLOOR_W, PATH - 3, PATH)   # tie-bar plate covers the last 5 mm
    for sg in (-1, 1):   # side walls down to flanges that rest on the ledges along the scan walls' strips
        fl = fl.union(box(x0 + 0.5, x1 - 5.5, *sorted((sg * 31.0, sg * FLOOR_W)), PATH - 10, PATH - 2.9))
        fl = fl.union(box(x0 + 0.5, x1 - 5.5, *sorted((sg * 31.0, sg * (STRIP_IN - 0.2))), PATH - 10, PATH - 7))
    for xc in (x0 + 20, x1 - 20):
        fl = fl.union(box(xc - 2, xc + 2, -FLOOR_W, FLOOR_W, PATH - 10, PATH))
    return fl.cut(fin_groove(x0 - 1, x1 + 1, GROOVE_Y1))

def hood():
    """Light-tight hood over the scan position. 155 x 150 x 165 mm (6.1 x 5.9 x 6.5 in), 3 mm walls.
    Inside: camera plate on top, ledges for the LED channels on all four walls, slots for the belts."""
    x0, x1, y0, y1 = HOOD_X0, HOOD_X1, -75.0, 75.0
    h = box(x0, x1, y0, y1, PATH + 10, PATH + HOOD_H)
    h = h.cut(box(x0 + 3, x1 - 3, y0 + 3, y1 - 3, PATH + 9, PATH + HOOD_H - 3))
    # card tunnel through both end walls
    h = h.cut(box(x0 - 1, x1 + 1, -(WALL_OUT + 0.5), WALL_OUT + 0.5, PATH + 9, WALL_TOP + 0.5))   # track + walls pass through
    # pads at the four corners sit on the wall tops; M3 into the wall-top inserts
    for xa, xb in ((x0 + 3, x0 + 19), (SCAN_X1 - 14.0, SCAN_X1 - 0.5)):   # right pair on the scan walls, short of the joint
        for sg in (-1, 1):
            y0p, y1p = sorted((sg * WALL_IN_UP, sg * 72.5))
            h = h.union(box(xa, xb, y0p, y1p, WALL_TOP, WALL_TOP + 5))
    # (the camera hangs from the removable lid: hood_lid)
    # Camera ribbon: it rises up the OUTSIDE of the left (hopper-side) wall in the gap, flat against the wall under
    # pairs of opposing L-rails, rolls over through this slot at camera height and goes straight into the camera
    # (connector facing the wall). No sideways turns or folds anywhere.
    h = h.cut(box(x0 - 1, x0 + 4, -12, 12, RIB_CONN_Z - 16, RIB_CONN_Z + 3))
    h = h.union(box(x0 + 3, x0 + 9, -14, 14, RIB_CONN_Z + 3, RIB_CONN_Z + 5))            # light lip over the slot
    for z in (RIB_RAIL_Z0,):                                                         # rail pair on the outside face
        for sg in (-1, 1):
            e = sg * 8.75
            y0r, y1r = sorted((e, e + sg * 2))
            h = h.union(box(RIB_X - 1.3, x0 + 0.1, y0r, y1r, z, z + 14))                  # stem off the wall
            y0l, y1l = sorted((e + sg * 2, e - sg * 3))
            h = h.union(box(RIB_X - 1.3, RIB_X - 0.5, y0l, y1l, z, z + 14))              # lip over the ribbon edge
    # LED channel ledges (aluminium channel 17 x 8 mm) on the front and back walls, LED_H above the card: low enough
    # that a glossy card or sleeve reflects them away from the lens (mirror point lands outside the card)
    zled = PATH + LED_H
    h = h.union(box(x0 + 3, x1 - 3, y0 + 3, y0 + 14, zled - 2, zled))
    h = h.union(box(x0 + 3, x1 - 3, y1 - 14, y1 - 3, zled - 2, zled))
    # sheen LED port (low angle, back wall): a 2 cm piece of the COB strip in sheen_cap shines in through it
    h = h.cut(box(SCAN_X - 22, SCAN_X + 22, y1 - 4, y1 + 1, SHEEN_Z - 4, SHEEN_Z + 4))   # port: a slot the strip shines through
    for dx in (-SHEEN_SCREW_DX, SHEEN_SCREW_DX):                           # sheen_cap screws (M3 inserts)
        h = h.union(cyl_y(SCAN_X + dx, SHEEN_Z, 4.5, y1 - 0.5, y1 + 5))
        h = h.cut(cyl_y(SCAN_X + dx, SHEEN_Z, M3_INSERT / 2, y1 - 1.5, y1 + 6))     # 6.5 deep: room for the 5.7 insert
    # LED wires (both channels + the sheen LED) leave through this hole low in the back wall, near the right end,
    # and drop down the back of the scan module into the back wire channel
    h = h.cut(cyl_y(x1 - 14, WALL_TOP + 22, 3.5, y1 - 4, y1 + 1))
    # feet: 4 x M3 x 10 into the wall-top inserts, all in the scan module's walls (X 228 and 349). The hood overhangs
    # the joint onto bin module 1 by 17 mm, but the bin modules carry no wall-top inserts (their front walls print flat)
    for s in (-1, 1):
        for xc in (x0 + 11, SCAN_X1 - 6.0):
            h = h.cut(cyl_z(xc, s * TOP_INSERT_Y, M3 / 2, WALL_TOP - 1, WALL_TOP + 6))
    # the top comes off as hood_lid: cut here, add the tongue of the light trap
    h = h.intersect(box(x0 - 15, x1 + 1, y0 - 1, y1 + 8, -1e3, LID_Z))   # (wide enough to keep the outside rails and sheen bosses)
    tongue = box(x0 + 1.6, x1 - 1.6, y0 + 1.6, y1 - 1.6, LID_Z - 0.01, LID_Z + 6).cut(box(x0 + 3, x1 - 3, y0 + 3, y1 - 3, LID_Z - 1, LID_Z + 7))
    tongue = tongue.cut(box(LID_KEY_X - 10.4, LID_KEY_X + 10.4, y1 - 4, y1 + 1, LID_Z - 1, LID_Z + 7))   # key notch
    return h.union(tongue)

def hood_lid():
    """Removable roof of the hood with the camera hanging from it. Light trap: the hood's 1.4 mm tongue sits in a
    groove between the lid's outer and inner skirts (two right-angle turns, light can't get through). A key on the
    back side only fits the notch in the tongue one way round, so the lid always goes on the right way.
    Lift it off and the camera comes with it: set the height and focus in your hands, watching the live view.
    Camera hanger: two ribs with vertical slots; camera_plate's tabs (M3 inserts) clamp on with 2 x M3 x 10.
    Prints roof down, no supports."""
    x0, x1, y0, y1 = HOOD_X0, HOOD_X1, -75.0, 75.0
    top = PATH + HOOD_H
    ring = lambda a, b, z0, z1: box(x0 + a, x1 - a, y0 + a, y1 - a, z0, z1).cut(box(x0 + b, x1 - b, y0 + b, y1 - b, z0 - 1, z1 + 1))
    l = box(x0, x1, y0, y1, top - 3, top)                                  # roof
    l = l.union(ring(0, 1.4, LID_Z + 0.2, top))                            # outer skirt (flush with the walls)
    l = l.union(ring(1.4, 3.0, LID_Z + 6.2, top))                          # wall over the tongue
    l = l.union(ring(3.2, 4.6, LID_Z + 1.0, top))                          # inner skirt
    l = l.union(box(LID_KEY_X - 10, LID_KEY_X + 10, y1 - 3.2, y1 - 1.4, LID_Z + 0.2, LID_Z + 6.2))   # key
    for xg in (x0 + 25, x1 - 25):                                          # finger grips on the roof
        l = l.cut(box(xg - 12, xg + 12, -30, 30, top - 1, top + 1))
    zr = top - 3
    for sy in (-1, 1):                                   # ribs front and back (the ribbon comes in from the left)
        ya, yb = sorted((sy * CAM_RIB_X0, sy * (CAM_RIB_X0 + 4)))
        l = l.union(box(SCAN_X - 10, SCAN_X + 10, ya, yb, CAM_SLOT_Z0 - 4.5, zr + 0.5))
        l = l.cut(box(SCAN_X - 1.7, SCAN_X + 1.7, ya - 1, yb + 1, CAM_SLOT_Z0, CAM_SLOT_Z1))
        for zz in (CAM_SLOT_Z0, CAM_SLOT_Z1):
            l = l.cut(cyl_y(SCAN_X, zz, 1.7, ya - 1, yb + 1))
    return l

SHEEN_SCREW_DX = 31.0

def sheen_cap():
    """Light-tight cap over the sheen LED port on the outside of the hood's back wall. Holds one cut piece of the same
    24 V COB strip as the hood lights (no extra part to buy: cut it at the strip's marked cut line, up to 52 mm long)
    facing in through the port. 2 x M3 x 12 (in counterbores) into the hood's inserts; wires out of the bottom."""
    c = box(-SHEEN_SCREW_DX - 7, SHEEN_SCREW_DX + 7, 0, 9, -10, 10)
    c = c.cut(box(-26.5, 26.5, -1, 6, -5.5, 5.5))                          # strip pocket (52 x 10 strip + room)
    c = c.cut(box(-3, 3, -1, 4, -11, -4))                                  # wire exit
    for dx in (-SHEEN_SCREW_DX, SHEEN_SCREW_DX):
        c = c.cut(cyl_y(dx, 0, M3 / 2, -1, 10))
        c = c.cut(cyl_y(dx, 0, 3.4, 6, 10))          # 3 mm counterbore: the head sits deeper, so an M3 x 12 reaches
    return c

def camera_plate():
    """Carries the HQ camera (4 x M2 x 8 self-tapping through the PCB's 2.7 mm holes, 30 x 30; the lens mount drops
    through the hole). (M2, not M2.5: the screw kit is M2/M3/M4.)
    Two tabs with M3 heat-set inserts clamp to the slotted ribs on the hood lid (M3 x 10, lid off).
    Local frame: plate z 0..4, top face against the camera PCB."""
    p = box(-31, 31, -31, 31, 0, 4)
    for sy in (-1, 1):                                   # tabs front and back; the camera's connector faces -X (left)
        ya, yb = sorted((sy * (CAM_RIB_X0 - 6.3), sy * (CAM_RIB_X0 - 0.3)))
        p = p.union(box(-8, 8, ya, yb, 0, 14))
        yi0, yi1 = sorted((sy * (CAM_RIB_X0 - 0.3 + 1), sy * (CAM_RIB_X0 - 6.3 - 1)))
        p = p.cut(cyl_y(0, CAM_HOLE_DZ + 4, M3_INSERT / 2, yi0, yi1))
    p = p.cut(cyl_z(0, 0, 18.5, -1, 5))
    for dx in (-15, 15):
        for dy in (-15, 15):
            p = p.cut(cyl_z(dx, dy, PILOT_M2 / 2, -1, 5))
    return p

LENS_D = 30.00      # 6 mm lens front, measured by Eric (its own cover's bore: 30.11)
LENS_BORE = 30.20   # cap bore as drawn: holes this size print ~0.1 mm small (fit coupon), so it comes out ~30.1, like the lens's cover

def polarizer_cap():
    """Slip-on cap for the front of the 6 mm lens (same fit as the cover it came with): holds a 32 mm disc of the
    polarizer film; turn it to cross-polarize (darkest glare). Index tab to mark the best angle."""
    ri = LENS_BORE / 2
    c = cq.Workplane("XY").circle(ri + 2.0).circle(ri).extrude(10)
    c = c.union(cq.Workplane("XY").circle(ri + 2.0).circle(ri - 4.0).extrude(1.6))
    c = c.cut(cq.Workplane("XY").circle(16.2).extrude(0.6).translate((0, 0, 1.6)))     # film disc seat (32 mm)
    c = c.union(box(ri + 1.5, ri + 7, -2, 2, 0, 10))   # index tab
    return c

# ============================================================================ BIN MODULES
# ---- trapdoors. Hinge axis along X just outside the door's back edge, under the back guide rail. The frame's three
# knuckles hang off the strip; the door's two long barrels sit in notches in the strip between them. One 2 mm x 100 mm
# pin runs through all of them (fit the door before the next module is bolted on: the pin goes in from the module end).
HINGE_Y, HINGE_Z = 34.0, PATH - 5.0
KN_R = 2.8
FRAME_KN = [(12.0, 16.0), (59.0, 63.0), (108.0, 112.0)]   # module x: frame knuckles (pin 12 -> 112 = 100 mm)
DOOR_BAR = [(16.5, 58.5), (63.5, 101.0)]                  # module x: door barrels (the 2nd stops short of the servo bracket)
DOOR_X0 = 5.5                                             # door from module x 5.5 to 116.5
DOOR_OPEN = 60.0
# servo (EMAX ES08MA II) inside the module under the back strip, output shaft along -X, horn in the same plane as the
# door lever. Lever and horn are the same length at the same angle, and the link is parallel to the hinge->shaft line:
# a parallelogram, so the door turns exactly as far as the horn (60 deg) and the servo never pushes against a toggle.
LEVER_X = (84.5, 88.5)        # lever plate on the second barrel
LEVER_R, LEVER_A0 = 12.0, 240.0   # lever length; angle (deg, in the YZ plane from +Y) with the door closed
SERVO_S = (HINGE_Y + 3.0, HINGE_Z - 22.0)   # servo shaft (Y, Z)
SERVO_TOP_X = 96.0            # servo's top face (the horn side); body runs to X 120
LINK_X = (89.0, 91.5)

def _lever_end(a_deg, origin=(HINGE_Y, HINGE_Z)):
    a = math.radians(a_deg)
    return (origin[0] + LEVER_R * math.cos(a), origin[1] + LEVER_R * math.sin(a))

def _stadium_yz(p, q, r, x0, x1):
    """A flat bar in the YZ plane from p to q with round ends of radius r, x0..x1 thick."""
    L = math.dist(p, q); ang = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
    bar = box(x0, x1, 0, L, -r, r).rotate((0, 0, 0), (1, 0, 0), ang).translate((0, p[0], p[1]))
    return bar.union(cyl_x(p[0], p[1], r, x0, x1)).union(cyl_x(q[0], q[1], r, x0, x1))

def door():
    """Trapdoor leaf in MODULE coordinates (closed): 111 x 67 x 2.4 mm, top flush with the floor. Two hinge barrels
    along the back edge (2.2 mm pin holes), notches where the frame knuckles go, the servo lever on the second barrel
    and a slot the bin's break-beam shines through when the door is open (the card sliding down crosses it).
    Print top face DOWN on the smooth side of the plate."""
    x0, x1, T = DOOR_X0, PITCH - DOOR_X0, 2.4
    d = box(x0, x1, -FLOOR_W, FLOOR_W, PATH - T, PATH)
    d = d.cut(fin_groove(x0 - 1, x1 + 1, GROOVE_Y1))
    d = d.cut(box(x0 - 1, x0 + 1.0, HINGE_Y - 1.0, FLOOR_W + 1, PATH - 1.0, PATH + 1))   # tiny chamfer feel at the back corners
    for xa, xb in FRAME_KN:                                                 # room for the frame knuckles
        d = d.cut(box(xa - 0.5, xb + 0.5, HINGE_Y - KN_R - 0.6, FLOOR_W + 1, PATH - 10, PATH + 1))
    for xa, xb in DOOR_BAR:
        bar = cyl_x(HINGE_Y, HINGE_Z, KN_R, xa, xb).union(box(xa, xb, HINGE_Y - KN_R, FLOOR_W, HINGE_Z, PATH - 2.0))
        d = d.union(bar)
    le = _lever_end(LEVER_A0)
    d = d.union(_stadium_yz((HINGE_Y, HINGE_Z), le, 3.0, *LEVER_X))
    for xa, xb in DOOR_BAR:
        d = d.cut(cyl_x(HINGE_Y, HINGE_Z, 1.1, xa - 1, xb + 1))           # 2.2 hole: the door turns on the pin
    d = d.cut(cyl_x(le[0], le[1], PILOT_M2 / 2, LEVER_X[0] - 1, LEVER_X[1] + 1))   # M2 x 8 from the link side
    # notch in the back edge where the servo bracket stands: the door goes in from below, past the bracket
    d = d.cut(box(SERVO_TOP_X + 6.0 - 0.6, SERVO_TOP_X + 9.0 + 0.6, 28.9, FLOOR_W + 1, PATH - 12, PATH + 1))
    # break-beam slot: where the beam (X 61, Z PATH-22) crosses the open door
    d = d.cut(box(PITCH / 2 - 3.0, PITCH / 2 + 3.0, 7.5, 16.5, PATH - 4, PATH + 1))
    return d

def door_open(d=None, ang=DOOR_OPEN):
    d = door() if d is None else d
    return d.rotate((0, HINGE_Y, HINGE_Z), (1, HINGE_Y, HINGE_Z), ang)

def servo_link():
    """Servo horn -> door lever, 22.2 mm between holes. Horn end: M2 x 8 self-taps into the horn's 12 mm hole (open
    it to 1.6 mm); door end: M2 x 8 through the link into the lever. Both screws snug, not tight: the link turns."""
    L = math.hypot(3.0, 22.0)
    l = box(0, L, -3, 3, 0, 2.5).union(cyl_z(0, 0, 3, 0, 2.5)).union(cyl_z(L, 0, 3, 0, 2.5))
    for x in (0, L):
        l = l.cut(cyl_z(x, 0, 1.3, -1, 4))
    return l

def link_placed(ang=0.0):
    """The link in module coordinates at door angle ang (0 closed)."""
    le = _lever_end(LEVER_A0 + ang)
    ht = (le[0] + SERVO_S[0] - HINGE_Y, le[1] + SERVO_S[1] - HINGE_Z)
    return _stadium_yz(le, ht, 3.0, *LINK_X).cut(cyl_x(le[0], le[1], 1.3, 0, 200)).cut(cyl_x(ht[0], ht[1], 1.3, 0, 200))

def servo_placed(ang=0.0):
    """ES08MA II envelope + its horn (single arm, 12 mm hole) in module coordinates."""
    xt, (ys, zs) = SERVO_TOP_X, SERVO_S
    zc = zs - 5.75
    body = box(xt, xt + 24.0, ys - 5.75, ys + 5.75, zc - 11.5, zc + 11.5)
    tabs = box(xt + 3.5, xt + 6.0, ys - 5.75, ys + 5.75, zc - 16.25, zc + 16.25)
    hub = cyl_x(ys, zs, 3.5, xt - 4.0, xt)
    ht = _lever_end(LEVER_A0 + ang, origin=SERVO_S)
    horn = _stadium_yz((ys, zs), ht, 3.0, xt - 4.0, xt - 2.0)
    return body.union(tabs).union(hub).union(horn)

def bin_module_side(side):
    """Side frame for one 122 mm bin module. Back side (+1): hinge knuckles, the servo bracket inside, the beam
    emitter, and 4 inserts for the back panel over the window (on one module the panel carries the bin hub).
    Front side (-1): door rest ledge, beam receiver, bin-level sensor pocket."""
    x0, x1 = 0.0, PITCH
    notch = [(-0.1, 2 * TIE_X + 0.6)] + ([(SERVO_TOP_X - 22.0, SERVO_TOP_X + 6.5)] if side > 0 else [])   # tie bar; lever, link, horn, servo (it slides in from -X)
    f = side_frame(x0, x1, side, bay=True, gusset_notches=notch, top_inserts=())   # no hood here: no wall-top bosses (they'd hold the flat-printed front wall 3 mm off the bed)
    s = side
    if s > 0:
        for xa, xb in FRAME_KN:                                   # frame knuckles hang off the strip
            f = f.union(cyl_x(HINGE_Y, HINGE_Z, KN_R, xa, xb)).union(box(xa, xb, HINGE_Y, STRIP_IN + 1, HINGE_Z - KN_R, PATH - 2))
        for xa, xb in DOOR_BAR:                                   # notches in the strip for the door barrels
            f = f.cut(box(xa - 0.5, xb + 0.5, STRIP_IN - 0.1, HINGE_Y + KN_R + 0.6, PATH - 12.1, PATH - 1.8))   # open below: the door goes in from underneath
        f = f.cut(box(LEVER_X[0] - 1, LEVER_X[1] + 1, STRIP_IN - 0.1, 44.0, PATH - 12.1, PATH - 1.8))   # lever swings up in here
        f = f.cut(cyl_x(HINGE_Y, HINGE_Z, 1.05, FRAME_KN[0][0] - 1, FRAME_KN[-1][1] + 1))             # 2.1 pin hole
        # servo bracket: a plate across the module (normal to X) that the servo's tabs screw to (2 x M2 x 8)
        ys, zs = SERVO_S; zc = zs - 5.75; xp = SERVO_TOP_X + 6.0
        br = (cq.Workplane("YZ").polyline([(29.5, zc - 20.0), (WALL_IN + 0.01, zc - 20.0 - (WALL_IN - 29.5)),
                                            (WALL_IN + 0.01, PATH - 11.99), (29.5, PATH - 11.99)]).close()
              .extrude(3.0).translate((xp, 0, 0)))                       # 45 degree underside: prints upright
        br = br.cut(box(xp - 1, xp + 4, ys - 5.95, ys + 5.95, zc - 11.7, zc + 11.7))
        for dz in (-13.9, 13.9):
            br = br.cut(cyl_x(ys, zc + dz, PILOT_M2 / 2, xp - 1, xp + 4))
        f = f.union(br)
        # back panel inserts round the window
        for xh in (6.5, PITCH - 6.5):
            for zh in (RAIL_Z + 42.0, PATH - 44.0):
                f = f.cut(cyl_y(xh, zh, M3_INSERT / 2, WALL_OUT - 6, WALL_OUT + 1))
    # (no door rest ledge on the front: the door's free edge swings DOWN, so a ledge under it stopped the door
    # opening past ~1 degree. The servo holds the door shut through the parallelogram link.)
    # break-beam housing (20 x 10 x 8) in a pocket on the outer face, 4 mm window through to the bin mouth; its leads
    # come inside through the slot beside it
    yp0, yp1 = sorted((s * (WALL_OUT - 7), s * (WALL_OUT + 5)))   # 1 mm skin left at the bin side
    f = f.cut(box(PITCH / 2 - 10.2, PITCH / 2 + 10.2, yp0, yp1, PATH - 27.2, PATH - 16.8))
    f = f.cut(cyl_y(PITCH / 2, PATH - 22, 2.0, -WALL_OUT - 1, WALL_OUT + 1))
    f = f.cut(box(PITCH / 2 + 4.0, PITCH / 2 + 9.0, *sorted((s * (WALL_IN - 1), s * (WALL_OUT - 6))), PATH - 27.2, PATH - 23.5))
    return f

def tie_bar():
    """Ties the front and back walls together at the start of each module (x 0..4), under the floor, and
    bridges the floor across the joint (top plate flush with the doors, x -5..5) so a card's leading edge can't
    dip into a gap. M3 screws come in through both walls into heat-set inserts in the bar ends. The front looms
    (bin-level sensor, beam receiver) cross to the back along its -X face: zip ties through the 3 slot pairs."""
    t = box(0, 4, -(WALL_IN - 0.2), WALL_IN - 0.2, PATH - 22, PATH - 13)
    for s in (-1, 1):   # the ends thicken to 7 mm round the inserts (a 4.7 mm insert hole in 4 mm broke out)
        t = t.union(box(0, TIE_X * 2, *sorted((s * 40.2, s * (WALL_IN - 0.2))), PATH - 22, PATH - 13))
    t = t.union(box(0, 4, -32.8, 32.8, PATH - 13, PATH - 2.4)).union(box(-5, 5, -FLOOR_W, FLOOR_W, PATH - 2.4, PATH))
    t = t.cut(fin_groove(-6, 6, GROOVE_Y1))
    for s in (-1, 1):
        t = t.cut(cyl_y(TIE_X, PATH - 17.5, M3_INSERT / 2, *sorted((s * (WALL_IN - 7), s * WALL_IN))))
    for y in (-30.0, 0.0, 30.0):
        for z in (PATH - 20.5, PATH - 14.5):
            t = t.cut(box(-1, 5, y - 2.0, y + 2.0, z - 0.8, z + 0.8))
    return t

BACK_PANEL = (2.0, PITCH - 2.0, CHAN_Z1, PATH - 27.0)   # x0, x1, z0, z1 on the outside of a bin module's back wall

def back_panel(hub=False):
    """Covers the window in a bin module's back wall (4 x M3 x 8 into the wall's inserts): it hides the wiring and
    looks finished. The one on bin module 2 carries the BIN HUB on its inside face, through the window: PCA9685
    servo board (4 x M2 x 8 self-tapping into the bosses), MCP23017 beam inputs, 2 x TCA9548A I2C switches for
    the bin-level sensors and the 3.3 V regulator (foam tape on the pads, a zip tie over each through the slots).
    Its bottom edge sits on the back wire channel; the looms come up out of the channel into the window."""
    x0, x1, z0, z1 = BACK_PANEL
    p = box(x0, x1, WALL_OUT, WALL_OUT + 3.0, z0, z1)
    for xh in (6.5, PITCH - 6.5):
        for zh in (RAIL_Z + 42.0, PATH - 44.0):
            p = p.cut(cyl_y(xh, zh, M3 / 2, WALL_OUT - 1, WALL_OUT + 4))
    for zv in range(int(z0) + 14, int(z1) - 10, 8):                       # a few vents (the regulator gets warm)
        p = p.cut(box(x1 - 14, x1 - 6, WALL_OUT - 1, WALL_OUT + 4, zv, zv + 3))
    if hub:
        for (bx, bz, bw, bh) in HUB_BOARDS.values():
            pad = box(bx, bx + bw, WALL_IN + 0.6, WALL_OUT + 0.01, bz, bz + bh)   # pads come in through the window
            p = p.union(pad)
            for zt in (bz + 3.0, bz + bh - 3.0):                          # zip-tie slots
                p = p.cut(box(bx - 4.0, bx - 1.0, WALL_IN, WALL_OUT + 4, zt - 1.0, zt + 1.0)).cut(
                          box(bx + bw + 1.0, bx + bw + 4.0, WALL_IN, WALL_OUT + 4, zt - 1.0, zt + 1.0))
        bx, bz, bw, bh = HUB_BOARDS["pca9685"]
        for dx in (3.3, 3.3 + 55.9):
            for dz in (3.15, 3.15 + 19.1):
                p = p.union(cyl_y(bx + dx, bz + dz, 3.0, WALL_IN - 4.0, WALL_IN + 0.7)).cut(cyl_y(bx + dx, bz + dz, PILOT_M2 / 2, WALL_IN - 5, WALL_IN + 0.5))
    return p

# hub boards on the back panel (x, z, width, height), all inside the window (x 12..110, z 40..165)
HUB_BOARDS = {"pca9685": (16.0, 58.0, 62.5, 25.4), "reg_3v3": (86.0, 58.0, 14.0, 12.0), "mcp23017": (16.0, 87.0, 55.0, 21.0),
              "tca9548a_1": (22.0, 111.0, 32.0, 21.0), "tca9548a_2": (64.0, 111.0, 32.0, 21.0)}
# (all inside the window, under its roof; PCA9685 on 4 bosses, the rest on foam tape + a zip tie)

def bin_box(height=135.0, depth=76.0):
    """Removable bin: outside 98 x 76 mm, inside 94 x 72 mm (3.7 x 2.8 in), 135 mm (5.3 in) tall: ~400 raw cards.
    Front lip doubles as the drawer front; the final shell adds a flush face."""
    W, D, H = 98.0, depth, height
    b = box(-W / 2, W / 2, -D / 2, D / 2, 0, H).edges("|Z").fillet(3)
    b = b.cut(box(-W / 2 + 2, W / 2 - 2, -D / 2 + 2, D / 2 - 2, 2, H + 1).edges("|Z").fillet(1))
    b = b.union(box(-W / 2, W / 2, -D / 2 - 3, -D / 2, 0, 18))                 # pull lip
    # open front: a big window leaves an 11 mm frame so the flat-lying cards (88 mm long) can't slide out
    b = b.cut(box(-W / 2 + 11, W / 2 - 11, -D / 2 - 4, -D / 2 + 2.1, 20, H - 12).edges("|Y").fillet(6))
    # fill marks on the left frame: one every 100 raw cards (30.5 mm / 1.2 in)
    for k in range(1, 5):
        z = 2 + 30.5 * k
        if z < H - 14:
            b = b.cut(box(-W / 2 + 3, -W / 2 + 10, -D / 2 - 0.1, -D / 2 + 0.6, z - 0.6, z + 0.6))
    return b

END_X0 = BIN_X[-2] + PITCH / 2                        # end module starts here
END_L = END_SHAFT_X - END_X0 + 21.5   # end module length (133.5): shaft 21.5 from its end (room round the motor inserts)

def end_side(side):
    """End module side: END_L long so the end-of-line bin sits fully under it and the drive shaft has room;
    carries the track drive shaft and motor. There's no floor here: cards are pushed off the end of the last door."""
    x0, x1 = 0.0, END_L
    # back: the ramp flange sits under the strip, so no gusset over it (tree supports under that stretch of strip)
    notch = [(-0.1, 2 * TIE_X + 0.6)] + ([(5.5, 118.0)] if side > 0 else [])
    f = side_frame(x0, x1, side, bin_opening=False, rails=False, bay=(side < 0), top_inserts=(), bosses=(x0 + 8,),
                   gusset_notches=notch)
    s = side
    xs = END_SHAFT_X - END_X0                            # drive shaft position in this module (112)
    f = f.cut((tear_y if s > 0 else cyl_y)(xs, PUL_Z, 2.75, -WALL_OUT - 1, WALL_OUT + 1))   # back prints upright: teardrops
    yb0, yb1 = sorted((s * (WALL_OUT - 5.2), s * (WALL_OUT + 0.1)))
    f = f.cut((tear_y if s > 0 else cyl_y)(xs, PUL_Z, SEAT_625 / 2, yb0, yb1))   # 625 bearing seat (outer face)
    f = f.cut(box(xs - 20, END_L + 1, *sorted((s * 35.0, s * WALL_IN_UP)), PATH, WALL_TOP + 1))  # room for pulley + fins
    if s > 0:   # ramp flange screws into the underside of the back strip
        for xh in (RAMP_X0 + 15, PITCH - 5.0 - 15):
            f = f.cut(cyl_z(xh, 41.0, M3_INSERT / 2, PATH - 12.5, PATH - 5))
    if s > 0:   # track motor on a 30 mm standoff on the back wall, screws into inserts
        for dx in (-1, 1):
            for dz in (-1, 1):
                f = f.cut(cyl_y(xs + dx * NEMA_HOLES / 2, PUL_Z + dz * NEMA_HOLES / 2, M3_INSERT / 2, WALL_OUT - 6.5, WALL_OUT + 1))
    if s > 0:
        f = f.cut(back_window(x0, x1, s, xb=x1 - 12, zr=103.0))
    # end cap: 2 inserts in each wall's end face (below the floor and above it, clear of the motor standoff's)
    for (yc, zc) in END_CAP_PTS:
        f = f.cut(cyl_x(s * yc, zc, M3_INSERT / 2, x1 - 6.5, x1 + 1))
    return f

END_CAP_PTS = (((WALL_IN + WALL_OUT) / 2, PATH - 30), ((WALL_IN + WALL_OUT) / 2, PATH - 5))   # end-cap screws (|Y|, Z): both below the floor, in the 8 mm wall
RAMP_X0 = 2 * TIE_X + 0.5          # end ramp starts just past the tie bar's insert bosses

def end_ramp():
    """Fixed ramp in the end module, the same plane as an open door (60 deg): cards pushed off the end of the
    track land on it and slide off its low edge into a standard bin, exactly like the other bins. A flange
    along the top screws up into the back strip (2 x M3 into heat-set inserts); two ribs underneath stiffen it.
    Module coordinates (x 0..PITCH)."""
    x0, x1 = RAMP_X0, PITCH - 5.0
    W, T = 2 * FLOOR_W, 3.0
    pl = box(x0, x1, -W / 2, W / 2, PATH - T, PATH)
    for xr in (x0 + 20, x1 - 20):
        pl = pl.union(box(xr - 1.5, xr + 1.5, -W / 2 + 6, W / 2, PATH - T - 6, PATH - T))
    pl = pl.rotate((0, HINGE_Y, HINGE_Z), (1, HINGE_Y, HINGE_Z), DOOR_OPEN)
    pl = pl.cut(box(-1, PITCH + 1, -60, 60, PATH - 4.0, PATH + 10))       # top trimmed flat, 4 mm under the floor line
    pl = pl.cut(box(-1, PITCH + 1, STRIP_IN - 0.5, 60, PATH - 12.5, PATH + 10))   # and clear of the back strip
    fl = box(x0, x1, 30.0, WALL_IN - 0.5, PATH - 16, PATH - 12.2)           # flange under the back strip
    for xh in (x0 + 15, x1 - 15):
        fl = fl.cut(cyl_z(xh, 41.0, M3 / 2, PATH - 17, PATH - 12))
    return pl.union(fl)

def print_skin_end_front():
    """0.2 mm sacrificial layer (STL only, not the assembly model): the front end wall prints on its outer face, so the
    5.5 mm shaft hole starts in mid-air above the 16.3 mm bearing seat. One layer across it lets the printer bridge
    first and lay a flat bearing shoulder on top; it's cut out after printing."""
    ys = -(WALL_OUT - 5.2)
    return cyl_y(END_SHAFT_X - END_X0, PUL_Z, 2.75 + 0.05, ys, ys + 0.2)

def end_cap():
    """Closes the end of the track above the last bin (catches cards that overshoot) and ties the two end walls
    together at the far end: 4 x M3 x 8 into the inserts in the walls' end faces."""
    c = box(0, 4, -(WALL_OUT - 1), WALL_OUT - 1, PATH - 60, WALL_TOP)   # stops 1 mm short of the motor standoff
    c = c.cut(box(-1, 5, -36, 36, PATH - 60, PATH - 10))
    for sg in (-1, 1):
        for (yc, zc) in END_CAP_PTS:
            c = c.cut(cyl_x(sg * yc, zc, M3 / 2, -1, 5))
    return c

def joint_plate():
    """Ties two modules' walls together at the joint (outside face, Z PATH-25): 2 x M3 x 8 into the outer-face
    inserts 8 mm either side of the joint. Lines the walls up and carries the front walls' free ends (the front
    walls of the bin modules stop above the bins). Frame: joint at x 0, against the wall face at y 0, out to +y."""
    p = box(-14, 14, 0, 3, -7, 7)
    for x in (-8, 8):
        p = p.cut(cyl_y(x, 0, M3 / 2, -1, 4))
    return p

# ============================================================================ ELECTRONICS, POWER, SCREEN
PSU_SCREW_Z = (RAIL_Z + 20.0, RAIL_Z + 115.0)   # cradle screws: front wall low, back wall above the inlet plate
PSU_Y = (-40.0, -10.0)                          # PSU on its side, toward the front: room behind it for the IEC inlet
SKR_Y0 = -28.0   # SKR Pico board's front edge on the tray (plugs reach 25 mm past it: -53, inside the -56 wall)

def electronics_tray():
    """Slides into the feeder base under the hopper through the front window (122 mm wide, window 126) and rests on
    the two ledges; 2 x M3 x 8 into the ledge inserts at the front corners hold it. SKR Pico (same 58 x 49 mm pattern
    as a Pi) at the front on 8 mm bosses, 4 x M2 x 8 self-tapping (M2 through its 2.7 mm holes), set 22 mm back from
    the window so its front plugs and their bends stay inside the base; a 10 mm grid of M3 holes and zip-tie slots
    for the looms. Tray frame: x 0 = world X 14, y = world Y, z 0 = tray underside."""
    T = 3.0
    W = TRAY_X[1] - TRAY_X[0]
    t = box(0, W, -54, 54, 0, T)
    for dx in (0, 58):
        for dy in (0, 49):
            xh, yh = SKR_X - TRAY_X[0] + dx, SKR_Y0 + 3.5 + dy
            t = t.union(cyl_z(xh, yh, 3, T, T + 8))
            t = t.cut(cyl_z(xh, yh, PILOT_M2 / 2, T, T + 9))
    for x in range(80, 111, 10):
        for y in range(10, 41, 10):
            t = t.cut(cyl_z(x, y, 1.7, -1, T + 1))
    for x in range(10, 61, 10):
        for y in (40,):
            t = t.cut(cyl_z(x, y, 1.7, -1, T + 1))
    for x in range(12, 105, 20):
        for y in (-50.5, 50.5):
            t = t.cut(box(x, x + 3, y - 1.5, y + 1.5, -1, T + 1))
    for x in TRAY_SCREW_X:
        t = t.cut(cyl_z(x - TRAY_X[0], TRAY_SCREW_Y, M3 / 2, -1, T + 1))
    return t

def bay_cover():
    """Front cover of the electronics bay, the full width of the base: vent slots + a 30 mm fan. 4 x M3 x 8 into the
    base's inserts (X 7 / 143, Z 50 / 110). Starts 6 mm above the foot so the front rail screws' heads clear it.
    Frame: x 0 = world X 0, z 0 = world Z 32; outer face at y 0, wall side at y 3."""
    c = box(0, 150, 0, 3, 0, 89)
    for z in range(10, 78, 7):
        c = c.cut(box(27, 87, -1, 4, z, z + 3.5))
    c = c.cut(cyl_y(123, 24, 14, -1, 4))
    for dx in (-12, 12):
        for dz in (-12, 12):
            c = c.cut(cyl_y(123 + dx, 24 + dz, M3 / 2, -1, 4))       # fan: M3 x 12 through the cover into the fan frame
    for (x, z) in ((7, 18), (143, 18), (7, 78), (143, 78)):
        c = c.cut(cyl_y(x, z, M3 / 2, -1, 4))
    c = c.cut(box(118, 140, -1, 4, 68, 80))                               # USB-C + the Pi's jumper loom (plugs pass through)
    return c

def psu_cradle():
    """Two of these hold the Mean Well LRS-100-24 on its side under the scanner, toward the front (the IEC inlet's
    body needs the room behind it). A U across the module between the walls: the PSU drops in from above (scan floor
    out) and a zip tie through the two slots goes over it. Each end is held by an M3 x 12 from OUTSIDE the wall into a
    captive M3 nut in the end tab (drop the nut into its slot from the top): front end low, back end above the inlet
    plate (the back wire channel covers the wall lower down). Frame: x 0..18 along the PSU, world Y and Z."""
    yi = WALL_IN - 0.2
    c = box(0, 18, -yi, yi, RAIL_Z + 1, RAIL_Z + 6)                                   # base under the PSU
    c = c.union(box(0, 18, -yi, PSU_Y[0] - 1.8, RAIL_Z + 1, PSU_SCREW_Z[0] + 10))      # front tab (also the front upright)
    c = c.union(box(0, 18, PSU_Y[1] + 1.5, PSU_Y[1] + 4.5, RAIL_Z + 6, RAIL_Z + 40))    # back upright
    c = c.union(box(0, 18, 40.0, yi, RAIL_Z + 1, PSU_SCREW_Z[1] + 8))                  # back tab
    c = c.union(box(0, 18, PSU_Y[1] + 4.5, 40.0, RAIL_Z + 1, RAIL_Z + 9))              # stiffener along the base
    for (y0, y1, zc) in ((-yi, PSU_Y[0] - 1.8, PSU_SCREW_Z[0]), (40.0, yi, PSU_SCREW_Z[1])):
        ys = -1 if y0 < 0 else 1
        c = c.cut(cyl_y(9, zc, M3 / 2, y0 - 1, y1 + 1))
        yn0, yn1 = (y0 + 1.0, y0 + 3.6) if ys < 0 else (y1 - 3.6, y1 - 1.0)            # nut slot (wall side), open at the top
        c = c.cut(box(9 - 3.0, 9 + 3.0, yn0, yn1, zc - 3.2, 999))
    for (y0, y1) in ((PSU_Y[0] - 1.8, PSU_Y[0]), (PSU_Y[1], PSU_Y[1] + 1.5)):            # zip-tie slots either side of the PSU
        c = c.cut(box(7, 11, y0, y1, RAIL_Z, RAIL_Z + 10))
    return c

def inlet_plate():
    """Covers the window in the scan module's back wall: fused, switched IEC C14 inlet (snap-in,
    27.5 x 47.5 mm cutout) and a grommet hole for the Ethernet/USB cable. 4 x M3 x 8 into the wall's inserts. The
    snap-in inlet's clips only grip a 1-2.5 mm panel, so the plate is thinned to 2.5 mm round the cutout (a pocket on
    the wall side, over the wall's window). Prints outer face down."""
    p = box(0, 116, 0, 4, 0, 68)
    p = p.cut(box(10, 18 + 47.5, -1, 1.5, 16, 24 + 27.5))
    p = p.cut(box(14, 14 + 47.5, -1, 5, 20, 20 + 27.5))
    p = p.cut(cyl_y(92, 34, 9, -1, 5))
    for x in (4, 112):
        for z in (4, 64):
            p = p.cut(cyl_y(x, z, M3 / 2, -1, 5))
    return p

def channel_cover():
    """Snap-on cover for the wire channel on the side walls (one per module side, one pitch long)."""
    h = CHAN_Z1 - CHAN_Z0
    c = box(0, 104, 0, 1.6, 0, h)
    c = c.union(box(0, 104, 0, 4, 0, 1.6)).union(box(0, 104, 0, 4, h - 1.6, h))
    return c

SCREEN_W, SCREEN_H, SCREEN_T = 189.5, 120.0, 16.0   # Raspberry Pi Touch Display 2: 189.5 x 120 x 15 mm

# ---- GoPro-style mount system: the screen clips onto any mount point with an M5 thumbscrew, and standard
# GoPro extension arms fit between them. Prongs 3.0 mm thick, 3.3 mm gaps, 15 mm round ends, 5.3 mm hole.
GP_T, GP_G, GP_R, GP_HOLE = 3.0, 3.3, 7.5, 5.3

def gopro(prongs, axis_z, base_w=24.0, base_t=4.0):
    """Prongs standing up from z=0 along +Z, pivot axis along X at height axis_z. prongs = 3 (base) or 2 (device)."""
    if prongs == 3:
        xs = [-(GP_T + GP_G), 0.0, GP_T + GP_G]
    else:
        xs = [-(GP_T + GP_G) / 2, (GP_T + GP_G) / 2]
    m = box(-base_w / 2, base_w / 2, -GP_R - 2, GP_R + 2, -base_t, 0)
    for x in xs:
        fin_ = box(x - GP_T / 2, x + GP_T / 2, -GP_R, GP_R, 0, axis_z)
        fin_ = fin_.union(cyl_x(0, axis_z, GP_R, x - GP_T / 2, x + GP_T / 2))
        m = m.union(fin_)
    return m.cut(cyl_x(0, axis_z, GP_HOLE / 2, -20, 20))

def mount_roof():
    """Screen mount point on the hood roof (front edge). 2 x M3."""
    m = gopro(3, 14, base_w=60)
    for x in (-24, 24):
        m = m.cut(cyl_z(x, 0, M3 / 2, -5, 1))
    return m

def mount_wall():
    """Screen wall bracket: flat on the scan module's front wall, 2 x M3 x 8 into its two inserts (89 mm apart,
    slots allow +-2.7 mm)."""
    m = box(-52, 52, 0, 5, -10, 10)
    for x in (-44.5, 44.5):
        m = m.cut(cq.Workplane("XZ").center(x, 0).slot2D(9, M3, 0).extrude(-6))
    g = gopro(3, 14, base_w=26).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, 5, 0))
    return m.union(g)

def mount_front():
    """Screen mount on the front of the hood (default spot, close to the Pi so the 500 mm display ribbon reaches
    over the roof): 2 x M3 x 10 into the hood's front pads. Also fits the electronics bay front (two of the
    bay cover screws, same 116 mm spacing) if the screen ever goes back down there."""
    m = box(-62, 62, -4, 0, -8, 8)
    for x in (-63 + 5, 63 - 5):
        m = m.cut(cyl_y(x, 0, M3 / 2, -5, 1))
    g = gopro(3, 14, base_w=26).rotate((0, 0, 0), (1, 0, 0), 90).translate((0, -4, 0))
    return m.union(g)

def gopro_arm(length=90.0):
    """Printed extension arm: 2 prongs one end, 3 prongs the other (same as a GoPro arm)."""
    a = box(-7.8, 7.8, -4, 4, 0, length)
    a = a.union(gopro(2, 10, base_w=10, base_t=0.01).translate((0, 0, length)))
    a = a.union(gopro(3, 10, base_w=16, base_t=0.01).rotate((0, 0, 0), (1, 0, 0), 180))
    return a

# ---- touchscreen block: Touch Display 2 with the Pi 5 screwed to its back (the display ribbon is short, so they
# stay together). Mounted landscape with the Pi's port edge UP: the camera ribbon leaves the Pi's CAM/DISP 0 port
# straight up, lies flat on the back of the screen, curves over to the hood and goes in through the front-wall slot
# to the camera. Bends only, no twist. (Turn the picture with screen-rotate.sh to suit.)
# Cradle frame: display back face on y = 0 (front face y = -15, toward the user), bottom edge z = 0, centre x = 0.
PI_ON_SCREEN_Z = 32.0    # Pi centred on the display back (measured): its GPIO edge 32 mm above the display edge
PI_STACK = 29.0          # display back to the top of the Pi's cooler
CAM_PORT_X = 18.0        # camera port centre from the screen centre, toward the Pi's USB/Ethernet end (measured off
                         # photos, ~0.7 in): the screen sits that far off-centre so the ribbon lines up with the camera
POD_STANDOFF = 34.0      # GoPro tab stands this far off the pod's back (clears the module walls when tilted)
POD_PIV_W = (MOUNT_X, -WALL_OUT - 5 - 14, PATH - 21)   # pivot on the wall mount's prongs (mount flat on the scan front wall)
POD_D = 40.0             # screen pod depth behind the display: Pi stack 29 + 6 mm air over the fan + 3 mm wall
SCR_PIV = (0.0, POD_D + POD_STANDOFF + 12.0, 12.0)   # GoPro pivot in the cradle frame: low on the pod's back
CONV_L, CONV_W, CONV_T, CONV_EARS = 48.0, 34.0, 14.0, 55.0   # 24 V -> 5 V USB-C converter (measured), ear slots 55 apart
CONV_X, CONV_Z = -68.0, 60.0   # 5 V USB-C converter in the pod, beside the Pi's USB-C end
USBC_X = -31.0                 # Pi's USB-C port, from the screen centre (port edge up, at the GPIO end)
RIB_EXIT_Z = PI_ON_SCREEN_Z + 56 + 10   # camera ribbon leaves the pod's back just above the Pi

POD_DX = RIB_X - POD_PIV_W[0] - CAM_PORT_X   # pod sits this far right of its mount so the camera port lines up

def screen_xf(x, y, z):
    """A point in the cradle frame -> machine coordinates (pivot on mount_wall_gap's prongs, tilted back)."""
    t = math.radians(-SCREEN_TILT)
    yr, zr = y - SCR_PIV[1], z - SCR_PIV[2]
    return (POD_PIV_W[0] + POD_DX + x, POD_PIV_W[1] + yr * math.cos(t) - zr * math.sin(t), POD_PIV_W[2] + yr * math.sin(t) + zr * math.cos(t))

def screen_placed(shape):
    """Puts a shape from the cradle frame into the machine: the pod sits in front of the gap between the hopper
    tower and the hood, on the wall mount, tilted back."""
    return (shape.translate((0, -SCR_PIV[1], -SCR_PIV[2])).rotate((0, 0, 0), (1, 0, 0), -SCREEN_TILT)
            .translate((POD_PIV_W[0] + POD_DX, POD_PIV_W[1], POD_PIV_W[2])))

def screen_block():
    """Display + Pi 5 + Active Cooler envelope, cradle frame (render and fit check)."""
    d = box(-SCREEN_W / 2, SCREEN_W / 2, -SCREEN_T, 0, 0, SCREEN_H)
    return d.union(box(-42.5, 42.5, 0, PI_STACK, PI_ON_SCREEN_Z, PI_ON_SCREEN_Z + 56))

def _tube(pts, ow, iw, so=1.3, si=1.2):
    """Closed square duct (outer ow, inner iw) along a 3-D polyline, rounded joints. Roomy inside so the ribbon can
    roll gently through 90 deg on the way."""
    outer = inner = None
    for a, b in zip(pts, pts[1:]):
        d = cq.Vector(b) - cq.Vector(a); L = d.Length; d = d.normalized()
        def seg(w, extra):
            s_ = box(-w / 2, w / 2, -w / 2, w / 2, -extra, L + extra)
            ax = cq.Vector(0, 0, 1).cross(d)
            if ax.Length > 1e-6:
                s_ = s_.rotate((0, 0, 0), ax.toTuple(), math.degrees(math.acos(max(-1, min(1, d.z)))))
            elif d.z < 0:
                s_ = s_.rotate((0, 0, 0), (1, 0, 0), 180)
            return s_.translate(a)
        o, i = seg(ow, 0), seg(iw, 0.5)
        outer = o if outer is None else outer.union(o)
        inner = i if inner is None else inner.union(i)
    for p in pts[1:-1]:
        outer = outer.union(cq.Workplane("XY").sphere(ow / 2 * so).translate(p))
        inner = inner.union(cq.Workplane("XY").sphere(iw / 2 * si).translate(p))
    return outer.cut(inner)

def _hollow_path(pts, ow, ot, iw, it):
    """A closed rectangular duct along a polyline in a YZ plane (all points share x): outer ow x ot, inner iw x it.
    Width along X, thickness across the path. Rounded at the bends."""
    x = pts[0][0]
    outer = inner = None
    for (xa, ya, za), (xb, yb, zb) in zip(pts, pts[1:]):
        L = math.hypot(yb - ya, zb - za); ang = math.degrees(math.atan2(zb - za, yb - ya))
        o = box(x - ow / 2, x + ow / 2, 0, L, -ot / 2, ot / 2).rotate((0, 0, 0), (1, 0, 0), ang).translate((0, ya, za))
        i = box(x - iw / 2, x + iw / 2, -1, L + 1, -it / 2, it / 2).rotate((0, 0, 0), (1, 0, 0), ang).translate((0, ya, za))
        outer = o if outer is None else outer.union(o)
        inner = i if inner is None else inner.union(i)
    for (_, y, z) in pts[1:-1]:
        outer = outer.union(cyl_x(y, z, ot / 2, x - ow / 2, x + ow / 2))
        inner = inner.union(cyl_x(y, z, it / 2, x - iw / 2, x + iw / 2))
    return outer.cut(inner)

def screen_cradle():
    """Front frame of the screen pod: lips round the glass, side rails, back lips; open at the back. Four ears with
    M3 inserts take the pod cover. Prints face down."""
    W, H, T = SCREEN_W + 0.8, SCREEN_H + 0.8, 3.0
    x0, x1, z0, z1 = -W / 2, W / 2, -0.4, H - 0.4
    c = box(x0 - T, x1 + T, -SCREEN_T - 2, T, z0 - T, z1 + T)
    c = c.cut(box(x0, x1, -SCREEN_T - 0.4, 0.4, z0, z1))                          # the display drops in
    c = c.cut(box(x0 + 5, x1 - 5, -SCREEN_T - 3, -SCREEN_T, z0 + 5, z1 - 5))       # front: 5 mm lips round the glass
    c = c.cut(box(x0 + 7, x1 - 7, -1, T + 1, z0 + 7, z1 - 7))                       # back: open
    for sx in (-1, 1):
        for zc in (z0 + 15, z1 - 15):
            xe0, xe1 = sorted((sx * (x1 + T), sx * (x1 + T + 9)))
            c = c.union(box(xe0, xe1, -8, T, zc - 6, zc + 6))
            c = c.cut(cyl_y(sx * (x1 + T + 4.5), zc, M3_INSERT / 2, -9, T + 1))
    return c

def pod_cover():
    """Back of the screen pod: hides the Pi, its 5 V USB-C converter (on 2 M3 inserts beside the Pi) and the cable
    ends. Vents over the Pi's fan and beside the converter. The camera ribbon leaves through a slot in the back just
    above the Pi; one bundle (the converter's 24 V pair + the Pi's jumper loom) leaves through the notch at the
    bottom and hangs free down into the electronics bay. GoPro tab on a standoff low on the back."""
    W, H, T, w = SCREEN_W + 0.8, SCREEN_H + 0.8, 3.0, 2.5
    x0, x1, z0, z1 = -W / 2 - T, W / 2 + T, -0.4 - T, H - 0.4 + T
    c = box(x0, x1, T, POD_D, z0, z1).cut(box(x0 + w, x1 - w, T - 1, POD_D - w, z0 + w, z1 - w))
    for sx in (-1, 1):                                                       # ears over the frame's ears
        for zc in (-0.4 + 15, H - 0.4 - 15):
            # 45 degree gusset under each ear (the cover prints back face down, so the ears are its top 5 mm)
            ear = (cq.Workplane("XY").polyline([(sx * x1, T), (sx * (x1 + 9), T), (sx * (x1 + 9), T + 5), (sx * x1, T + 14)])
                   .close().extrude(12).translate((0, 0, zc - 6)))
            c = c.union(ear)
            c = c.cut(cyl_y(sx * (x1 + 4.5), zc, M3 / 2, T - 1, T + 6))
            c = c.cut(cyl_y(sx * (x1 + 4.5), zc, 3.4, T + 5, T + 20))       # head pocket down through the gusset
    for xv in range(-32, 33, 8):                                             # fan / board vents
        c = c.cut(box(xv - 2, xv + 2, POD_D - w - 1, POD_D + 1, PI_ON_SCREEN_Z + 6, PI_ON_SCREEN_Z + 50))
    c = c.cut(box(CAM_PORT_X - 11, CAM_PORT_X + 11, POD_D - w - 1, POD_D + 1, RIB_EXIT_Z - 2.5, RIB_EXIT_Z + 2.5))
    c = c.cut(box(USBC_X - 11, USBC_X + 11, POD_D - w - 1, POD_D + 1, z0 - 1, z0 + w + 12))   # USB-C + GPIO loom notch
    for zv in range(20, 101, 10):                                            # converter vents (side wall)
        c = c.cut(box(x0 - 1, x0 + w + 1, 12, 30, zv, zv + 4))
    for dz in (-CONV_EARS / 2, CONV_EARS / 2):                               # 5 V converter bosses (M3 inserts)
        c = c.union(cyl_y(CONV_X, CONV_Z + dz, 4.5, POD_D - w - 6, POD_D - w + 0.1))
        c = c.cut(cyl_y(CONV_X, CONV_Z + dz, M3_INSERT / 2, POD_D - w - 7, POD_D - w - 1))
    # GoPro standoff is its own part (pod_standoff): 2 x M3 x 12 from inside the pod, through a 2 mm pad on the back
    # wall, into inserts in the standoff. That keeps the cover's back face flat on the bed (no 50 mm of supports).
    c = c.union(box(-POD_DX - 17, -POD_DX + 17, POD_D - w - POD_PAD, POD_D - w + 0.1, SCR_PIV[2] - GP_R, SCR_PIV[2] + 9.5))
    for dx in POD_SCREW_DX:
        c = c.cut(cyl_y(-POD_DX + dx, SCR_PIV[2], M3 / 2, POD_D - w - POD_PAD - 1, POD_D + 1))
    return c

POD_PAD = 2.0                    # extra back-wall thickness under the standoff screws
POD_SCREW_DX = (-10.0, 10.0)     # standoff screws either side of the GoPro tab's centre line

def pod_standoff():
    """GoPro tab on a 34 mm standoff behind the screen pod (carries the whole pod). Two M3 heat-set inserts in its
    pod face. Prints standing on its flat bottom (cradle -Z): layers run along the standoff, the strong way, and
    the tab's prongs stand up as plain walls - no supports."""
    c = box(-POD_DX - 17, -POD_DX + 17, POD_D, POD_D + POD_STANDOFF, SCR_PIV[2] - GP_R, SCR_PIV[2] + 9.5)
    tab = gopro(2, 12, base_w=30, base_t=0.01).rotate((0, 0, 0), (1, 0, 0), -90).translate((-POD_DX, POD_D + POD_STANDOFF, SCR_PIV[2]))
    c = c.union(tab).cut(box(-60, 60, POD_D - 1, POD_D + 80, -40, SCR_PIV[2] - GP_R))   # flat bottom: the tab's base trimmed to the prongs
    yf = POD_D + POD_STANDOFF                       # 1.5 mm fillets where the prongs meet the block (no sharp inside corner
    c = c.edges("|Z").edges(cq.selectors.BoxSelector((-50, yf - 0.05, -50), (80, yf + 0.05, 80))).fillet(1.5)   # under load)
    for dx in POD_SCREW_DX:
        c = c.cut(cyl_y(-POD_DX + dx, SCR_PIV[2], M3_INSERT / 2, POD_D - 1, POD_D + 6.0))
        c = c.cut(cyl_y(-POD_DX + dx, SCR_PIV[2], M3 / 2, POD_D, POD_D + 10.0))
    return c

def converter_block():
    """The 24 V -> 5 V USB-C converter on its bosses inside the pod (body + ears), cradle frame."""
    yb = POD_D - 2.5 - 6
    b = box(CONV_X - CONV_W / 2, CONV_X + CONV_W / 2, yb - CONV_T, yb, CONV_Z - CONV_L / 2, CONV_Z + CONV_L / 2)
    return b.union(box(CONV_X - 6, CONV_X + 6, yb - 2, yb, CONV_Z - CONV_L / 2 - 7, CONV_Z + CONV_L / 2 + 7))

def _ribbon_points():
    """Centre-line corners of the camera ribbon and the direction of its width at each one."""
    x, zt = RIB_X, RIB_CONN_Z
    X, Y = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    pts = [(screen_xf(CAM_PORT_X, 12.5, PI_ON_SCREEN_Z + 56), X), (screen_xf(CAM_PORT_X, 12.5, RIB_EXIT_Z), X),
           (screen_xf(CAM_PORT_X, POD_D + 2, RIB_EXIT_Z), X), ((x, -16.0, RIB_RUN_Z), X),
           ((x, 0.0, RIB_TWIST_Z[0]), X), ((x, 0.0, RIB_TWIST_Z[1]), Y), ((x, 0.0, zt - 14), Y),
           ((x + 14, 0.0, zt), Y), ((SCAN_X - 19, 0.0, zt), Y)]
    return pts

def ribbon_strip(step=1.0, radius=12.0, thick=0.6, width=16.0):
    """The ribbon as one continuous strip: corners rounded to `radius`, width direction blended smoothly (the twist).
    Returns (vertices Nx3, triangles Mx3) for an STL; used for the pictures."""
    import numpy as np
    P = [np.array(p, float) for p, _ in _ribbon_points()]
    W = [np.array(w, float) for _, w in _ribbon_points()]
    # round each corner: replace it with a quadratic Bezier between points `radius` back and ahead
    cl, wl = [P[0]], [W[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        r = min(radius, np.linalg.norm(b - a) / 2, np.linalg.norm(c - b) / 2)
        p0 = b + (a - b) / np.linalg.norm(a - b) * r
        p2 = b + (c - b) / np.linalg.norm(c - b) * r
        for t in np.linspace(0, 1, 9):
            cl.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * b + t ** 2 * p2); wl.append(W[i])
    cl.append(P[-1]); wl.append(W[-1])
    # resample by arc length, blending the width direction where it changes (the twist segment)
    seg = [np.linalg.norm(cl[i + 1] - cl[i]) for i in range(len(cl) - 1)]
    s_ = np.concatenate([[0], np.cumsum(seg)]); n = int(s_[-1] / step) + 2
    ss = np.linspace(0, s_[-1], n)
    C = np.array([np.interp(ss, s_, [p[k] for p in cl]) for k in range(3)]).T
    Wv = np.array([np.interp(ss, s_, [w[k] for w in wl]) for k in range(3)]).T
    T = np.gradient(C, axis=0); T /= np.linalg.norm(T, axis=1)[:, None]
    Wv = Wv - T * (Wv * T).sum(1)[:, None]; Wv /= np.linalg.norm(Wv, axis=1)[:, None]
    N = np.cross(T, Wv)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    V = np.concatenate([C + Wv * sw * width / 2 + N * sn * thick / 2 for sw, sn in corners], axis=0)
    tris = []
    for i in range(n - 1):
        for k in range(4):
            a0, a1 = k * n + i, ((k + 1) % 4) * n + i
            tris += [(a0, a1, a1 + 1), (a0, a1 + 1, a0 + 1)]
    for e, flip in ((0, False), (n - 1, True)):
        q = [k * n + e for k in range(4)]
        tris += [(q[0], q[2], q[1]), (q[0], q[3], q[2])] if not flip else [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    return V, np.array(tris), float(s_[-1])

def write_stl(path, V, F):
    import numpy as np, struct
    with open(path, "wb") as f:
        f.write(b"\0" * 80); f.write(struct.pack("<I", len(F)))
        for a, b, c in F:
            n = np.cross(V[b] - V[a], V[c] - V[a]); ln = np.linalg.norm(n) or 1.0
            f.write(struct.pack("<12fH", *(n / ln), *V[a], *V[b], *V[c], 0))

def camera_ribbon():
    """The camera ribbon's path (fit check + length). Only bends across its width and one long, gentle twist:
    Pi port -> up inside the pod -> out the pod's back -> straight back across the gap just above the conveyor
    walls -> soft bend upward -> rises beside the hood, rolling 90 deg over ~64 mm until it lies flat against the
    hood's left wall -> under the L-rails -> rolls over through the slot -> straight into the camera's connector
    (camera turned so the connector faces left). Fit-check solid: straight pieces; picture: ribbon_strip()."""
    pts = [p for p, _ in _ribbon_points()]
    X, Y, XY = cq.Vector(1, 0, 0), cq.Vector(0, 1, 0), cq.Vector(1, 1, 0)
    widths = [X, X, X, X, XY, Y, Y, Y]
    shp, total = None, 0.0
    for (a, b), wd in zip(zip(pts, pts[1:]), widths):
        d = cq.Vector(b) - cq.Vector(a); L = d.Length; total += L; d = d.normalized()
        wd = (wd - d * wd.dot(d)).normalized()
        s_ = cq.Workplane(cq.Plane(origin=a, xDir=wd, normal=d)).box(16, 0.6, L, centered=(True, True, False))
        shp = s_ if shp is None else shp.union(s_)
    return shp, total + 6 * 6                                            # + the bends and folds

# ============================================================================ final-look shell (render / later print)
def shell_parts(length=660.0):
    """Outer skin for the finished look: one continuous body, smoked lid over the track, flush drawer fronts.
    Not needed for the prototype; panels clip onto the wall bosses."""
    parts = {}
    R = 10.0
    body = cq.Workplane("XY").box(length, 170, PATH - 10, centered=False).translate((-8, -85, 8)).edges("|X").fillet(R)
    body = body.cut(box(-20, length + 20, -78, 78, 8 + 3, PATH + 20))
    # drawer openings on the front face
    for xb in BIN_X:
        body = body.cut(box(xb - 50, xb + 50, -90, -78, 18, 160))
    parts["shell_body"] = body
    lid = cq.Workplane("XY").box(length - HOOD_X1 + 8, 150, 52, centered=False).translate((HOOD_X1, -75, PATH + 8)).edges("|X").fillet(8)
    lid = lid.cut(box(HOOD_X1 - 1, length + 10, -72, 72, PATH + 7, PATH + 57))
    parts["smoked_lid"] = lid
    hood_skin = cq.Workplane("XY").box(HOOD_X1 - HOOD_X0 + 10, 160, HOOD_H + 5, centered=False).translate((HOOD_X0 - 5, -80, PATH + 8)).edges("|Z or >Z").fillet(8)
    parts["hood_skin"] = hood_skin
    tower_skin = cq.Workplane("XY").box(130, 160, 200, centered=False).translate((-8, -80, PATH + 8)).edges("|Z or >Z").fillet(8)
    tower_skin = tower_skin.cut(box(TOWER_X0 - 3, TOWER_X0 + TOWER_IN_X + 3, -TOWER_IN_Y / 2 - 3, TOWER_IN_Y / 2 + 3, PATH, PATH + 230))
    parts["tower_skin"] = tower_skin
    fronts = []
    for xb in BIN_X:
        fronts.append(cq.Workplane("XY").box(99, 6, 141, centered=False).translate((xb - 49.5, -91, 19)).edges("|Y").fillet(4))
    parts["drawer_fronts"] = fronts
    return parts

# ============================================================================ catalogue
# name: (builder, material, note), and how many to print in each stage:
#   A = first test machine: 3 bins, raw cards (feeder, scanner, bin modules 1-2, end module)
#   B = the other 6 bins (bin modules 3-8 go in between module 2 and the end module; 2684 mm belts replace the 1220s)
#   C = the sleeved towers
PRINTED = {
    "fit_coupon":      (fit_coupon, "PETG", "PRINT FIRST (done). Hole sizes are tuned to it."),
    "feeder_base":     (feeder_base, "PETG", "v3. Upright, 15% gyroid, 4 walls, 5 top layers, ~19 h. Tree supports only under the card-clear sensor pocket."),
    "raw_tower":       (raw_tower, "PETG", "Upright, 3 walls. Magnet in position 1 (front), south pole down."),
    "single_tower":    (lambda: tower("single"), "PETG", "Single-sleeved cards (inside 92.5 x 67.5). Magnet in position 2 (back)."),
    "double_tower":    (lambda: tower("double"), "PETG", "Double-sleeved cards (inside 93.5 x 68.5). Magnets in both positions."),
    "gate_plate":      (gate_plate, "PETG", "v4 (reprint: the v3 gate can't be adjusted). On its outer (+X) face, no supports. 1 M3 insert in the top; 1.5 mm silicone pad under the foot. Fits all three towers."),
    "feed_roller":     (feed_roller, "PETG", "On its end, 100% infill. Three 16 ID x 3.5 O-rings."),
    "exit_roller":     (exit_roller, "PETG", "On its end, 100% infill. Two 16 ID x 3.5 O-rings each (one is the pressure roller)."),
    "pressure_bridge": (pressure_bridge, "PETG", "Beam down, no supports. 2 x M3 x 10 into the post-top inserts."),
    "stack_weight":    (stack_weight, "PLA", "Fill the pocket with about 50 g (2 oz) of coins or nuts."),
    "idler_slider":    (idler_slider, "PETG", "On its side, 100% infill. One M3 insert; print 2 (one mirrored in the slicer is not needed: it's symmetric)."),
    "joint_plate":     (joint_plate, "PETG", "Flat."),
    "fin":             (fin, "PETG", "Half of them mirrored. On its side, 0.12 mm layers. 3 x 3 mm silicone square in the face pocket."),
    "belt_drill_jig":  (belt_drill_jig, "PETG", "Ridges up."),
    "fin_gauge":       (fin_gauge, "PETG", "Flat."),
    "track_pulley_idler": (lambda: track_pulley(False), "PETG", "Axis vertical, 0.12 mm layers, 100% infill. 2 x 685ZZ each."),
    "track_pulley_drive": (lambda: track_pulley(True), "PETG", "Hub down, 0.12 mm layers, 100% infill. M3 nut + M3 x 4 grub."),
    "motor_standoff":  (motor_standoff, "PETG", "Rev H: stand it on its OPEN side (both plate edges on the bed): every wall is vertical, no bridges, no supports, 5 walls. The 2 printed on plate 1 (on a side wall) work as they are; the sag under their top wall is inside, cosmetic only."),
    "scan_side_front": (scan_side_front, "PETG", "UPRIGHT (foot down), 225 mm tall. No supports. Tall on a narrow foot: 8 mm brim + glue stick, long edge front-to-back on the bed (the Neptune's bed moves front-to-back), outer walls at 80 mm/s or less for the top half."),
    "scan_side_back":  (scan_side_back, "PETG", "UPRIGHT (foot down). Tree supports only under the strip over the belt-home sensor. Tall on a narrow foot: 8 mm brim + glue stick, long edge front-to-back on the bed (the Neptune's bed moves front-to-back), outer walls at 80 mm/s or less for the top half."),
    "scan_floor":      (scan_floor, "PLA matte green", "Top face DOWN on the smooth side of the plate."),
    "hood":            (hood, "PLA matte black", "Upright, tongue on top. Tree supports under the tunnel, pads and LED ledges."),
    "hood_lid":        (hood_lid, "PLA matte black", "Roof down, no supports."),
    "sheen_cap":       (sheen_cap, "PLA matte black", "Back face down. 50 mm piece of the COB strip inside."),
    "camera_plate":    (camera_plate, "PETG", "Tabs up. Camera connector faces LEFT (hopper side)."),
    "polarizer_cap":   (polarizer_cap, "PETG", "Open end up, no supports. Slip fit on the 30.00 mm lens; film disc goes in the seat at the bottom."),
    "bin_side_back":   (lambda: bin_module_side(1), "PETG", "UPRIGHT (foot down), 225 mm tall. Tree supports under the hinge knuckles only. Tall on a narrow foot: 8 mm brim + glue stick, long edge front-to-back on the bed (the Neptune's bed moves front-to-back), outer walls at 80 mm/s or less for the top half."),
    "bin_side_front":  (lambda: bin_module_side(-1), "PETG", "On its outer face (flat, 122 x 105). No supports."),
    "door":            (door, "PETG", "Top face DOWN on the smooth side, tree supports under the barrels and lever."),
    "servo_link":      (servo_link, "PETG", "Flat, 100% infill."),
    "tie_bar":         (tie_bar, "PETG", "Floor plate face DOWN on the smooth side."),
    "back_panel":      (back_panel, "PLA matte black", "Outside face down. Covers a bin module's back window."),
    "back_panel_hub":  (lambda: back_panel(hub=True), "PLA matte black", "Outside face down. Bin module 2's panel: carries the bin hub boards."),
    "bin":             (bin_box, "PLA", "Open side up, 2 walls, 10% infill. ~5 h each."),
    "end_side_front":  (lambda: end_side(-1).union(print_skin_end_front()), "PETG", "On its outer face (flat). No supports. A 0.2 mm skin closes the shaft hole at the bottom of the bearing seat (it gives the printer a bridge to start the hole on): cut it out with a hobby knife before pressing the 625 bearing in."),
    "end_side_back":   (lambda: end_side(1), "PETG", "UPRIGHT (foot down). Tree supports under the strip over the ramp flange. Tall on a narrow foot: 8 mm brim + glue stick, long edge front-to-back on the bed (the Neptune's bed moves front-to-back), outer walls at 80 mm/s or less for the top half."),
    "end_cap":         (end_cap, "PETG", ""),
    "end_ramp":        (end_ramp, "PETG", "Ramp face DOWN on the smooth side, tree supports under the flange."),
    "electronics_tray":(electronics_tray, "PETG", "Flat, bosses up."),
    "bay_cover":       (bay_cover, "PLA matte black", "Flat, outside face down."),
    "psu_cradle":      (psu_cradle, "PETG", "On its side (X face down). Two M3 nuts drop into the slots."),
    "inlet_plate":     (inlet_plate, "PETG", "Flat."),
    "screen_cradle":   (screen_cradle, "PETG", "Face down. 4 M3 inserts in the ears."),
    "pod_cover":       (pod_cover, "PLA matte black", "Back face down, no supports (the GoPro standoff is now a separate part)."),
    "pod_standoff":    (pod_standoff, "PETG", "Flat bottom down, prongs standing up, no supports, 5 walls. 2 M3 inserts in the pod face; 2 x M3 x 12 from inside the pod."),
    "mount_wall":      (mount_wall, "PETG", "Screen mount across the hopper/scanner gap on the front walls."),
}
STAGES = {   # name: (A, B, C)
    "fit_coupon": (1, 0, 0), "feeder_base": (1, 0, 0), "raw_tower": (1, 0, 0), "single_tower": (0, 0, 1), "double_tower": (0, 0, 1),
    "gate_plate": (1, 0, 0), "feed_roller": (1, 0, 0), "exit_roller": (2, 0, 0), "pressure_bridge": (1, 0, 0), "stack_weight": (1, 0, 0),
    "fin": (24, 24, 0), "belt_drill_jig": (1, 0, 0), "fin_gauge": (1, 0, 0), "track_pulley_idler": (2, 0, 0), "track_pulley_drive": (2, 0, 0),
    "motor_standoff": (2, 0, 0), "scan_side_front": (1, 0, 0), "scan_side_back": (1, 0, 0), "scan_floor": (1, 0, 0), "hood": (1, 0, 0),
    "hood_lid": (1, 0, 0), "sheen_cap": (1, 0, 0), "camera_plate": (1, 0, 0), "polarizer_cap": (1, 0, 0),
    "bin_side_back": (2, 6, 0), "bin_side_front": (2, 6, 0), "door": (2, 6, 0), "servo_link": (3, 6, 0), "tie_bar": (3, 6, 0),
    "back_panel": (1, 6, 0), "back_panel_hub": (1, 0, 0), "bin": (3, 6, 0), "end_side_front": (1, 0, 0), "end_side_back": (1, 0, 0),
    "end_cap": (1, 0, 0), "end_ramp": (1, 0, 0), "electronics_tray": (1, 0, 0), "bay_cover": (1, 0, 0), "psu_cradle": (2, 0, 0),
    "inlet_plate": (1, 0, 0), "idler_slider": (2, 0, 0), "joint_plate": (4, 12, 0), "screen_cradle": (1, 0, 0), "pod_cover": (1, 0, 0), "pod_standoff": (1, 0, 0), "mount_wall": (1, 0, 0),
}

def placed():
    """All parts placed in machine coordinates for the assembly render."""
    P = {}
    P["feeder_base"] = feeder_base()
    P["raw_tower"] = raw_tower()
    gp = gate_plate().union(box(-4, GATE_T, -GATE_W / 2, GATE_W / 2, -3, 1).intersect(gate_floor(0.0)).cut(gate_floor(-GATE_PAD)))   # + the pad
    def lean(w):
        return (w.rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN)
                 .rotate((TOWER_X0 + TOWER_IN_X, 0, PATH), (TOWER_X0 + TOWER_IN_X, 1, PATH), TOWER_LEAN_X))
    gx0 = TOWER_X0 + TOWER_IN_X + 3.5 + 1.0
    g = lean(gp.translate((gx0, 0, PATH + 0.45)))
    dz = PATH + GATE - g.val().BoundingBox().zmin
    ax = lean(cq.Workplane("XY").add(cq.Vertex.makeVertex(0, 0, PATH + 1))).val().Center() - \
         lean(cq.Workplane("XY").add(cq.Vertex.makeVertex(0, 0, PATH))).val().Center()
    P["gate_plate"] = lean(gp.translate((gx0, 0, PATH + 0.45 + dz / ax.z)))   # slid along its track: 0.45 under the pad
    P["feed_roller"] = feed_roller().translate((FEED_X, 0, FEED_Z))
    P["exit_roller"] = exit_roller().translate((EXIT_X, 0, EXIT_Z))
    P["exit_roller_top"] = exit_roller().translate((EXIT_X, 0, PR_Z))
    P["pressure_bridge"] = pressure_bridge()
    P["scan_side_front"] = scan_side_front()
    P["scan_side_back"] = scan_side_back()
    P["scan_floor"] = scan_floor()
    P["hood"] = hood()
    P["hood_lid"] = hood_lid()
    P["sheen_cap"] = sheen_cap().translate((SCAN_X, 75.0 + 5, SHEEN_Z))
    for i, xb in enumerate(BIN_X[:-1]):
        x0 = xb - PITCH / 2
        P[f"bin_side_back_{i}"] = bin_module_side(1).translate((x0, 0, 0))
        P[f"bin_side_front_{i}"] = bin_module_side(-1).translate((x0, 0, 0))
        P[f"door_{i}"] = door().translate((x0, 0, 0))
        P[f"servo_link_{i}"] = link_placed().translate((x0, 0, 0))
        P[f"back_panel_{i}"] = back_panel(hub=(i == HUB_MODULE)).translate((x0, 0, 0))
    for i, xb in enumerate(BIN_X):
        P[f"bin_{i}"] = bin_box().translate((xb + BIN_DX, BIN_Y, 0.0))
    P["electronics_tray"] = electronics_tray().translate((TRAY_X[0], 0, RAIL_Z + 17.0))
    P["bay_cover"] = bay_cover().translate((0, -63, RAIL_Z + 12))
    for xc in CRADLE_XC:
        P[f"psu_cradle_{int(xc)}"] = psu_cradle().translate((xc - 9, 0, 0))
    for sg, nm in ((1, "back"), (-1, "front")):
        k = idler_slider() if sg > 0 else idler_slider().mirror("XZ")
        P[f"idler_slider_{nm}"] = k
    P["inlet_plate"] = inlet_plate().translate((SCAN_X0 + 32, WALL_OUT, RAIL_Z + 39))
    # screen pod in front of the hopper/hood gap, tilted back; the camera ribbon leaves its back
    P["screen_cradle"] = screen_placed(screen_cradle())
    P["pod_cover"] = screen_placed(pod_cover())
    P["pod_standoff"] = screen_placed(pod_standoff())
    P["mount_wall_gap"] = mount_wall().rotate((0, 0, 0), (0, 0, 1), 180).translate((MOUNT_X, -WALL_OUT, PATH - 21))
    xe = END_X0
    P["end_side_front"] = end_side(-1).translate((xe, 0, 0))
    P["end_side_back"] = end_side(1).translate((xe, 0, 0))
    P["end_cap"] = end_cap().translate((xe + END_L, 0, 0))
    P["end_ramp"] = end_ramp().translate((xe, 0, 0))
    for k, xb in enumerate(BIN_X):
        P[f"tie_bar_{k}"] = tie_bar().translate((xb - PITCH / 2, 0, 0))   # start of every bin module + the end module
    for k in range(1, BINS):                                             # joints bin|bin and bin|end, front and back
        xj = BIN_X[0] - PITCH / 2 + PITCH * k
        P[f"joint_plate_f{k}"] = joint_plate().rotate((0, 0, 0), (0, 0, 1), 180).translate((xj, -WALL_OUT, JOINT_Z))
        P[f"joint_plate_b{k}"] = joint_plate().translate((xj, WALL_OUT, JOINT_Z))
    return P

LENGTH = END_X0 + END_L + 4.0

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out_stl = os.path.join(here, "..", "stl"); out_step = os.path.join(here, "..", "step")
    os.makedirs(out_stl, exist_ok=True); os.makedirs(out_step, exist_ok=True)
    for name, (fn, mat, note) in PRINTED.items():
        qty = sum(STAGES[name])
        s = fn()
        cq.exporters.export(s, os.path.join(out_stl, f"{name}.stl"), tolerance=0.05, angularTolerance=0.1)
        cq.exporters.export(s, os.path.join(out_step, f"{name}.step"))
        bb = s.val().BoundingBox()
        print(f"{name:18s} x{qty:<2d} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm  {mat}")
