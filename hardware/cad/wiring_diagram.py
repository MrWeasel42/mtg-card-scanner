"""Picture wiring diagrams for the 9-bin card sorter: one sheet per board, the board drawn in the middle with the
connectors you plug into, and every wire going straight out to the part it goes to, in its real color (the 22 AWG
spool colors in WIRING.md). No crossing wires.

    python3 hardware/cad/wiring_diagram.py      -> hardware/wiring/1-power.svg/.png ... 4-bin-hub.svg/.png

Pins and connectors are the ones in WIRING.md (cad/wiring.py) and machine/klipper/printer.cfg.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "wiring")

COL = {  # wire colors
    "24V": "#e11d48", "GND": "#111827", "6V": "#f97316", "3V3": "#ec4899", "5V": "#b91c1c", "SDA": "#2563eb",
    "SCL": "#eab308", "TX": "#16a34a", "RX": "#7c3aed", "SIG": "#0d9488", "MOT": "#64748b", "RIB": "#94a3b8",
    "L": "#92400e", "N": "#1d4ed8", "PE": "#65a30d", "WHT": "#d4d4d8", "GRN": "#22c55e",
}
NAMES = {"24V": "24 V (red)", "GND": "GND (black)", "6V": "6 V servo bus (red wire; orange here)", "3V3": "3.3 V", "5V": "5 V",
         "SDA": "SDA (blue)", "SCL": "SCL (yellow)", "TX": "Pi TX → board RX", "RX": "Pi RX ← board TX",
         "SIG": "signal", "MOT": "stepper cable (4 wires)", "RIB": "ribbon cable", "L": "mains L (brown)",
         "N": "mains N (blue)", "PE": "earth (green/yellow)", "WHT": "white", "GRN": "green"}


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Sheet:
    def __init__(self, w: int, h: int, title: str, note: str):
        self.w, self.h, self.s, self.used = w, h, [], set()
        self.s.append(f'<rect width="{w}" height="{h}" fill="#f8fafc"/>')
        self.text(36, 50, title, 30, 800)
        self.text(36, 80, note, 15, 400, "#475569")

    def text(self, x, y, t, size=15, weight=400, color="#0f172a", anchor="start", italic=False):
        st = ' font-style="italic"' if italic else ""
        self.s.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
                      f'text-anchor="{anchor}"{st}>{esc(t)}</text>')

    def board(self, x, y, w, h, title, sub, fill="#065f46"):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="#022c22" stroke-width="2"/>')
        for hx, hy in ((x + 12, y + 12), (x + w - 12, y + 12), (x + 12, y + h - 12), (x + w - 12, y + h - 12)):
            self.s.append(f'<circle cx="{hx}" cy="{hy}" r="5" fill="#d1d5db" stroke="#022c22"/>')
        lines = sub.split("\n")
        y0 = y + 46
        self.text(x + w / 2, y0, title, 22, 800, "#ecfdf5", "middle")
        for i, line in enumerate(lines):
            self.text(x + w / 2, y0 + 26 + i * 18, line, 13, 400, "#e2e8f0", "middle", True)

    def device(self, x, y, w, h, title, sub="", fill="#e2e8f0"):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="#334155" stroke-width="1.6"/>')
        self.text(x + w / 2, y + 24, title, 16, 700, "#0f172a", "middle")
        for i, line in enumerate(sub.split("\n")):
            self.text(x + w / 2, y + 44 + i * 16, line, 12, 400, "#334155", "middle")

    def link(self, side, board_x, y, dev_x, label, wires, note=""):
        """A connector on the board's left/right edge at height y, and its wires straight out to x = dev_x."""
        n = len(wires)
        pw = max(110, 8.0 * len(label) + 24)
        bx = board_x + 6 if side == "left" else board_x - pw - 6     # header sits on the board, inside its edge
        h = 18 + 12 * n
        self.s.append(f'<rect x="{bx}" y="{y - h / 2}" width="{pw}" height="{h}" rx="5" fill="#f8fafc" stroke="#0f172a" stroke-width="1.4"/>')
        self.text(bx + pw / 2, y + 5, label, 13, 700, "#0f172a", "middle")
        edge = bx if side == "left" else bx + pw
        for i, key in enumerate(wires):
            self.used.add(key)
            wy = y + (i - (n - 1) / 2) * 12
            self.s.append(f'<path d="M{edge},{wy} L{dev_x},{wy}" stroke="#fff" stroke-width="8" stroke-linecap="round"/>')
            self.s.append(f'<path d="M{edge},{wy} L{dev_x},{wy}" stroke="{COL[key]}" stroke-width="5" stroke-linecap="round"/>')
            self.s.append(f'<circle cx="{edge}" cy="{wy}" r="3.8" fill="#facc15" stroke="#713f12"/>')
        if note:
            self.text((edge + dev_x) / 2, y - 6 * n - 12, note, 12, 600, "#334155", "middle")

    def legend(self, x, y):
        self.text(x, y, "Wire colors on this sheet", 15, 800)
        for i, k in enumerate([k for k in COL if k in self.used]):
            yy = y + 22 + i * 21
            self.s.append(f'<path d="M{x},{yy} L{x + 40},{yy}" stroke="{COL[k]}" stroke-width="6" stroke-linecap="round"/>')
            self.text(x + 50, yy + 5, NAMES[k], 13)

    def save(self, name):
        doc = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
               f'font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">' + "".join(self.s) + "</svg>")
        os.makedirs(OUT_DIR, exist_ok=True)
        svg_path = os.path.join(OUT_DIR, name + ".svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(doc)
        chrome = shutil.which("google-chrome") or shutil.which("chromium")
        if chrome:
            with tempfile.TemporaryDirectory() as d:
                html = os.path.join(d, "w.html")
                with open(html, "w") as f:
                    f.write(f"<html><body style='margin:0'>{doc}</body></html>")
                subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu",
                                f"--screenshot={os.path.abspath(svg_path[:-4] + '.png')}", f"--window-size={self.w},{self.h}",
                                "--hide-scrollbars", "file://" + html], capture_output=True, timeout=60)
        print("wrote", os.path.relpath(svg_path))


def side_devices(sh: Sheet, side, board_edge, items, dev_x, dev_w, top, step):
    """items: (connector label, wires, device title, device sub, fill, note). board_edge = the board's left or right x."""
    for i, (lab, wires, title, sub, fill, note) in enumerate(items):
        y = top + i * step
        x_dev = dev_x + dev_w if side == "left" else dev_x
        sh.link(side, board_edge, y, x_dev, lab, wires, note)
        sh.device(dev_x, y - 38, dev_w, 76, title, sub, fill)


# ------------------------------------------------------------------------------------------------ 1. power
def power():
    sh = Sheet(1700, 860, "1 · Power: the 24 V supply feeds everything",
               "Mean Well LRS-100-24 in the base. All grounds are common (-V). Use your 22 AWG red + black, cut to length.")
    sh.board(620, 150, 420, 620, "24 V supply", "Mean Well LRS-100-24\nscrew terminals on one end", fill="#475569")
    side_devices(sh, "left", 620, [
        ("L  N  ⏚", ["L", "N", "PE"], "IEC inlet + switch", "back of the scan module\nits own pre-wired leads", "#fef3c7", "mains"),
    ], 60, 280, 300, 200)
    side_devices(sh, "right", 1040, [
        ("+V  -V", ["24V", "GND"], "SKR Pico VIN", "screw terminal (sheet 2)", "#d1fae5", "126 mm (5.0 in)"),
        ("+V  -V", ["24V", "GND"], "6 V step-down", "for the servos (sheet 4)", "#ffedd5", "186 mm (7.3 in)"),
        ("+V  -V", ["24V", "GND"], "5 V USB-C converter", "in the screen pod → Pi 5\nruns with the Pi loom", "#fee2e2", "298 mm (11.7 in)"),
    ], 1330, 320, 250, 200)
    sh.text(60, 420, "Unplug it from the wall before", 15, 700, "#b91c1c")
    sh.text(60, 442, "you touch the mains side.", 15, 700, "#b91c1c")
    sh.text(60, 470, "Earth goes to the ⏚ screw.", 14, 400, "#334155")
    sh.legend(60, 560)
    sh.save("1-power")


# ------------------------------------------------------------------------------------------------ 2. SKR Pico
def skr():
    sh = Sheet(1900, 1420, "2 · BTT SKR Pico (motor board): what plugs in where",
               "Klipper names in brackets (printer.cfg). Motors use their own cables; sensors use female-female jumpers.")
    sh.board(700, 140, 480, 1000, "BTT SKR Pico", "motor board, in the bay tray")
    side_devices(sh, "left", 700, [
        ("VIN", ["24V", "GND"], "24 V supply +V / -V", "sheet 1", "#e2e8f0", "24 V in"),
        ("X motor (feed)", ["MOT"], "Feed motor, NEMA 17", "feeder base back wall\nits own 1 m cable", "#e5e7eb", "275 mm run"),
        ("Y motor (track)", ["MOT"], "Track motor, NEMA 17", "end module back\n1 m cable + 1 m extension", "#e5e7eb", "1684 mm run"),
        ("HE0", ["24V", "GND"], "Hood LED strips", "2 COB strips, front + back\nledges, joined in the hood", "#fee2e2", "24 V switched"),
        ("FAN2 (jumper on 24 V)", ["WHT", "GRN"], "Sheen LED", "50 mm COB strip\nhood back wall", "#dcfce7", "white + green pair"),
        ("FAN3", ["24V", "GND"], "Bay fan 30 mm", "on the bay cover\nits own leads", "#e2e8f0", "24 V fan"),
    ], 50, 280, 270, 160)
    side_devices(sh, "right", 1180, [
        ("UART: RX TX GND", ["TX", "RX", "GND"], "Raspberry Pi 5", "pins 8 (TX), 10 (RX), 6 (GND)\nsheet 3", "#dcfce7", "TX crosses to RX"),
        ("X-STOP (card clear)", ["3V3", "GND", "SIG"], "Card-clear sensor", "TCRT5000, under the floor\nat the feeder exit", "#ccfbf1", "30 cm jumpers"),
        ("Y-STOP (belt home)", ["3V3", "GND", "SIG"], "Belt-home sensor", "TCRT5000, under the scan\nmodule's back strip", "#ccfbf1", "50 cm jumpers"),
        ("Z-STOP (tower 1)", ["SIG", "GND"], "Tower-ID hall sensor 1", "A3144 in the hopper floor\n5 V from the probe header", "#ccfbf1", "30 cm jumpers"),
        ("E0-STOP (tower 2)", ["SIG", "GND"], "Tower-ID hall sensor 2", "A3144 in the hopper floor\n5 V from the probe header", "#ccfbf1", "30 cm jumpers"),
        ("probe header 5 V", ["5V"], "Both hall sensors' 5 V", "split to the two A3144\nVcc legs (heat-shrink)", "#ccfbf1", "5 V"),
    ], 1580, 280, 290, 160)
    sh.legend(1100, 1190)
    sh.save("2-skr-pico")


# ------------------------------------------------------------------------------------------------ 3. Pi 5
def pi():
    sh = Sheet(1850, 1230, "3 · Raspberry Pi 5 (in the screen pod): only 7 header pins are used",
               "Pin numbers are the physical pins on the 40-pin header (pin 1 is the corner pin with the square pad).")
    sh.board(700, 140, 440, 800, "Raspberry Pi 5", "runs the sorter app and\nidentifies cards", fill="#14532d")
    side_devices(sh, "left", 700, [
        ("USB-C power", ["5V"], "5 V USB-C converter", "24 V in from the supply\n(sheet 1)", "#fee2e2", "its own 12 in lead"),
        ("CAM/DISP 0", ["RIB"], "HQ camera", "500 mm ribbon: out the pod back,\none gentle twist, never folded", "#e0e7ff", "camera ribbon"),
        ("CAM/DISP 1", ["RIB"], "Touch Display 2", "the display's own ribbon\n(in the box)", "#dbeafe", "display ribbon"),
        ("pin 2 (5 V)  pin 6 (GND)", ["5V", "GND"], "Touch Display 2 power", "the display's power lead", "#dbeafe", "display power"),
    ], 50, 280, 290, 190)
    side_devices(sh, "right", 1140, [
        ("pin 8 (TX)", ["TX"], "SKR Pico UART RX", "sheet 2 · 40 cm jumper", "#d1fae5", "UART"),
        ("pin 10 (RX)", ["RX"], "SKR Pico UART TX", "sheet 2 · 40 cm jumper", "#d1fae5", "UART"),
        ("pin 6 (GND)", ["GND"], "SKR Pico UART GND", "sheet 2", "#d1fae5", "shared with the display"),
        ("pin 3 (SDA)", ["SDA"], "Bin bus SDA", "bay junction → hub (sheet 4)", "#dbeafe", "I2C"),
        ("pin 5 (SCL)", ["SCL"], "Bin bus SCL", "bay junction → hub (sheet 4)", "#dbeafe", "I2C"),
        ("pin 9 (GND)", ["GND"], "Bin bus GND", "bay junction → hub (sheet 4)", "#dbeafe", "I2C ground"),
    ], 1510, 240, 300, 125)
    sh.text(50, 1000, "UART and I2C jumpers run together in one black braided sleeve: pod → notch → bay-cover slot.", 14, 600, "#334155")
    sh.legend(1200, 1000)
    sh.save("3-pi5")


# ------------------------------------------------------------------------------------------------ 4. bin hub
def hub():
    sh = Sheet(2000, 1260, "4 · Bin hub (back panel of bin module 2) and each bin's four parts",
               "One 4-wire bus from the bay feeds the hub. Each bin's parts plug in on that bin's channel: channel N = bin N+1.")
    sh.board(700, 140, 520, 1000, "Bin hub",
             "PCA9685 servo board (0x40)\nMCP23017 inputs (0x20)\nTCA9548A #1 (0x71) + #2 (0x72)\n3.3 V regulator D24V5F3", fill="#7c2d12")
    side_devices(sh, "left", 700, [
        ("bus in: 6 V  GND", ["6V", "GND"], "6 V step-down (servos)", "in the bay, from the 24 V supply\n22 AWG red + black", "#ffedd5", "674 mm run"),
        ("bus in: SDA  SCL", ["SDA", "SCL"], "Pi 5 pins 3 + 5", "via the bay junction\ntwist each with a GND", "#dbeafe", "blue + yellow"),
        ("3.3 V out", ["3V3", "GND"], "All sensors + emitters", "from the regulator (6 V in)", "#fce7f3", "logic power"),
    ], 50, 300, 300, 220)
    side_devices(sh, "right", 1220, [
        ("PCA9685 ch N", ["SIG", "6V", "GND"], "Door servo, bin N+1", "EMAX ES08MA II, under the back strip\n25 cm lead + servo extension", "#fef3c7", "servo plug: signal, 6 V, GND"),
        ("3.3 V + GND", ["3V3", "GND"], "Beam emitter, bin N+1", "IR LED, back pocket at the bin mouth\nDupont crimped on its leads", "#fce7f3", "always on"),
        ("MCP23017 GPA N", ["SIG", "3V3", "GND"], "Beam receiver, bin N+1", "front pocket at the bin mouth\nunder the front strip → tie bar", "#ede9fe", "input, pull-up on"),
        ("TCA #1 SDN / SCN", ["SDA", "SCL", "3V3", "GND"], "Bin-level sensor, bin N+1", "VL53L1X under the front strip\nheaders: VIN GND SDA SCL", "#dbeafe", "alone on its channel (0x29)"),
        ("TCA #2 SD0 / SC0", ["SDA", "SCL", "3V3", "GND"], "Bin-level sensor, bin 9", "the end bin (no door)", "#dbeafe", "bin 9 only"),
    ], 1600, 280, 370, 190)
    sh.text(50, 1200, "Example: bin 1 = PCA9685 ch 0, MCP23017 GPA0, TCA #1 channel 0.   Bin 8 = ch 7, GPA7, channel 7.", 15, 700)
    sh.text(50, 1226, "Stage A (3-bin build): bins 1, 2 and the end bin 9. Bins 3-8 plug in the same way later.", 14, 400, "#334155")
    sh.legend(50, 860)
    sh.save("4-bin-hub")


if __name__ == "__main__":
    power()
    skr()
    pi()
    hub()
