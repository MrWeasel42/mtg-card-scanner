"""Every screw in the machine: where it goes, which way it points (head -> tip), what it clamps, what it threads
into. Positions come from the CAD constants, so a design change moves the screws with it."""
import os, sys, math, json, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import *

HERE = os.path.dirname(os.path.abspath(__file__))
ALL = json.load(open(os.path.join(HERE, "placed", "index.json")))
def without(*pre):
    return [n for n in ALL if not any(n.startswith(p) for p in pre)]

MODS = sorted({0, HUB_MODULE, BINS - 2})            # bin modules checked (all are identical prints)
J = []
def add(name, screw, pts, dir, clamp, thread, **kw):
    if thread[0] == "tnut":
        kw.setdefault("ignore", ("rail",))            # the rail is what the T-nut is in
    if thread[0] == "motor":
        kw.setdefault("ignore", ("nema_",))
    J.append(dict(name=name, screw=screw, pts=pts, dir=dir, clamp=clamp, thread=thread, **kw))

# --- frame: M5 x 10 + 2020 T-nut (T-nut sits 1.8 mm under the rail top, 4 mm thick; slot is 6 deep)
TNUT = ("tnut", 4.0 + 1.8, 4.2)    # 4 mm of foot left under the counterbore, 1.8 mm slot lip, T-nut; slot ~6 deep
xs = [150 / 3, 300 / 3]
add("feeder base -> rails", (5, 10), [(x, y, RAIL_Z + 4) for x in xs for y in (-RAIL_Y, RAIL_Y)], (0, 0, -1),
    ["feeder_base"], TNUT, present=without("bay_cover", "electronics_tray", "psu", "skr", "conv6", "nema_", "motor_standoff"))
sx = [SCAN_X0 + (SCAN_X1 - SCAN_X0) * k / 3 for k in (1, 2)]
add("scan module -> rails (front)", (5, 10), [(x, -RAIL_Y, RAIL_Z + 4) for x in sx], (0, 0, -1), ["scan_side_front"], TNUT)
add("scan module -> rails (back)", (5, 10), [(x, RAIL_Y, RAIL_Z + 4) for x in sx], (0, 0, -1), ["scan_side_back"], TNUT,
    present=without("hood", "sheen_cap", "inlet_plate", "iec_inlet"))
for i in MODS:
    x0 = BIN_X[i] - PITCH / 2
    bx = [x0 + PITCH * k / 3 for k in (1, 2)]
    add(f"bin module {i+1} -> back rail", (5, 10), [(x, RAIL_Y, RAIL_Z + 4) for x in bx], (0, 0, -1), [f"bin_side_back_{i}"], TNUT,
        present=without("hood"))
    add(f"bin module {i+1} -> second rail (from the bay)", (5, 10), [(x, RAIL2_Y, RAIL_Z + 4) for x in bx], (0, 0, -1),
        [f"bin_side_back_{i}"], TNUT, present=without("bin_", "door_", "hood"))
ex = [END_X0 + END_L * k / 3 for k in (1, 2)]
add("end module -> back rail", (5, 10), [(x, RAIL_Y, RAIL_Z + 4) for x in ex], (0, 0, -1), ["end_side_back"], TNUT,
    present=without("nema_track", "motor_standoff_track", "coupler_track"))

# --- feeder
add("tower thumb screws", (3, 16), [(x, y, PATH + 9) for x, y in TOWER_SCREW], (0, 0, -1), ["raw_tower"], ("insert", "feeder_base"))
add("bay cover", (3, 8), [(x, -63, z) for x in (7, 143) for z in (RAIL_Z + 30, RAIL_Z + 90)], (0, 1, 0), ["bay_cover"], ("insert", "feeder_base"))
add("electronics tray hold-downs", (3, 8), [(x, TRAY_SCREW_Y, RAIL_Z + 20) for x in TRAY_SCREW_X], (0, 0, -1),
    ["electronics_tray"], ("insert", "feeder_base"), present=without("skr", "conv6", "bay_cover", "v_"), min_tool=8)
add("SKR Pico -> tray bosses (M2 self-tapping)", (2, 8), [(x, y, RAIL_Z + 20 + 8 + 1.6) for x in (SKR_X, SKR_X + 58) for y in (SKR_Y0 + 3.5, SKR_Y0 + 52.5)],
    (0, 0, -1), ["v_skr_pcb"], ("pilot", "electronics_tray"), present=["electronics_tray", "v_skr_pcb"], head="pan")
for (yw, sgn) in ((60.0, 1),):
    pts = [(FEED_X + dx, yw + 4, FEED_Z + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)]
    add("feed-motor standoff -> base", (3, 10), pts, (0, -1, 0), ["motor_standoff_feed"], ("insert", "feeder_base"),
        present=without("nema_feed", "coupler_feed", "shaft_feed"), min_tool=15)
    add("feed motor -> standoff", (3, 8), [(FEED_X + dx, yw + 26, FEED_Z + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)],
        (0, 1, 0), ["motor_standoff_feed"], ("motor", 4.0, 4.5), present=without("nema_feed", "coupler_feed", "shaft_feed"), min_tool=15)
for sg in (-1, 1):
    nm = "back" if sg > 0 else "front"
    add(f"start idler tension ({nm})", (3, 20), [(FIN_START_X - 16, sg * SLIDER_YC, SLIDER_SCREW_Z)], (1, 0, 0),
        ["feeder_base"], ("insert", f"idler_slider_{nm}"))
add("pressure bridge -> post tops", (3, 10), [(X1_BASE - 6, sg * 54.0, WALL_TOP + 5) for sg in (-1, 1)], (0, 0, -1),
    ["pressure_bridge"], ("insert", "feeder_base"))
# gate adjust screw: down the leaned track axis through the boss into the gate's insert
def lean_pt(x, y, z):
    v = cq.Workplane("XY").add(cq.Vertex.makeVertex(x, y, z))
    v = v.rotate((0, 0, PATH), (1, 0, PATH), -TOWER_LEAN).rotate((TOWER_X0 + TOWER_IN_X, 0, PATH), (TOWER_X0 + TOWER_IN_X, 1, PATH), TOWER_LEAN_X)
    c = v.val().Center(); return (c.x, c.y, c.z)
gx = TOWER_EXIT_X + 3.5 + 1 + GATE_T / 2
a, b = lean_pt(gx, 0, PATH + 46), lean_pt(gx, 0, PATH + 45)
add("gate adjust screw (gate hangs on it)", (3, 12), [a], tuple(b[k] - a[k] for k in range(3)), ["raw_tower"], ("insert", "gate_plate"))

# --- scan module
add("inlet plate", (3, 8), [(x, WALL_OUT + 4, z) for x in (SCAN_X0 + 36, SCAN_X0 + 144) for z in (RAIL_Z + 43, RAIL_Z + 103)],
    (0, -1, 0), ["inlet_plate"], ("insert", "scan_side_back"), present=without("iec_inlet"))
add("belt-home sensor board", (3, 6), [(HOME_X + 23, HOME_Y, PATH - 13 - 1.6)], (0, 0, 1), ["v_home_pcb"], ("insert", "scan_side_back"),
    present=["scan_side_back", "v_home_pcb", "rail_62"], min_tool=10)
for zc, side, yo, dy, nm in ((PSU_SCREW_Z[0], "scan_side_front", -WALL_OUT, 1, "front"), (PSU_SCREW_Z[1], "scan_side_back", WALL_OUT, -1, "back")):
    add(f"PSU cradles ({nm}, M3 nut in the cradle)", (3, 12), [(x, yo, zc) for x in CRADLE_XC], (0, dy, 0), [side],
        ("nut", WALL_OUT - WALL_IN + 0.2 + 0.2, 2.4), present=without("inlet_plate", "iec_inlet"))
add("screen wall mount", (3, 8), [(MOUNT_X + dx, -WALL_OUT - 5, PATH - 21) for dx in (-44.5, 44.5)], (0, 1, 0), ["mount_wall_gap"],
    ("insert", "scan_side_front"), present=without("screen_", "pod_cover", "pod_standoff", "conv5"))
add("hood feet -> wall tops", (3, 10), [(x, sg * TOP_INSERT_Y, WALL_TOP + 5) for x in (HOOD_X0 + 11, SCAN_X1 - 6.0) for sg in (-1, 1)],
    (0, 0, -1), ["hood"], ("insert_any",), present=without("hood_lid", "camera", "v_cam"))
add("sheen cap", (3, 12), [(SCAN_X + dx, 75 + 5 + 6, SHEEN_Z) for dx in (-SHEEN_SCREW_DX, SHEEN_SCREW_DX)], (0, -1, 0), ["sheen_cap"], ("insert", "hood"))
zt = PATH + CAM_D + 44 - 4 + CAM_HOLE_DZ + 4
add("camera plate -> lid ribs (lid off)", (3, 10), [(SCAN_X, sg * (CAM_RIB_X0 + 4), zt) for sg in (-1, 1)], None, ["hood_lid"], ("insert", "camera_plate"),
    present=["hood_lid", "camera_plate", "camera", "v_cam_pcb"], per_point_dir=True)
add("HQ camera -> camera plate (M2 self-tapping)", (2, 8), [(SCAN_X + dx, dy, PATH + CAM_D + 44 + 1.6) for dx in (-15, 15) for dy in (-15, 15)],
    (0, 0, -1), ["v_cam_pcb"], ("pilot", "camera_plate"), present=["camera_plate", "v_cam_pcb"], head="pan")

# --- bin modules
for i in MODS:
    x0 = BIN_X[i] - PITCH / 2
    add(f"bin {i+1}: tie bar (both walls)", (3, 12), [(x0 + TIE_X, sg * WALL_OUT, PATH - 17.5) for sg in (-1, 1)], None,
        [f"bin_side_front_{i}", f"bin_side_back_{i}"], ("insert", f"tie_bar_{i}"), per_point_dir=True, clamp_by_side=True)
    add(f"bin {i+1}: back panel", (3, 8), [(x0 + xh, WALL_OUT + 3, zh) for xh in (6.5, PITCH - 6.5) for zh in (RAIL_Z + 42, PATH - 44)],
        (0, -1, 0), [f"back_panel_{i}"], ("insert", f"bin_side_back_{i}"))
    ys, zs = SERVO_S; zcs = zs - 5.75
    add(f"bin {i+1}: servo tabs -> bracket (M2 self-tapping)", (2, 8), [(x0 + SERVO_TOP_X + 3.5, ys, zcs + dz) for dz in (-13.9, 13.9)], (1, 0, 0),
        [f"v_servo_tab_{i}"], ("pilot", f"bin_side_back_{i}"), present=without("servo_", "door_", "servo_link_", "back_panel_", "hub_"), head="pan")
    le = (HINGE_Y + LEVER_R * math.cos(math.radians(LEVER_A0)), HINGE_Z + LEVER_R * math.sin(math.radians(LEVER_A0)))
    add(f"bin {i+1}: link -> door lever (M2 self-tapping)", (2, 8), [(x0 + LINK_X[1], le[0], le[1])], (-1, 0, 0), [f"servo_link_{i}"],
        ("pilot", f"door_{i}"), head="pan", min_tool=10)
    ht = (le[0] + SERVO_S[0] - HINGE_Y, le[1] + SERVO_S[1] - HINGE_Z)
    add(f"bin {i+1}: link -> servo horn (M2 self-tapping)", (2, 6), [(x0 + LINK_X[0], ht[0], ht[1])], (1, 0, 0), [f"servo_link_{i}"],
        ("fixed", LINK_X[1] - LINK_X[0] + 0.5, 2.0), head="pan", min_tool=10, min_eng=2.0, ignore=(f"horn_{i}",))
for k in range(1, BINS):
    xj = BIN_X[0] - PITCH / 2 + PITCH * k
    if k not in (1, BINS - 1):
        continue
    add(f"joint plates at joint {k} (front + back)", (3, 8), [(xj + dx, sg * (WALL_OUT + 3), JOINT_Z) for dx in (-8, 8) for sg in (-1, 1)],
        None, [f"joint_plate_f{k}", f"joint_plate_b{k}"], ("insert_any",), per_point_dir=True, clamp_by_side=True)

# --- end module
xe = END_X0
add("end ramp flange -> back strip", (3, 8), [(xe + x, 41.0, PATH - 16) for x in (RAMP_X0 + 15, PITCH - 5 - 15)], (0, 0, 1), ["end_ramp"],
    ("insert", "end_side_back"), present=without(f"bin_{BINS-1}"))
add("end cap", (3, 8), [(xe + END_L + 4, sg * yc, zc) for sg in (-1, 1) for (yc, zc) in END_CAP_PTS],
    (-1, 0, 0), ["end_cap"], ("insert_any",), present=without("nema_track", "motor_standoff_track", "coupler_track"))
add("track-motor standoff -> end wall", (3, 10), [(END_SHAFT_X + dx, WALL_OUT + 4, PUL_Z + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)],
    (0, -1, 0), ["motor_standoff_track"], ("insert", "end_side_back"), present=without("nema_track", "coupler_track", "shaft_track"), min_tool=15)
add("track motor -> standoff", (3, 8), [(END_SHAFT_X + dx, WALL_OUT + 26, PUL_Z + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)],
    (0, 1, 0), ["motor_standoff_track"], ("motor", 4.0, 4.5), present=without("coupler_track", "shaft_track"), min_tool=15)

# --- screen pod (cradle frame -> machine)
def sxf(x, y, z):
    return screen_xf(x, y, z)
W, H, T = SCREEN_W + 0.8, SCREEN_H + 0.8, 3.0
x1 = W / 2 + T
pts, dirs = [], []
for sx in (-1, 1):
    for zc in (-0.4 + 15, H - 0.4 - 15):
        a = sxf(sx * (x1 + 4.5), T + 5, zc); b = sxf(sx * (x1 + 4.5), T + 4, zc)
        pts.append(a); dirs.append(tuple(b[k] - a[k] for k in range(3)))
add("pod cover -> screen cradle ears", (3, 10), pts, dirs[0], ["pod_cover"], ("insert", "screen_cradle"), present=without("screen_block", "conv5"))
_y = POD_D - 2.5 - POD_PAD                      # inside face of the pad on the pod's back wall (head seat)
pts = [sxf(-POD_DX + dx, _y, SCR_PIV[2]) for dx in POD_SCREW_DX]
_b = sxf(-POD_DX + POD_SCREW_DX[0], _y + 1, SCR_PIV[2])
add("GoPro standoff -> pod cover (from inside the pod)", (3, 12), pts, tuple(_b[k] - pts[0][k] for k in range(3)),
    ["pod_cover"], ("insert", "pod_standoff"), present=["pod_cover", "pod_standoff"])

JOINTS = J
