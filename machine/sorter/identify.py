"""Who says what a card is. The machine asks an identifier and decides the bin itself.

  PcIdentifier     the Windows app on your PC (Settings -> Phone link on), over Wi-Fi. The faster one.
  LocalIdentifier  (engine/local.py) the same recognition engine on the Pi: same catalog, same AI model, same text
                   reader models, same rules (a Python copy of the C# code, checked against it in CI:
                   .github/workflows/pi-engine.yml). Used whenever the PC isn't there, even partway through a card.

Every identifier answers identify(jpeg) with the same dict:
    {"ok": True, "id": "m12", "noCard": False, "pinned": True, "pinReason": "...", "flagReason": None,
     "finish": "nonfoil", "finishUnsure": False, "finishes": [{"key": "nonfoil", "label": "Non-foil"}, ...],
     "card": CARD, "candidates": [CARD, ...], "source": "PC (DESKTOP-1)"}
    CARD = {"id": scryfall id, "name", "setCode", "setName", "number", "rarity", "colors", "typeLine", "lang",
            "finishes": ["nonfoil", "foil"], "prices": {"nonfoil": 1.2, "foil": 3.4, "etched": None}, "imageUrl"}
"""
from __future__ import annotations

import json
import random
import socket
import time
import urllib.error
import urllib.request


def discover(timeout: float = 1.5) -> tuple[str, int, str] | None:
    """The Windows app answers a UDP broadcast on port 8771 with "MTGSCAN <port> <pc name>"."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(timeout)
    try:
        s.sendto(b"MTGSCAN?", ("255.255.255.255", 8771))
        data, (host, _) = s.recvfrom(256)
        parts = data.decode(errors="replace").split(" ", 2)
        if len(parts) >= 2 and parts[0] == "MTGSCAN":
            return host, int(parts[1]), parts[2] if len(parts) > 2 else "PC"
    except OSError:
        return None
    finally:
        s.close()
    return None


def price_for(card: dict | None, finish: str | None) -> float | None:
    if not card:
        return None
    p = card.get("prices") or {}
    if finish == "foil":
        return p.get("foil") if p.get("foil") is not None else p.get("nonfoil")
    if finish == "etched":
        for k in ("etched", "foil", "nonfoil"):
            if p.get(k) is not None:
                return p[k]
        return None
    return p.get("nonfoil") if p.get("nonfoil") is not None else p.get("foil")


class PcIdentifier:
    kind = "pc"

    def __init__(self, host: str = "", port: int = 8770):
        self.fixed_host = host
        self.host, self.port, self.name = host, port, ""
        self.online = False
        self.supports_identify = True
        self.last_try = 0.0

    @property
    def label(self) -> str:
        return f"PC ({self.name})" if self.name else "PC"

    def connect(self) -> bool:
        """Find the PC (or check it's still there). Cheap to call often: it backs off between tries."""
        now = time.monotonic()
        if not self.online and now - self.last_try < 4:
            return False
        self.last_try = now
        if not self.fixed_host:
            found = discover()
            if not found:
                self.online = False
                return False
            self.host, self.port, self.name = found
        try:
            with urllib.request.urlopen(f"http://{self.host}:{self.port}/api/hello", timeout=3) as r:
                info = json.load(r)
            self.name = info.get("pc", self.name or self.host)
            self.online = True
        except (OSError, ValueError):
            self.online = False
        return self.online

    def _call(self, path: str, data: bytes | None = None, ctype: str = "application/json", timeout: float = 10):
        req = urllib.request.Request(f"http://{self.host}:{self.port}{path}", data=data,
                                     headers={"Content-Type": ctype}, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                return json.loads(body) if r.headers.get_content_type() == "application/json" or body[:1] in b"{[" else body
        except urllib.error.HTTPError as e:
            if e.code == 404 and path.startswith("/api/identify"):
                self.supports_identify = False
            try:
                return json.load(e)
            except ValueError:
                return {"ok": False, "error": f"PC answered {e.code}"}

    def identify(self, jpeg: bytes, sets=None, turn: bool = False) -> dict:
        """sets: the session's set lock; turn: identify it turned around (older PC apps ignore both: the session
        then flags any card outside the locked sets)."""
        q = "&".join(x for x in (f"sets={','.join(sets)}" if sets else "", "turn=1" if turn else "") if x)
        try:
            r = self._call("/api/identify" + ("?" + q if q else ""), jpeg, "image/jpeg", timeout=90)
        except OSError as e:
            self.online = False
            return {"ok": False, "error": f"PC not reachable ({e})", "offline": True}
        if not self.supports_identify:
            return {"ok": False, "error": "The PC app is too old for the machine: update it (it asks on start).",
                    "offline": True}
        r.setdefault("source", self.label)
        return r

    def printings(self, name: str) -> list[dict]:
        try:
            r = self._call("/api/printings", json.dumps({"name": name}).encode())
            return r.get("printings", []) if isinstance(r, dict) else []
        except OSError:
            return []

    def search(self, text: str) -> list[dict]:
        try:
            r = self._call("/api/search", json.dumps({"text": text}).encode())
            return r.get("cards", []) if isinstance(r, dict) else []
        except OSError:
            return []

    def feedback(self, item: dict) -> None:
        try:
            self._call("/api/feedback", json.dumps(item).encode(), timeout=5)
        except OSError:
            pass

    def setup(self) -> dict | None:
        """The bin setup saved in the Windows app, to offer as "My PC setup"."""
        try:
            r = self._call("/api/setup", timeout=4)
            return r if isinstance(r, dict) and r.get("ok") else None
        except OSError:
            return None

    def image(self, card_id: str) -> bytes | None:
        try:
            r = self._call(f"/api/card-image/{card_id}", timeout=8)
            return r if isinstance(r, bytes) else None
        except OSError:
            return None


class SimIdentifier:
    """Answers like the PC with made-up cards (for --sim and the tests). Can be switched off or made to hang, to try
    what the machine does when the PC goes away mid-run."""
    kind = "sim"

    def __init__(self, seed: int = 3, label: str = "Simulator", delay: float = 0.0):
        self.rng = random.Random(seed)
        self.n = 0
        self.label = label
        self.delay = delay
        self.online = True
        self.ready = True
        self.hang_s = 0.0                 # > 0: the next identify hangs this long, then fails (a PC that went to sleep)

    def status(self) -> dict:
        return {"state": "ready", "detail": "Simulated", "catalog": "sim", "lastMs": None, "avgMs": None}

    def wait_ready(self, timeout: float) -> bool:
        return True

    NAMES = ["Lightning Bolt", "Counterspell", "Llanowar Elves", "Swords to Plowshares", "Dark Ritual", "Sol Ring",
             "Island", "Thoughtseize", "Goblin Guide", "Brainstorm", "Opt", "Wrath of God", "Zuran Orb"]

    def connect(self) -> bool:
        return True

    def _card(self, name: str, i: int) -> dict:
        colors = {"Lightning Bolt": "R", "Counterspell": "U", "Llanowar Elves": "G", "Swords to Plowshares": "W",
                  "Dark Ritual": "B", "Thoughtseize": "B", "Goblin Guide": "R", "Brainstorm": "U", "Opt": "U",
                  "Wrath of God": "W"}.get(name, "")
        return {"id": f"sim-{name.replace(' ', '-').lower()}-{i}", "name": name, "setCode": ["M10", "2XM", "MH3"][i % 3],
                "setName": ["Magic 2010", "Double Masters", "Modern Horizons 3"][i % 3], "number": str(100 + i),
                "rarity": ["common", "uncommon", "rare", "mythic"][i % 4], "colors": colors,
                "typeLine": "Basic Land — Island" if name == "Island" else "Instant", "lang": "en",
                "finishes": ["nonfoil", "foil"], "prices": {"nonfoil": round(self.rng.uniform(0.05, 40), 2),
                                                             "foil": round(self.rng.uniform(1, 80), 2), "etched": None},
                "imageUrl": ""}

    def identify(self, jpeg: bytes, sets=None, turn: bool = False) -> dict:
        if self.hang_s > 0:
            time.sleep(self.hang_s)
            if self.hang_s > 0:
                self.online = False
            return {"ok": False, "error": "PC not reachable (timed out)", "offline": True}
        if not self.online:
            return {"ok": False, "error": "PC not reachable (connection refused)", "offline": True}
        if self.delay:
            time.sleep(self.delay)
        self.n += 1
        r = self.rng.random()
        if r < 0.05:
            return {"ok": False, "noCard": True, "error": "No card found in the photo.", "source": self.label}
        name = self.rng.choice(self.NAMES)
        cands = [self._card(name, i) for i in range(3)]
        pinned = r > 0.2
        return {"ok": True, "id": f"sim{self.n}", "noCard": False, "pinned": pinned,
                "pinReason": "name + set + number agree" if pinned else None,
                "flagReason": None if pinned else "not sure of the printing", "finish": "nonfoil",
                "finishUnsure": False, "finishes": [{"key": "nonfoil", "label": "Non-foil"}, {"key": "foil", "label": "Foil"}],
                "card": cands[0], "candidates": cands, "source": self.label}

    def printings(self, name: str) -> list[dict]:
        return [self._card(name, i) for i in range(6)]

    def search(self, text: str) -> list[dict]:
        return [self._card(n, 0) for n in self.NAMES if text.lower() in n.lower()][:10]

    def feedback(self, item: dict) -> None:
        pass

    def setup(self) -> dict | None:
        return None

    def image(self, card_id: str) -> bytes | None:
        return None
