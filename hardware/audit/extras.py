"""Bought parts / hardware placed in machine coordinates (envelopes incl. plug keep-outs), for the audit."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
from sorter import *
import bought as B

def extras():
    E = {}
    E["motor_standoff_feed"] = motor_standoff().translate((FEED_X, 60.0, FEED_Z))
    E["motor_standoff_track"] = motor_standoff().translate((END_SHAFT_X, WALL_OUT, PUL_Z))
    E["nema_feed"] = B.nema17().translate((FEED_X, 60.0 + 30, FEED_Z))
    E["nema_track"] = B.nema17().translate((END_SHAFT_X, WALL_OUT + 30, PUL_Z))
    E["coupler_feed"] = cyl_y(FEED_X, FEED_Z, 9.5, 60 + 2.5, 60 + 27.5)
    E["coupler_track"] = cyl_y(END_SHAFT_X, PUL_Z, 9.5, WALL_OUT + 2.5, WALL_OUT + 27.5)
    for sg, nm in ((1, "b"), (-1, "f")):
        E[f"idler_{nm}"] = track_pulley(False).translate((FIN_START_X, sg * 42.0, PUL_Z))
        E[f"drive_{nm}"] = (track_pulley(True) if sg > 0 else track_pulley(True).mirror("XZ")).translate((END_SHAFT_X, sg * 42.0, PUL_Z))
        y0, y1 = sorted((sg * 36.6, sg * 59.8))
        E[f"idler_stub_{nm}"] = cyl_y(FIN_START_X, PUL_Z, 2.5, y0, y1)
    E["shaft_feed"] = cyl_y(FEED_X, FEED_Z, 2.5, -58, 62.5 + 12)
    E["shaft_exit"] = cyl_y(EXIT_X, EXIT_Z, 2.5, -58, 58)
    E["shaft_track"] = cyl_y(END_SHAFT_X, PUL_Z, 2.5, -WALL_OUT, WALL_OUT + 2.5 + 12)
    E["shaft_pressure"] = cyl_y(EXIT_X, PR_Z, 2.5, -20, 20)
    E["loop_pulleys_122"] = cyl_y(FEED_X, FEED_Z, 8, -55, -39).union(cyl_y(EXIT_X, EXIT_Z, 8, -55, -39))
    E["psu_body"] = box(PSU_X0, PSU_X0 + PSU_L, PSU_Y[0], PSU_Y[1], RAIL_Z + 6, RAIL_Z + 6 + 97)
    E["psu"] = B.lrs100().translate((PSU_X0, 0, RAIL_Z + 6)).translate((0, sum(PSU_Y) / 2, 0))
    # IEC inlet: flange outside the plate, body + clips + fastons + 18 AWG bend behind it (35 + 15 mm)
    xi, zi = SCAN_X0 + 32 + 14, RAIL_Z + 39 + 20
    E["iec_inlet"] = box(xi - 3, xi + 47.5 + 3, WALL_OUT + 4, WALL_OUT + 8, zi - 3, zi + 27.5 + 3).union(
        box(xi, xi + 47.5, WALL_OUT - 35 - 15 + 4 - 2.5, WALL_OUT + 4, zi, zi + 27.5))
    tray_z = RAIL_Z + 17.0 + 3
    E["skr"] = B.skr_pico().translate((SKR_X - 3.5, SKR_Y0, tray_z + 8))
    E["conv6"] = B.potted_converter().rotate((0, 0, 0), (0, 1, 0), 90).translate((4.3, 8.0, 105.0))
    E["bay_fan"] = box(108, 138, -60 + 0.0, -50, RAIL_Z + 12 + 24 - 15, RAIL_Z + 12 + 24 + 15)
    E["hall_leads"] = cyl_z(HALL[0][0], HALL[0][1], 5.0, PATH - 30, PATH - 4).union(cyl_z(HALL[1][0], HALL[1][1], 5.0, PATH - 30, PATH - 4))
    E["card_clear_tcrt"] = box(CARD_CLEAR_X - 5.0, CARD_CLEAR_X + 5.0, -24.9, -19.1, PATH - 11.0, PATH - 4.0)
    E["home_tcrt"] = box(HOME_X - 5.0, HOME_X + 5.0, HOME_Y - 2.9, HOME_Y + 2.9, PATH - 12.0, PATH - 4.5).union(
        box(HOME_X - 6.0, HOME_X + 27.0, HOME_Y - 7.0, HOME_Y + 7.0, PATH - 22.0, PATH - 12.0))
    E["screen_block"] = screen_placed(screen_block())
    E["conv5"] = screen_placed(converter_block())
    E["camera"] = B.hq_camera().translate((SCAN_X, 0, PATH + CAM_D + 44))
    E["camera_plate"] = camera_plate().translate((SCAN_X, 0, PATH + CAM_D + 44 - 4))
    for sg, nm in ((-1, "f"), (1, "b")):                 # LED channels (17 x 8 alu) on the hood ledges
        y0, y1 = sorted((sg * 72.0, sg * 55.0))
        E[f"led_channel_{nm}"] = box(HOOD_X0 + 4, HOOD_X1 - 4, y0, y1, PATH + LED_H, PATH + LED_H + 8)
    for i in range(BINS - 1):
        x0 = BIN_X[i] - PITCH / 2
        xt, (ys, zs) = SERVO_TOP_X, SERVO_S
        horn = box(x0 + xt - 4.0, x0 + xt - 2.0, -99, 99, -999, 999).intersect(servo_placed(0).translate((x0, 0, 0)))
        E[f"servo_{i}"] = servo_placed(0).translate((x0, 0, 0)).cut(box(x0 + xt - 4.01, x0 + xt - 1.99, -99, 99, -999, 999)).union(
            cyl_x(ys, zs, 3.5, x0 + xt - 4.0, x0 + xt))
        E[f"horn_{i}"] = horn.cut(cyl_x(ys, zs, 3.6, x0 + xt - 5, x0 + xt))
        E[f"beam_tx_{i}"] = B.beam_half().translate((BIN_X[i], WALL_OUT + 1, PATH - 22)).cut(box(-1e4, 1e4, WALL_OUT, 1e4, -1e4, 1e4))
        E[f"beam_rx_{i}"] = B.beam_half().mirror("XZ").translate((BIN_X[i], -WALL_OUT - 1, PATH - 22)).cut(box(-1e4, 1e4, -1e4, -WALL_OUT, -1e4, 1e4))
    for i in range(BINS):
        x0 = BIN_X[i] - PITCH / 2
        E[f"tof_{i}"] = box(x0 + TOF_X - 9.0, x0 + TOF_X + 9.0, -48.4, -35.6, PATH - 17.0, PATH - 15.0)
    x0h = BIN_X[HUB_MODULE] - PITCH / 2
    for k, (bx, bz, bw, bh) in HUB_BOARDS.items():
        yf = WALL_IN - 4.0 if k == "pca9685" else WALL_IN + 0.6          # PCA9685 stands on its 4 bosses
        E[f"hub_{k}"] = box(x0h + bx, x0h + bx + bw, yf - 16.0, yf, bz, bz + bh)
    # thin "clamp" plates for the board / tab screws (the PCB or tab the screw passes through)
    tz = RAIL_Z + 17.0 + 3 + 8
    E["v_skr_pcb"] = box(SKR_X - 3.5, SKR_X + 81.5, SKR_Y0, SKR_Y0 + 56, tz, tz + 1.6)
    zc = PATH + CAM_D + 44
    E["v_cam_pcb"] = box(SCAN_X - 19, SCAN_X + 19, -19, 19, zc, zc + 1.6)
    bx, bz, bw, bh = HUB_BOARDS["pca9685"]
    E["v_pca_pcb"] = box(x0h + bx, x0h + bx + bw, WALL_IN - 4.0 - 1.6, WALL_IN - 4.0, bz, bz + bh)
    E["v_home_pcb"] = box(HOME_X + 13, HOME_X + 27, HOME_Y - 7, HOME_Y + 7, PATH - 13 - 1.6, PATH - 13)
    for i in sorted({0, HUB_MODULE, BINS - 2}):
        x0 = BIN_X[i] - PITCH / 2
        ys, zs = SERVO_S; zcs = zs - 5.75
        E[f"v_servo_tab_{i}"] = box(x0 + SERVO_TOP_X + 3.5, x0 + SERVO_TOP_X + 6.0, ys - 5.75, ys + 5.75, zcs - 16.25, zcs + 16.25)
    for y in (-RAIL_Y, RAIL_Y):
        E[f"rail_{int(y)}"] = box(0, SCAN_X1 if y < 0 else END_X0 + END_L, y - 10, y + 10, 0, RAIL_Z)
    E["rail2"] = box(BIN_X[0] - PITCH / 2, END_X0, RAIL2_Y - 10, RAIL2_Y + 10, 0, RAIL_Z)
    return E
