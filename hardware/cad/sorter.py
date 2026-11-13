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
BELT_Y0, BELT_Y1 = 37.0, 47.0      # 10 mm GT2 belt, vertical loop ABOVE the floor, Y range
WALL_IN_UP = 48.5                  # inner face of the side walls above the floor (room for the pulley flanges)
WALL_TOP = PATH + 40.0             # side walls rise 40 mm above the floor and hide the belts
PUL_T = 30                         # printed GT2 pulleys, 30 teeth: pitch diameter 19.10 mm
PUL_R = PUL_T * 2.0 / math.pi / 2  # 9.55 pitch radius
PUL_Z = PATH + 17.0                # all belt pulley shafts: bottom (card-pushing) run back face 7 mm above the floor
BELT_BACK_LOW = PUL_Z - PUL_R - 0.45   # underside of the bottom run (belt back), ~PATH + 7
BELT_TEETH_HIGH = PUL_Z + PUL_R - 1.0  # underside of the top run (tooth tips), ~PATH + 25.5
FIN_REACH_Y = 27.0                 # fin fingers reach in to |Y| = 27 (raw card edge 31.5, or 29.25 when it sits off-centre)
GROOVE_Y0, GROOVE_D = 26.5, 1.2    # fin lanes: groove from |Y| 26.5 out to the floor edge, 1.2 mm deep
RAIL_IN, RAIL_W, RAIL_H = 33.75, 2.0, 2.5   # side guides: 67.5 mm apart (sleeved card 66 + 0.75 a side), 2.5 tall
TAPER_X0, TAPER_X1, TAPER_IN0 = 136.0, 230.0, 36.5   # lead-in: 73 mm wide at the exit-roller nip, 67.5 mm by X 230 (1.7 deg a side)
TOWER_LEAN_X = 3.0                 # the L-shaped hopper also leans 3 degrees toward the exit wall
FIN_PITCHES = 10                   # 3-bin build: belt loop = 10 x 105 = 1050 mm, one fin every 105 mm
CARD_L, CARD_W = 88.0, 63.0
SCAN_X = 277.0        # card centre when photographed
BIN_X = [382.0, 487.0, 592.0]     # bin centres: bin 1, bin 2, end-of-line bin
M5 = 5.4; M3 = 3.3; M3_INSERT = 4.0   # clearance / heat-set insert holes
M2 = 2.2
FIN_START_X = 131.0   # start idlers (stub shafts in the posts on the feeder base); fins land here, 5 mm behind the exit nip
END_SHAFT_X = FIN_START_X + (FIN_PITCHES * 105.0 - 2 * math.pi * PUL_R) / 2   # drive shaft in the end module (626)
NEMA = 42.3; NEMA_HOLES = 31.0; NEMA_BOSS = 22.5

# tower (raw cards)
TOWER_IN_X, TOWER_IN_Y = 89.5, 64.5
TOWER_X0 = 20.0                   # inside face of the back wall
TOWER_H = 185.0
GATE = 0.45                       # raw-card gate opening, set with the adjuster
TOWER_LEAN = 3.0                  # degrees the hopper leans back (+Y)
PSU_L, PSU_W, PSU_H = 129.0, 97.0, 30.0   # Mean Well LRS-100-24 (L x W x H); terminal block on one 97 mm end
PSU_X0 = 180.0                    # PSU case starts here; its terminals face -X with 25 mm for the wires
CAM_D = 200.0                     # lens front to card, adjustable 160-205 mm (the 6 mm lens focuses from 200 mm)
CHAN_Z0, CHAN_Z1 = 28.0, 50.0     # back wire channel: 10 x 18 mm inside (fits the full 9-bin loom at <40% fill)
CHAN_F0, CHAN_F1 = 150.0, 172.0   # front channel runs higher, above the bin bays
END_BIN_D = 113.0; END_BIN_Y = -18.5   # end bin: Y +38 .. -75
BIN_Y = -37.0                     # bins sit forward: inner back wall at Y -1, right under the open door's low edge
BAY_TOP = 140.0                   # front wall is open below this between 2.5 mm posts so the bins slide out the front
POST_T = 2.5
RAIL2_Y = 24.0                    # second back rail (under the doors) replaces the front rail under the bin modules
TOF_X = 33.0                      # bin-level ToF sensor (Pololu VL53L1X carrier, 13 x 18 mm) position in each module

FEED_X, FEED_Z, FEED_R = 95.0, PATH - 15.0, 16.0     # feed roller (O-ring tyres, OD 32)
EXIT_X, EXIT_Z, EXIT_R = 136.0, PATH - 11.0, 12.0    # exit roller pair; 122 mm GT2 closed loop from the feed shaft

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
    r = cq.Workplane("XY").polyline(pts).close().extrude(RAIL_H - 0.15).translate((0, 0, PATH + 0.15))
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
    b = b.cut(box(X1 - 5, X1 + 1, -17, 17, EXIT_Z - 14, PATH - 4))
    b = b.cut(box(EXIT_X - 10, EXIT_X + 10, -56, -38, PATH - 4.1, PATH - 2.2))   # recess over the exit pulley (122 mm loop)   # exit roller (D23.6) reaches past the end wall's inner face
    # feed roller shaft: bearing seats (625: 16 mm OD x 5) in inner ribs at Y = +-24
    for y in (-28, 24):
        b = b.union(box(FEED_X - 14, FEED_X + 14, y, y + 4, FEED_Z - 18, PATH - 4))
    b = b.cut(cyl_y(FEED_X, FEED_Z, 8.05, -29, 29))
    b = b.cut(cyl_y(FEED_X, FEED_Z, 3.0, Y0 - 1, Y1 + 1))
    # exit roller shaft through both walls
    # exit roller bearings sit in slots (+-2 mm along X) so the 122 mm belt can be tensioned
    for yy in ((Y0 - 1, Y0 + 5), (Y1 - 5, Y1 + 1)):
        b = b.cut(cyl_y(EXIT_X - 2, EXIT_Z, 8.05, *yy)).cut(cyl_y(EXIT_X + 2, EXIT_Z, 8.05, *yy)).cut(box(EXIT_X - 2, EXIT_X + 2, yy[0], yy[1], EXIT_Z - 8.05, EXIT_Z + 8.05))
    # feed motor on the back wall at the feed shaft (on a 30 mm standoff)
    for (x, z) in ((FEED_X, FEED_Z),):
        b = b.cut(cyl_y(x, z, 8.05, Y1 - 5, Y1 + 1))      # 625 bearing seat in the wall; shaft passes out to the coupler
        for dx in (-1, 1):
            for dz in (-1, 1):
                b = b.cut(cyl_y(x + dx * NEMA_HOLES / 2, z + dz * NEMA_HOLES / 2, M3_INSERT / 2, Y1 - 6.5, Y1 + 1))
    # posts on top of the base carry the start idlers above the floor (they continue the track side walls)
    for sg in (-1, 1):
        y0p, y1p = sorted((sg * WALL_IN_UP, sg * 60.0))
        b = b.union(box(FIN_START_X - 16, X1, y0p, y1p, PATH, WALL_TOP))
        # 5 mm stub in a +-3 mm slot along X; an M3 screw from the end face pulls it back to tension the belt
        b = b.cut(box(FIN_START_X - 3, FIN_START_X + 3, y0p - 1, y1p + 1, PUL_Z - 2.6, PUL_Z + 2.6))
        b = b.cut(cyl_y(FIN_START_X - 3, PUL_Z, 2.6, y0p - 1, y1p + 1)).cut(cyl_y(FIN_START_X + 3, PUL_Z, 2.6, y0p - 1, y1p + 1))
        b = b.cut(cyl_x(sg * 54.0, PUL_Z, M3 / 2, FIN_START_X, X1 + 1))
        # outer ledges the belt rides on (same as the track walls), and the heat-set inserts for the lid
        yl0, yl1 = sorted((sg * 44.0, sg * WALL_IN_UP))
        b = b.union(box(FIN_START_X + 12, X1, yl0, yl1, BELT_BACK_LOW - 2, BELT_BACK_LOW))
        b = b.cut(cyl_z(X1 - 6, sg * 54.0, M3_INSERT / 2, WALL_TOP - 7, WALL_TOP + 1))
    # fin lanes where the fins come down round the start idlers, and the start of the tapered side guides
    b = b.cut(fin_groove(FIN_START_X - 7, X1 + 1, 40.0))
    for sg in (-1, 1):
        b = b.union(guide_rail(TAPER_X0, X1, sg, chamfer=False))
    # card-clear sensor (TCRT5000 reflective IR) under a slot in the floor at X 127, |Y| 22: the track only
    # steps once the card's tail has left it, so a fin can't come down on a card
    b = b.cut(box(122.5, 131.5, -24.0, -20.0, PATH - 5, PATH + 1))
    b = b.cut(box(121.8, 132.2, -25.0, -19.0, PATH - 12, PATH - 3.9))
    b = b.union(box(119.8, 134.2, -27.0, -17.0, PATH - 13, PATH - 4).cut(box(121.8, 132.2, -25.0, -19.0, PATH - 14, PATH - 3.9)))
    # tower dovetail rails on top (tower slides on from the back, +Y)
    for x in (TOWER_X0 - 9, TOWER_X0 + TOWER_IN_X - 3):     # exit-side rail sits under the tower wall (fins sweep past it)
        b = b.union(box(x, x + 6, -40, 40, PATH, PATH + 3))
    # heat-set inserts for the tower thumb screws and the pressure-roller arm
    for (x, y) in ((TOWER_X0 - 6, -45), (TOWER_X0 - 6, 45), (EXIT_X, -21), (EXIT_X, 21)):
        b = b.cut(cyl_z(x, y, M3_INSERT / 2, PATH - 8, PATH + 1))
    # magnet pockets for the tower-ID magnets read by the hall sensors (two positions)
    for y in (-30, 30):
        b = b.cut(cyl_z(TOWER_X0 - 6, y, 3.1, PATH - 3.2, PATH + 1))
    return b

def raw_tower():
    """L-shaped open hopper for raw cards: back wall (+Y) and exit wall (+X) only, inside 89.5 x 64.5 mm,
    about 550 cards. Leans 3 degrees back and 3 degrees toward the exit, so the stack rests in that corner,
    square against the gate; front and entry sides are open for loading. The bottom card still lies flat on the
    floor; the base skirt keeps the bottom few cards in on the open sides."""
    t = 3.5
    xo0, xo1 = TOWER_X0 - t, TOWER_X0 + TOWER_IN_X + t
    yo0, yo1 = -TOWER_IN_Y / 2 - t, TOWER_IN_Y / 2 + t
    xi1, yi1 = TOWER_X0 + TOWER_IN_X, TOWER_IN_Y / 2
    back = box(TOWER_X0 + 6, xo1, yi1, yo1, PATH - 6, PATH + TOWER_H)          # back wall
    exitw = box(xi1, xo1, yo0 + 6, yo1, PATH - 6, PATH + TOWER_H)              # exit wall (carries the gate)
    for sg in (-1, 1):   # 1 mm relief on the outside, low down beside the gate track: the fins sweep past here
        exitw = exitw.cut(box(xi1 + 2.5, xo1 + 1, *sorted((sg * 22.0, sg * 50.0)), PATH - 7, PATH + 40))
    walls = back.union(exitw)
    # corner gusset and top rim for stiffness
    walls = walls.union(box(xi1 - 8, xi1, yi1 - 8, yi1, PATH + 20, PATH + TOWER_H))
    walls = walls.cut(box(xi1 - 9, xi1 - 0.01, yi1 - 9, yi1 - 0.01, PATH + 19, PATH + TOWER_H + 1)
                      .cut(box(xi1 - 9, xi1 + 1, yi1 - 9, yi1 + 1, PATH + 19, PATH + TOWER_H + 1)
                           .cut(cq.Workplane("XY").polyline([(xi1 - 8, yi1), (xi1, yi1), (xi1, yi1 - 8)]).close()
                                .extrude(TOWER_H + 2).translate((0, 0, PATH + 18)))))
    walls = walls.union(box(TOWER_X0 + 6, xo1, yi1 - 3, yi1, PATH + TOWER_H - 6, PATH + TOWER_H))
    walls = walls.union(box(xi1 - 3, xi1, yo0 + 6, yi1, PATH + TOWER_H - 6, PATH + TOWER_H))
    # gate track on the exit face (+X) + boss for the M3 adjust screw
    gx = xo1
    walls = walls.union(box(gx, gx + 6, -20, 20, PATH + 6, PATH + 40))
    walls = walls.cut(box(gx + 1, gx + 6.1, -14, 14, PATH + 5, PATH + 41))
    walls = walls.union(box(gx, gx + 10, -6, 6, PATH + 40, PATH + 46))
    walls = walls.cut(cyl_z(gx + 5, 0, 1.4, PATH + 39, PATH + 47))
    # lean: back about the X axis through the floor line, then toward the exit about the Y axis through the exit wall foot
    walls = walls.rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN)
    walls = walls.rotate((xi1, 0, PATH), (xi1, 1, PATH), TOWER_LEAN_X)
    # flat bottom: walls stop 3 mm above the floor, the exit wall 6 mm (that's where cards leave)
    walls = walls.cut(box(xo0 - 20, xo1 + 20, -80, 80, PATH - 20, PATH + 3))
    walls = walls.cut(box(xi1 - 1, xo1 + 1, -TOWER_IN_Y / 2, TOWER_IN_Y / 2 + 4, PATH - 1, PATH + 6))
    # base skirt (frame on the base rails); 9 mm high on the open sides keeps the bottom cards in
    skirt = box(xo0 - 9, xo1 + 1, -45, 45, PATH + 3, PATH + 9)     # stops at the exit wall so the fins clear it
    skirt = skirt.cut(box(TOWER_X0, xo1 + 1, -TOWER_IN_Y / 2, TOWER_IN_Y / 2 + 4, PATH + 2, PATH + 10))
    for y in (-40, 40):
        skirt = skirt.cut(cyl_z(TOWER_X0 - 6, y, M3 / 2, PATH, PATH + 12))
    for y in (-30, 30):
        skirt = skirt.cut(cyl_z(TOWER_X0 - 6, y, 3.1, PATH + 3, PATH + 6.3))
    return walls.union(skirt)

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
    yf0, yf1 = -(yc - FIN_REACH_Y), -(yc - (RAIL_IN - 1.0))     # finger |Y| 27 .. 32.75 (clears the hinge knuckles)
    f = box(0, 5, -1.75, 1.75, zb0, 0)                                  # leg
    f = f.union(box(0, 5, yf0, 1.75, zb0, zb1))                         # bridge
    f = f.union(box(1.5, 5, yf0, yf1, z_floor - (GROOVE_D - 0.5), zb0))  # finger (pushing face at x = 5)
    f = f.cut(box(4.0, 5.1, yf0 + 1.5, yf0 + 4.5, z_floor - 0.2, z_floor + 2.8))   # pad pocket, 1 mm deep
    f = f.cut(cyl_z(2.0, 0, 0.8, -4.5, 0.1))                            # 1.6 mm pilot for the M2 screw
    return f

def belt_drill_jig():
    """Clamps on a straight run of the 10 mm belt, teeth down on printed GT2 ridges, so every fin hole is drilled
    on the belt's centre line at a tooth. Two 2.1 mm guide holes 52 and 53 teeth from the index ridge set the
    alternating 104 / 106 mm fin spacing (105 mm average). Same jig for the 4 splice holes."""
    L = 130.0
    j = box(0, L, -9, 9, 0, 6)
    j = j.cut(box(-1, L + 1, -5.1, 5.1, 3, 7))               # belt channel (10.2 wide)
    for k in range(int(L / 2)):
        j = j.union(box(2 * k + 0.6, 2 * k + 1.4, -5.1, 5.1, 3, 3.75))   # tooth ridges at 2 mm pitch
    for x in (2.0 + 1.0, 2.0 + 1.0 + 104.0, 2.0 + 1.0 + 106.0):
        j = j.cut(cyl_z(x, 0, 1.05, -1, 8))
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
    Drive: 5 mm D bore, hub with an M3 grub screw (captive nut). Axis along Y, centred at the origin."""
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
        p = p.union(cyl_y(0, 0, 8.0, face / 2 + 1.0, face / 2 + 8.0))
        p = p.cut(cyl_y(0, 0, 2.55, -20, 20))
        p = p.cut(cyl_z(0, face / 2 + 4.5, 1.6, 0, 9)).cut(box(-2.9, 2.9, face / 2 + 3.2, face / 2 + 5.8, 3.0, 5.6))
    else:
        p = p.cut(cyl_y(0, 0, 5.55, -10, 10)).union(cyl_y(0, 0, 5.55, -0.5, 0.5).cut(cyl_y(0, 0, 4.0, -1, 1)))
    return p

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

def side_frame(x0, x1, side, drive_floor=False, bin_opening=True, rails=True, bay=False):
    """One side of a track module (side = -1 front, +1 back). Wall + top strip with belt run + foot.
    Floor edge is at |Y| = 35; belt loop at |Y| 41..47 (top run on the rib, return run in the lower slot)."""
    s = side
    yw0, yw1 = sorted((s * WALL_IN, s * WALL_OUT))
    ys0, ys1 = sorted((s * STRIP_IN, s * WALL_IN))
    f = box(x0, x1, yw0, yw1, RAIL_Z, PATH)                      # wall below the floor
    yu0, yu1 = sorted((s * WALL_IN_UP, s * WALL_OUT))
    f = f.union(box(x0, x1, yu0, yu1, PATH, WALL_TOP))          # wall above the floor hides the belt
    f = f.union(box(x0, x1, ys0, ys1, PATH - 12, PATH))         # strip: floor edge
    # ledges under the belt's outer 3 mm (bottom run rests on its back, top run on its tooth tips)
    yl0, yl1 = sorted((s * 44.0, s * WALL_IN_UP))
    f = f.union(box(x0, x1, yl0, yl1, BELT_BACK_LOW - 2, BELT_BACK_LOW))
    f = f.union(box(x0, x1, yl0, yl1, BELT_TEETH_HIGH - 2, BELT_TEETH_HIGH))
    if rails:
        f = f.union(guide_rail(x0, x1, s, xoff=0.0 if x0 > 0 else 1e4))   # bin modules (built at x 0) are past the taper
    for xc in (x0 + 8, x1 - 8):                                   # lid / hood inserts in the wall top
        f = f.cut(cyl_z(xc, s * (WALL_IN_UP + WALL_OUT) / 2, M3_INSERT / 2, WALL_TOP - 7, WALL_TOP + 1))
    # foot over the rail
    yf0, yf1 = sorted((s * WALL_IN, s * (RAIL_Y + 10)))
    f = f.union(box(x0, x1, yf0, yf1, RAIL_Z, RAIL_Z + 6))
    f = rail_slots(f, x0, x1, ys=(s * RAIL_Y,))
    # wire channel on the outside face (servo, sensor and LED looms), open at both ends so it runs through
    # every module; snap-on cover = channel_cover
    cz0, cz1 = (CHAN_Z0, CHAN_Z1) if s > 0 else (CHAN_F0, CHAN_F1)
    yc0, yc1 = sorted((s * WALL_OUT, s * (WALL_OUT + 12)))
    f = f.union(box(x0, x1, yc0, yc1, cz0, cz1))
    yi0, yi1 = sorted((s * (WALL_OUT + 0.01), s * (WALL_OUT + 10)))
    f = f.cut(box(x0 - 1, x1 + 1, yi0, yi1, cz0 + 2, cz1 - 2))
    # lightening window + panel clips (final shell clips onto these bosses)
    if bin_opening:
        f = f.cut(box(x0 + 12, x1 - 12, yw0 - 1, yw1 + 1, RAIL_Z + 20, PATH - 40))
    for xc in (x0 + 8, x1 - 8):
        f = f.cut(cyl_y(xc, PATH - 25, M3_INSERT / 2, s * WALL_OUT - (6 if s > 0 else 0), s * WALL_OUT + (6 if s < 0 else 0)))
    # end faces get two M3 holes so modules bolt to each other (keeps the floor seams flush)
    for xe in (x0, x1):
        for z in (PATH - 30, RAIL_Z + 30):
            f = f.cut(cyl_x(s * (WALL_IN + WALL_OUT) / 2, z, M3 / 2, xe - 8, xe + 8))
        f = f.cut(cyl_x(s * (WALL_IN_UP + WALL_OUT) / 2, PATH + 30, M3 / 2, xe - 8, xe + 8))
    f = f.cut(cyl_y(x0 + 2, PATH - 17.5, M3 / 2, yw0 - 1, yw1 + 1))     # tie-bar screw
    if bay and s < 0:
        # open bay below BAY_TOP so the bin slides out the front; 2.5 mm posts at each end down to the desk
        f = f.cut(box(x0 + POST_T, x1 - POST_T, -(RAIL_Y + 11), -(WALL_IN - 1), -1, BAY_TOP))
        for xa in (x0, x1 - POST_T):
            f = f.union(box(xa, xa + POST_T, -(WALL_OUT + 17), -WALL_IN, 0, BAY_TOP))
            f = f.union(box(xa, xa + POST_T, -(WALL_OUT + 17), -WALL_IN, BAY_TOP - 1, CHAN_F0))
        f = f.cut(box(x0 - 1, x1 + 1, -(RAIL_Y + 11), -(WALL_OUT + 0.01), -1, RAIL_Z + 7).cut(
                  box(x0 - 2, x1 + 2, -(WALL_OUT + 17), -WALL_IN, -1, 0)))   # no front rail foot here
        for xa in (x0, x1 - POST_T):   # posts sit on the desk on small pads (rubber feet)
            f = f.union(box(xa, xa + POST_T, -(WALL_OUT + 17), -WALL_IN, 0, 3))
        # bin-level sensor: VL53L1X carrier slides into a pocket under the strip, looking straight down at
        # Y -42 (into the stack), wires out through the wall to the front channel
        tb = box(x0 + TOF_X - 11, x0 + TOF_X + 11, -WALL_IN, -35.5, PATH - 19, PATH - 12)
        tb = tb.cut(box(x0 + TOF_X - 9.2, x0 + TOF_X + 9.2, -48.6, -35.4, PATH - 17.2, PATH - 14.8))
        tb = tb.cut(cyl_z(x0 + TOF_X, -42.0, 3.5, PATH - 20, PATH - 17))
        f = f.union(tb)
        f = f.cut(box(x0 + TOF_X - 3, x0 + TOF_X + 3, -(WALL_OUT + 1), -(WALL_IN - 1), PATH - 17.2, PATH - 14.8))
    if bay and s > 0:
        # foot reaching in to the second back rail under the doors
        f = f.union(box(x0, x1, RAIL2_Y - 10, WALL_IN, RAIL_Z, RAIL_Z + 6))
        f = rail_slots(f, x0, x1, ys=(RAIL2_Y,))
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
    fl = box(x0 + 0.5, x1 - 5.5, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 3, PATH)   # tie-bar plate covers the last 5 mm
    fl = fl.cut(fin_groove(x0 - 1, x1 + 1, STRIP_IN))
    fl = fl.union(box(x0 + 0.5, x1 - 0.5, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 10, PATH - 7))  # ribs
    for xc in (x0 + 20, x1 - 20):
        fl = fl.union(box(xc - 2, xc + 2, -STRIP_IN + 0.2, STRIP_IN - 0.2, PATH - 10, PATH))
    return fl.cut(fin_groove(x0 - 1, x1 + 1, STRIP_IN))

def hood():
    """Light-tight hood over the scan position. 155 x 150 x 165 mm (6.1 x 5.9 x 6.5 in), 3 mm walls.
    Inside: camera plate on top, ledges for the LED channels on all four walls, slots for the belts."""
    x0, x1, y0, y1 = HOOD_X0, HOOD_X1, -75.0, 75.0
    h = box(x0, x1, y0, y1, PATH + 10, PATH + HOOD_H)
    h = h.cut(box(x0 + 3, x1 - 3, y0 + 3, y1 - 3, PATH + 9, PATH + HOOD_H - 3))
    # card tunnel through both end walls
    h = h.cut(box(x0 - 1, x1 + 1, -(WALL_OUT + 0.5), WALL_OUT + 0.5, PATH + 9, WALL_TOP + 0.5))   # track + walls pass through
    # pads at the four corners sit on the wall tops; M3 into the wall-top inserts
    for xa, xb in ((x0 + 3, x0 + 19), (x1 - 19, x1 - 3)):
        for sg in (-1, 1):
            y0p, y1p = sorted((sg * WALL_IN_UP, sg * 72.5))
            h = h.union(box(xa, xb, y0p, y1p, WALL_TOP, WALL_TOP + 5))
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
    h = h.cut(cyl_y(SCAN_X, WALL_TOP + 10, 6, y1 - 4, y1 + 1))
    # feet that sit on the scan-module walls, M3 holes
    for s in (-1, 1):
        for xc in (x0 + 8, x1 - 8):
            if SCAN_X0 + 8 <= xc <= SCAN_X1 - 8 or True:
                h = h.cut(cyl_z(xc, s * (WALL_IN_UP + WALL_OUT) / 2, M3 / 2, WALL_TOP - 1, WALL_TOP + 6))
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
    L, W, T = 94.0, 69.6, 2.4               # 94 long: leaves 5.5 mm each end for the tie-bar floor bridges
    d = box(0, L, -W / 2, W / 2, -T, 0)
    d = d.cut(fin_groove(-1, L + 1, W / 2 + 1).translate((0, 0, -PATH)))   # fin lanes along both long edges
    for xk in (1, L / 2 - 8, L - 16):       # hinge knuckles (between the frame knuckles)
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
    f = side_frame(x0, x1, side, bay=True)
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
    """Ties the front and back walls together at the start of each module (x 0..4), under the floor, and
    bridges the floor across the joint (top plate flush with the doors, x -5..5) so a card's leading edge can't
    dip into a gap. M3 screws come in through both walls into heat-set inserts in the bar ends."""
    t = box(0, 4, -(WALL_IN - 0.2), WALL_IN - 0.2, PATH - 22, PATH - 13)
    t = t.union(box(0, 4, -32.8, 32.8, PATH - 13, PATH - 2.4)).union(box(-5, 5, -32.8, 32.8, PATH - 2.4, PATH))
    t = t.cut(fin_groove(-6, 6, 34.0))
    for s in (-1, 1):
        t = t.cut(cyl_y(2, PATH - 17.5, M3_INSERT / 2, *sorted((s * (WALL_IN - 7), s * WALL_IN))))
    return t

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

def end_side(side):
    """End module side: one full pitch (105 mm) so the end-of-line bin sits fully under it; carries the end
    idler pulley stub shaft. There's no floor here: cards are pushed off the end of the last door."""
    x0, x1 = 0.0, PITCH
    f = side_frame(x0, x1, side, bin_opening=False, rails=False, bay=(side < 0))
    s = side
    xs = END_SHAFT_X - (BIN_X[1] + PITCH / 2)            # drive shaft position in this module (86.5)
    f = f.cut(cyl_y(xs, PUL_Z, 2.75, -WALL_OUT - 1, WALL_OUT + 1))
    yb0, yb1 = sorted((s * (WALL_OUT - 5.2), s * (WALL_OUT + 0.1)))
    f = f.cut(cyl_y(xs, PUL_Z, 8.05, yb0, yb1))           # 625 bearing seat (outer face)
    f = f.cut(box(xs - 20, PITCH + 1, *sorted((s * 35.0, s * WALL_IN_UP)), PATH, WALL_TOP + 1))  # room for pulley + fins
    if s > 0:   # track motor on a 30 mm standoff on the back wall, screws into inserts
        for dx in (-1, 1):
            for dz in (-1, 1):
                f = f.cut(cyl_y(xs + dx * NEMA_HOLES / 2, PUL_Z + dz * NEMA_HOLES / 2, M3_INSERT / 2, WALL_OUT - 6.5, WALL_OUT + 1))
    f = f.cut(box(x0 + 12, x1 - 12, *sorted((s * WALL_IN - s, s * WALL_OUT + s)), RAIL_Z + 20, PATH - 40))
    return f

def end_cap():
    """Closes the end of the track above the last bin (catches cards that overshoot)."""
    c = box(0, 4, -(WALL_OUT - 1), WALL_OUT - 1, PATH - 60, WALL_TOP)   # stops 1 mm short of the motor standoff
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
PRINTED = {
    # name: (builder, qty, material, note)
    "feeder_base":     (feeder_base, 1, "PETG", "Upright, 15% gyroid, 4 walls. ~19 h."),
    "raw_tower":       (raw_tower, 1, "PETG", "Upright, 3 walls. L-shaped: back + exit walls, leans 3 deg back and 3 deg toward the exit."),
    "gate_plate":      (gate_plate, 1, "PETG", "Foot down. Glue a 1.5 mm silicone pad strip under the foot."),
    "feed_roller":     (feed_roller, 1, "PETG", "Flat on its end, 100% infill. Fit three 24 x 3.5 mm O-rings."),
    "exit_roller":     (exit_roller, 2, "PETG", "Flat on its end, 100% infill. Two 16 x 3.5 mm O-rings each."),
    "pressure_arm":    (pressure_arm, 1, "PETG", "Flat."),
    "stack_weight":    (stack_weight, 1, "PLA", "Add 4 M8 washers in the pocket."),
    "fin":             (fin, 24, "PETG", "12 + 12 mirrored (10 per side + spares). On its side, 0.12 mm layers. Glue a 3 x 3 mm silicone square in the face pocket."),
    "belt_drill_jig":  (belt_drill_jig, 1, "PETG", "Ridges up. 2 mm drill through the guide holes."),
    "fin_gauge":       (fin_gauge, 1, "PETG", "Flat."),
    "track_pulley_idler": (lambda: track_pulley(False), 2, "PETG", "Axis vertical, 0.12 mm layers, 100% infill. 2 x 685ZZ each. Test-fit the belt first."),
    "track_pulley_drive": (lambda: track_pulley(True), 2, "PETG", "Hub up, 0.12 mm layers, 100% infill. M3 nut + grub screw."),
    "sensor_clip":     (sensor_clip, 4, "PETG", "Holds an Adafruit break-beam half (20 x 10 x 8 housing)."),
    "motor_standoff":  (motor_standoff, 2, "PETG", "On its side, 5 walls. One for the feed motor, one for the track motor (end module)."),
    "scan_side_front": (lambda: side_frame(SCAN_X0, SCAN_X1, -1, bin_opening=False), 1, "PETG", "On its outer face."),
    "scan_side_back":  (lambda: scan_side_back(), 1, "PETG", "On its outer face."),
    "scan_floor":      (scan_floor, 1, "PLA matte black", "Top face DOWN on the smooth side of the plate: flat, slick, dull."),
    "hood":            (hood, 1, "PLA matte black", "Upside down (roof on the plate), tree supports for the tunnel only. ~16 h."),
    "camera_plate":    (camera_plate, 1, "PETG", ""),
    "polarizer_cap":   (polarizer_cap, 1, "PETG", ""),
    "bin_side_back":   (lambda: bin_module_side(1), 2, "PETG", "On its outer face; one per bin module."),
    "bin_side_front":  (lambda: bin_module_side(-1), 2, "PETG", "On its outer face; one per bin module."),
    "door":            (door, 2, "PETG", "Top face down on the smooth plate side (slick surface)."),
    "servo_link":      (servo_link, 2, "PETG", ""),
    "tie_bar":         (tie_bar, 4, "PETG", "Floor plate face DOWN on the smooth side of the plate (slick top)."),
    "end_bin":         (lambda: bin_box(depth=END_BIN_D), 1, "PLA", "Open side up, 2 walls, 10% infill. Deeper: catches cards pushed off the end of the track."),
    "bin":             (bin_box, 2, "PLA", "Open side up, 2 walls, 10% infill. Big front window + a fill mark every 100 cards. ~5 h each."),
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
    P["gate_plate"] = (gate_plate().translate((TOWER_X0 + TOWER_IN_X + 3.5 + 1, 0, PATH + 0.45))
                       .rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN)
                       .rotate((TOWER_X0 + TOWER_IN_X, 0, PATH), (TOWER_X0 + TOWER_IN_X, 1, PATH), TOWER_LEAN_X))
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
        P[f"door_{i}"] = door().translate((x0 + 5.5, 0, PATH))
    for i, xb in enumerate(BIN_X):
        if i < 2:
            P[f"bin_{i}"] = bin_box().translate((xb, BIN_Y, 0.0))
        else:   # end bin catches cards pushed off the end (centred), front lined up with the others
            P[f"bin_{i}"] = bin_box(depth=END_BIN_D).translate((xb, END_BIN_Y, 0.0))
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
    P["mount_wall_gap"] = mount_wall().rotate((0, 0, 0), (0, 0, 1), 180).translate((175, -WALL_OUT - 9, PATH - 21))
    xe = BIN_X[1] + PITCH / 2
    P["end_side_front"] = end_side(-1).translate((xe, 0, 0))
    P["end_side_back"] = end_side(1).translate((xe, 0, 0))
    P["end_cap"] = end_cap().translate((xe + PITCH, 0, 0))
    for k, xj in enumerate((BIN_X[0] - PITCH / 2, BIN_X[1] - PITCH / 2, BIN_X[1] + PITCH / 2)):
        P[f"tie_bar_{k}"] = tie_bar().translate((xj, 0, 0))
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
