"""Every cable on the 3-bin machine: where it starts, the way it goes, how long the run is, and what length it has
(or what to buy). Routes are lists of points through the real openings in the CAD (windows, channels, holes).
Run:  python3 wiring.py  -> writes ../WIRING.md.  fitcheck.py imports runs() and checks each one."""
import math, os
from sorter import *

# ---- landmarks (machine coordinates, mm)
SKR = (SKR_X + 40.0, 0.0, 60.0)                   # SKR Pico on the electronics tray (bay under the hopper)
CONV5 = screen_xf(CONV_X, 26.0, CONV_Z)            # 24 V -> 5 V USB-C converter, in the screen pod beside the Pi
CONV6 = (11.0, 18.0, 105.0)                       # 24 V -> 6 V servo step-down, on the bay's left inner wall
JUNC = (40.0, 40.0, 70.0)                         # bay junction: Pi I2C meets the 6 V pair -> the bin bus
BAY_BACK = (130.0, 50.0, (CHAN_Z0 + CHAN_Z1) / 2)  # where the bay opens into the back channel (base, x 115..146)
PASS = (148.0, 0.0, 50.0)                         # pass-through from the bay into the space under the scanner
BAY_SLOT = (96.0, -63.0, 98.0)                    # slot in the bay cover (USB-C + the Pi's jumper loom), under the window's peak
BACK_CH = lambda x: (x, 61.0, (CHAN_Z0 + CHAN_Z1) / 2)   # back wire channel (every module, outside face)
PSU_T = (PSU_X0 - 4.0, sum(PSU_Y) / 2, 70.0)    # PSU terminal block (faces the bay)
INLET = (SCAN_X0 + 70.0, 20.0, RAIL_Z + 73.0)     # IEC inlet's leads (out of the back of its body)
HOOD_LED_EXIT = (HOOD_X1 - 14.0, 78.0, WALL_TOP + 22.0)
PI_HDR = screen_xf(0.0, 12.0, PI_ON_SCREEN_Z + 3.5)   # Pi's 40-pin header (bottom edge of the Pi, in the pod)
POD_NOTCH = screen_xf(USBC_X, POD_D, 2.0)
X0H = BIN_X[HUB_MODULE] - PITCH / 2               # the bin hub's module
def hub(board):
    bx, bz, bw, bh = HUB_BOARDS[board]
    return (X0H + bx + bw / 2, WALL_IN - 6.0, bz + bh / 2)
HUB_IN = (X0H + 60.0, 51.0, CHAN_Z1 - 6)           # looms come up out of the channel into the hub's window
CH_Y, CH_Z = 60.0, (CHAN_Z0 + CHAN_Z1) / 2         # middle of the back channel
def gap_x(x):
    """The nearest channel gap (at a back rail screw: where a cable can get into the closed channel)."""
    xs = [SCAN_X0 + (SCAN_X1 - SCAN_X0) * k / 3 for k in (1, 2)]
    for i in range(BINS - 1):
        x0 = BIN_X[i] - PITCH / 2; xs += [x0 + PITCH / 3, x0 + 2 * PITCH / 3]
    xs += [END_X0 + END_L / 3, END_X0 + 2 * END_L / 3]
    return min(xs, key=lambda g: abs(g - x))
def down_window(x, z_from):
    """Inside a bin module, down the back wall's inner face into its window, then out into the channel."""
    return [(x, 44.0, z_from), (x, 51.0, 112.0), (x, 51.0, 45.0), (x, CH_Y, CH_Z)]
SERVO_EXT = (0, 300, 500, 1000, 1500, 2000)        # servo extension lengths you can buy (mm)

def L(pts):
    return 0.0 if not pts else sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

def to_hub(x_drop, board):
    """Along the back channel to the hub module, up into its window, in to a board."""
    return [BACK_CH(HUB_IN[0]), HUB_IN, (HUB_IN[0], 44.0, HUB_IN[2]), hub(board)]

def pick_ext(run, lead=250.0):
    for e in SERVO_EXT:
        if lead + e >= run * 1.15:
            return e
    return None

def front_cross(x0, zdrop=150.0):
    """A front loom's way to the back: along the front wall's inner face under the strip's gusset to the module
    start, across under the tie bar (clear of both doors), then down this module's back wall into its window."""
    return [(x0 + 2.0, -44.5, PATH - 26.0), (x0 + 2.0, 44.0, PATH - 26.0)] + down_window(x0 + 30.0, zdrop)

def runs():
    """(cable, from, to, route words, run mm, have mm or None, what to use)"""
    out = []
    def add(cable, frm, to, route, pts, have, use, stage="A"):
        out.append(dict(cable=cable, frm=frm, to=to, route=route, run=L(pts), have=have, use=use, stage=stage, pts=pts))
    # --- power
    add("Mains (IEC inlet -> PSU)", "IEC inlet, back of scan module", "PSU L / N / earth", "inside the scan module",
        [INLET, (PSU_X0 - 4, 15.0, INLET[2]), PSU_T], 150, "the inlet's own pre-wired 18 AWG leads")
    for nm, dst, extra in (("SKR Pico", SKR, "VIN screw terminal"), ("6 V step-down (servos)", CONV6, "red/black leads")):
        add(f"24 V -> {nm}", "PSU +V / -V", f"{nm} {extra}", "PSU -> pass-through -> bay", [PSU_T, PASS, dst], None,
            "22 AWG red + black (your spools), cut to length")
    add("24 V -> 5 V USB-C converter (in the screen pod)", "PSU +V / -V", "converter red/black leads",
        "PSU -> pass-through -> bay -> bay-cover slot -> hangs free with the Pi's loom -> pod notch",
        [PSU_T, PASS, (130, -40, 80), BAY_SLOT, POD_NOTCH, screen_xf(USBC_X, POD_D - 6, 6.0), CONV5], None,
        "22 AWG red + black spliced onto the converter's leads (solder + heat-shrink), in the loom's braided sleeve")
    port = screen_xf(USBC_X, 10, PI_ON_SCREEN_Z + 56)
    add("USB-C power (Pi)", "5 V USB-C converter (in the pod)", "Pi 5 USB-C", "inside the pod (coil the spare beside the converter)",
        [CONV5, screen_xf(CONV_X + 10, 20, PI_ON_SCREEN_Z + 70), port], 305 - 25, "the converter's own 12 in (305 mm) lead")
    # --- Pi (in the screen pod): ribbons + one small jumper loom down to the bay
    add("Camera ribbon", "Pi 5 CAM/DISP 0", "HQ camera (connector facing left)", "out the pod's back -> back across the gap above the conveyor -> up beside the hood (one long twist) -> under the L-rails -> through the slot straight into the camera",
        None, 500, "Pi 5 camera cable, 500 mm (22-pin mini -> 15-pin standard)")
    out[-1]["run"] = camera_ribbon()[1]
    add("Display ribbon + power", "Pi 5 CAM/DISP 1 + pins 2/6", "Touch Display 2", "inside the pod", [(0, 0, 0), (0, 0, 60)], 100,
        "the cables in the display box")
    out[-1]["internal"] = True                     # inside the pod, between two boards that are screwed together
    loom = [PI_HDR, POD_NOTCH, BAY_SLOT, (BAY_SLOT[0], -40, 80)]
    add("USB to the motor board", "Pi USB-A port", "SKR Pico USB-C", "pod -> notch -> bay-cover slot -> tray",
        loom + [SKR], 500, "USB-A to USB-C data cable, 50 cm (in the black braided sleeve with the I2C wires)")
    add("I2C to the bay junction (SDA, SCL, GND)", "Pi pins 3, 5, 9", "bay junction (joins the bin bus)", "same loom",
        loom + [JUNC], 400, "female-female jumpers, 40 cm")
    # --- the bin bus: one 4-wire loom from the bay to the hub on bin module 2
    add("Bin bus (6 V, GND, SDA, SCL)", "6 V step-down + bay junction", "bin hub: PCA9685 V+/GND, 3.3 V regulator in, I2C in",
        "bay -> back window -> back channel -> up into the hub's window",
        [CONV6, JUNC, BAY_BACK, BACK_CH(BAY_BACK[0])] + to_hub(0, "pca9685"), None,
        "22 AWG: red 6 V, black GND, blue SDA, yellow SCL (twist SDA with GND and SCL with GND), cut to length")
    # --- motor board side
    add("Feed motor", "feeder base back wall (NEMA 17)", "SKR Pico X driver", "down the back of the base -> back window -> tray",
        [(FEED_X, 120, FEED_Z - 25), (FEED_X - 20, 66, 60), (FEED_X - 20, 50, 55), SKR], 1000, "the motor's own 1 m cable (coil the spare)")
    xe, ze = END_SHAFT_X, PUL_Z
    gx = gap_x(xe)
    tm = [(xe, 120, ze - 25), (gx, 70, 70), (gx, CH_Y, CH_Z), BACK_CH(BAY_BACK[0]), BAY_BACK, SKR]
    have = 1000 + (1000 if L(tm) * 1.15 <= 2000 else 2000)
    add("Track motor", "end module back (NEMA 17)", "SKR Pico Y driver", "down the end module -> back channel -> back window -> tray",
        tm, have, f"its 1 m cable + a {(have - 1000) / 1000:.0f} m 4-pin stepper extension (BUY)")
    add("Card-clear sensor (TCRT5000)", "under the floor at the feeder exit", "SKR X-STOP (3.3 V, GND, signal)", "inside the feeder base",
        [(CARD_CLEAR_X, -22, PATH - 8), (CARD_CLEAR_X, -22, 80), SKR], 300, "female-female jumpers, 30 cm")
    add("Belt-home sensor (TCRT5000)", "under the scan module's back strip", "SKR Y-STOP", "out the back wall -> down -> back channel -> back window",
        [(HOME_X + 23, HOME_Y, PATH - 16), (HOME_X + 30, 44, PATH - 18), (HOME_X + 30, 61, PATH - 18), (HOME_X + 30, 66, PATH - 25), (gap_x(HOME_X + 30), 66, 58),
         (gap_x(HOME_X + 30), CH_Y, CH_Z), BACK_CH(BAY_BACK[0]), BAY_BACK, SKR], 500,
        "female-female jumpers, 50 cm")
    for i, (hx, hy) in enumerate(HALL):
        add(f"Tower-ID hall sensor {i + 1} (A3144)", "pocket in the hopper floor (leads down the 3 mm hole)",
            f"SKR {('Z', 'E0')[i]}-STOP signal + GND; 5 V from the probe header's 5 V pin",
            "straight down into the bay", [(hx, hy, PATH - 3), (hx, hy, 140), (30, -10, 80), SKR], 300,
            "female-female jumpers, 30 cm (the A3144 legs plug straight in; heat-shrink each leg)")
    add("Hood LED strips (2 x COB channels)", "SKR HE0 (24 V switched)", "COB strips on the front + back ledges, joined inside the hood",
        "tray -> back window -> back channel -> up the back of the scan module -> hood's LED hole",
        [SKR, BAY_BACK, BACK_CH(BAY_BACK[0]), BACK_CH(gap_x(HOOD_LED_EXIT[0])), (gap_x(HOOD_LED_EXIT[0]), 76, 60), (HOOD_LED_EXIT[0], 77, HOOD_LED_EXIT[2]),
         (HOOD_LED_EXIT[0], 70, HOOD_LED_EXIT[2]), (HOOD_LED_EXIT[0], 70, PATH + LED_H + 10), (HOOD_X0 + 10, 70, PATH + LED_H + 10)], None, "22 AWG red + black (+ 15 cm jumper to the front strip)")
    add("Sheen LED (50 mm of COB strip)", "SKR FAN2 (jumper on 24 V)", "sheen_cap on the hood's back wall", "with the LED pair, last 7 cm outside the hood back",
        [SKR, BAY_BACK, BACK_CH(BAY_BACK[0]), BACK_CH(gap_x(HOOD_LED_EXIT[0])), (gap_x(HOOD_LED_EXIT[0]), 76, 60), (HOOD_LED_EXIT[0], 77, SHEEN_Z - 12),
         (SCAN_X + 20, 82, SHEEN_Z - 15), (SCAN_X, 82, SHEEN_Z - 15), (SCAN_X, 82, SHEEN_Z - 8)], None,
        "22 AWG white + green pair")
    add("Bay fan (30 mm)", "bay cover", "SKR FAN3 (24 V fan)", "inside the bay", [(123, -55, 56), SKR], 150, "fan's own leads")
    # --- every bin: servo, beam emitter, beam receiver, bin-level sensor -> the hub
    for i, xb in enumerate(BIN_X):
        x0 = xb - PITCH / 2
        st = "A" if (i < 2 or i == BINS - 1) else "B"
        if i < BINS - 1:
            hubm = (i == HUB_MODULE)       # the hub module's own looms go straight to the boards, inside
            sv = [(x0 + SERVO_TOP_X + 24.5, SERVO_S[0], SERVO_S[1] - 8), (x0 + SERVO_TOP_X + 24.5, 44, SERVO_S[1] - 10),
                  (x0 + 118, 44, 160), (x0 + 116, 44, 128)] + \
                 ([(x0 + 100, 40, 100), hub("pca9685")] if hubm else down_window(x0 + 108, 118) + to_hub(0, "pca9685"))
            e = pick_ext(L(sv))
            add(f"Door servo, bin {i + 1}", f"inside bin module {i + 1}, under the back strip", f"PCA9685 channel {i}",
                "down through the module's window -> back channel -> hub", sv, 250 + (e or 0),
                f"servo's 25 cm lead" + (f" + {e / 10:.0f} cm servo extension" if e else ""), st)
            em = [(x0 + PITCH / 2 + 6.5, 47.5, PATH - 25.4), (x0 + PITCH / 2 + 6.5, 44, PATH - 28)] + \
                 ([hub("mcp23017")] if hubm else down_window(x0 + PITCH / 2 + 6.5, PATH - 32) + to_hub(0, "mcp23017"))
            e = pick_ext(L(em))
            add(f"Beam emitter, bin {i + 1}", "back pocket at the bin mouth", "3.3 V + GND (hub)", "in through its lead slot -> window -> channel -> hub",
                em, 250 + (e or 0), "its 25 cm leads" + (f" + {e / 10:.0f} cm servo extension (Dupont crimped on the leads)" if e else ""), st)
            rc = [(x0 + PITCH / 2 + 6.5, -47.5, PATH - 25.4), (x0 + PITCH / 2 + 6.5, -44.5, PATH - 26)] + \
                 (front_cross(x0)[:2] + [(x0 + 30, 40, 150), hub("mcp23017")] if hubm else front_cross(x0) + to_hub(0, "mcp23017"))
            e = pick_ext(L(rc))
            add(f"Beam receiver, bin {i + 1}", "front pocket at the bin mouth", f"MCP23017 GPA{i} + 3.3 V/GND (hub)",
                "in through its lead slot -> under the front strip -> along the tie bar -> window -> channel -> hub",
                rc, 250 + (e or 0), "its 25 cm leads" + (f" + {e / 10:.0f} cm servo extension (Dupont crimped on the leads)" if e else ""), st)
        tca = "tca9548a_1" if i < 8 else "tca9548a_2"
        tf = [(x0 + TOF_X + 8, -38.0, PATH - 16), (x0 + TOF_X + 8, -35.0, PATH - 20), (x0 + TOF_X + 8, -44.5, PATH - 26)] + \
             (front_cross(x0)[:2] + [(x0 + 30, 40, 150), hub(tca)] if i == HUB_MODULE else
              front_cross(x0, 118.0 if i == BINS - 1 else 150.0) + to_hub(0, tca))
        n = math.ceil(L(tf) * 1.15 / 500)
        add(f"Bin-level sensor (VL53L1X), bin {i + 1}", "pocket under the front strip", f"TCA9548A {'1' if i < 8 else '2'} channel {i % 8} (SD/SC) + 3.3 V/GND",
            "under the front strip -> along the tie bar -> window -> channel -> hub", tf, n * 500,
            f"4 Dupont jumpers, {n} x 50 cm chained (headers soldered on the carrier: VIN, GND, SDA, SCL)", st)
    return out

def fmt(mm):
    return f"{mm:.0f} mm ({mm / 25.4:.1f} in)"

if __name__ == "__main__":
    rows = runs()
    lines = [f"# Wiring: every cable on the {BINS}-bin machine", "",
             "Generated by `cad/wiring.py` from the CAD (routes go through the real windows, channels and holes; run length",
             "includes the bends; the check wants 15% slack). `cad/fitcheck.py` fails if any run is longer than what it has.",
             "Stage A = the 3-bin test build, B = bins 3-8 added later (bin 9's cables are the end module's, built in A).", "",
             "Picture diagrams, one per board (what plugs in where, wires in their real colors): "
             "[power](wiring/1-power.png), [SKR Pico](wiring/2-skr-pico.png), [Pi 5](wiring/3-pi5.png), "
             "[bin hub](wiring/4-bin-hub.png) (made by `cad/wiring_diagram.py`).", "",
             "| Cable | From | To | Route | Run | Have / use | OK | Stage |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        need = r["run"] * 1.15
        ok = "cut to length" if r["have"] is None else ("yes" if r["have"] >= need else "**extend**")
        have = r["use"] if r["have"] is None else f'{fmt(r["have"])}: {r["use"]}'
        lines.append(f'| {r["cable"]} | {r["frm"]} | {r["to"]} | {r["route"]} | {fmt(r["run"])} | {have} | {ok} | {r["stage"]} |')
    cut = [r for r in rows if r["have"] is None]
    lines += ["", "## Bin hub (back panel of bin module 2)",
              "PCA9685 (I2C 0x40): door servos on channels 0-7, V+ from the bus's 6 V. MCP23017 (0x27, CQRobot default): beam receivers on GPA0-7",
              "(inputs, pull-ups on). TCA9548A #1 (0x71: bridge A0): bin-level sensors 1-8 on channels 0-7; #2 (0x72: bridge A1): bin 9",
              "on channel 0 (not 0x70: the PCA9685 answers its all-call there). Pololu D24V5F3 3.3 V regulator from the bus's 6 V powers the logic, the sensors and the emitters.",
              "Each VL53L1X is alone on its switch channel, so they all keep address 0x29 and need no XSHUT wire.", "",
              "## Pins",
              "Pi 5: USB to the SKR Pico, I2C SDA/SCL (pins 3/5) to the bin bus, GND on pin 9; display power on",
              "pins 2 (5 V) and 6. Nothing else: every per-bin signal lives on the hub.",
              "SKR Pico: X (feed), Y (track), X-STOP (card-clear), Y-STOP (belt-home), Z-STOP + E0-STOP (tower-ID hall sensors,",
              "5 V from the probe header), HE0 (hood LEDs), FAN2 (sheen LED, jumper on 24 V), FAN3 (bay fan), VIN 24 V,",
              "USB-C to the Pi (its UART header is not used). All grounds are common (PSU -V)."]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "WIRING.md")
    open(p, "w").write("\n".join(lines) + "\n")
    for r in rows:
        print(f'{r["cable"][:44]:44s} run {r["run"]:6.0f}  have {r["have"] if r["have"] else "-":>5}  {r["use"][:60]}')
