"""
Card sorter main program (runs on the Pi 5).

The PC app decides every card's bin (its session's bin rules: price, color, letters, rarity or set). The machine
has up to 9 bins; `bins.in_use` says how many are built (the prototype: 3). Stations sit one fin pitch apart:
    0 landing -> 1 scan -> 2 bin 1 door -> 3 bin 2 door -> ... -> in_use+1 end ramp (bin in_use, also Flagged)
One cycle, every fin on a station:
  1. Card on the scan station: lights on, photo, send to the PC, it answers with the bin.
  2. Card over its bin's door: open, wait for the break-beam to see it fall, close.
  3. Every few cards: check the bin levels; wait while a bin is full.
  4. Feed the next card onto the landing station.
  5. Index the track one station. A card that reaches the end ramp falls into the last bin.
An empty hopper never ends the run: the track is cleared, then the machine waits for more cards. It ends when the
session is stopped on the PC (the PC then shows the flagged cards to review and writes the CSV).

Run:  python3 sorter.py            (on the machine)
      python3 sorter.py --sim 20   (anywhere: fake hardware and a fake PC, 20 cards)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
import time
from dataclasses import dataclass, field

import yaml

import hw
import pc as pclink

HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass
class Card:
    n: int
    result: dict | None = None
    bin: int | None = None
    why: str = ""
    times: dict = field(default_factory=dict)


class Stop(Exception):
    """Something needs a person (jam, missed drop, no home)."""


class SessionOver(Exception):
    """The session was stopped (on the touchscreen, in a browser, or on the PC)."""


class EStop(Stop):
    """The emergency stop was pressed."""


class Sorter:
    def __init__(self, cfg: dict, machine, doors, beams, levels, camera, pc, log_dir: str, sleep=time.sleep):
        self.cfg, self.m, self.doors, self.beams, self.levels, self.camera, self.pc = cfg, machine, doors, beams, levels, camera, pc
        self.sleep = sleep
        self.in_use = int(cfg["bins"]["in_use"])
        if not 2 <= self.in_use <= int(cfg["bins"]["max"]):
            raise ValueError("bins.in_use must be 2..bins.max")
        self.end_bin = self.in_use                        # last bin: off the end of the track, takes Flagged too
        self.end_station = self.in_use + 1
        self.slots: list[Card | None] = [None] * (self.end_station + 1)
        self.count = 0
        self.stopping = False                             # the PC said stop: no more feeding, clear the track
        self.bin_counts = {b: 0 for b in range(1, self.in_use + 1)}
        # read by the touchscreen service
        self.on_say = None                                # callback(msg)
        self.alert: dict | None = None                    # {"kind": "full"|"empty"|"paused"|..., "text": ...}
        self.last_levels: list[int] = []
        self.phase = "idle"
        self.estop = False
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, f"sort_{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
        self._logf = open(self.log_path, "w", newline="")
        self._log = csv.writer(self._logf)
        self._log.writerow(["card", "bin", "bin_label", "bin_wanted", "why", "scan", "name", "set", "number",
                            "pinned", "finish_unsure", "price", "error"])

    def say(self, msg: str) -> None:
        print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)
        if self.on_say:
            self.on_say(msg)

    def nap(self, s: float) -> None:
        """sleep, but the emergency stop ends it at once"""
        if self.estop:
            raise EStop("Emergency stop pressed.")
        self.sleep(s)
        if self.estop:
            raise EStop("Emergency stop pressed.")

    def control(self) -> None:
        """Between cycles: hold while paused; on Stop, stop feeding and clear the track."""
        if self.estop:
            raise EStop("Emergency stop pressed.")
        st = self.pc.status()
        if st.get("stop") or not st.get("active"):
            self.stopping = True
            return
        if st.get("paused"):
            self.wait_while_paused()

    # ---------------------------------------------------------------- PC session
    def join_session(self) -> None:
        st = self.pc.start()
        name = st.get("session") or "?"
        self.say(f"Session: {name} ({st.get('mode', '')}). PC bins in use: {st.get('binsInUse')}, machine: {self.in_use}.")
        if st.get("binsInUse") and int(st["binsInUse"]) != self.in_use:
            self.say(f"WARNING: the PC session uses {st['binsInUse']} bins but this machine has {self.in_use}. "
                     f"Cards for bins it doesn't have go to bin {self.end_bin}. Fix 'Bins in use' on the PC.")

    def wait_while_paused(self) -> None:
        said = False
        self.m.lights(0)
        try:
            while True:
                st = self.pc.status()
                if st.get("stop") or not st.get("active"):
                    self.stopping = True
                    return
                if not st.get("paused"):
                    return
                if not said:
                    self.say("Paused. Waiting...")
                    self.alert = {"kind": "paused", "text": "Paused"}
                    said = True
                self.nap(min(self.cfg["pc"]["poll_s"], 0.5))
        finally:
            if self.alert and self.alert.get("kind") == "paused":
                self.alert = None

    # ---------------------------------------------------------------- homing
    def home(self) -> None:
        t = self.cfg["track"]
        self.say("Homing the belt...")
        if self.m.fin_at_home():                      # a fin is already on the sensor: move it off first
            self.m.move("track", 30, t["home_speed"])
        self.m.move("track", t["home_search_mm"], t["home_speed"], stop_on=2)
        if not self.m.fin_at_home():
            raise Stop("Home sensor never saw a fin. Check the sensor, the white paint on the fins and the belt.")
        self.m.move("track", t["home_to_station_mm"], t["index_speed"])
        self.say("Belt homed: fins on their stations.")

    # ---------------------------------------------------------------- feeding
    def feed(self) -> bool:
        f = self.cfg["feed"]
        for attempt in range(f["retries"] + 1):
            if not self.m.card_at_sensor():
                self.m.move("feed", f["max_to_sensor_mm"], f["speed"], stop_on=2)
            if self.m.card_at_sensor():
                break
        else:
            return False
        self.m.move("feed", f["max_card_mm"], f["speed"], stop_on=-2)
        if self.m.card_at_sensor():
            raise Stop("Card jammed in the feeder (it never cleared the card-clear sensor).")
        self.m.move("feed", f["after_clear_mm"], f["speed"])
        return True

    # ---------------------------------------------------------------- stations
    def scan(self, card: Card) -> None:
        cam = self.cfg["camera"]
        while True:
            self.m.lights(cam["lights_pwm"])
            self.nap(cam["settle_ms"] / 1000)
            jpeg = self.camera.jpeg()
            try:
                r = self.pc.identify(jpeg)
            except Exception as e:                       # PC unreachable: keep sorting, send it to the end bin
                r = {"ok": False, "error": f"PC not reachable: {e}"}
            if r.get("paused") and not r.get("stop"):
                self.wait_while_paused()                 # then take the photo again
                if not self.stopping:
                    continue
            break
        if r.get("stop"):
            self.stopping = True
            r.setdefault("error", "session stopped before this card was read")
        card.result = r
        b = int(r.get("bin") or 0)
        if b < 1 or b > self.end_bin:
            card.why = r.get("error") or (f"PC chose bin {b}, machine has {self.in_use}" if b else "no bin from the PC")
            b = self.end_bin
        else:
            card.why = r.get("binReason") or ""
        card.bin = b
        what = r.get("name") or r.get("error") or "?"
        self.say(f"Card {card.n}: {what} -> bin {b} ({r.get('binLabel') or card.why})")

    def drop(self, card: Card, bin_no: int) -> None:
        d = self.cfg["doors"]
        for attempt in range(2):
            self.doors.set(bin_no, True)
            seen = False
            t_end = time.monotonic() + d["beam_timeout_ms"] / 1000
            while time.monotonic() < t_end:
                if self.beams.broken(bin_no):
                    seen = True
                    break
                self.nap(0.01)
            self.nap(d["open_ms"] / 1000)
            self.doors.set(bin_no, False)
            self.nap(0.25)
            if seen:
                return
            self.say(f"Bin {bin_no}: break-beam didn't see card {card.n} fall (try {attempt + 1}).")
        raise Stop(f"Card {card.n} didn't drop into bin {bin_no}. Check the door and clear the track.")

    def record(self, card: Card, bin_no: int) -> None:
        r = card.result or {}
        self.bin_counts[bin_no] = self.bin_counts.get(bin_no, 0) + 1
        if hasattr(self.pc, "dropped") and r.get("n"):
            self.pc.dropped(r["n"], bin_no)
        self._log.writerow([card.n, bin_no, r.get("binLabel"), r.get("binWanted"), card.why, r.get("scan"), r.get("name"),
                            r.get("setCode"), r.get("number"), r.get("pinned"), r.get("finishUnsure"), r.get("price"),
                            r.get("error")])
        self._logf.flush()

    def check_levels(self) -> None:
        full = self.cfg["levels"]["full_mm"]
        said = None
        try:
            while True:
                dist = self.levels.distances()
                self.last_levels = dist
                fulls = [i + 1 for i, v in enumerate(dist) if 0 < v < full]
                if not fulls:
                    return
                if fulls != said:
                    self.say(f"Bin {', '.join(map(str, fulls))} full ({dist} mm). Empty it; sorting carries on by itself.")
                    self.alert = {"kind": "full", "bins": fulls,
                                  "text": f"Bin {', '.join(map(str, fulls))} full: empty it and sorting carries on by itself"}
                    said = fulls
                self.nap(1)
                st = self.pc.status()
                if st.get("stop") or not st.get("active"):
                    self.stopping = True
                    return
        finally:
            if self.alert and self.alert.get("kind") == "full":
                self.alert = None

    def index(self) -> None:
        t = self.cfg["track"]
        self.m.move("track", t["pitch_mm"], t["index_speed"])
        last = self.slots[-1]
        if last is not None:                          # off the end, onto the ramp
            self.record(last, self.end_bin)
        self.slots = [None] + self.slots[:-1]

    def wait_for_cards(self) -> None:
        """Track is empty and so is the hopper: wait for more cards (or for Stop on the PC)."""
        self.m.lights(0)
        self.say("Waiting for cards (load the hopper; Stop ends the session).")
        self.alert = {"kind": "empty", "text": "Hopper empty: add cards and sorting carries on"}
        try:
            while True:
                waited = 0.0
                while waited < self.cfg["feed"]["empty_poll_s"]:
                    st = self.pc.status()
                    if st.get("stop") or not st.get("active"):
                        raise SessionOver()
                    if st.get("paused"):
                        self.wait_while_paused()
                        if self.stopping:
                            raise SessionOver()
                    self.nap(0.5)
                    waited += 0.5
                if self.feed():
                    self.count += 1
                    self.slots[0] = Card(self.count)
                    self.say("Cards again: carrying on.")
                    return
        finally:
            if self.alert and self.alert.get("kind") == "empty":
                self.alert = None

    # ---------------------------------------------------------------- main loop
    def run(self, limit: int | None = None, resume: bool = False) -> None:
        """resume: carry on after a jam was cleared (the track was emptied by hand; same session)."""
        self.m.enable(True)
        self.phase = "homing"
        if resume:
            self.slots = [None] * (self.end_station + 1)
            self.stopping = False
        self.home()
        if not resume:
            self.join_session()
        self.phase = "sorting"
        door_station = {b + 1: b for b in range(1, self.in_use)}      # station -> bin, doors for bins 1..in_use-1
        try:
            while True:
                self.control()
                card = self.slots[1]
                if card is not None and card.result is None:
                    self.scan(card)
                for st, b in door_station.items():
                    c = self.slots[st]
                    if c is not None and c.bin == b:
                        self.drop(c, b)
                        self.record(c, b)
                        self.slots[st] = None
                if self.count and self.count % self.cfg["levels"]["check_every"] == 0:
                    self.check_levels()
                fed = False
                if not self.stopping and (limit is None or self.count < limit):
                    if self.feed():
                        self.count += 1
                        self.slots[0] = Card(self.count)
                        fed = True
                if not fed and all(s is None for s in self.slots):
                    if self.stopping or (limit is not None and self.count >= limit):
                        break
                    self.wait_for_cards()                 # returns with a card on the landing, or ends the session
                self.index()
        except SessionOver:
            self.say("Session stopped.")
        finally:
            self.phase = "idle"
            try:
                self.m.lights(0)
            except Exception:
                pass
            counts = ", ".join(f"bin {b}: {n}" for b, n in self.bin_counts.items())
            self.say(f"Done: {sum(self.bin_counts.values())} cards ({counts}). Log: {self.log_path}")
            self._logf.flush()

    def close(self) -> None:
        self._logf.close()


def bench(cfg: dict, args) -> int:
    """Bench tests that need no PC: one door, all doors, one photo, bin levels."""
    if args.door:
        b, us = args.door
        d = hw.Doors(cfg)
        d._pulse(d.cfg[b]["channel"], us)
        print(f"Door {b} held at {us} us. Ctrl+C to stop.", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    if args.test_doors:
        d = hw.Doors(cfg)
        for b in d.cfg:
            for _ in range(3):
                d.set(b, open_=True); time.sleep(0.6)
                d.set(b, open_=False); time.sleep(0.6)
            print(f"Door {b} done.", flush=True)
        return 0
    if args.photo:
        m = hw.Klipper(cfg["moonraker"])
        m.lights(float(cfg["camera"]["lights_pwm"]))
        cam = hw.Camera(cfg)
        time.sleep(cfg["camera"]["settle_ms"] / 1000)
        open(args.photo, "wb").write(cam.jpeg())
        m.lights(0.0)
        print(f"Saved {args.photo}", flush=True)
        return 0
    if args.levels:
        lv = hw.Levels(cfg)
        try:
            while True:
                print("  ".join(f"bin {i + 1}: {mm} mm" for i, mm in enumerate(lv.distances())), flush=True)
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Card sorter")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--sim", type=int, metavar="CARDS", help="run with pretend hardware and a pretend PC")
    ap.add_argument("--limit", type=int, help="stop feeding after this many cards")
    ap.add_argument("--home-only", action="store_true", help="home the belt and stop (for setting home_to_station_mm)")
    ap.add_argument("--door", nargs=2, type=int, metavar=("BIN", "US"),
                    help="hold one door servo at a pulse width in microseconds (for finding closed_us / open_us)")
    ap.add_argument("--test-doors", action="store_true", help="open and close every door 3 times using config.yaml")
    ap.add_argument("--photo", metavar="FILE", help="lights on, take one photo to FILE (focus and polarizer setup)")
    ap.add_argument("--levels", action="store_true", help="print each bin-level sensor's distance in mm, every second")
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(args.config))
    if args.door or args.test_doors or args.photo or args.levels:
        return bench(cfg, args)
    log_dir = os.path.join(os.path.expanduser("~"), "sorter_logs")

    if args.sim is not None:
        m = hw.SimMachine(cards=args.sim)
        s = Sorter(cfg, m, m, m, m, m, pclink.SimPc(), log_dir, sleep=lambda _: None)
    else:
        m = hw.Klipper(cfg["moonraker"])
        pc = pclink.PcLink(cfg["pc"]["host"], cfg["pc"]["port"])
        print("Looking for the PC app (Settings -> Phone link)...", flush=True)
        while not pc.connect():
            time.sleep(3)
        print(f"Connected to {pc.name} ({pc.host}).", flush=True)
        s = Sorter(cfg, m, hw.Doors(cfg), hw.Beams(cfg), hw.Levels(cfg), hw.Camera(cfg), pc, log_dir)
    try:
        if args.home_only:
            s.m.enable(True)
            s.home()
        else:
            s.run(limit=args.limit)
            s.close()
    except Stop as e:
        print(f"STOPPED: {e}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
