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


class Beams:
    def __init__(self, cfg: dict):
        from gpiozero import DigitalInputDevice
        self.broken_low = bool(cfg["doors"]["beam_broken_when_low"])
        self.pins = {d["bin"]: DigitalInputDevice(d["beam_gpio"], pull_up=True) for d in cfg["doors"]["servos"]}

    def broken(self, bin_no: int) -> bool:
        v = self.pins[bin_no].value
        return (v == 0) if self.broken_low else (v == 1)


# ------------------------------------------------------------------------------------------------ bin levels
class Levels:
    """Three VL53L1X on one I2C bus: hold all in reset with XSHUT, wake one at a time and give each its own address."""

    def __init__(self, cfg: dict):
        from gpiozero import DigitalOutputDevice
        import VL53L1X
        self.xshut = [DigitalOutputDevice(p, initial_value=False) for p in cfg["levels"]["xshut_gpio"]]
        time.sleep(0.05)
        self.tofs = []
        for i, x in enumerate(self.xshut):
            x.on()
            time.sleep(0.05)
            t = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
            t.open()
            t.change_address(0x30 + i)
            t.close()
            t = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x30 + i)
            t.open()
            t.set_user_roi(VL53L1X.VL53L1xUserRoi(6, 9, 9, 6))   # 4 x 4 SPADs in the middle: about 15 deg
            t.start_ranging(1)                                     # short range mode
            self.tofs.append(t)

    def distances(self) -> list[int]:
        return [int(t.get_distance()) for t in self.tofs]


# ------------------------------------------------------------------------------------------------ camera
class Camera:
    def __init__(self, cfg: dict):
        from picamera2 import Picamera2
        c = cfg["camera"]
        self.cam = Picamera2()
        conf = self.cam.create_still_configuration(main={"size": (c["width"], c["height"])})
        self.cam.configure(conf)
        self.cam.set_controls({"ExposureTime": int(c["exposure_us"]), "AnalogueGain": float(c["gain"]), "AwbEnable": True})
        self.cam.start()
        time.sleep(1.0)

    def jpeg(self) -> bytes:
        buf = io.BytesIO()
        self.cam.capture_file(buf, format="jpeg")
        return buf.getvalue()


# ------------------------------------------------------------------------------------------------ simulation
class SimMachine:
    """Pretend hardware: a hopper of N cards, fins on a belt, sensors that answer like the real ones."""

    def __init__(self, cards: int = 12, seed: int = 1, jam_at: int | None = None):
        self.hopper = cards
        self.rng = random.Random(seed)
        self.track_pos = self.rng.uniform(0, 1050)   # where the belt happens to be at power-up
        self.card_on_sensor = False
        self.jam_at = jam_at
        self.fed = 0
        self.light = 0.0
        self.doors = {1: False, 2: False}
        self.levels = [250, 250, 250]
        self.log: list[str] = []

    # Klipper-like
    def card_at_sensor(self) -> bool: return self.card_on_sensor
    def fin_at_home(self) -> bool: return (self.track_pos % 105.0) < 4.0
    def enable(self, on: bool) -> None: pass
    def lights(self, v: float) -> None: self.light = v

    def move(self, stepper: str, mm: float, speed: float, stop_on: int = 0) -> None:
        self._moved = mm
        if stepper == "track":
            if stop_on == 2:
                # run until a fin reaches the home sensor
                d = (105.0 - (self.track_pos % 105.0)) % 105.0
                d = d if d > 0 else 105.0
                self._moved = min(d, mm)
            self.track_pos = (self.track_pos + self._moved) % 1050.0
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
