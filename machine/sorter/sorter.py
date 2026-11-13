"""
Card sorter main program (runs on the Pi 5).

One cycle, with every fin sitting on a station (stations are 105 mm apart, one fin each):
    0 landing -> 1 scan -> 2 bin 1 door -> 3 bin 2 door -> 4 end ramp (bin 3)
  1. Card on the scan station: lights on, photo, send to the PC app, pick its bin from the rules.
  2. Card over its bin's door: open the door, wait for the break-beam to see it fall, close.
  3. Every few cards: check the bin levels; pause while a bin is full.
  4. Feed the next card onto the landing station (feed until the card-clear sensor sees it, then until it clears).
  5. Index the track one station. A card that reaches station 4 falls off the end into bin 3.

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
    rule: str = ""
    times: dict = field(default_factory=dict)


class Stop(Exception):
    pass


def pick_bin(rules: list[dict], r: dict) -> tuple[int, str]:
    """First matching rule wins; the last bin catches everything."""
    for rule in rules:
        ok = True
        for k, v in rule.items():
            if k in ("bin", "name"):
                continue
            if k == "ok":
                ok &= bool(r.get("ok")) == v
            elif k == "pinned":
                ok &= bool(r.get("pinned")) == v
            elif k == "finish_unsure":
                ok &= bool(r.get("finishUnsure")) == v
            elif k == "min_price":
                ok &= (r.get("price") or 0) >= v
            elif k == "max_price":
                ok &= (r.get("price") or 0) <= v
            elif k == "set_codes":
                ok &= (r.get("setCode") or "").upper() in [s.upper() for s in v]
            elif k == "name_contains":
                ok &= v.lower() in (r.get("name") or "").lower()
            else:
                raise ValueError(f"Unknown rule key: {k}")
        if ok:
            return int(rule["bin"]), rule.get("name", f"bin {rule['bin']}")
    return 3, "default"


class Sorter:
    def __init__(self, cfg: dict, machine, doors, beams, levels, camera, pc, log_dir: str, sleep=time.sleep):
        self.cfg, self.m, self.doors, self.beams, self.levels, self.camera, self.pc = cfg, machine, doors, beams, levels, camera, pc
        self.sleep = sleep
        n = cfg["track"]["stations"]
        self.slots: list[Card | None] = [None] * n
        self.count = 0
        self.hopper_empty = False
        self.bin_counts = {1: 0, 2: 0, 3: 0}
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, f"sort_{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
        self._log = csv.writer(open(self.log_path, "w", newline=""))
        self._log.writerow(["card", "bin", "rule", "scan", "name", "set", "number", "pinned", "finish_unsure", "price", "error"])

    def say(self, msg: str) -> None:
        print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)

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
            self.say(f"No card reached the sensor (try {attempt + 1}).")
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
        self.m.lights(cam["lights_pwm"])
        self.sleep(cam["settle_ms"] / 1000)
        jpeg = self.camera.jpeg()
        try:
            r = self.pc.identify(jpeg)
        except Exception as e:                       # PC unreachable: keep sorting, send it to the catch-all bin
            r = {"ok": False, "error": f"PC not reachable: {e}"}
        card.result = r
        card.bin, card.rule = pick_bin(self.cfg["rules"], r)
        what = r.get("name") or r.get("error") or "?"
        flag = "" if r.get("pinned") else " (check)"
        self.say(f"Card {card.n}: {what}{flag} -> bin {card.bin} ({card.rule})")

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
                self.sleep(0.01)
            self.sleep(d["open_ms"] / 1000)
            self.doors.set(bin_no, False)
            self.sleep(0.25)
            if seen:
                return
            self.say(f"Bin {bin_no}: break-beam didn't see card {card.n} fall (try {attempt + 1}).")
        raise Stop(f"Card {card.n} didn't drop into bin {bin_no}. Check the door and clear the track.")

    def record(self, card: Card, bin_no: int) -> None:
        r = card.result or {}
        self.bin_counts[bin_no] = self.bin_counts.get(bin_no, 0) + 1
        self._log.writerow([card.n, bin_no, card.rule, r.get("scan"), r.get("name"), r.get("setCode"), r.get("number"),
                            r.get("pinned"), r.get("finishUnsure"), r.get("price"), r.get("error")])

    def check_levels(self) -> None:
        full = self.cfg["levels"]["full_mm"]
        while True:
            dist = self.levels.distances()
            fulls = [i + 1 for i, v in enumerate(dist) if 0 < v < full]
            if not fulls:
                return
            self.say(f"Bin {', '.join(map(str, fulls))} full ({dist} mm). Empty it; sorting carries on by itself.")
            self.sleep(3)

    def index(self) -> None:
        t = self.cfg["track"]
        self.m.move("track", t["pitch_mm"], t["index_speed"])
        last = self.slots[-1]
        if last is not None:                          # off the end, onto the ramp
            self.record(last, 3)
        self.slots = [None] + self.slots[:-1]

    # ---------------------------------------------------------------- main loop
    def run(self, limit: int | None = None) -> None:
        self.m.enable(True)
        self.home()
        door_station = {2: 1, 3: 2}
        try:
            while True:
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
                if not self.hopper_empty and (limit is None or self.count < limit):
                    if self.feed():
                        self.count += 1
                        self.slots[0] = Card(self.count)
                    else:
                        self.hopper_empty = True
                        self.say("Hopper empty: finishing the cards on the track.")
                if all(s is None for s in self.slots):
                    break
                self.index()
        finally:
            self.m.lights(0)
            self.say(f"Done: {sum(self.bin_counts.values())} cards. Bin 1: {self.bin_counts[1]}, bin 2: {self.bin_counts[2]}, "
                     f"bin 3: {self.bin_counts[3]}. Log: {self.log_path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Card sorter")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--sim", type=int, metavar="CARDS", help="run with pretend hardware and a pretend PC")
    ap.add_argument("--limit", type=int, help="stop feeding after this many cards")
    ap.add_argument("--home-only", action="store_true", help="home the belt and stop (for setting home_to_station_mm)")
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(args.config))
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
    except Stop as e:
        print(f"STOPPED: {e}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
