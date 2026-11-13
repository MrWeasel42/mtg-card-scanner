"""Sends each photo to the PC app (the same phone link the Android app uses) and returns its answer."""
from __future__ import annotations

import json
import socket
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

    def identify(self, jpeg: bytes) -> dict:
        req = urllib.request.Request(f"http://{self.host}:{self.port}/api/scan", data=jpeg,
                                     headers={"Content-Type": "image/jpeg"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)


class SimPc:
    """Answers like the PC app: most cards pinned, some unsure, a few unreadable."""

    def __init__(self, seed: int = 2):
        import random
        self.rng = random.Random(seed)
        self.name = "SIM-PC"
        self.n = 0

    def connect(self) -> bool:
        return True

    def identify(self, jpeg: bytes) -> dict:
        self.n += 1
        r = self.rng.random()
        if r < 0.08:
            return {"ok": False, "scan": f"Scan {self.n:04d}", "error": "No card found in the photo."}
        return {"ok": True, "scan": f"Scan {self.n:04d}", "name": f"Card {self.n}", "setCode": "SIM", "number": str(self.n),
                "pinned": r > 0.25, "finishUnsure": 0.25 < r < 0.35, "price": round(self.rng.uniform(0.1, 20), 2)}
