"""Every cable on the 3-bin machine: where it starts, the way it goes, how long the run is, and what length it has
(or what to buy). Routes are lists of points through the real openings in the CAD (windows, channels, holes).
Run:  python3 wiring.py  -> writes ../WIRING.md.  fitcheck.py imports runs() and checks each one."""
import math, os
from sorter import *

# ---- landmarks (machine coordinates, mm)
SKR = (60.0, -22.0, 60.0)                         # SKR Pico on the electronics tray (bay under the hopper)
PCA = (59.0, 46.0, 96.0)                          # PCA9685 servo board on the bay's back inner wall
CONV5 = screen_xf(CONV_X, 26.0, CONV_Z)            # 24 V -> 5 V USB-C converter, in the screen pod beside the Pi
CONV6 = (11.0, 18.0, 105.0)                       # 24 V -> 6 V servo step-down, on the bay's left inner wall
BAY_BACK = (75.0, 62.0, 56.0)                     # cable window in the feeder base's back wall
PASS = (148.0, 0.0, 50.0)                         # pass-through from the bay into the space under the scanner
BAY_SLOT = (129.0, -63.0, 106.0)                  # slot in the bay cover (USB-C + the Pi's jumper loom)
BACK_CH = lambda x: (x, 61.0, 39.0)               # back wire channel (every module, outside face)
FRONT_CH = lambda x: (x, -61.0, 161.0)            # front wire channel (scan + bin modules)
FRONT_HOLE = (163.0, -51.0, 161.0)                # hole from the front channel into the scan module
PSU_T = (PSU_X0, 0.0, 70.0)                       # PSU terminal block (faces the bay)
INLET = (SCAN_X0 + 90.0, 40.0, RAIL_Z + 63.0)     # IEC inlet (back of the scan module)
HOOD_LED_EXIT = (HOOD_X1 - 14.0, 78.0, WALL_TOP + 22.0)
PI_HDR = screen_xf(0.0, 12.0, PI_ON_SCREEN_Z + 3.5)   # Pi's 40-pin header (bottom edge of the Pi, in the pod)
POD_NOTCH = screen_xf(USBC_X, POD_D, 2.0)

def L(pts):
    return 0.0 if not pts else sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

def runs():
    """(cable, from, to, route words, run mm, have mm or None, what to use)"""
    out = []
    def add(cable, frm, to, route, pts, have, use):
        out.append(dict(cable=cable, frm=frm, to=to, route=route, run=L(pts), have=have, use=use))
    # --- power
    add("Mains (IEC inlet -> PSU)", "IEC inlet, back of scan module", "PSU L / N / earth", "inside the scan module",
        [INLET, (INLET[0], 10, INLET[2]), PSU_T], 150, "the inlet's own pre-wired 18 AWG leads")
    for nm, dst, extra in (("SKR Pico", SKR, "VIN screw terminal"), ("6 V step-down (servos)", CONV6, "red/black leads")):
        add(f"24 V -> {nm}", "PSU +V / -V", f"{nm} {extra}", "PSU -> pass-through -> bay", [PSU_T, PASS, dst], None,
            "18 AWG red/black, cut to length")
    add("24 V -> 5 V USB-C converter (in the screen pod)", "PSU +V / -V", "converter red/black leads",
        "PSU -> pass-through -> bay -> bay-cover slot -> hangs free with the Pi's loom -> pod notch",
        [PSU_T, PASS, (130, -40, 80), BAY_SLOT, POD_NOTCH, CONV5], None,
        "20 AWG red/black spliced onto the converter's leads (solder + heat-shrink), in the loom's braided sleeve")
    add("6 V -> servo board", "6 V step-down out", "PCA9685 V+ terminal", "inside the bay", [CONV6, PCA], None, "18 AWG pair")
    port = screen_xf(USBC_X, 10, PI_ON_SCREEN_Z + 56)
    add("USB-C power (Pi)", "5 V USB-C converter (in the pod)", "Pi 5 USB-C", "inside the pod (coil the spare beside the converter)",
        [CONV5, screen_xf(CONV_X + 10, 20, PI_ON_SCREEN_Z + 70), port], 305 - 25, "the converter's own 12 in (305 mm) lead")
    # --- Pi (in the screen pod): ribbons + one jumper loom down to the bay
    add("Camera ribbon", "Pi 5 CAM/DISP 0", "HQ camera (connector facing front)", "out the pod's back -> soft fold -> hood's left-wall slot -> up under the L-rails -> across to the camera",
        None, 500, "Pi 5 camera cable, 500 mm (22-pin mini -> 15-pin standard)")
    out[-1]["run"] = camera_ribbon()[1]
    add("Display ribbon + power", "Pi 5 CAM/DISP 1 + pins 2/6", "Touch Display 2", "inside the pod", [(0, 0, 0), (0, 0, 60)], 100,
        "the cables in the display box")
    loom = [PI_HDR, POD_NOTCH, BAY_SLOT, (BAY_SLOT[0], -40, 80)]
    add("UART to the motor board (TX, RX, GND)", "Pi pins 8, 10, 6", "SKR Pico UART header", "pod -> notch -> bay-cover slot -> tray",
        loom + [SKR], 400, "female-female jumpers, 40 cm (in one black braided sleeve with the rest of the loom)")
    add("I2C + 3.3 V (servo board, bin sensors)", "Pi pins 1, 3, 5, 9", "PCA9685 VCC/SDA/SCL/GND (in); its out header feeds the bin sensors",
        "same loom", loom + [PCA], 400, "female-female jumpers, 40 cm")
    add("Bin-sensor XSHUT x3 + beam signals x2", "Pi GPIO 17, 27, 22, 5, 6", "bay junction -> front-channel looms",
        "same loom to the bay", loom + [(130, -30, 70)], 400, "female-female jumpers, 40 cm, joined in the bay")
    # --- motor board side
    add("Feed motor", "feeder base back wall (NEMA 17)", "SKR Pico X driver", "down the back of the base -> back window -> tray",
        [(FEED_X, 138, FEED_Z), (FEED_X, 66, FEED_Z), BAY_BACK, SKR], 1000, "the motor's own 1 m cable (coil the spare)")
    xe, ze = END_SHAFT_X, PUL_Z
    add("Track motor", "end module back (NEMA 17)", "SKR Pico Y driver", "down the end module -> back channel -> back window -> tray",
        [(xe, 133, ze), (xe, 62, ze), BACK_CH(xe), BACK_CH(150), BAY_BACK, SKR], 2000, "its 1 m cable + a 1 m 4-pin stepper extension (BUY)")
    add("Card-clear sensor (TCRT5000)", "under the floor at the feeder exit", "SKR X-STOP (3.3 V, GND, signal)", "inside the feeder base",
        [(127, -22, PATH - 8), (127, -22, 80), SKR], 300, "female-female jumpers, 30 cm")
    add("Belt-home sensor (TCRT5000)", "under the scan module's back strip", "SKR Y-STOP", "out the back wall -> down -> back channel -> back window",
        [(HOME_X + 30, 55, PATH - 18), (HOME_X + 30, 62, PATH - 18), BACK_CH(HOME_X + 30), BACK_CH(150), BAY_BACK, SKR], 500,
        "female-female jumpers, 50 cm (BUY)")
    add("Hood LED strips (2 x COB channels)", "SKR HE0 (24 V switched)", "COB strips on the front + back ledges, joined inside the hood",
        "tray -> back window -> back channel -> up the back of the scan module -> hood's LED hole",
        [SKR, BAY_BACK, BACK_CH(150), BACK_CH(HOOD_LED_EXIT[0]), (HOOD_LED_EXIT[0], 62, HOOD_LED_EXIT[2]), HOOD_LED_EXIT,
         (HOOD_LED_EXIT[0], 70, PATH + LED_H + 2), (HOOD_X0 + 10, 70, PATH + LED_H + 2)], None, "22 AWG red/black, ~1 m (+ 15 cm jumper to the front strip)")
    add("Sheen LED (20 mm of COB strip)", "SKR FAN2 (jumper on 24 V)", "sheen_cap on the hood's back wall", "with the LED pair, last 7 cm outside the hood back",
        [SKR, BAY_BACK, BACK_CH(150), BACK_CH(HOOD_LED_EXIT[0]), (HOOD_LED_EXIT[0], 62, HOOD_LED_EXIT[2]), (SCAN_X, 80, WALL_TOP + 2)], None,
        "22 AWG pair, ~1 m")
    # --- servo board / bins
    for i, xb in enumerate(BIN_X[:2]):
        x0 = xb - PITCH / 2
        add(f"Door servo, bin {i + 1}", f"back wall of bin module {i + 1}", f"PCA9685 channel {i}", "down the wall -> back channel -> back window -> bay wall",
            [(xb, 66, PATH - 38), BACK_CH(xb), BACK_CH(150), BAY_BACK, PCA], (750, 1250)[i],
            ("servo's 25 cm lead + 50 cm servo extension (BUY)", "servo's 25 cm lead + 1 m servo extension (BUY)")[i])
        add(f"Beam emitter, bin {i + 1}", "back pocket at the bin mouth", "3.3 V + GND (PCA9685 out header)", "down -> back channel -> back window",
            [(x0 + PITCH / 2, 60, PATH - 22), BACK_CH(x0 + PITCH / 2), BACK_CH(150), BAY_BACK, PCA], (750, 1250)[i],
            ("its 25 cm leads + 50 cm servo extension (Dupont crimped on the leads)", "its 25 cm leads + 1 m servo extension (Dupont crimped on the leads)")[i])
        add(f"Beam receiver, bin {i + 1}", "front pocket at the bin mouth", f"Pi GPIO {(5, 6)[i]} (via the loom) + 3.3 V/GND",
            "front channel -> hole into the scan module -> pass-through -> bay",
            [(x0 + PITCH / 2, -60, PATH - 22), FRONT_CH(x0 + PITCH / 2), FRONT_CH(FRONT_HOLE[0]), FRONT_HOLE, PASS, (130, -30, 70)], 750,
            "its 25 cm leads + 50 cm servo extension (Dupont crimped on the leads)")
    for i, xb in enumerate(BIN_X):
        x0 = xb - PITCH / 2
        add(f"Bin-level sensor (VL53L1X), bin {i + 1}", "pocket under the front strip", "I2C chain from the PCA9685 out header + XSHUT",
            "out through the front wall -> front channel -> hole -> pass-through -> bay",
            [(x0 + TOF_X, -51, PATH - 16), FRONT_CH(x0 + TOF_X), FRONT_CH(FRONT_HOLE[0]), FRONT_HOLE, PASS, PCA], None,
            "5 x 26 AWG soldered to the carrier (VIN, GND, SDA, SCL, XSHUT)")
    add("Bay fan (optional, 30 mm)", "bay cover", "SKR FAN3 (24 V fan)", "inside the bay", [(115, -60, 56), SKR], 150, "fan's own leads")
    return out

def fmt(mm):
    return f"{mm:.0f} mm ({mm / 25.4:.1f} in)"

if __name__ == "__main__":
    rows = runs()
    lines = ["# Wiring: every cable on the 3-bin machine", "",
             "Generated by `cad/wiring.py` from the CAD (routes go through the real windows, channels and holes; run length",
             "includes the bends, plus 15% slack in the check). `cad/fitcheck.py` fails if any run is longer than what it has.", "",
             "| Cable | From | To | Route | Run | Have / use | OK |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        need = r["run"] * 1.15
        ok = "cut to length" if r["have"] is None else ("yes" if r["have"] >= need else "**extend**")
        have = r["use"] if r["have"] is None else f'{fmt(r["have"])}: {r["use"]}'
        lines.append(f'| {r["cable"]} | {r["frm"]} | {r["to"]} | {r["route"]} | {fmt(r["run"])} | {have} | {ok} |')
    lines += ["", "Pi 5 GPIO used: UART 14/15 (pins 8/10) to the SKR Pico, I2C SDA/SCL (pins 3/5), beam receivers GPIO 5/6,",
              "bin-sensor XSHUT GPIO 17/27/22, display power on pins 2 (5 V) and 6 (GND), 3.3 V on pin 1, more GND on 9/14/20.",
              "SKR Pico used: X (feed), Y (track), X-STOP (card-clear), Y-STOP (belt-home), HE0 (hood LEDs), FAN2 (sheen LED,",
              "voltage jumper on 24 V), FAN3 (bay fan), VIN 24 V, UART header to the Pi. All grounds are common (PSU -V)."]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "WIRING.md")
    open(p, "w").write("\n".join(lines) + "\n")
    for r in rows:
        print(f'{r["cable"][:44]:44s} run {r["run"]:6.0f}  have {r["have"] if r["have"] else "-":>5}')
