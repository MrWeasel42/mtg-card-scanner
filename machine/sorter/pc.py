"""Sends each photo to the PC app (the same phone link the Android app uses) and returns its answer."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request


def discover(timeout: float = 1.5) -> tuple[str, int, str] | None:
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


class PcLink:
    def __init__(self, host: str = "", port: int = 8770):
        self.host, self.port, self.name = host, port, "PC"

    def connect(self) -> bool:
        if not self.host:
            found = discover()
            if not found:
                return False
            self.host, self.port, self.name = found
        try:
            with urllib.request.urlopen(f"http://{self.host}:{self.port}/api/hello", timeout=4) as r:
                self.name = json.load(r).get("pc", self.name)
            return True
        except OSError:
            return False

    def _call(self, path: str, data: bytes | None = None, ctype: str = "text/plain", timeout: float = 10) -> dict:
        req = urllib.request.Request(f"http://{self.host}:{self.port}{path}", data=data,
                                     headers={"Content-Type": ctype}, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:          # 409 paused / stopped still carries a JSON answer
            return json.load(e)

    def identify(self, jpeg: bytes) -> dict:
        """The PC's answer, including the bin it chose (bin, binLabel, binWanted, binReason, flagged)."""
        return self._call("/api/scan", jpeg, "image/jpeg", timeout=90)

    def start(self) -> dict:
        """Join the session open on the PC, or start one with the PC's last session setup."""
        return self._call("/api/session/start", b"")

    def status(self) -> dict:
        try:
            return self._call("/api/status")
        except OSError:
            return {"active": True, "paused": False, "stop": False}   # PC briefly away: keep waiting


class SimPc:
    """Answers like the PC app with a 3-bin price session: Under $1 -> 1, $1-5 -> 2, rest and Flagged -> 3.
    Says Stop after a few idle polls, so a --sim run ends once the hopper is empty."""

    def __init__(self, seed: int = 2, idle_polls_to_stop: int = 3, bins_in_use: int = 3):
        import random
        self.rng = random.Random(seed)
        self.name = "SIM-PC"
        self.n = 0
        self.polls = 0
        self.idle_polls_to_stop = idle_polls_to_stop
        self.bins_in_use = bins_in_use

    def connect(self) -> bool:
        return True

    def start(self) -> dict:
        return {"active": True, "session": "Sim session", "mode": "Catalog", "binsInUse": self.bins_in_use}

    def status(self) -> dict:
        self.polls += 1
        stop = self.polls > self.idle_polls_to_stop
        return {"active": not stop, "paused": False, "stop": stop}

    def identify(self, jpeg: bytes) -> dict:
        self.n += 1
        self.polls = 0
        end = self.bins_in_use
        r = self.rng.random()
        if r < 0.08:
            return {"ok": False, "noCard": True, "scan": None, "error": "No card found in the photo.", "bin": end,
                    "binLabel": "No card"}
        price = round(self.rng.uniform(0.1, 20), 2)
        pinned = r > 0.25
        flagged = not pinned
        wanted = 0 if flagged else (1 if price < 1 else 2 if price < 5 else 3 if price < 10 else 4)
        b = end if flagged or wanted >= end else wanted
        return {"ok": True, "scan": f"Scan {self.n:04d}", "name": f"Card {self.n}", "setCode": "SIM", "number": str(self.n),
                "pinned": pinned, "finishUnsure": False, "price": price, "bin": b, "binWanted": wanted, "flagged": flagged,
                "binLabel": "Flagged" if flagged else ["Under $1", "$1-5", "$5-10", "$10-25"][wanted - 1],
                "binReason": "not sure" if flagged else f"${price:.2f}"}
