"""Hardware access for the sorter. Each part has a real class (Pi + SKR Pico via Klipper) and a Sim class, so
the whole cycle can be run on any computer with `python sorter.py --sim`."""
from __future__ import annotations

import io
import json
import random
import time
import urllib.parse
import urllib.request


# ------------------------------------------------------------------------------------------------ Klipper
class Klipper:
    """Motors, the two TCRT sensors and the lights, through Moonraker's HTTP API."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def gcode(self, script: str, timeout: float = 60) -> None:
        q = urllib.parse.urlencode({"script": script})
        req = urllib.request.Request(f"{self.url}/printer/gcode/script?{q}", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()

    def _button(self, name: str) -> bool:
        q = urllib.parse.quote(f"gcode_button {name}")
        with urllib.request.urlopen(f"{self.url}/printer/objects/query?{q}", timeout=5) as r:
            st = json.load(r)["result"]["status"][f"gcode_button {name}"]["state"]
        return st == "PRESSED"

    def card_at_sensor(self) -> bool:
        return self._button("card_clear")

    def fin_at_home(self) -> bool:
        return self._button("belt_home")

    def move(self, stepper: str, mm: float, speed: float, stop_on: int = 0) -> None:
        """Relative move. stop_on: 0 = full move, 2 = stop when the sensor triggers, -2 = stop when it clears
        (no error if it never happens; callers check the sensor afterwards)."""
        s = f"MANUAL_STEPPER STEPPER={stepper} SET_POSITION=0\n"
        s += f"MANUAL_STEPPER STEPPER={stepper} MOVE={mm:.3f} SPEED={speed:.1f}"
        if stop_on:
            s += f" STOP_ON_ENDSTOP={stop_on}"
        s += "\nM400"
        self.gcode(s, timeout=max(30, abs(mm) / max(speed, 1) * 3 + 10))

    def moved(self, stepper: str) -> float:
        """How far the last move actually went (it may have stopped early on a sensor)."""
        q = urllib.parse.quote(f"manual_stepper {stepper}")
        try:
            with urllib.request.urlopen(f"{self.url}/printer/objects/query?{q}", timeout=5) as r:
                return float(json.load(r)["result"]["status"][f"manual_stepper {stepper}"]["position"])
        except Exception:
            return float("nan")

    def enable(self, on: bool) -> None:
        for st in ("track", "feed"):
            self.gcode(f"MANUAL_STEPPER STEPPER={st} ENABLE={1 if on else 0}")

    def lights(self, value: float) -> None:
        self.gcode(f"SET_PIN PIN=lights VALUE={value:.2f}")

    def sheen(self, value: float) -> None:
        """Low-angle sheen LED (foil check photo)."""
        self.gcode(f"SET_PIN PIN=sheen VALUE={value:.2f}")


# ------------------------------------------------------------------------------------------------ servos
class Doors:
    """Door servos on a PCA9685 (Adafruit 815) at I2C 0x40, powered from the 6 V step-down."""

    def __init__(self, cfg: dict):
        from smbus2 import SMBus
        self.bus = SMBus(1)
        self.addr = 0x40
        self.cfg = {d["bin"]: d for d in cfg["doors"]["servos"]}
        # 50 Hz: prescale = 25 MHz / (4096 * 50) - 1 = 121
        self.bus.write_byte_data(self.addr, 0x00, 0x10)       # sleep
        self.bus.write_byte_data(self.addr, 0xFE, 121)        # prescale
        self.bus.write_byte_data(self.addr, 0x00, 0x20)       # wake, auto-increment
        time.sleep(0.005)
        for b in self.cfg:
            self.set(b, open_=False)

    def _pulse(self, ch: int, us: int) -> None:
        ticks = int(us / 20000 * 4096)
        reg = 0x06 + 4 * ch
        self.bus.write_i2c_block_data(self.addr, reg, [0, 0, ticks & 0xFF, ticks >> 8])

    def set(self, bin_no: int, open_: bool) -> None:
        d = self.cfg[bin_no]
        self._pulse(d["channel"], d["open_us"] if open_ else d["closed_us"])


class Mcp23017:
    """MCP23017 on the bin hub: GPA0-7 = beam receivers of bins 1-8 (inputs, pull-ups on)."""

    def __init__(self, bus, addr: int = 0x20):
        self.bus, self.addr = bus, addr
        self.bus.write_byte_data(addr, 0x00, 0xFF)   # IODIRA: all inputs
        self.bus.write_byte_data(addr, 0x0C, 0xFF)   # GPPUA: pull-ups on

    def port_a(self) -> int:
        return self.bus.read_byte_data(self.addr, 0x12)


class Beams:
    """Break-beam receivers, one per door, on the hub's MCP23017 (pin = bin number - 1 unless set in the config)."""

    def __init__(self, cfg: dict, bus=None):
        from smbus2 import SMBus
        self.bus = bus or SMBus(1)
        self.broken_low = bool(cfg["doors"]["beam_broken_when_low"])
        self.mcp = Mcp23017(self.bus, int(cfg["hub"].get("mcp23017", 0x27)))
        self.pins = {d["bin"]: int(d.get("beam_pin", d["bin"] - 1)) for d in cfg["doors"]["servos"]}

    def broken(self, bin_no: int) -> bool:
        v = (self.mcp.port_a() >> self.pins[bin_no]) & 1
        return (v == 0) if self.broken_low else (v == 1)


# ------------------------------------------------------------------------------------------------ bin levels
class Levels:
    """One VL53L1X per bin, each alone on a channel of the hub's TCA9548A I2C switches, so they all keep address
    0x29 (no XSHUT wires). Bin 1-8: switch 1 (0x71) channels 0-7; bin 9: switch 2 (0x72) channel 0."""

    def __init__(self, cfg: dict, bins: int | None = None):
        import VL53L1X
        from smbus2 import SMBus
        self.bus = SMBus(1)
        self.muxes = [int(a) for a in cfg["hub"].get("tca9548a", [0x71, 0x72])]
        n = int(bins or cfg["bins"]["in_use"])
        self.chan = [(self.muxes[i // 8], i % 8) for i in range(n)]
        self.tofs = []
        for mux, ch in self.chan:
            self._select(mux, ch)
            t = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
            t.open()
            t.set_user_roi(VL53L1X.VL53L1xUserRoi(6, 9, 9, 6))   # 4 x 4 SPADs in the middle: about 15 deg
            t.start_ranging(1)                                     # short range mode
            self.tofs.append(t)
        self._select(None, None)

    def _select(self, mux, ch) -> None:
        for m in self.muxes:
            try:
                self.bus.write_byte(m, (1 << ch) if m == mux else 0)
            except OSError:
                if m == mux:
                    raise

    def distances(self) -> list[int]:
        out = []
        for (mux, ch), t in zip(self.chan, self.tofs):
            self._select(mux, ch)
            out.append(int(t.get_distance()))
        self._select(None, None)
        return out


# ------------------------------------------------------------------------------------------------ tower ID
TOWER_KINDS = {(True, False): "raw", (False, True): "single", (True, True): "double", (False, False): None}


def tower_kind(klipper) -> str | None:
    """Which hopper tower is on the feeder: two hall sensors under the skirt read its magnets
    (raw = front magnet, single-sleeved = back, double-sleeved = both, none = no tower)."""
    try:
        return TOWER_KINDS[(klipper._button("tower_a"), klipper._button("tower_b"))]
    except Exception:
        return "unknown"


# ------------------------------------------------------------------------------------------------ camera
class Camera:
    def __init__(self, cfg: dict):
        from picamera2 import Picamera2
        c = cfg["camera"]
        self.cam = Picamera2()
        conf = self.cam.create_still_configuration(main={"size": (c["width"], c["height"])})
        self.cam.configure(conf)
        self.fixed = {"AeEnable": False, "ExposureTime": int(c["exposure_us"]), "AnalogueGain": float(c["gain"]), "AwbEnable": True}
        self.cam.set_controls(self.fixed)
        self.is_auto = False
        import os
        lp = os.path.expanduser(c.get("lens_file", "~/sorter_data/lens.json"))
        self.lens = None
        if c.get("undistort", True) and os.path.exists(lp):
            try:
                self.lens = Lens(lp)
            except Exception:
                self.lens = None
        self.cam.start()
        time.sleep(1.0)

    def auto(self, on: bool) -> None:
        """Auto exposure (live view in room light) or the fixed exposure the sorting photos use under the hood LEDs."""
        if on == self.is_auto:
            return
        self.cam.set_controls({"AeEnable": True, "AwbEnable": True} if on else self.fixed)
        self.is_auto = on
        time.sleep(0.3)

    def jpeg(self) -> bytes:
        buf = io.BytesIO()
        self.cam.capture_file(buf, format="jpeg")
        data = buf.getvalue()
        return self.lens.undistort(data) if self.lens else data


class Lens:
    """Takes the 6 mm lens's barrel distortion out of every photo, from a one-off calibration (touchscreen Tools -> Lens photo x8, then Finish:
    photos of the printed checkerboard, see machine/README.md). Stored in ~/sorter_data/lens.json."""

    def __init__(self, path: str):
        import cv2, numpy as np
        d = json.load(open(path))
        self.cv2, self.np = cv2, np
        self.K, self.D, self.size = np.array(d["K"]), np.array(d["D"]), tuple(d["size"])
        self.maps = None

    def undistort(self, jpeg: bytes) -> bytes:
        cv2, np = self.cv2, self.np
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        if self.maps is None or self.maps[2] != (w, h):
            sx, sy = w / self.size[0], h / self.size[1]
            K = self.K.copy(); K[0] *= sx; K[1] *= sy
            m1, m2 = cv2.initUndistortRectifyMap(K, self.D, None, K, (w, h), cv2.CV_16SC2)
            self.maps = (m1, m2, (w, h))
        out = cv2.remap(img, self.maps[0], self.maps[1], cv2.INTER_LINEAR)
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return enc.tobytes() if ok else jpeg


def calibrate_lens(jpegs: list[bytes], path: str, board=(9, 6), square_mm: float = 10.0) -> dict:
    """Checkerboard calibration (9 x 6 inner corners, 10 mm squares: machine/calibration_board.pdf). Needs 8+ photos
    with the board in different spots and tilts under the camera. Returns the RMS error in pixels."""
    import cv2, numpy as np
    objp = np.zeros((board[0] * board[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board[0], 0:board[1]].T.reshape(-1, 2) * square_mm
    obj, img, size = [], [], None
    for j in jpegs:
        g = cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_GRAYSCALE)
        size = g.shape[::-1]
        ok, c = cv2.findChessboardCorners(g, board, cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            c = cv2.cornerSubPix(g, c, (11, 11), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
            obj.append(objp); img.append(c)
    if len(obj) < 6:
        raise ValueError(f"found the board in only {len(obj)} photos (need 6+): more light, hold it flat, fill more of the view")
    rms, K, D, _, _ = cv2.calibrateCamera(obj, img, size, None, None)
    json.dump({"K": K.tolist(), "D": D.tolist(), "size": list(size), "rms": rms, "photos": len(obj)}, open(path, "w"), indent=1)
    return {"rms": rms, "photos": len(obj)}


# ------------------------------------------------------------------------------------------------ simulation
class SimMachine:
    """Pretend hardware: a hopper of N cards, fins on a belt, sensors that answer like the real ones."""

    def __init__(self, cards: int = 12, seed: int = 1, jam_at: int | None = None):
        self.hopper = cards
        self.rng = random.Random(seed)
        self.track_pos = self.rng.uniform(0, 1220)   # where the belt happens to be at power-up
        self.card_on_sensor = False
        self.jam_at = jam_at
        self.fed = 0
        self.light = 0.0
        self.doors: dict[int, bool] = {}
        self.levels = [250] * 9
        self.tower = "raw"
        self.log: list[str] = []

    # Klipper-like
    def card_at_sensor(self) -> bool: return self.card_on_sensor
    def fin_at_home(self) -> bool: return (self.track_pos % 122.0) < 4.0
    def enable(self, on: bool) -> None: pass
    def lights(self, v: float) -> None: self.light = v

    def move(self, stepper: str, mm: float, speed: float, stop_on: int = 0) -> None:
        self._moved = mm
        if stepper == "track":
            if stop_on == 2:
                # run until a fin reaches the home sensor
                d = (122.0 - (self.track_pos % 122.0)) % 122.0
                d = d if d > 0 else 122.0
                self._moved = min(d, mm)
            self.track_pos = (self.track_pos + self._moved) % 1220.0
        else:
            if stop_on == 2:          # until the card reaches the sensor
                if self.hopper == 0:
                    self._moved = mm
                    return
                self.card_on_sensor = True
                self._moved = 20.0
            elif stop_on == -2:       # until it clears
                if self.jam_at is not None and self.fed == self.jam_at:
                    self._moved = mm
                    return
                self.card_on_sensor = False
                self.hopper -= 1
                self.fed += 1
                self._moved = 88.0

    def moved(self, stepper: str) -> float: return getattr(self, "_moved", 0.0)

    # doors / beams / levels / camera
    def set(self, bin_no: int, open_: bool) -> None: self.doors[bin_no] = open_
    def broken(self, bin_no: int) -> bool: return self.doors.get(bin_no, False)
    def distances(self) -> list[int]: return list(self.levels)
    def jpeg(self) -> bytes: return b"\xff\xd8sim\xff\xd9"
