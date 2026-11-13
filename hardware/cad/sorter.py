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
    b = b.cut(box(X0 + 15, X1 - 15, Y0 - 1, Y0 + 5, RAIL_Z + 15, PATH - 45))
    b = b.cut(box(X0 + 15, X1 - 15, Y1 - 5, Y1 + 1, RAIL_Z + 15, PATH - 45))
    # hopper floor openings: feed roller, exit roller, fin slots where the fins rise around the start pulleys
    b = b.cut(box(FEED_X - 18, FEED_X + 18, -21, 21, PATH - 6, PATH + 1))
    b = b.cut(box(EXIT_X - 14, EXIT_X + 14, -17, 17, PATH - 6, PATH + 1))
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
        b = b.cut(cyl_y(x, z, NEMA_BOSS / 2 + 0.5, Y1 - 5, Y1 + 1))
        for dx in (-1, 1):
            for dz in (-1, 1):
                b = b.cut(cyl_y(x + dx * NEMA_HOLES / 2, z + dz * NEMA_HOLES / 2, M3 / 2, Y1 - 5, Y1 + 1))
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
    """Hopper for raw cards: inside 89.5 x 64.5 mm, about 550 cards. Open top, sight slot on the front.
    The exit wall stops at the gate; the gate plate (separate) sets the 0.45 mm opening."""
    t = 3.0
    xo0, xo1 = TOWER_X0 - t, TOWER_X0 + TOWER_IN_X + t
    yo0, yo1 = -TOWER_IN_Y / 2 - t, TOWER_IN_Y / 2 + t
    tw = box(xo0, xo1, yo0, yo1, PATH + 0.0, PATH + TOWER_H)
    tw = tw.cut(box(TOWER_X0, TOWER_X0 + TOWER_IN_X, -TOWER_IN_Y / 2, TOWER_IN_Y / 2, PATH - 1, PATH + TOWER_H + 1))
    # base skirt with dovetail grooves that sit over the base rails
    tw = tw.union(box(xo0 - 9, xo1 + 9, -45, 45, PATH + 3, PATH + 9))
    tw = tw.cut(box(xo0 - 9, xo1 + 9, -TOWER_IN_Y / 2, TOWER_IN_Y / 2, PATH + 2, PATH + 10))
    # the card floor is the base itself: the walls stop 3 mm above it except the exit wall, which stops 6 mm up
    tw = tw.cut(box(xo0 - 10, xo1 + 10, -60, 60, PATH - 1, PATH + 3))
    tw = tw.cut(box(TOWER_X0 + TOWER_IN_X - 1, xo1 + 1, -TOWER_IN_Y / 2, TOWER_IN_Y / 2, PATH - 1, PATH + 6))
    # sight slot on the front wall (-Y) to see the stack level
    tw = tw.cut(box(TOWER_X0 + 30, TOWER_X0 + TOWER_IN_X - 30, yo0 - 1, yo0 + t + 1, PATH + 20, PATH + TOWER_H - 15))
    # thumb-screw holes in the skirt (match base inserts)
    for y in (-40, 40):
        tw = tw.cut(cyl_z(TOWER_X0 - 6, y, M3 / 2, PATH, PATH + 12))
    # gate adjuster: vertical dovetail track on the exit face + boss for the M3 adjust screw
    gx = xo1
    tw = tw.union(box(gx, gx + 6, -20, 20, PATH + 6, PATH + 40))
    tw = tw.cut(box(gx + 1, gx + 6.1, -14, 14, PATH + 5, PATH + 41))
    tw = tw.union(box(gx, gx + 10, -6, 6, PATH + 40, PATH + 46))
    tw = tw.cut(cyl_z(gx + 5, 0, 1.4, PATH + 39, PATH + 47))   # M3 tapped into plastic (or insert)
    # magnet pockets (tower ID): raw tower has both positions filled
    for y in (-30, 30):
        tw = tw.cut(cyl_z(TOWER_X0 - 6, y, 3.1, PATH + 3, PATH + 6.3))
    return tw

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
    """Holds one 5 mm IR break-beam LED. Screws to the side walls (M3)."""
    c = box(0, 14, 0, 10, 0, 16)
    c = c.cut(cyl_y(7, 9, 2.6, -1, 11))
    c = c.cut(cyl_z(7, 5, M3 / 2, -1, 5))
    return c

# ============================================================================ SCANNER
SCAN_X0, SCAN_X1 = 150.0, 330.0  # scan module footprint along X (under the hood)
HOOD_X0, HOOD_X1 = 200.0, 355.0
HOOD_H = 165.0

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
    # camera opening + HQ camera bolt pattern (30 x 30, M2.5) on the roof
    h = h.cut(cyl_z(SCAN_X, 0, 16, PATH + HOOD_H - 4, PATH + HOOD_H + 1))
    for dx in (-15, 15):
        for dy in (-15, 15):
            h = h.cut(cyl_z(SCAN_X + dx, dy, 1.35, PATH + HOOD_H - 4, PATH + HOOD_H + 1))
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
    """Spacer between the HQ camera board and the hood roof; holds the 6 mm lens's polarizer cap."""
    p = box(-19, 19, -19, 19, 0, 4)
    p = p.cut(cyl_z(0, 0, 15, -1, 5))
    for dx in (-15, 15):
        for dy in (-15, 15):
            p = p.cut(cyl_z(dx, dy, 1.35, -1, 5))
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
    # break-beam LED hole across the bin mouth
    f = f.cut(cyl_y(PITCH / 2, PATH - 22, 2.6, -WALL_OUT - 1, WALL_OUT + 1))
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
    b = b.cut(box(-15, 15, -D / 2 - 4, -D / 2 + 3, H - 30, H + 1))            # finger notch
    return b

def end_side(side):
    """End module side: carries the end idler pulley stub shaft. 70 mm long; the floor stops here."""
    x0, x1 = 0.0, 70.0
    f = side_frame(x0, x1, side, bin_opening=False)
    s = side
    f = f.cut(cyl_y(55, PATH - 1, 2.6, -WALL_OUT - 1, WALL_OUT + 1))
    f = f.cut(box(40, 71, *sorted((s * BELT_Y0 - 1, s * BELT_Y1 + 1)), PATH - 9, PATH + 10.1))
    return f

def end_cap():
    """Closes the end of the track above the last bin (catches cards that overshoot)."""
    c = box(0, 4, -WALL_IN, WALL_IN, PATH - 60, PATH + 30)
    c = c.cut(box(-1, 5, -36, 36, PATH - 60, PATH - 10))
    return c

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
    "raw_tower":       (raw_tower, 1, "PETG", "Upright, 3 walls. ~7 h."),
    "gate_plate":      (gate_plate, 1, "PETG", "Foot down. Glue a 1.5 mm silicone pad strip under the foot."),
    "feed_roller":     (feed_roller, 1, "PETG", "Flat on its end, 100% infill. Fit three 24 x 3.5 mm O-rings."),
    "exit_roller":     (exit_roller, 2, "PETG", "Flat on its end, 100% infill. Two 16 x 3.5 mm O-rings each."),
    "pressure_arm":    (pressure_arm, 1, "PETG", "Flat."),
    "stack_weight":    (stack_weight, 1, "PLA", "Add 4 M8 washers in the pocket."),
    "fin":             (fin, 14, "PETG", "Print 7 + 7 mirrored. 0.12 mm layers."),
    "sensor_clip":     (sensor_clip, 4, "PETG", ""),
    "scan_side_front": (lambda: side_frame(SCAN_X0, SCAN_X1, -1, bin_opening=False), 1, "PETG", "On its outer face."),
    "scan_side_back":  (lambda: side_frame(SCAN_X0, SCAN_X1, 1, bin_opening=False), 1, "PETG", "On its outer face."),
    "scan_floor":      (scan_floor, 1, "PLA matte black", "Top face down for a flat, dull surface."),
    "hood":            (hood, 1, "PLA matte black", "Upside down (roof on the plate), tree supports for the tunnel only. ~16 h."),
    "camera_plate":    (camera_plate, 1, "PETG", ""),
    "polarizer_cap":   (polarizer_cap, 1, "PETG", ""),
    "bin_side_back":   (lambda: bin_module_side(1), 2, "PETG", "On its outer face; one per bin module."),
    "bin_side_front":  (lambda: bin_module_side(-1), 2, "PETG", "On its outer face; one per bin module."),
    "door":            (door, 2, "PETG", "Top face down on the smooth plate side (slick surface)."),
    "servo_link":      (servo_link, 2, "PETG", ""),
    "tie_bar":         (tie_bar, 4, "PETG", "On its side."),
    "bin":             (bin_box, 3, "PLA", "Open side up, 2 walls, 10% infill. ~6 h each."),
    "end_side_front":  (lambda: end_side(-1), 1, "PETG", ""),
    "end_side_back":   (lambda: end_side(1), 1, "PETG", ""),
    "end_cap":         (end_cap, 1, "PETG", ""),
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
    P["scan_side_back"] = side_frame(SCAN_X0, SCAN_X1, 1, bin_opening=False)
    P["scan_floor"] = scan_floor()
    P["hood"] = hood()
    for i, xb in enumerate(BIN_X[:2]):
        x0 = xb - PITCH / 2
        P[f"bin_side_back_{i}"] = bin_module_side(1).translate((x0, 0, 0))
        P[f"bin_side_front_{i}"] = bin_module_side(-1).translate((x0, 0, 0))
        P[f"door_{i}"] = door().translate((x0 + 2, 0, PATH))
    for i, xb in enumerate(BIN_X):
        P[f"bin_{i}"] = bin_box().translate((xb, 0, 0.0))
    xe = BIN_X[1] + PITCH / 2
    P["end_side_front"] = end_side(-1).translate((xe, 0, 0))
    P["end_side_back"] = end_side(1).translate((xe, 0, 0))
    P["end_cap"] = end_cap().translate((xe + 70, 0, 0))
    return P

LENGTH = BIN_X[1] + PITCH / 2 + 74.0

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
