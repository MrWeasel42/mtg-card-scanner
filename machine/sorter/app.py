"""
The machine's service: runs the sorter and serves its touchscreen app.

The touchscreen shows http://localhost:8080 full screen; the same page works in any browser on your Wi-Fi at
http://sorter.local:8080 (phone or PC: start sessions, review flagged cards, download the CSVs).

    python3 app.py            on the machine (systemd: card-sorter.service)
    python3 app.py --sim      anywhere: pretend hardware and a pretend identifier, to try the screens

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
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hw                     # noqa: E402
import identify               # noqa: E402
import rules                  # noqa: E402
import sessions               # noqa: E402
import sorter as sorter_mod   # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
UI = os.path.join(HERE, "ui")
DEFAULT_SETTINGS = {
    "identifyOn": "auto",            # auto (PC when it's on, else the machine) | pc | machine
    "priceShow": "both",             # last | top | both
    "sleepMinutes": 10,              # screen dims after this long idle (never while sorting); 0 = never
    "brightness": 100,
    "lastMode": "Catalog",
    "lastSetup": None,               # the bin setup used last time
    "savedSetups": [],               # [{"name": "...", "setup": {...}}]
    "lastName": "",
}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ================================================================================================= machine state
class Machine:
    """Owns the hardware, the session store, the identifiers and the sorter thread."""

    def __init__(self, cfg: dict, sim: bool, data_dir: str):
        self.cfg, self.sim = cfg, sim
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
        self.pc = identify.SimIdentifier() if sim else identify.PcIdentifier(cfg["pc"]["host"], cfg["pc"]["port"])
        self.local = None                      # the on-machine identifier (coming later)
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
        self.hw_status = {"motors": "unknown", "servos": "unknown", "camera": "unknown", "levels": "unknown"}
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
        mode = self.settings["identifyOn"]
        if mode == "machine":
            return self.local
        if mode == "pc":
            return self.pc
        if self.pc.online:
            return self.pc
        return self.local

    def identifier_label(self) -> str:
        i = self.identifier()
        if i is None:
            return "On the machine (coming soon)" if self.settings["identifyOn"] == "machine" else "No PC found"
        return i.label

    def _background(self) -> None:
        """Keeps an eye on the PC, the motor board and updates."""
        last_update_check = 0.0
        while True:
            try:
                if not self.sim:
                    was = self.pc.online
                    self.pc.connect()
                    if self.pc.online != was:
                        self.say(f"PC {'connected: ' + self.pc.name if self.pc.online else 'disconnected'}.")
                    self.hw_status["motors"] = self._klipper_state()
                if time.time() - last_update_check > 1800:
                    last_update_check = time.time()
                    self.check_update()
            except Exception:
                traceback.print_exc()
            time.sleep(3)

    def _klipper_state(self) -> str:
        try:
            with urllib.request.urlopen(self.cfg["moonraker"] + "/printer/info", timeout=2) as r:
                st = json.load(r)["result"]["state"]
            return "ready" if st == "ready" else ("not connected" if st in ("error", "shutdown") else st)
        except Exception:
            return "Klipper not running"

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

    def preview_jpeg(self) -> bytes:
        """A small frame for the camera view (lights on while it's open)."""
        with self._cam_lock:
            if self.sim:
                return _placeholder_jpeg()
            cam = self.camera()
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
            m.jpeg = _placeholder_jpeg
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
            levels = _NoLevels(len(cfg["levels"]["xshut_gpio"]))
        with self._cam_lock:
            cam = self.camera()
        return sorter_mod.Sorter(cfg, m, doors, beams, levels, cam, brain, logs)

    # ------------------------------------------------------------------ sessions
    def start(self, name: str, mode: str, setup: dict) -> dict:
        with self.lock:
            if self.state in ("starting", "running", "stopping"):
                return {"ok": False, "error": "A session is already running."}
            if self.state == "estop":
                return {"ok": False, "error": "Reset the emergency stop first."}
            setup = rules.normalize(setup, self.bins_in_use)
            name = (name or "").strip() or f"Scan {dt.datetime.now():%b %-d, %-I:%M %p}"
            self.settings.update({"lastMode": mode, "lastSetup": setup, "lastName": name})
            self.save_settings()
            self.session = self.store.new(name, mode, setup)
            self.paused = False
            self.stop_requested = False
            self.error = ""
            self.last_card = None
            self.messages.clear()
            self.state = "starting"
            self.started_at = time.time()
        self.say(f"Session started: {name} ({mode}).")
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
        files = s.finish()
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
            alert = {"kind": "nopc", "text": "No PC found: cards are kept and flagged until it's back"}
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
            "hw": self.hw_status, "settings": self.settings_public(), "update": self.update,
            "version": self.version(), "messages": self.messages[-8:], "sim": self.sim,
        }

    def settings_public(self) -> dict:
        return {k: self.settings[k] for k in ("identifyOn", "priceShow", "sleepMinutes", "brightness", "lastMode", "lastName")}

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
        ident_by = m.identifier()
        if ident_by is None:
            ident = {"ok": False, "offline": True, "error": "No PC found (on-machine identifying is coming)"}
        else:
            ident = ident_by.identify(jpeg)
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
                    "presets": {by: rules.apply_preset(last, by) for by in rules.SORT_BY},
                    "kinds": rules.KINDS, "colors": list(zip(rules.COLOR_CODES, rules.COLOR_NAMES)),
                    "rarities": rules.RARITY_CODES, "types": rules.TYPE_NAMES,
                    "defaultName": f"Scan {dt.datetime.now():%b %-d, %-I:%M %p}"}
            return self.json(opts)
        if method == "POST" and a == ["labels"]:          # live preview while editing bins
            s = rules.normalize(self.body().get("setup"), m.bins_in_use)
            return self.json({"ok": True, "labels": rules.bin_labels(s), "setup": s})
        if method == "POST" and a == ["preset"]:
            b = self.body()
            s = rules.apply_preset(rules.normalize(b.get("setup"), m.bins_in_use), b.get("by", "Price"))
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
            return self.json(m.start(b.get("name", ""), b.get("mode", "Catalog"), b.get("setup") or {}))
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
                which = (q.get("show") or ["review"])[0]
                cards = s.to_review() if which == "review" else (
                    [c for c in s.cards if c["flagged"]] if which == "flagged" else s.cards)
                return self.json({"ok": True, "cards": cards[::-1] if which == "all" else cards})
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
                c = s.review(int(b["n"]), b.get("verdict", "ok"), b.get("card"), b.get("finish"), b.get("note"),
                             b.get("condition"))
                ident = m.identifier() or m.pc
                if ident and c.get("ident", {}).get("id"):
                    threading.Thread(target=ident.feedback, args=({
                        "id": c["ident"]["id"], "verdict": c["verdict"], "cardId": (c.get("card") or {}).get("id"),
                        "finish": c["finish"], "note": c.get("note", ""), "session": s.name},), daemon=True).start()
                return self.json({"ok": True, "card": c, "session": s.summary()})
            if method == "POST" and rest == ["reidentify"]:
                n = int(self.body()["n"])
                ident_by = m.identifier()
                if ident_by is None:
                    return self.json({"ok": False, "error": "No PC found to identify with."})
                jpeg = open(s.photo_path(n), "rb").read()
                c = s.replace_ident(n, ident_by.identify(jpeg))
                return self.json({"ok": True, "card": c, "session": s.summary()})
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
            return self._send(200, m.preview_jpeg(), "image/jpeg")
        if method == "POST" and a == ["lights"]:
            m.lights(bool(self.body().get("on")))
            return self.json({"ok": True})
        if method == "POST" and len(a) == 2 and a[0] == "tools":
            return self.json(tool(m, a[1], self.body()))

        # ---- settings, screen, updates
        if method == "POST" and a == ["settings"]:
            b = self.body()
            for k in ("identifyOn", "priceShow", "sleepMinutes", "brightness"):
                if k in b:
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
                threading.Timer(1, lambda: subprocess.run(["sudo", "shutdown", "now"])).start()
            return self.json({"ok": True})
        return self.json({"ok": False, "error": "Unknown request"}, 404)


def tool(m: Machine, name: str, b: dict) -> dict:
    """Setup and test tools (only when nothing is running)."""
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
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--data", default=os.path.join(os.path.expanduser("~"), "sorter_data"))
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(args.config))
    Handler.machine = Machine(cfg, args.sim, args.data)
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
