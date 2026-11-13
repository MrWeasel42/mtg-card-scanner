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
PITCH = 105.0         # one bin / one belt-fin step
CH = 70.0             # channel width between the side strips (Y -35..35)
STRIP_IN, STRIP_OUT = 35.0, 47.0   # side strip (floor edge + belt guide) Y range
WALL_IN, WALL_OUT = 47.0, 55.0     # side wall Y range
BELT_Y0, BELT_Y1 = 41.0, 47.0      # 6 mm GT2 belt, vertical loop, Y range
CARD_L, CARD_W = 88.0, 63.0
SCAN_X = 277.0        # card centre when photographed
BIN_X = [382.0, 487.0, 592.0]     # bin centres: bin 1, bin 2, end-of-line bin
M5 = 5.4; M3 = 3.3; M3_INSERT = 4.0   # clearance / heat-set insert holes
M2 = 2.2
FIN_START_X = 125.0   # start pulleys (stub shafts) in the feeder base
NEMA = 42.3; NEMA_HOLES = 31.0; NEMA_BOSS = 22.5

# tower (raw cards)
TOWER_IN_X, TOWER_IN_Y = 89.5, 64.5
TOWER_X0 = 20.0                   # inside face of the back wall
TOWER_H = 185.0
GATE = 0.45                       # raw-card gate opening, set with the adjuster
TOWER_LEAN = 3.0                  # degrees the hopper leans back (+Y) so an open front can't spill
PSU_L, PSU_W, PSU_H = 129.0, 97.0, 30.0   # Mean Well LRS-100-24 (L x W x H); terminal block on one 97 mm end
PSU_X0 = 180.0                    # PSU case starts here; its terminals face -X with 25 mm for the wires
CAM_D = 200.0                     # lens front to card, adjustable 160-205 mm (the 6 mm lens focuses from 200 mm)
CHAN_Z0, CHAN_Z1 = 28.0, 50.0     # wire channel: 10 x 18 mm inside (fits the full 9-bin loom at <40% fill)

FEED_X, FEED_Z, FEED_R = 95.0, PATH - 15.0, 16.0     # feed roller (O-ring tyres, OD 32)
EXIT_X, EXIT_Z, EXIT_R = 136.0, PATH - 11.0, 12.0    # exit roller pair; 122 mm GT2 closed loop from the feed shaft
TRACK_MOTOR_X, TRACK_MOTOR_Z = 125.0, PATH - 61.0     # cross shaft; 160 mm GT2 closed loops up to the start pulleys

def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))

def cyl_y(x, z, r, y0, y1):
    return cq.Workplane("XZ").center(x, z).circle(r).extrude(-(y1 - y0)).translate((0, y0, 0))

def cyl_x(y, z, r, x0, x1):
    return cq.Workplane("YZ").center(y, z).circle(r).extrude(x1 - x0).translate((x0, 0, 0))

def cyl_z(x, y, r, z0, z1):
    return cq.Workplane("XY").center(x, y).circle(r).extrude(z1 - z0).translate((0, 0, z0))

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
    return part

# ============================================================================ FEEDER (head unit)
def feeder_base():
    """Head unit: hopper floor, feed roller, exit roller, both motors, start of the edge belts.
    Footprint 150 x 130 mm (5.9 x 5.1 in), 185 mm (7.3 in) tall, prints upright without supports
    (window openings are bridged). Walls 4 mm."""
    X0, X1, Y0, Y1 = 0.0, 150.0, -60.0, 60.0
    shell = box(X0, X1, Y0, Y1, RAIL_Z, PATH)
    inner = box(X0 + 4, X1 - 4, Y0 + 4, Y1 - 4, RAIL_Z + 6, PATH - 4)
    b = shell.cut(inner)
    # feet over the rails
    b = b.union(box(X0, X1, -RAIL_Y - 10, -RAIL_Y + 10, RAIL_Z, RAIL_Z + 6)).union(box(X0, X1, RAIL_Y - 10, RAIL_Y + 10, RAIL_Z, RAIL_Z + 6))
    b = rail_slots(b, X0, X1)
    # open the front (-X side) bottom for wiring and the side windows to reach the belts
    # electronics bay windows: front (service, covered by bay_cover) and back (cables); kept below the motor bolts
    b = b.cut(box(X0 + 12, X1 - 12, Y0 - 1, Y0 + 5, RAIL_Z + 12, RAIL_Z + 95))
    b = b.cut(box(X0 + 30, X1 - 30, Y1 - 5, Y1 + 1, RAIL_Z + 12, RAIL_Z + 60))
    # tray rails (electronics_tray slides in from the front)
    for xr in (X0 + 4, X1 - 8):
        b = b.union(box(xr, xr + 4, Y0 + 4, Y1 - 4, RAIL_Z + 14, RAIL_Z + 17))
        b = b.union(box(xr, xr + 4, Y0 + 4, Y1 - 4, RAIL_Z + 21, RAIL_Z + 24))
    # cover screw inserts beside the front window
    for (x, z) in ((X0 + 7, RAIL_Z + 30), (X1 - 7, RAIL_Z + 30), (X0 + 7, RAIL_Z + 90), (X1 - 7, RAIL_Z + 90)):
        b = b.cut(cyl_y(x, z, M3_INSERT / 2, Y0 - 1, Y0 + 6))
    # wiring pass-through into the space under the scanner (24 V in, sensor and servo looms out)
    b = b.cut(box(X1 - 5, X1 + 1, -25, 25, RAIL_Z + 15, RAIL_Z + 45))
    # hopper floor openings: feed roller, exit roller, fin slots where the fins rise around the start pulleys
    b = b.cut(box(FEED_X - 18, FEED_X + 18, -21, 21, PATH - 6, PATH + 1))
    b = b.cut(box(EXIT_X - 14, EXIT_X + 14, -17, 17, PATH - 6, PATH + 1))
    b = b.cut(box(X1 - 5, X1 + 1, -17, 17, EXIT_Z - 14, PATH - 4))   # exit roller (D23.6) reaches past the end wall's inner face
    for s in (-1, 1):
        b = b.cut(box(FIN_START_X - 12, X1 + 1, s * 26 if s > 0 else -40, s * 40 if s > 0 else -26, PATH - 6, PATH + 1))
    # feed roller shaft: bearing seats (625: 16 mm OD x 5) in inner ribs at Y = +-24
    for y in (-28, 24):
        b = b.union(box(FEED_X - 14, FEED_X + 14, y, y + 4, FEED_Z - 18, PATH - 4))
    b = b.cut(cyl_y(FEED_X, FEED_Z, 8.05, -29, 29))
    b = b.cut(cyl_y(FEED_X, FEED_Z, 3.0, Y0 - 1, Y1 + 1))
    # exit roller shaft through both walls
    # exit roller bearings sit in slots (+-2 mm along X) so the 122 mm belt can be tensioned
    for yy in ((Y0 - 1, Y0 + 5), (Y1 - 5, Y1 + 1)):
        b = b.cut(cyl_y(EXIT_X - 2, EXIT_Z, 8.05, *yy)).cut(cyl_y(EXIT_X + 2, EXIT_Z, 8.05, *yy)).cut(box(EXIT_X - 2, EXIT_X + 2, yy[0], yy[1], EXIT_Z - 8.05, EXIT_Z + 8.05))
    # track cross shaft (bearings in both walls), motor on the back wall (+Y) outside
    b = b.cut(cyl_y(TRACK_MOTOR_X, TRACK_MOTOR_Z, 8.05, Y0 - 1, Y0 + 5)).cut(cyl_y(TRACK_MOTOR_X, TRACK_MOTOR_Z, 3.0, Y0 - 1, Y1 + 1))
    # feed motor on the back wall at the feed shaft, track motor below it
    for (x, z) in ((FEED_X, FEED_Z), (TRACK_MOTOR_X, TRACK_MOTOR_Z)):
        b = b.cut(cyl_y(x, z, 8.05, Y1 - 5, Y1 + 1))      # 625 bearing seat in the wall; shaft passes out to the coupler
        for dx in (-1, 1):
            for dz in (-1, 1):
                b = b.cut(cyl_y(x + dx * NEMA_HOLES / 2, z + dz * NEMA_HOLES / 2, M3_INSERT / 2, Y1 - 6.5, Y1 + 1))
    # start-pulley stub shafts (Y = +-44 and +-52 pulleys) carried in bosses at Z = PATH
    for s in (-1, 1):
        y_wall = s * 56
        b = b.union(box(FIN_START_X - 9, FIN_START_X + 9, min(y_wall, s * 60), max(y_wall, s * 60), PATH - 22, PATH - 4))
        y0s, y1s = sorted((s * 38.0, s * 61.0))
        b = b.cut(cyl_y(FIN_START_X, PATH - 1.0, 2.6, y0s, y1s))     # 5 mm stub shaft, pulleys at |Y| 41-55
    # tower dovetail rails on top (tower slides on from the back, +Y)
    for x in (TOWER_X0 - 9, TOWER_X0 + TOWER_IN_X + 3):
        b = b.union(box(x, x + 6, -40, 40, PATH, PATH + 3))
    # heat-set inserts for the tower thumb screws and the pressure-roller arm
    for (x, y) in ((TOWER_X0 - 6, -45), (TOWER_X0 - 6, 45), (EXIT_X, -48), (EXIT_X, 48)):
        b = b.cut(cyl_z(x, y, M3_INSERT / 2, PATH - 8, PATH + 1))
    # magnet pockets for the tower-ID magnets read by the hall sensors (two positions)
    for y in (-30, 30):
        b = b.cut(cyl_z(TOWER_X0 - 6, y, 3.1, PATH - 3.2, PATH + 1))
    return b

def raw_tower():
    """Open-front hopper for raw cards: inside 89.5 x 64.5 mm, about 550 cards. Leans back 3 degrees so the
    stack rests against the back wall and can't spill out of the open front; the bottom card still sits flat
    on the floor and slides out under the gate. Lips at the front corners and a top band keep it rigid."""
    t = 3.0
    xo0, xo1 = TOWER_X0 - t, TOWER_X0 + TOWER_IN_X + t
    yo0, yo1 = -TOWER_IN_Y / 2 - t, TOWER_IN_Y / 2 + t
    walls = box(xo0, xo1, yo0, yo1, PATH - 6, PATH + TOWER_H)
    walls = walls.cut(box(TOWER_X0, TOWER_X0 + TOWER_IN_X, -TOWER_IN_Y / 2, TOWER_IN_Y / 2, PATH - 7, PATH + TOWER_H + 1))
    # open the front (-Y) between 8 mm corner lips, leaving a 10 mm band at the top
    walls = walls.cut(box(TOWER_X0 + 8, TOWER_X0 + TOWER_IN_X - 8, yo0 - 1, yo0 + t + 1, PATH + 12, PATH + TOWER_H - 10))
    # gate track on the exit face (+X) + boss for the M3 adjust screw
    gx = xo1
    walls = walls.union(box(gx, gx + 6, -20, 20, PATH + 6, PATH + 40))
    walls = walls.cut(box(gx + 1, gx + 6.1, -14, 14, PATH + 5, PATH + 41))
    walls = walls.union(box(gx, gx + 10, -6, 6, PATH + 40, PATH + 46))
    walls = walls.cut(cyl_z(gx + 5, 0, 1.4, PATH + 39, PATH + 47))
    # lean: rotate about the X axis through the floor line
    walls = walls.rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN)
    # flat bottom: walls stop 3 mm above the floor, the exit wall 6 mm (that's where cards leave)
    walls = walls.cut(box(xo0 - 20, xo1 + 20, -80, 80, PATH - 20, PATH + 3))
    walls = walls.cut(box(TOWER_X0 + TOWER_IN_X - 1, xo1 + 1, -TOWER_IN_Y / 2, TOWER_IN_Y / 2 + 4, PATH - 1, PATH + 6))
    tw = walls
    # base skirt with dovetail grooves that sit over the base rails
    skirt = box(xo0 - 9, xo1 + 9, -45, 45, PATH + 3, PATH + 9)
    skirt = skirt.cut(box(xo0 - 9, xo1 + 9, -TOWER_IN_Y / 2, TOWER_IN_Y / 2 + 4, PATH + 2, PATH + 10))
    for y in (-40, 40):
        skirt = skirt.cut(cyl_z(TOWER_X0 - 6, y, M3 / 2, PATH, PATH + 12))
    for y in (-30, 30):
        skirt = skirt.cut(cyl_z(TOWER_X0 - 6, y, 3.1, PATH + 3, PATH + 6.3))
    return tw.union(skirt)

def gate_plate():
    """Slides in the tower's exit track; silicone pad glued under its foot. M3 screw from the top sets the gap."""
    g = box(0, 5, -13.8, 13.8, 0, 36)
    g = g.union(box(-4, 5, -13.8, 13.8, 0, 4))           # foot that reaches over the card path
    g = g.cut(cyl_z(2.5, 0, 1.4, 30, 37))                # screw pushes on a captive nut pocket
    g = g.cut(box(0.5, 4.5, -3.2, 3.2, 31, 34))          # M3 nut trap
    return g

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

def feed_roller():   # OD with tyres ~32 mm: three 24 x 3.5 mm O-rings (ID x cross-section)
    return o_ring_roller(14.0, 40.0, 3)

def exit_roller():   # OD with tyres ~24 mm: two 16 x 3.5 mm O-rings (print 2: driven + pressure)
    return o_ring_roller(10.0, 30.0, 2)

def pressure_arm():
    """Gravity-loaded arm that holds the pressure roller on the exit roller. Pivots on an M3 screw."""
    a = box(0, 60, -3, 3, 0, 10)
    a = a.union(box(0, 10, -24, 24, 0, 10))
    for y in (-21, 21):
        a = a.cut(cyl_x(y, 5, M3 / 2, -1, 11))
    a = a.union(box(50, 60, -22, 22, 0, 6)).cut(box(52, 58, -18, 18, -1, 7))
    a = a.cut(cyl_y(55, 3, 2.6, -23, 23))          # 5 mm axle for the pressure roller
    return a

def stack_weight():
    """Rides on top of the stack so the last few cards still feed. Pocket for 4 x M8 washers."""
    w = box(0, 86, -30.5, 30.5, 0, 12)
    w = w.cut(box(8, 78, -22, 22, 3, 13))
    w = w.union(box(38, 48, -6, 6, 12, 40))       # handle
    return w

def fin():
    """Clips onto the 6 mm GT2 belt (two teeth) and reaches 10 mm in over the floor to push the card's corner.
    Print 2 per pitch per side; flip for the other side."""
    f = box(0, 8, 0, 8, 0, 3.0)               # clamp plate under the belt
    f = f.union(box(0, 8, 0, 8, 3.0 + 1.4, 6.4))  # cap over the belt (belt thickness 1.4 sits between)
    f = f.union(box(0, 2, 0, 8, 0, 6.4))         # spine
    f = f.union(box(6, 8, -12, 8, -6.0, 6.4))    # pusher reaching inward and down to the floor
    for x in (2.5, 5.5):
        f = f.cut(cyl_z(x, 4, 0.9, -1, 8))       # 1.6 mm pin holes through the belt (or zip-tie)
    return f

def sensor_clip():
    """Holds one break-beam half (20 x 10 x 8 housing) with a 4 mm window for the beam. M3 to a wall insert."""
    c = box(0, 26, 0, 12, 0, 16)
    c = c.cut(box(2.8, 23.2, 2, 12.1, 2.8, 13.2))
    c = c.cut(cyl_y(13, 8, 2.0, -1, 3))
    c = c.union(box(26, 36, 0, 3, 0, 16)).cut(cyl_y(31, 8, M3 / 2, -1, 4))
    return c

def motor_standoff():
    """Holds a NEMA 17 30 mm off the feeder base's back wall so the 5x5 coupler sits outside the wall
    (bearing inside, pulley on the shaft inside). Windows on two sides to reach the coupler set screws.
    Frame in its own coordinates: wall side at y=0, motor face at y=30."""
    L = 30.0
    m = box(-21.15, 21.15, 0, L, -21.15, 21.15)
    m = m.cut(cyl_y(0, 0, 11.5, -1, L + 1))
    m = m.cut(box(-12, 12, 4, L - 4, -22, 22))           # set-screw windows (top and bottom)
    m = m.cut(box(-22, 22, 4, L - 4, -12, 12))
    for dx in (-15.5, 15.5):
        for dz in (-15.5, 15.5):
            m = m.cut(cyl_y(dx, dz, M3 / 2, -1, L + 1))  # M3 x 40 screws pass straight through into the wall inserts
    return m

# ============================================================================ SCANNER
SCAN_X0, SCAN_X1 = 150.0, 330.0  # scan module footprint along X (under the hood)
HOOD_X0, HOOD_X1 = 200.0, 355.0
HOOD_H = 266.0        # lens-to-card 160-205 mm with 2 mm over the camera at the top; prints 256 tall (Neptune 4 Pro: 265)

def side_frame(x0, x1, side, drive_floor=False, bin_opening=True):
    """One side of a track module (side = -1 front, +1 back). Wall + top strip with belt run + foot.
    Floor edge is at |Y| = 35; belt loop at |Y| 41..47 (top run on the rib, return run in the lower slot)."""
    s = side
    yw0, yw1 = sorted((s * WALL_IN, s * WALL_OUT))
    ys0, ys1 = sorted((s * STRIP_IN, s * WALL_IN))
    f = box(x0, x1, yw0, yw1, RAIL_Z, PATH + 10)                 # wall
    f = f.union(box(x0, x1, ys0, ys1, PATH - 12, PATH))         # strip: floor edge + belt guide
    yb0, yb1 = sorted((s * BELT_Y0, s * BELT_Y1))
    f = f.cut(box(x0 - 1, x1 + 1, yb0, yb1, PATH - 9, PATH - 4))   # return-run slot
    f = f.cut(box(x0 - 1, x1 + 1, yb0 - (0.5 if s > 0 else 0), yb1 + (0.5 if s < 0 else 0), PATH, PATH + 10.1))
    # foot over the rail
    yf0, yf1 = sorted((s * WALL_IN, s * (RAIL_Y + 10)))
    f = f.union(box(x0, x1, yf0, yf1, RAIL_Z, RAIL_Z + 6))
    f = rail_slots(f, x0, x1, ys=(s * RAIL_Y,))
    # wire channel on the outside face (servo, sensor and LED looms), open at both ends so it runs through
    # every module; snap-on cover = channel_cover
    yc0, yc1 = sorted((s * WALL_OUT, s * (WALL_OUT + 12)))
    f = f.union(box(x0, x1, yc0, yc1, CHAN_Z0, CHAN_Z1))
    yi0, yi1 = sorted((s * (WALL_OUT + 0.01), s * (WALL_OUT + 10)))
    f = f.cut(box(x0 - 1, x1 + 1, yi0, yi1, CHAN_Z0 + 2, CHAN_Z1 - 2))
    # lightening window + panel clips (final shell clips onto these bosses)
    if bin_opening:
        f = f.cut(box(x0 + 12, x1 - 12, yw0 - 1, yw1 + 1, RAIL_Z + 20, PATH - 40))
    for xc in (x0 + 8, x1 - 8):
        f = f.cut(cyl_y(xc, PATH - 25, M3_INSERT / 2, s * WALL_OUT - (6 if s > 0 else 0), s * WALL_OUT + (6 if s < 0 else 0)))
    # end faces get two M3 holes so modules bolt to each other (keeps the floor seams flush)
    for xe in (x0, x1):
        for z in (PATH - 30, RAIL_Z + 30):
            f = f.cut(cyl_x(s * (WALL_IN + WALL_OUT) / 2, z, M3 / 2, xe - 8, xe + 8))
    return f

def scan_side_back():
    """Back wall of the scan module, with the power/cable window that the inlet plate covers."""
    f = side_frame(SCAN_X0, SCAN_X1, 1, bin_opening=False)
    f = f.cut(box(SCAN_X0 + 40, SCAN_X0 + 140, WALL_IN - 1, WALL_OUT + 1, RAIL_Z + 38, RAIL_Z + 88))
    for x in (SCAN_X0 + 36, SCAN_X0 + 144):
        for z in (RAIL_Z + 33, RAIL_Z + 93):
            f = f.cut(cyl_y(x, z, M3_INSERT / 2, WALL_OUT - 6, WALL_OUT + 1))
    return f

def scan_floor():
    """Solid matte-black floor under the camera, between the strips (Y -35..35). Slots let the fins pass."""
    x0, x1 = SCAN_X0, SCAN_X1
    fl = box(x0 + 0.5, x1 - 0.5, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 3, PATH)
    fl = fl.union(box(x0 + 0.5, x1 - 0.5, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 10, PATH - 7))  # ribs
    for xc in (x0 + 20, x1 - 20):
        fl = fl.union(box(xc - 2, xc + 2, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 10, PATH))
    return fl

def hood():
    """Light-tight hood over the scan position. 155 x 150 x 165 mm (6.1 x 5.9 x 6.5 in), 3 mm walls.
    Inside: camera plate on top, ledges for the LED channels on all four walls, slots for the belts."""
    x0, x1, y0, y1 = HOOD_X0, HOOD_X1, -75.0, 75.0
    h = box(x0, x1, y0, y1, PATH + 10, PATH + HOOD_H)
    h = h.cut(box(x0 + 3, x1 - 3, y0 + 3, y1 - 3, PATH + 9, PATH + HOOD_H - 3))
    # card tunnel through both end walls
    h = h.cut(box(x0 - 1, x1 + 1, -38, 38, PATH + 9, PATH + 22))
    # camera hangs from the roof on 4 x M3 x 80 screws through camera_plate: nuts above and below set the
    # lens height anywhere from 160 to 205 mm above the card. Slot for the camera ribbon.
    for dx in (-26, 26):
        for dy in (-26, 26):
            h = h.cut(cyl_z(SCAN_X + dx, dy, M3 / 2, PATH + HOOD_H - 4, PATH + HOOD_H + 1))
    h = h.cut(box(SCAN_X - 12, SCAN_X + 12, 30, 34, PATH + HOOD_H - 4, PATH + HOOD_H + 1))
    # LED channel ledges (aluminium channel 17 x 8 mm) at 90 mm above the card, all round
    zled = PATH + 90
    h = h.union(box(x0 + 3, x1 - 3, y0 + 3, y0 + 14, zled - 2, zled))
    h = h.union(box(x0 + 3, x1 - 3, y1 - 14, y1 - 3, zled - 2, zled))
    # sheen LED port (low angle, back wall)
    h = h.cut(cyl_y(SCAN_X, PATH + 30, 6, y1 - 4, y1 + 1))
    # feet that sit on the scan-module walls, M3 holes
    for s in (-1, 1):
        for xc in (x0 + 10, x1 - 10):
            h = h.cut(cyl_z(xc, s * 51, M3 / 2, PATH + 9, PATH + 30))
    return h

def camera_plate():
    """Carries the HQ camera (M2.5 on 30 x 30) and hangs from the hood roof on 4 x M3 screws (52 mm square)."""
    p = box(-31, 31, -31, 31, 0, 4)
    p = p.cut(cyl_z(0, 0, 18.5, -1, 5))
    for dx in (-15, 15):
        for dy in (-15, 15):
            p = p.cut(cyl_z(dx, dy, 1.35, -1, 5))
    for dx in (-26, 26):
        for dy in (-26, 26):
            p = p.cut(cyl_z(dx, dy, M3 / 2, -1, 5))
    return p

def polarizer_cap():
    """Push-on cap for the 6 mm lens with a slot for a 32 mm disc of polarizer film; rotate to cross-polarize."""
    c = cq.Workplane("XY").circle(17).circle(14.4).extrude(10)
    c = c.union(cq.Workplane("XY").circle(17).circle(11).extrude(1.6))
    c = c.cut(cq.Workplane("XY").circle(16.2).extrude(0.6).translate((0, 0, 1.6)))
    c = c.union(box(15, 22, -2, 2, 0, 10))   # index tab for setting the angle
    return c

# ============================================================================ BIN MODULES
def door():
    """Trapdoor leaf: 101 x 69.6 x 2.4 mm. Hinged at the back edge (Y = +35) on a 2 mm pin; the lever
    under the back strip is pushed by the servo link. Smooth top (print top face up on the textured sheet? no:
    print top face DOWN on the smooth side of the plate for the slickest surface)."""
    L, W, T = 101.0, 69.6, 2.4
    d = box(0, L, -W / 2, W / 2, -T, 0)
    for xk in (6, L / 2 - 5, L - 16):       # hinge knuckles
        d = d.union(box(xk, xk + 10, W / 2 - 3, W / 2 + 2.0, -6, 0))
        d = d.cut(cyl_x(W / 2 - 0.5, -3.0, 1.1, xk - 1, xk + 11))
    d = d.union(box(L / 2 - 4, L / 2 + 4, W / 2, W / 2 + 14, -12, -8))   # lever arm
    d = d.union(box(L / 2 - 4, L / 2 + 4, W / 2 - 2, W / 2 + 2, -12, 0))
    d = d.cut(cyl_x(W / 2 + 11, -10, 0.9, L / 2 - 5, L / 2 + 5))   # link pin hole
    return d

def servo_link():
    """Connects the servo horn to the door lever. Hole spacing 22 mm."""
    l = box(0, 26, -3, 3, 0, 3)
    for x in (2, 24):
        l = l.cut(cyl_z(x, 0, 0.9, -1, 4))
    return l

def bin_module_side(side):
    """Side frame for one 105 mm bin module. Back side (+1) carries the hinge, servo and LED emitter;
    front side (-1) carries the door rest ledge and the receiver."""
    x0, x1 = 0.0, PITCH
    f = side_frame(x0, x1, side)
    s = side
    if s > 0:
        # hinge knuckle row under the strip edge, pin at Y = +34.5, Z = PATH - 3
        for xk in (1, PITCH / 2 + 5, PITCH - 6):
            f = f.union(box(xk, xk + 5, 33, 38, PATH - 7, PATH - 0.2))
        f = f.cut(cyl_x(34.5, PATH - 3.0, 1.05, -1, PITCH + 1))
        # servo pocket on the outside of the wall: ES08MA II body 32.5 x 12 x 27 (with tabs)
        sx = PITCH / 2
        f = f.union(box(sx - 20, sx + 20, WALL_OUT, WALL_OUT + 4, PATH - 50, PATH - 14))
        f = f.cut(box(sx - 11.75, sx + 11.75, WALL_IN - 1, WALL_OUT + 5, PATH - 44, PATH - 32))
        for dx in (-14, 14):
            f = f.cut(cyl_y(sx + dx, PATH - 38, 0.9, WALL_OUT - 2, WALL_OUT + 5))
        # slot for the door lever to swing through
        f = f.cut(box(sx - 6, sx + 6, STRIP_IN - 1, WALL_IN + 1, PATH - 30, PATH - 6))
    else:
        f = f.union(box(x0 + 2, x1 - 2, -STRIP_IN - 2, -STRIP_IN + 0.01, PATH - 4.4, PATH - 2.4))  # door rest ledge
    # break-beam housing (20 x 10 x 8) in a pocket on the outer face, 4 mm window through to the bin mouth
    yp0, yp1 = sorted((s * (WALL_OUT - 7), s * (WALL_OUT + 5)))   # 1 mm skin left at the bin side
    f = f.cut(box(PITCH / 2 - 10.2, PITCH / 2 + 10.2, yp0, yp1, PATH - 27.2, PATH - 16.8))
    f = f.cut(cyl_y(PITCH / 2, PATH - 22, 2.0, -WALL_OUT - 1, WALL_OUT + 1))
    return f

def tie_bar():
    """Ties the front and back walls together at the module joint, just under the floor."""
    t = box(0, 4, -WALL_OUT, WALL_OUT, PATH - 22, PATH - 13)
    for s in (-1, 1):
        t = t.cut(cyl_x(s * (WALL_IN + WALL_OUT) / 2, PATH - 17.5, M3 / 2, -1, 5))
    return t

def bin_box(height=135.0):
    """Removable bin: outside 98 x 76 mm, inside 94 x 72 mm (3.7 x 2.8 in), 135 mm (5.3 in) tall: ~400 raw cards.
    Front lip doubles as the drawer front; the final shell adds a flush face."""
    W, D, H = 98.0, 76.0, height
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

def end_side(side):
    """End module side: one full pitch (105 mm) so the end-of-line bin sits fully under it; carries the end
    idler pulley stub shaft. There's no floor here: cards are pushed off the end of the last door."""
    x0, x1 = 0.0, PITCH
    f = side_frame(x0, x1, side, bin_opening=False)
    s = side
    f = f.cut(cyl_y(90, PATH - 1, 2.6, -WALL_OUT - 1, WALL_OUT + 1))
    f = f.cut(box(75, PITCH + 1, *sorted((s * BELT_Y0 - 1, s * BELT_Y1 + 1)), PATH - 9, PATH + 10.1))
    f = f.cut(box(x0 + 12, x1 - 12, *sorted((s * WALL_IN - s, s * WALL_OUT + s)), RAIL_Z + 20, PATH - 40))
    return f

def end_cap():
    """Closes the end of the track above the last bin (catches cards that overshoot)."""
    c = box(0, 4, -WALL_IN, WALL_IN, PATH - 60, PATH + 30)
    c = c.cut(box(-1, 5, -36, 36, PATH - 60, PATH - 10))
    return c

# ============================================================================ ELECTRONICS, POWER, SCREEN
def electronics_tray():
    """Slides into the feeder base under the hopper. Pi 5 (58 x 49 mm M2.5 pattern) at the front so its ports
    face the service cover; motor board, servo driver, 6 V step-down and LED MOSFET on a 10 mm grid of M3
    holes behind it. Zip-tie slots along both edges for the looms."""
    T = 3.0
    t = box(0, 133, -54, 54, 0, T)
    for dx in (0, 58):
        for dy in (0, 49):
            t = t.cut(cyl_z(12 + dx, -50 + 3.5 + dy, 1.35, -1, T + 1))
            t = t.union(cyl_z(12 + dx, -50 + 3.5 + dy, 3, T, T + 5).cut(cyl_z(12 + dx, -50 + 3.5 + dy, 1.35, T - 1, T + 6)))
    # SKR Pico stacks above the Pi on 4 x 40 mm M2.5 standoffs (bought) in the same 58 x 49 pattern
    for x in range(80, 131, 10):
        for y in range(10, 51, 10):
            t = t.cut(cyl_z(x, y, 1.7, -1, T + 1))
    for x in range(10, 71, 10):
        for y in (20, 30, 40, 50):
            t = t.cut(cyl_z(x, y, 1.7, -1, T + 1))
    for x in range(15, 125, 20):
        for y in (-52, 52):
            t = t.cut(box(x, x + 3, y - 1.5, y + 1.5, -1, T + 1))
    return t

def bay_cover():
    """Front cover of the electronics bay: vent slots + a 30 mm fan position. 4 x M3."""
    c = box(0, 136, 0, 3, 0, 89)
    for z in range(12, 80, 7):
        c = c.cut(box(20, 80, -1, 4, z, z + 3.5))
    c = c.cut(cyl_y(108, 30, 14, -1, 4))
    for dx in (-12, 12):
        for dz in (-12, 12):
            c = c.cut(cyl_y(108 + dx, 30 + dz, 1.5, -1, 4))
    for (x, z) in ((5, 6), (131, 6), (5, 66), (131, 66)):
        c = c.cut(cyl_y(x, z, M3 / 2, -1, 4))
    return c

def psu_cradle():
    """Two of these hold the Mean Well LRS-100-24 on its side under the scanner, bolted to both rails.
    The PSU slides in from the end and is held by M3 screws into its side threads."""
    c = box(0, 18, -RAIL_Y - 10, RAIL_Y + 10, RAIL_Z, RAIL_Z + 5)
    c = c.union(box(0, 18, -PSU_H / 2 - 4, PSU_H / 2 + 4, RAIL_Z, RAIL_Z + 60))
    c = c.cut(box(-1, 19, -PSU_H / 2 - 0.3, PSU_H / 2 + 0.3, RAIL_Z + 5, RAIL_Z + 61))
    for y in (-RAIL_Y, RAIL_Y):
        c = c.cut(cq.Workplane("XY").center(9, y).slot2D(M5 + 6, M5, 90).extrude(8).translate((0, 0, RAIL_Z - 1)))
    for s in (-1, 1):
        c = c.cut(cyl_y(9, RAIL_Z + 40, M3 / 2, *sorted((s * (PSU_H / 2 - 1), s * (PSU_H / 2 + 5)))))
    return c

def inlet_plate():
    """Covers the window in the scan module's back wall: fused, switched IEC C14 inlet (snap-in,
    27.5 x 47.5 mm cutout) and a grommet hole for the Ethernet/USB cable. 4 x M3 into the wall's inserts."""
    p = box(0, 116, 0, 4, 0, 68)
    p = p.cut(box(14, 14 + 47.5, -1, 5, 20, 20 + 27.5))
    p = p.cut(cyl_y(92, 34, 9, -1, 5))
    for x in (4, 112):
        for z in (4, 64):
            p = p.cut(cyl_y(x, z, M3 / 2, -1, 5))
    return p

def channel_cover():
    """Snap-on cover for the wire channel on the side walls (one per module side, 105 mm)."""
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
    """Universal wall bracket: bolts to the two M3 panel bosses on the outside of ANY module wall
    (89 mm apart on bin modules; slotted to also fit the scan module's end bosses). Front or back."""
    m = box(-52, 52, 0, 5, -10, 10)
    for x in (-44.5, 44.5):
        m = m.cut(cq.Workplane("XZ").center(x, 0).slot2D(9, M3, 0).extrude(-6))
    g = gopro(3, 14, base_w=26).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, 5, 0))
    return m.union(g)

def mount_bay():
    """Screen mount on the front of the electronics bay: replaces two of the bay cover screws."""
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

def screen_cradle():
    """Holds the 7 in Touch Display 2 by its edges (lips) with a slot for the ribbon cable, plus a 2-prong
    GoPro tab on the back so it clips onto any mount point. Prints face down."""
    W, H, T = SCREEN_W + 4, SCREEN_H + 4, 3.0
    c = box(-W / 2 - 3, W / 2 + 3, 0, T, -10, H + 3)                    # back plate
    c = c.union(box(-W / 2 - 3, W / 2 + 3, -SCREEN_T, T, -10, -7))      # bottom lip shelf
    c = c.union(box(-W / 2 - 3, -W / 2, -SCREEN_T, T, -10, H + 3))      # side rails
    c = c.union(box(W / 2, W / 2 + 3, -SCREEN_T, T, -10, H + 3))
    c = c.union(box(-W / 2 - 3, -W / 2 + 6, -SCREEN_T - 2, -SCREEN_T, -10, H + 3))   # front lips
    c = c.union(box(W / 2 - 6, W / 2 + 3, -SCREEN_T - 2, -SCREEN_T, -10, H + 3))
    c = c.cut(box(-25, 25, -1, T + 1, 10, 30))                          # ribbon + USB-C slot
    for x in range(-80, 81, 20):                                         # cooling slots
        if abs(x) > 15:
            c = c.cut(box(x - 3, x + 3, -1, T + 1, 60, 100))
    tab = gopro(2, 12, base_w=30, base_t=0.01).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, T, H / 2))
    return c.union(tab)

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
    lid = cq.Workplane("XY").box(length - HOOD_X1 + 8, 150, 26, centered=False).translate((HOOD_X1, -75, PATH + 8)).edges("|X").fillet(8)
    lid = lid.cut(box(HOOD_X1 - 1, length + 10, -72, 72, PATH + 7, PATH + 31))
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
PRINTED = {
    # name: (builder, qty, material, note)
    "feeder_base":     (feeder_base, 1, "PETG", "Upright, 15% gyroid, 4 walls. ~19 h."),
    "raw_tower":       (raw_tower, 1, "PETG", "Upright, 3 walls; open front leans back 3 degrees. ~6 h."),
    "gate_plate":      (gate_plate, 1, "PETG", "Foot down. Glue a 1.5 mm silicone pad strip under the foot."),
    "feed_roller":     (feed_roller, 1, "PETG", "Flat on its end, 100% infill. Fit three 24 x 3.5 mm O-rings."),
    "exit_roller":     (exit_roller, 2, "PETG", "Flat on its end, 100% infill. Two 16 x 3.5 mm O-rings each."),
    "pressure_arm":    (pressure_arm, 1, "PETG", "Flat."),
    "stack_weight":    (stack_weight, 1, "PLA", "Add 4 M8 washers in the pocket."),
    "fin":             (fin, 14, "PETG", "Print 7 + 7 mirrored. 0.12 mm layers."),
    "sensor_clip":     (sensor_clip, 4, "PETG", "Holds an Adafruit break-beam half (20 x 10 x 8 housing)."),
    "motor_standoff":  (motor_standoff, 2, "PETG", "On its side, 5 walls (it carries the motor torque)."),
    "scan_side_front": (lambda: side_frame(SCAN_X0, SCAN_X1, -1, bin_opening=False), 1, "PETG", "On its outer face."),
    "scan_side_back":  (lambda: scan_side_back(), 1, "PETG", "On its outer face."),
    "scan_floor":      (scan_floor, 1, "PLA matte black", "Top face down for a flat, dull surface."),
    "hood":            (hood, 1, "PLA matte black", "Upside down (roof on the plate), tree supports for the tunnel only. ~16 h."),
    "camera_plate":    (camera_plate, 1, "PETG", ""),
    "polarizer_cap":   (polarizer_cap, 1, "PETG", ""),
    "bin_side_back":   (lambda: bin_module_side(1), 2, "PETG", "On its outer face; one per bin module."),
    "bin_side_front":  (lambda: bin_module_side(-1), 2, "PETG", "On its outer face; one per bin module."),
    "door":            (door, 2, "PETG", "Top face down on the smooth plate side (slick surface)."),
    "servo_link":      (servo_link, 2, "PETG", ""),
    "tie_bar":         (tie_bar, 4, "PETG", "On its side."),
    "bin":             (bin_box, 3, "PLA", "Open side up, 2 walls, 10% infill. Big front window + a fill mark every 100 cards. ~5 h each."),
    "end_side_front":  (lambda: end_side(-1), 1, "PETG", ""),
    "end_side_back":   (lambda: end_side(1), 1, "PETG", ""),
    "end_cap":         (end_cap, 1, "PETG", ""),
    "electronics_tray":(electronics_tray, 1, "PETG", "Flat."),
    "bay_cover":       (bay_cover, 1, "PLA matte black", "Flat, outside face down."),
    "psu_cradle":      (psu_cradle, 2, "PETG", "On its back."),
    "inlet_plate":     (inlet_plate, 1, "PETG", "Flat. Cutout 47.5 x 27.5 mm for a snap-in C14 inlet; check yours."),
    "channel_cover":   (channel_cover, 6, "PLA", "On its back. Clips over the wire channels."),
    "screen_cradle":   (screen_cradle, 1, "PETG", "Face down. Check the display size on arrival. GoPro tab on the back."),
    "mount_bay":       (mount_bay, 1, "PETG", "Screen mount on the electronics bay front (default spot)."),
    "mount_wall":      (mount_wall, 2, "PETG", "Bolts to any module wall: between hopper and scanner, or on the back for an arm over the track."),
    "mount_roof":      (mount_roof, 1, "PETG", "Optional: screen on top of the hood."),
    "gopro_arm":       (gopro_arm, 2, "PETG", "100% infill. Or use store-bought GoPro extension arms."),
}

def placed():
    """All parts placed in machine coordinates for the assembly render."""
    P = {}
    P["feeder_base"] = feeder_base()
    P["raw_tower"] = raw_tower()
    P["gate_plate"] = gate_plate().translate((TOWER_X0 + TOWER_IN_X + 3 + 1, 0, PATH + 0.45 + 4 - 4))
    P["feed_roller"] = feed_roller().translate((FEED_X, 0, FEED_Z))
    P["exit_roller"] = exit_roller().translate((EXIT_X, 0, EXIT_Z))
    P["exit_roller_top"] = exit_roller().translate((EXIT_X, 0, PATH + 9.6))
    P["scan_side_front"] = side_frame(SCAN_X0, SCAN_X1, -1, bin_opening=False)
    P["scan_side_back"] = scan_side_back()
    P["scan_floor"] = scan_floor()
    P["hood"] = hood()
    for i, xb in enumerate(BIN_X[:2]):
        x0 = xb - PITCH / 2
        P[f"bin_side_back_{i}"] = bin_module_side(1).translate((x0, 0, 0))
        P[f"bin_side_front_{i}"] = bin_module_side(-1).translate((x0, 0, 0))
        P[f"door_{i}"] = door().translate((x0 + 2, 0, PATH))
    for i, xb in enumerate(BIN_X):
        P[f"bin_{i}"] = bin_box().translate((xb, 0, 0.0))
    P["electronics_tray"] = electronics_tray().translate((8.5, 0, RAIL_Z + 17.2))
    P["bay_cover"] = bay_cover().translate((7, -63, RAIL_Z + 6))
    for xc in (PSU_X0 + 8, PSU_X0 + PSU_L - 26):
        P[f"psu_cradle_{int(xc)}"] = psu_cradle().translate((xc, 0, 0))
    P["inlet_plate"] = inlet_plate().translate((SCAN_X0 + 32, WALL_OUT, RAIL_Z + 29))
    # default screen spot: on the front of the electronics bay, tilted back 25 degrees
    bay_y = -63.0; bay_z = RAIL_Z + 6 + 66
    P["mount_bay"] = mount_bay().translate((75, bay_y, bay_z))
    piv = (75, bay_y - 4 - 14, bay_z)
    P["screen_cradle"] = (screen_cradle().translate((0, -3 - 12, -(SCREEN_H + 4) / 2))
                          .rotate((0, 0, 0), (0, 0, 1), 180).translate((0, 0, 0))
                          .rotate((0, 0, 0), (1, 0, 0), 25).translate(piv))
    P["mount_wall_gap"] = mount_wall().rotate((0, 0, 0), (0, 0, 1), 180).translate((175, -WALL_OUT - 9, PATH - 25))
    xe = BIN_X[1] + PITCH / 2
    P["end_side_front"] = end_side(-1).translate((xe, 0, 0))
    P["end_side_back"] = end_side(1).translate((xe, 0, 0))
    P["end_cap"] = end_cap().translate((xe + PITCH, 0, 0))
    return P

LENGTH = BIN_X[1] + PITCH / 2 + PITCH + 4.0

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out_stl = os.path.join(here, "..", "stl"); out_step = os.path.join(here, "..", "step")
    os.makedirs(out_stl, exist_ok=True); os.makedirs(out_step, exist_ok=True)
    for name, (fn, qty, mat, note) in PRINTED.items():
        s = fn()
        cq.exporters.export(s, os.path.join(out_stl, f"{name}.stl"), tolerance=0.05, angularTolerance=0.1)
        cq.exporters.export(s, os.path.join(out_step, f"{name}.step"))
        bb = s.val().BoundingBox()
        print(f"{name:18s} x{qty:<2d} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm  {mat}")
