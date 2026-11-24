"""
The machine's service: runs the sorter and serves its touchscreen app.

The touchscreen shows http://localhost:8080 full screen; the same page works in any browser on your Wi-Fi at
http://sorter.local:8080 (phone or PC: start sessions, review flagged cards, download the CSVs).

    python3 app.py            on the machine (systemd: card-sorter.service)
    python3 app.py --sim      anywhere: pretend hardware and a pretend identifier, to try the screens
    python3 app.py --sim --sim-engine --sim-photos DIR
                              pretend hardware, but cards identified by the real on-machine engine from photos in DIR

Everything the screen does goes through the JSON API below; the page itself is ui/index.html.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import io
import json
import os
import subprocess
import sys
import threading
import concurrent.futures as cf
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import exports                # noqa: E402
import hw                     # noqa: E402
import identify               # noqa: E402
import rules                  # noqa: E402
import sessions               # noqa: E402
import sorter as sorter_mod   # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
UI = os.path.join(HERE, "ui")
DEFAULT_SETTINGS = {
    "identifyOn": "auto",            # auto (the PC while it's connected, else the machine) | pc | machine
    "priceShow": "both",             # last | top | both
    "sleepMinutes": 10,              # screen dims after this long idle (never while sorting); 0 = never
    "brightness": 100,
    "lastMode": "Catalog",
    "lastSetup": None,               # the bin setup used last time
    "savedSetups": [],               # [{"name": "...", "setup": {...}}]
    "lastName": "",
    "lastSetLock": [],               # sets the last session was locked to (blank = every set)
    "exportFormats": ["ManaBox", "Moxfield"],   # written at Finish (same six formats as the Windows app)
    "assumeNonFoil": False,          # photo can't tell foil from non-foil: call it non-foil instead of flagging
    "theme": "dark",                 # dark | light | system (same choice as the Windows app)
}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ================================================================================================= machine state
class Machine:
    """Owns the hardware, the session store, the identifiers and the sorter thread."""

    def __init__(self, cfg: dict, sim: bool, data_dir: str, sim_engine: bool = False, sim_photos: str = ""):
        self.cfg, self.sim = cfg, sim
        self.sim_photos = sorted(os.path.join(sim_photos, f) for f in os.listdir(sim_photos)
                                 if f.lower().endswith(".jpg")) if sim_photos else []
        self.sim_photo_i = 0
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.store = sessions.Store(os.path.join(data_dir, "sessions"))
        self.settings_path = os.path.join(data_dir, "settings.json")
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        try:
            self.settings.update(json.load(open(self.settings_path)))
        except (OSError, ValueError):
            pass
        self.bins_in_use = int(cfg["bins"]["in_use"])
        self.sim_cards = 25                    # cards in the pretend hopper (--sim)
        self.sim_speed = 0.25                  # seconds per pretend step
        idc = cfg.get("identify") or {}
        self.give_up_s = float(idc.get("pc_give_up_s", 15))
        self.local_wait_s = float(idc.get("machine_wait_s", 120))
        self.pc = identify.SimIdentifier() if sim else identify.PcIdentifier(cfg["pc"]["host"], cfg["pc"]["port"])
        if sim and not sim_engine:
            self.local = identify.SimIdentifier(seed=11, label="This machine (simulated)", delay=0.6)
        else:                                  # the same recognition engine as the PC app, on the Pi
            from engine.local import LocalIdentifier
            self.local = LocalIdentifier(data_dir, threads=idc.get("machine_threads"), log=log)
        self.pc_pool = cf.ThreadPoolExecutor(8, thread_name_prefix="pc-identify")
        self.local_pool = cf.ThreadPoolExecutor(2, thread_name_prefix="machine-identify")   # never queues behind the PC
        self.pc_rest_until = 0.0               # a PC that stopped answering gets a rest before it's asked again
        self.lock = threading.RLock()
        self.session: sessions.Session | None = None
        self.state = "idle"                    # idle | starting | running | stopping | stopped | error | estop
        self.paused = False
        self.stop_requested = False
        self.error = ""
        self.sorter: sorter_mod.Sorter | None = None
        self.thread: threading.Thread | None = None
        self.messages: list[dict] = []
        self.last_card: dict | None = None
        self.started_at = 0.0
        self.hw_status = {"motors": "unknown", "servos": "unknown", "camera": "unknown", "levels": "unknown", "tower": "unknown"}
        self._cam = None
        self._cam_lock = threading.Lock()
        self._sim_machine = None
        self.update = {"available": False, "current": "", "latest": "", "changes": [], "checking": False,
                       "updating": False, "error": ""}
        # resume a session that was running when the power went off: it's kept, stopped, for review
        for s in self.store.all():
            if s.d["state"] in ("running", "stopping"):
                s.d["state"] = "stopped"
                s.d["ended"] = s.d.get("ended") or sessions.now()
                s.save()
        threading.Thread(target=self._background, daemon=True).start()
        if not sim:
            threading.Thread(target=self._catalog_loop, daemon=True).start()

    # ------------------------------------------------------------------ settings
    def save_settings(self) -> None:
        tmp = self.settings_path + ".tmp"
        json.dump(self.settings, open(tmp, "w"), indent=1)
        os.replace(tmp, self.settings_path)

    def say(self, text: str, kind: str = "info") -> None:
        log(text)
        self.messages.append({"t": time.time(), "text": text, "kind": kind})
        del self.messages[:-60]

    # ------------------------------------------------------------------ identifiers
    def identifier(self):
        """Who identifies the next card: the PC app while it's connected (faster), else this machine."""
        mode = self.settings.get("identifyOn", "auto")
        if mode != "machine" and self.pc.online:
            return self.pc
        if mode != "pc" and self.local.ready:
            return self.local
        return None

    def identifier_label(self) -> str:
        i = self.identifier()
        if i is not None:
            return i.label
        mode = self.settings.get("identifyOn", "auto")
        if mode == "pc":
            return "No PC found: cards are kept and flagged"
        st = self.local.status()
        if st["state"] in ("starting", "loading"):
            return "This machine (getting ready…)"
        return "Nothing: " + (st["detail"] or "the machine's card reader isn't ready") + " · cards are kept and flagged"

    def _flag_offline(self, why: str) -> dict:
        return {"ok": False, "offline": True, "error": why + ": card kept and flagged, identify it later"}

    def _identify_local(self, jpeg: bytes, why: str = "", sets=None, turn: bool = False) -> dict:
        loc = self.local
        if not loc.ready and loc.status()["state"] in ("starting", "loading"):
            loc.wait_ready(self.local_wait_s)       # the catalog is still loading: worth the wait (seconds)
        if not loc.ready:
            return self._flag_offline(f"{why or 'No PC'} and the machine's card reader isn't ready ({loc.status()['detail']})")
        r = loc.identify(jpeg, sets=sets, turn=turn) if sets or turn else loc.identify(jpeg)
        r.setdefault("source", loc.label)
        return r

    def identify_card(self, jpeg: bytes, sets=None, turn: bool = False) -> dict:
        """One photo -> the identifier's answer. The PC is asked first while it's connected; if it drops out (an
        error, the background check loses it, or no answer within pc_give_up_s) this machine identifies the same
        photo, and whichever answers first is used. Nothing waits for a PC that has gone.
        sets: the session's set lock (only those printings are considered); turn: identify it turned around."""
        mode = self.settings.get("identifyOn", "auto")
        pc, loc = self.pc, self.local
        if mode == "machine":
            return self._identify_local(jpeg, "Set to identify on this machine", sets, turn)
        if not pc.online:
            if mode == "pc":
                return self._flag_offline("No PC found")
            return self._identify_local(jpeg, "No PC", sets, turn)
        fallback = mode == "auto"
        if fallback and time.monotonic() < self.pc_rest_until and loc.ready:
            return self._identify_local(jpeg, "PC not answering", sets, turn)
        pc_job = self.pc_pool.submit(pc.identify, jpeg, sets, turn) if sets or turn else self.pc_pool.submit(pc.identify, jpeg)
        t0 = time.monotonic()
        why = ""
        while True:
            try:
                r = pc_job.result(timeout=0.2)
                if r.get("ok") or r.get("noCard") or not fallback:
                    return r
                why = f"PC answered: {r.get('error') or 'no answer'}"
                break
            except cf.TimeoutError:
                pass
            except Exception as e:                   # noqa: BLE001
                why = f"PC not reachable ({e})"
                if not fallback:
                    return self._flag_offline(why)
                break
            if fallback and not pc.online:
                why = "PC disconnected"
                break
            if fallback and time.monotonic() - t0 > self.give_up_s and loc.ready:
                why = f"PC took over {self.give_up_s:.0f} s"
                self.pc_rest_until = time.monotonic() + 60      # try it again in a minute
                break
        self.say(f"{why}: this card is identified on the machine.", "warn")
        local_job = self.local_pool.submit(self._identify_local, jpeg, why, sets, turn)
        done, _ = cf.wait([pc_job, local_job], return_when=cf.FIRST_COMPLETED)
        if pc_job in done and not pc_job.exception() and (pc_job.result().get("ok") or pc_job.result().get("noCard")):
            return pc_job.result()                   # the slow PC got there first after all
        return local_job.result()

    def _background(self) -> None:
        """Keeps an eye on the PC, the motor board and updates."""
        last_update_check = 0.0
        while True:
            try:
                if not self.sim:
                    was = self.pc.online
                    self.pc.connect()
                    if self.pc.online != was:
                        if self.pc.online:
                            self.pc_rest_until = 0.0          # it's back: use it again straight away
                        self.say(f"PC {'connected: ' + self.pc.name if self.pc.online else 'disconnected'}.")
                    self.hw_status["motors"] = self._klipper_state()
                    if self.hw_status["motors"] == "ready":
                        t = hw.tower_kind(hw.Klipper(self.cfg["moonraker"]))
                        if t != self.hw_status.get("tower"):
                            self.hw_status["tower"] = t
                            self.say({"raw": "Raw-card tower fitted.", "single": "Single-sleeved tower fitted.",
                                      "double": "Double-sleeved tower fitted.", None: "No tower on the feeder."}.get(t, "Tower sensors not read."))
                if time.time() - last_update_check > 1800:
                    last_update_check = time.time()
                    self.check_update()
            except Exception:
                traceback.print_exc()
            time.sleep(3)

    def _sim_photo(self) -> bytes:
        f = self.sim_photos[self.sim_photo_i % len(self.sim_photos)]
        self.sim_photo_i += 1
        return open(f, "rb").read()

    def _catalog_loop(self) -> None:
        """Keeps the machine's card catalog as fresh as the PC's (a new one is published weekly)."""
        time.sleep(600)
        while True:
            if self.local.ready and hasattr(self.local, "update_catalog"):
                r = self.local.update_catalog(busy=lambda: self.state in ("running", "starting", "stopping"))
                if r == "updated":
                    self.say("Card catalog on the machine updated.")
            time.sleep(12 * 3600)

    def _klipper_state(self) -> str:
        try:
            with urllib.request.urlopen(self.cfg["moonraker"] + "/printer/info", timeout=2) as r:
                st = json.load(r)["result"]["state"]
            return "ready" if st == "ready" else ("not connected" if st in ("error", "shutdown") else st)
        except Exception:
            return "Klipper not running"

    def letter_counts(self) -> dict:
        """Cards identified on this machine, by first letter (alphabetical bins learn your collection)."""
        out: dict = {}
        try:
            for sess in self.store.all():
                for c in sess.cards:
                    f = rules.first_letter(((c.get("card") or {}).get("name")) or "")
                    if f:
                        out[f] = out.get(f, 0) + 1
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------ hardware
    def camera(self):
        if self.sim:
            return self._sim()
        if self._cam is None:
            self._cam = hw.Camera(self.cfg)
            self.hw_status["camera"] = "ready"
        return self._cam

    def _sim(self):
        if self._sim_machine is None:
            self._sim_machine = hw.SimMachine(cards=40)
        return self._sim_machine

    def preview_jpeg(self, auto: bool = True) -> bytes:
        """A small frame for the camera view (lights on while it's open). auto = auto exposure (room light);
        off = the fixed exposure the sorting photos use, to check the picture under the hood lights."""
        with self._cam_lock:
            if self.sim:
                return _placeholder_jpeg()
            cam = self.camera()
            cam.auto(auto)
            try:
                from PIL import Image
                img = cam.cam.capture_image("main")
                img.thumbnail((1280, 960))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=80)
                return buf.getvalue()
            except ImportError:
                return cam.jpeg()

    def lights(self, on: bool) -> None:
        if self.sim:
            return
        try:
            hw.Klipper(self.cfg["moonraker"]).lights(float(self.cfg["camera"]["lights_pwm"]) if on else 0.0)
        except Exception:
            pass

    def _build_sorter(self) -> sorter_mod.Sorter:
        cfg = copy.deepcopy(self.cfg)
        cfg["bins"]["in_use"] = self.bins_in_use
        brain = Brain(self)
        logs = os.path.join(self.data_dir, "logs")
        if self.sim:
            m = hw.SimMachine(cards=self.sim_cards)
            m.jpeg = self._sim_photo if self.sim_photos else _placeholder_jpeg
            self._sim_machine = m
            return sorter_mod.Sorter(cfg, m, m, m, m, m, brain, logs, sleep=lambda s: time.sleep(min(s, 0.05) + self.sim_speed))
        m = hw.Klipper(cfg["moonraker"])
        try:
            doors = hw.Doors(cfg); self.hw_status["servos"] = "ready"
        except Exception as e:
            self.hw_status["servos"] = "not found"
            raise RuntimeError(f"Servo board (PCA9685) not found on I2C: {e}")
        beams = hw.Beams(cfg)
        try:
            levels = hw.Levels(cfg); self.hw_status["levels"] = "ready"
        except Exception as e:
            self.hw_status["levels"] = "not found"
            self.say(f"Bin-level sensors not found ({e}): bins won't be checked for full.", "warn")
            levels = _NoLevels(int(cfg["bins"]["in_use"]))
        with self._cam_lock:
            cam = self.camera()
            cam.auto(False)                    # sorting photos: fixed exposure under the hood lights
        return sorter_mod.Sorter(cfg, m, doors, beams, levels, cam, brain, logs)

    # ------------------------------------------------------------------ sessions
    def start(self, name: str, mode: str, setup: dict, sets=None, keep_going: str = "") -> dict:
        """A new session, or keep_going = an unfinished session's id: carry on scanning into it (Windows: Continue
        session). sets = the set lock: only those printings are considered, anything else is flagged."""
        with self.lock:
            if self.state in ("starting", "running", "stopping"):
                return {"ok": False, "error": "A session is already running."}
            if self.state == "estop":
                return {"ok": False, "error": "Reset the emergency stop first."}
            if keep_going:
                old = self.store.get(keep_going)
                if not old:
                    return {"ok": False, "error": "No such session."}
                if old.d["state"] == "finished":
                    return {"ok": False, "error": "That session is finished: start a new one."}
                old.d["state"] = "running"
                old.save()
                self.session = old
                name, mode = old.name, old.d["mode"]
            else:
                setup = rules.normalize(setup, self.bins_in_use)
                name = (name or "").strip() or f"Scan {dt.datetime.now():%b %-d, %-I:%M %p}"
                sets = rules.parse_sets(sets)
                self.settings.update({"lastMode": mode, "lastSetup": setup, "lastName": name, "lastSetLock": sets})
                self.save_settings()
                self.session = self.store.new(name, mode, setup, sets, self.settings.get("assumeNonFoil", False))
            self.paused = False
            self.stop_requested = False
            self.error = ""
            self.last_card = None
            self.messages.clear()
            self.state = "starting"
            self.started_at = time.time()
        self.say(f"Session {'continued' if keep_going else 'started'}: {name} ({mode}).")
        self._launch(resume=False)
        return {"ok": True, "session": self.session.summary()}

    def _launch(self, resume: bool) -> None:
        def work():
            try:
                if self.sorter is None:
                    self.sorter = self._build_sorter()
                    self.sorter.on_say = lambda m: self.say(m)
                self.sorter.estop = False
                with self.lock:
                    self.state = "running"
                self.sorter.run(resume=resume)
                with self.lock:
                    if self.session and self.session.d["state"] in ("running", "stopping"):
                        self.session.d["state"] = "stopped"
                        self.session.d["ended"] = sessions.now()
                        self.session.save()
                    self.state = "stopped"
                    self._release_sorter()
            except sorter_mod.EStop as e:
                with self.lock:
                    self.state = "estop"
                    self.error = str(e)
            except sorter_mod.Stop as e:
                with self.lock:
                    self.state = "error"
                    self.error = str(e)
                self.say(f"Stopped: {e}", "error")
            except Exception as e:
                traceback.print_exc()
                with self.lock:
                    self.state = "estop" if self.sorter and self.sorter.estop else "error"
                    self.error = str(e) if not (self.sorter and self.sorter.estop) else "Emergency stop pressed."
                self.say(f"Problem: {e}", "error")
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def _release_sorter(self) -> None:
        if self.sorter:
            try:
                self.sorter.close()
            except Exception:
                pass
        self.sorter = None

    def pause(self, on: bool) -> dict:
        with self.lock:
            if self.state not in ("running", "starting"):
                return {"ok": False, "error": "Nothing is running."}
            self.paused = on
        self.say("Paused." if on else "Resumed.")
        return {"ok": True}

    def stop(self) -> dict:
        """Stop feeding; cards already on the track still go to their bins. Then review and Finish."""
        with self.lock:
            if self.state in ("running", "starting"):
                self.stop_requested = True
                self.paused = False
                self.state = "stopping"
                if self.session:
                    self.session.d["state"] = "stopping"
                self.say("Stopping: clearing the track...")
                return {"ok": True}
            if self.state == "error" and self.session:          # stopped by a jam: end the session here
                self.session.d["state"] = "stopped"
                self.session.d["ended"] = sessions.now()
                self.session.save()
                self.state = "stopped"
                self._release_sorter()
                return {"ok": True}
        return {"ok": False, "error": "Nothing is running."}

    def carry_on(self) -> dict:
        """After a jam: the track has been cleared by hand; home and carry on with the same session."""
        with self.lock:
            if self.state != "error" or not self.session or not self.sorter:
                return {"ok": False, "error": "Nothing to carry on with."}
            self.error = ""
            self.state = "starting"
        self.say("Carrying on: homing the belt...")
        self._launch(resume=True)
        return {"ok": True}

    def estop(self) -> dict:
        """Motors off now (Klipper emergency stop), doors closed, sorting stopped."""
        with self.lock:
            if self.sorter:
                self.sorter.estop = True
            prev = self.state
            self.state = "estop"
            self.error = "Emergency stop pressed."
        if not self.sim:
            try:
                urllib.request.urlopen(urllib.request.Request(self.cfg["moonraker"] + "/printer/emergency_stop",
                                                              method="POST"), timeout=2).read()
            except Exception:
                pass
            try:
                if self.sorter:
                    for b in list(self.sorter.doors.cfg):
                        self.sorter.doors.set(b, False)
            except Exception:
                pass
        self.say(f"EMERGENCY STOP (was {prev}).", "error")
        return {"ok": True}

    def reset(self) -> dict:
        """After an emergency stop: restart the motor board. The session (if any) is kept, stopped."""
        if not self.sim:
            try:
                urllib.request.urlopen(urllib.request.Request(self.cfg["moonraker"] + "/printer/firmware_restart",
                                                              method="POST"), timeout=5).read()
            except Exception as e:
                self.say(f"Motor board restart failed: {e}", "warn")
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)
        with self.lock:
            if self.session and self.session.d["state"] in ("running", "stopping"):
                self.session.d["state"] = "stopped"
                self.session.d["ended"] = sessions.now()
                self.session.save()
            self.state = "stopped" if self.session and self.session.d["state"] == "stopped" else "idle"
            self.error = ""
            self._release_sorter()
        self.say("Reset: motor board restarted. Clear any cards off the track before sorting again.")
        return {"ok": True}

    def finish(self, sid: str | None = None) -> dict:
        s = self.store.get(sid) if sid else self.session
        if not s:
            return {"ok": False, "error": "No session."}
        if s is self.session and self.state in ("running", "starting", "stopping"):
            return {"ok": False, "error": "Stop the session first."}
        files = s.finish(self.settings.get("exportFormats"))
        if s is self.session:
            with self.lock:
                self.session = None
                self.state = "idle"
                self.last_card = None
        self.say(f"Session finished: {s.name}" + (f" ({', '.join(files)})" if files else "."))
        return {"ok": True, "exports": files}

    def close_view(self) -> dict:
        """Back to the home screen without finishing (the session stays in the list, unfinished)."""
        with self.lock:
            if self.state in ("stopped",):
                self.session = None
                self.state = "idle"
                self.last_card = None
        return {"ok": True}

    # ------------------------------------------------------------------ status for the screen
    def state_json(self) -> dict:
        s = self.session
        sm = s.summary() if s else None
        sorter = self.sorter
        alert = None
        if self.state == "estop":
            alert = {"kind": "estop", "text": self.error or "Emergency stop"}
        elif self.state == "error":
            alert = {"kind": "jam", "text": self.error}
        elif sorter and sorter.alert:
            alert = sorter.alert
        elif self.state in ("running", "starting") and self.identifier() is None:
            alert = {"kind": "nopc", "text": "Nothing to identify cards with: " + self.identifier_label()}
        levels = []
        if sorter and sorter.last_levels:
            full, empty = self.cfg["levels"]["full_mm"], self.cfg["levels"].get("empty_mm", 230)
            for v in sorter.last_levels:
                levels.append(None if v <= 0 else max(0, min(100, round((empty - v) / max(1, empty - full) * 100))))
        rate = 0.0
        if s and self.started_at and len(s.cards):
            rate = len(s.cards) / max(0.5, (time.time() - self.started_at) / 60)
        return {
            "state": self.state, "paused": self.paused, "error": self.error, "alert": alert,
            "phase": sorter.phase if sorter else "", "session": sm, "lastCard": sessions.card_brief(self.last_card),
            "rate": round(rate, 1), "levels": levels, "binsInUse": self.bins_in_use,
            "pc": {"online": bool(self.pc.online), "name": getattr(self.pc, "name", "")},
            "identifyOn": self.settings["identifyOn"], "identifier": self.identifier_label(),
            "machineId": self.local.status(),
            "hw": self.hw_status, "settings": self.settings_public(), "update": self.update,
            "version": self.version(), "messages": self.messages[-8:], "sim": self.sim,
        }

    def settings_public(self) -> dict:
        return {k: self.settings[k] for k in ("identifyOn", "priceShow", "sleepMinutes", "brightness", "lastMode", "lastName",
                                              "exportFormats", "assumeNonFoil", "theme", "lastSetLock")}

    # ------------------------------------------------------------------ updates
    def _git(self, *args, timeout=60) -> str:
        return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, timeout=timeout,
                              check=True).stdout.strip()

    def version(self) -> str:
        try:
            return self._git("log", "-1", "--format=%cd · %h", "--date=format:%b %-d %Y", timeout=5)
        except Exception:
            return "dev"

    def check_update(self) -> dict:
        u = self.update
        if self.sim or u["updating"]:
            return u
        u["checking"] = True
        try:
            self._git("fetch", "-q", "origin", "main", timeout=60)
            changes = self._git("log", "--format=%s", "HEAD..origin/main", "--", "machine", timeout=10)
            u["changes"] = [c for c in changes.splitlines() if c][:8]
            u["available"] = bool(u["changes"])
            u["current"] = self.version()
            u["latest"] = self._git("log", "-1", "--format=%cd · %h", "--date=format:%b %-d %Y", "origin/main", timeout=5)
            u["error"] = ""
        except Exception as e:
            u["error"] = f"Couldn't check for updates: {e}"
        finally:
            u["checking"] = False
        return u

    def do_update(self) -> dict:
        if self.state in ("running", "starting", "stopping"):
            return {"ok": False, "error": "Stop the session before updating."}
        self.update["updating"] = True
        try:
            self._git("pull", "--ff-only", "-q", "origin", "main", timeout=180)
            req = os.path.join(HERE, "requirements.txt")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "-r", req],
                           timeout=600, capture_output=True)
        except Exception as e:
            self.update["updating"] = False
            self.update["error"] = f"Update failed: {e}"
            return {"ok": False, "error": self.update["error"]}
        self.say("Updated: restarting...")
        threading.Timer(1.5, lambda: os._exit(0)).start()      # systemd starts the new version
        return {"ok": True}


class _NoLevels:
    def __init__(self, n): self.n = n
    def distances(self): return [0] * self.n


class Brain:
    """What the sorter loop talks to: this machine's session (it used to be the PC app's)."""

    def __init__(self, m: Machine):
        self.m = m

    def start(self) -> dict:
        s = self.m.session
        return {"active": True, "session": s.name if s else "", "mode": s.d["mode"] if s else "",
                "binsInUse": s.setup["binsInUse"] if s else self.m.bins_in_use}

    def status(self) -> dict:
        m = self.m
        return {"active": m.session is not None and m.state in ("running", "starting", "stopping"),
                "paused": m.paused, "stop": m.stop_requested}

    def identify(self, jpeg: bytes) -> dict:
        m = self.m
        if m.stop_requested:
            return {"ok": False, "stop": True, "error": "session stopped before this card was read"}
        if m.paused:
            return {"paused": True}
        ident = m.identify_card(jpeg, m.session.d.get("setLock"))
        c = m.session.add_card(jpeg, ident)
        m.last_card = c
        return {"ok": bool(c.get("card")) and not c["noCard"], "n": c["n"],
                "name": (c.get("card") or {}).get("name") or ident.get("error"),
                "bin": c["bin"], "binLabel": c["binLabel"], "binWanted": c["wanted"], "binReason": c["binReason"],
                "flagged": c["flagged"], "price": c.get("price"),
                "setCode": ((c.get("card") or {}).get("setCode") or "").upper(),
                "number": (c.get("card") or {}).get("number"), "scan": c["n"], "error": ident.get("error")}

    def dropped(self, n: int, bin_no: int) -> None:
        if self.m.session:
            self.m.session.mark_dropped(n, bin_no)


def _placeholder_jpeg() -> bytes:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 480), (24, 60, 40))
        d = ImageDraw.Draw(img)
        d.rectangle((200, 90, 440, 420), outline=(230, 230, 230), width=4)
        d.text((230, 230), "simulated camera", fill=(230, 230, 230))
        buf = io.BytesIO(); img.save(buf, "JPEG"); return buf.getvalue()
    except ImportError:
        return b""


# ================================================================================================= HTTP
class Handler(BaseHTTPRequestHandler):
    machine: Machine = None  # set in main
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # ---------------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        extra = dict(extra or {})
        self.send_header("Cache-Control", extra.pop("Cache-Control", "no-store"))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def body(self) -> dict:
        raw = getattr(self, "_raw", b"")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    def file(self, path: str, ctype: str | None = None, download: str | None = None) -> None:
        if not os.path.isfile(path):
            return self.json({"ok": False, "error": "Not found"}, 404)
        ctype = ctype or {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                          ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml", ".csv": "text/csv",
                          ".json": "application/json", ".zip": "application/zip"}.get(os.path.splitext(path)[1], "application/octet-stream")
        extra = {"Content-Disposition": f'attachment; filename="{download}"'} if download else {}
        if ctype.startswith("image/") and "/photos/" in path:
            extra["Cache-Control"] = "max-age=3600"
        self._send(200, open(path, "rb").read(), ctype, extra)

    # ---------------------------------------------------------- routes
    def do_GET(self):
        try:
            self.route("GET")
        except Exception as e:
            traceback.print_exc()
            self.json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._raw = self.rfile.read(n) if n else b""      # always read it, or keep-alive breaks
        try:
            self.route("POST")
        except Exception as e:
            traceback.print_exc()
            self.json({"ok": False, "error": str(e)}, 500)

    def route(self, method: str):
        m = self.machine
        u = urlparse(self.path)
        path, q = unquote(u.path), parse_qs(u.query)
        parts = [p for p in path.split("/") if p]

        if method == "GET" and (path == "/" or path == "/index.html"):
            return self.file(os.path.join(UI, "index.html"))
        if method == "GET" and parts[:1] == ["ui"]:
            p = os.path.normpath(os.path.join(UI, *parts[1:]))
            return self.file(p) if p.startswith(UI) else self.json({}, 404)
        if parts[:1] != ["api"]:
            return self.json({"ok": False, "error": "Not found"}, 404)
        a = parts[1:]

        if method == "GET" and a == ["hello"]:
            return self.json({"ok": True, "machine": "card-sorter", "version": m.version()})
        if method == "GET" and a == ["state"]:
            return self.json(m.state_json())

        # ---- start screen
        if method == "GET" and a == ["setup-options"]:
            pc = m.pc.setup() if m.pc.online else None
            last = rules.normalize(m.settings.get("lastSetup") or rules.default_setup(m.bins_in_use), m.bins_in_use)
            opts = {"ok": True, "binsInUse": m.bins_in_use, "last": last, "lastMode": m.settings["lastMode"],
                    "lastName": m.settings.get("lastName", ""), "saved": m.settings["savedSetups"],
                    "pc": rules.normalize(pc.get("bins"), m.bins_in_use) if pc and pc.get("bins") else None,
                    "pcSaved": [{"name": x.get("name", ""), "setup": rules.normalize(x.get("setup"), m.bins_in_use)}
                                for x in (pc or {}).get("saved") or [] if x.get("setup")],
                    "presets": {by: rules.apply_preset(last, by, m.letter_counts()) for by in rules.SORT_BY},
                    "kinds": rules.KINDS, "colors": list(zip(rules.COLOR_CODES, rules.COLOR_NAMES)),
                    "rarities": rules.RARITY_CODES, "types": rules.TYPE_NAMES,
                    "lastSetLock": m.settings.get("lastSetLock", []),
                    "unfinished": [x.summary() for x in m.store.all() if x.d["state"] == "stopped"][:6],
                    "defaultName": f"Scan {dt.datetime.now():%b %-d, %-I:%M %p}"}
            return self.json(opts)
        if method == "POST" and a == ["labels"]:          # live preview while editing bins
            s = rules.normalize(self.body().get("setup"), m.bins_in_use)
            return self.json({"ok": True, "labels": rules.bin_labels(s), "setup": s})
        if method == "POST" and a == ["preset"]:
            b = self.body()
            s = rules.apply_preset(rules.normalize(b.get("setup"), m.bins_in_use), b.get("by", "Price"), m.letter_counts())
            return self.json({"ok": True, "setup": s, "labels": rules.bin_labels(s)})
        if method == "POST" and a == ["setups", "save"]:
            b = self.body()
            name = (b.get("name") or "").strip() or "My setup"
            saved = [x for x in m.settings["savedSetups"] if x["name"] != name]
            saved.insert(0, {"name": name, "setup": rules.normalize(b.get("setup"), m.bins_in_use)})
            m.settings["savedSetups"] = saved[:12]
            m.save_settings()
            return self.json({"ok": True, "saved": m.settings["savedSetups"]})
        if method == "POST" and a == ["setups", "delete"]:
            name = self.body().get("name")
            m.settings["savedSetups"] = [x for x in m.settings["savedSetups"] if x["name"] != name]
            m.save_settings()
            return self.json({"ok": True, "saved": m.settings["savedSetups"]})

        # ---- running a session
        if method == "POST" and a == ["session", "start"]:
            b = self.body()
            return self.json(m.start(b.get("name", ""), b.get("mode", "Catalog"), b.get("setup") or {},
                                     b.get("sets"), b.get("keepGoing", "")))
        if method == "POST" and a == ["session", "pause"]:
            return self.json(m.pause(True))
        if method == "POST" and a == ["session", "resume"]:
            return self.json(m.pause(False))
        if method == "POST" and a == ["session", "stop"]:
            return self.json(m.stop())
        if method == "POST" and a == ["session", "continue"]:
            return self.json(m.carry_on())
        if method == "POST" and a == ["session", "finish"]:
            return self.json(m.finish())
        if method == "POST" and a == ["session", "close"]:
            return self.json(m.close_view())
        if method == "POST" and a == ["estop"]:
            return self.json(m.estop())
        if method == "POST" and a == ["reset"]:
            return self.json(m.reset())

        # ---- sessions list, review, downloads
        if method == "GET" and a == ["sessions"]:
            return self.json({"ok": True, "sessions": [s.summary() for s in m.store.all()]})
        if len(a) >= 2 and a[0] == "sessions":
            s = m.store.get(a[1])
            if not s:
                return self.json({"ok": False, "error": "No such session"}, 404)
            rest = a[2:]
            if method == "GET" and not rest:
                return self.json({"ok": True, "session": s.summary()})
            if method == "GET" and rest == ["cards"]:
                return self.json({"ok": True, "cards": s.cards_for((q.get("show") or ["review"])[0])})
            if method == "GET" and len(rest) == 2 and rest[0] == "photo":
                return self.file(s.photo_path(int(rest[1])))
            if method == "GET" and len(rest) == 2 and rest[0] == "file":
                p = os.path.normpath(os.path.join(s.folder, rest[1]))
                return self.file(p, download=rest[1]) if p.startswith(s.folder) else self.json({}, 404)
            if method == "GET" and rest == ["bundle.zip"]:
                return self._send(200, s.zip_bytes(), "application/zip",
                                  {"Content-Disposition": f'attachment; filename="{os.path.basename(s.folder)}.zip"'})
            if method == "POST" and rest == ["review"]:
                b = self.body()
                c = s.review(int(b["n"]), b.get("verdict"), b.get("card"), b.get("finish"), b.get("note"),
                             b.get("condition"), b.get("altered"), b.get("misprint"))
                src = c.get("ident", {}).get("source") or ""
                ident = m.local if src.startswith(m.local.label) else m.pc
                if ident and c.get("ident", {}).get("id") and b.get("verdict"):
                    threading.Thread(target=ident.feedback, args=({
                        "id": c["ident"]["id"], "verdict": c["verdict"], "cardId": (c.get("card") or {}).get("id"),
                        "finish": c["finish"], "note": c.get("note", ""), "session": s.name},), daemon=True).start()
                return self.json({"ok": True, "card": c, "session": s.summary()})
            if method == "POST" and rest == ["reidentify"]:
                b = self.body()
                n = int(b["n"])
                if m.identifier() is None:
                    return self.json({"ok": False, "error": m.identifier_label()})
                jpeg = open(s.photo_path(n), "rb").read()
                c = s.replace_ident(n, m.identify_card(jpeg, s.d.get("setLock"), bool(b.get("turn"))))
                return self.json({"ok": True, "card": c, "session": s.summary()})
            if method == "POST" and rest == ["confirm-pinned"]:
                k = s.confirm_pinned()
                return self.json({"ok": True, "marked": k, "session": s.summary()})
            if method == "POST" and rest == ["export"]:
                fm = [f for f in (self.body().get("formats") or m.settings["exportFormats"]) if f in exports.KEYS]
                files = s.export(fm)
                s.d["exports"] = sorted(set(s.d.get("exports", [])) | set(files))
                s.save()
                return self.json({"ok": True, "files": files, "session": s.summary()})
            if method == "POST" and rest == ["photo"]:          # identify an uploaded photo into this session
                if s is m.session and m.state in ("running", "starting", "stopping"):
                    return self.json({"ok": False, "error": "The machine is sorting into this session."})
                if s.d["state"] == "finished":
                    return self.json({"ok": False, "error": "That session is finished."})
                jpeg = getattr(self, "_raw", b"")
                if len(jpeg) < 1000:
                    return self.json({"ok": False, "error": "No photo in the request."})
                jpeg = to_jpeg(jpeg)
                c = s.add_card(jpeg, m.identify_card(jpeg, s.d.get("setLock")))
                return self.json({"ok": True, "card": sessions.card_brief(c), "session": s.summary()})
            if method == "POST" and rest == ["finish"]:
                return self.json(m.finish(s.id))
            if method == "POST" and rest == ["rename"]:
                s.d["name"] = (self.body().get("name") or s.name).strip()
                s.save()
                return self.json({"ok": True, "session": s.summary()})
            if method == "POST" and rest == ["delete"]:
                if s is m.session:
                    return self.json({"ok": False, "error": "That session is open."})
                return self.json({"ok": m.store.delete(s.id)})

        # ---- identify photos without the machine (from a phone or PC browser): a session of uploaded photos
        if method == "POST" and a == ["photos", "session"]:
            b = self.body()
            name = (b.get("name") or "").strip() or f"Photos {dt.datetime.now():%b %-d, %-I:%M %p}"
            s = m.store.new(name, "Catalog", rules.normalize(m.settings.get("lastSetup") or rules.default_setup(m.bins_in_use),
                                                              m.bins_in_use),
                            rules.parse_sets(b.get("sets")), m.settings.get("assumeNonFoil", False), source="photos")
            s.d["state"] = "stopped"
            s.save()
            return self.json({"ok": True, "session": s.summary()})
        if method == "GET" and a == ["export-formats"]:
            return self.json({"ok": True, "formats": [{"key": k, "title": t, "about": d} for k, t, d, _ in exports.FORMATS]})

        # ---- card lookups for review
        if method == "POST" and a == ["printings"]:
            ident = m.identifier() or m.pc
            return self.json({"ok": True, "printings": ident.printings(self.body().get("name", "")) if ident else []})
        if method == "POST" and a == ["search"]:
            ident = m.identifier() or m.pc
            return self.json({"ok": True, "cards": ident.search(self.body().get("text", "")) if ident else []})
        if method == "GET" and len(a) == 2 and a[0] == "card-image":
            img = None
            ident = m.identifier() or m.pc
            if ident:
                img = ident.image(a[1])
            if not img:
                return self.json({"ok": False}, 404)
            return self._send(200, img, "image/jpeg", {"Cache-Control": "max-age=86400"})

        # ---- camera, tools
        if method == "GET" and a == ["preview.jpg"]:
            if m.state in ("running", "starting", "stopping"):
                return self.json({"ok": False, "error": "Camera is busy sorting"}, 409)
            return self._send(200, m.preview_jpeg(auto=q.get("exp", ["auto"])[0] != "fixed"), "image/jpeg")
        if method == "POST" and a == ["lights"]:
            m.lights(bool(self.body().get("on")))
            return self.json({"ok": True})
        if method == "POST" and len(a) == 2 and a[0] == "tools":
            return self.json(tool(m, a[1], self.body()))

        # ---- settings, screen, updates
        if method == "POST" and a == ["settings"]:
            b = self.body()
            for k in ("identifyOn", "priceShow", "sleepMinutes", "brightness", "exportFormats", "assumeNonFoil", "theme"):
                if k in b:
                    if k == "identifyOn" and b[k] not in ("auto", "pc", "machine"):
                        continue
                    if k == "theme" and b[k] not in ("dark", "light", "system"):
                        continue
                    if k == "exportFormats":
                        b[k] = [f for f in b[k] if f in exports.KEYS] or list(exports.DEFAULT)
                    if k == "assumeNonFoil":
                        b[k] = bool(b[k])
                    m.settings[k] = b[k]
            m.save_settings()
            if "brightness" in b:
                set_backlight(int(b["brightness"]))
            return self.json({"ok": True, "settings": m.settings_public()})
        if method == "POST" and a == ["screen"]:
            on = bool(self.body().get("on", True))
            set_backlight(m.settings["brightness"] if on else 0)
            return self.json({"ok": True})
        if method == "POST" and a == ["update", "check"]:
            return self.json({"ok": True, "update": m.check_update()})
        if method == "POST" and a == ["update", "install"]:
            return self.json(m.do_update())
        if method == "POST" and a == ["shutdown"]:
            if m.state in ("running", "starting", "stopping"):
                return self.json({"ok": False, "error": "Stop the session first."})
            if not m.sim:
                err = power_off(m.cfg["moonraker"])
                if err:
                    return self.json({"ok": False, "error": err})
            return self.json({"ok": True})
        return self.json({"ok": False, "error": "Unknown request"}, 404)


SHUTDOWN = "/usr/sbin/shutdown"


def power_off(moonraker: str) -> str | None:
    """Shut the Pi down. Returns None when it's on its way down, or the reason it can't.

    1. Moonraker: KIAUH gives it PolicyKit rights to power off without a password.
    2. sudo without a password prompt: works when install.sh's sudoers rule is in place.
    A plain `sudo shutdown` from this service fails silently when sudo wants a password, which is
    what made the button do nothing."""
    try:
        req = urllib.request.Request(moonraker + "/machine/shutdown", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status == 200:
                return None
    except (ConnectionResetError, TimeoutError):
        return None                                   # it answered by going down mid-reply
    except Exception as e:                            # Moonraker off, or not allowed: try sudo
        why = getattr(e, "reason", e)
        if isinstance(why, (ConnectionResetError, TimeoutError)):
            return None
    if subprocess.run(["sudo", "-n", "-l", SHUTDOWN], capture_output=True).returncode != 0:
        return ("The Pi won't let the app shut it down (sudo wants a password). Over SSH run: "
                "bash ~/mtg-card-scanner/machine/install.sh   then try again.")
    threading.Timer(1, lambda: subprocess.run(["sudo", "-n", SHUTDOWN, "now"])).start()
    return None


def tool(m: Machine, name: str, b: dict) -> dict:
    """Setup and test tools (only when nothing is running)."""
    if m.sim and name.startswith("sim-pc-"):         # --sim only: take the pretend PC away mid-run
        what = name[7:]
        m.pc.online, m.pc.hang_s = what != "off", (20.0 if what == "hang" else 0.0)
        if what == "on":
            m.pc_rest_until = 0.0
        return {"ok": True, "text": {"off": "Pretend PC switched off.", "hang": "Pretend PC will stop answering (hangs).",
                                     "on": "Pretend PC back on."}.get(what, what)}
    if m.state in ("running", "starting", "stopping"):
        return {"ok": False, "error": "Stop the session first."}
    if m.sim:
        return {"ok": True, "text": f"(simulated) {name} done"}
    try:
        if name == "home":
            k = hw.Klipper(m.cfg["moonraker"])
            s = sorter_mod.Sorter(m.cfg, k, None, None, None, None, None, os.path.join(m.data_dir, "logs"))
            k.enable(True)
            s.home()
            s.close()
            return {"ok": True, "text": "Belt homed: a fin is on the scan station."}
        if name == "doors":
            d = hw.Doors(m.cfg)
            for bn in d.cfg:
                for _ in range(2):
                    d.set(bn, True); time.sleep(0.6); d.set(bn, False); time.sleep(0.6)
            return {"ok": True, "text": f"Opened and closed {len(d.cfg)} doors."}
        if name == "door":
            d = hw.Doors(m.cfg)
            d._pulse(d.cfg[int(b["bin"])]["channel"], int(b["us"]))
            return {"ok": True, "text": f"Door {b['bin']} at {b['us']} µs."}
        if name == "levels":
            lv = hw.Levels(m.cfg)
            return {"ok": True, "levels": lv.distances(), "text": "  ".join(f"bin {i + 1}: {v} mm" for i, v in enumerate(lv.distances()))}
        if name == "tower":
            t = hw.tower_kind(hw.Klipper(m.cfg["moonraker"]))
            words = {"raw": "Raw-card tower", "single": "Single-sleeved tower", "double": "Double-sleeved tower",
                     None: "No tower on the feeder", "unknown": "Couldn't read the tower sensors"}
            return {"ok": True, "text": words.get(t, str(t))}
        if name == "calib-shot":
            with m._cam_lock:
                cam = m.camera(); cam.auto(True)
                lens, cam.lens = cam.lens, None              # raw photo, not corrected
                try:
                    j = cam.jpeg()
                finally:
                    cam.lens = lens
            m._calib = (getattr(m, "_calib", []) + [j])[-30:]
            return {"ok": True, "text": f"{len(m._calib)} photo(s). Move or tilt the board and tap again; 8 or more, then Finish."}
        if name == "calib-done":
            shots = getattr(m, "_calib", [])
            path = os.path.expanduser(m.cfg["camera"].get("lens_file", "~/sorter_data/lens.json"))
            r = hw.calibrate_lens(shots, path)
            with m._cam_lock:
                m.camera().lens = hw.Lens(path)
            m._calib = []
            return {"ok": True, "text": f"Lens calibrated from {r['photos']} photos (error {r['rms']:.2f} px). Photos are corrected from now on."}
        if name == "feed":
            k = hw.Klipper(m.cfg["moonraker"]); k.enable(True)
            k.move("feed", float(b.get("mm", 50)), m.cfg["feed"]["speed"])
            return {"ok": True, "text": f"Fed {b.get('mm', 50)} mm."}
        if name == "index":
            k = hw.Klipper(m.cfg["moonraker"]); k.enable(True)
            k.move("track", m.cfg["track"]["pitch_mm"], m.cfg["track"]["index_speed"])
            return {"ok": True, "text": "Track moved one station."}
        if name == "motors-off":
            hw.Klipper(m.cfg["moonraker"]).enable(False)
            return {"ok": True, "text": "Motors off: the belt turns by hand."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Unknown tool {name}"}


def to_jpeg(data: bytes) -> bytes:
    """Uploaded photos can be PNG/WebP/HEIC-as-JPEG from a phone: stored as JPEG like the machine's own photos."""
    if data[:3] == b"\xff\xd8\xff":
        return data
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                return buf.tobytes()
    except ImportError:
        pass
    return data


def set_backlight(level: int) -> None:
    """Touch Display 2 backlight (install.sh lets the pi user write it). level 0..100."""
    base = "/sys/class/backlight"
    try:
        for d in os.listdir(base):
            mx = int(open(os.path.join(base, d, "max_brightness")).read())
            open(os.path.join(base, d, "brightness"), "w").write(str(round(mx * max(0, min(100, level)) / 100)))
    except OSError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Card sorter service + touchscreen app")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--sim", action="store_true", help="pretend hardware and identifier (try the screens anywhere)")
    ap.add_argument("--sim-engine", action="store_true",
                    help="with --sim: identify with the real on-machine engine (downloads the catalog into --data)")
    ap.add_argument("--sim-photos", default="", help="with --sim: folder of card photos the pretend camera takes")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--data", default=os.path.join(os.path.expanduser("~"), "sorter_data"))
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(args.config))
    Handler.machine = Machine(cfg, args.sim, args.data, args.sim_engine, args.sim_photos)
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    srv.daemon_threads = True
    log(f"Card sorter app on http://0.0.0.0:{args.port} ({'simulation' if args.sim else 'machine'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
