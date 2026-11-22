"""Who identifies the cards: the PC while it's there, the machine when it isn't (python3 test_identify.py).

Runs the real app (Machine) in --sim: pretend hardware, a pretend PC that can be switched off or made to hang
mid-card, and a pretend on-machine engine. With MTG_CATALOG=<folder with the published catalog files> it also runs
the real on-machine engine on a drawn card.
"""
import os
import sys
import tempfile
import threading
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import app  # noqa: E402
import rules  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))


def machine(**identify_cfg):
    cfg = dict(CFG)
    cfg["identify"] = {**CFG.get("identify", {}), **identify_cfg}
    m = app.Machine(cfg, True, tempfile.mkdtemp())
    m.sim_speed = 0.0
    m.local.delay = 0.05
    return m


def test_pc_used_while_connected():
    m = machine()
    r = m.identify_card(b"jpeg")
    assert r["source"] == "Simulator" and m.identifier() is m.pc


def test_pc_off_machine_identifies():
    m = machine()
    m.pc.online = False
    r = m.identify_card(b"jpeg")
    assert r["source"].startswith("This machine") and not r.get("offline")
    assert m.identifier() is m.local and m.identifier_label().startswith("This machine")


def test_pc_hangs_mid_card_machine_takes_over_quickly():
    m = machine(pc_give_up_s=1.5)
    m.pc.hang_s = 30                      # a PC that went to sleep: no answer, no error
    t = time.monotonic()
    r = m.identify_card(b"jpeg")
    took = time.monotonic() - t
    assert r["source"].startswith("This machine") and took < 3, took


def test_pc_drops_off_wifi_mid_card():
    m = machine(pc_give_up_s=60)
    m.pc.hang_s = 30
    threading.Timer(0.5, lambda: setattr(m.pc, "online", False)).start()   # the background check loses the PC
    t = time.monotonic()
    r = m.identify_card(b"jpeg")
    assert r["source"].startswith("This machine") and time.monotonic() - t < 2


def test_pc_error_answer_falls_back():
    m = machine()
    m.pc.identify = lambda j: {"ok": False, "error": "The PC app is too old for the machine"}
    assert m.identify_card(b"jpeg")["source"].startswith("This machine")


def test_no_card_from_pc_is_trusted():
    m = machine()
    m.pc.identify = lambda j: {"ok": False, "noCard": True, "error": "No card found in the photo.", "source": "PC"}
    assert m.identify_card(b"jpeg")["source"] == "PC"


def test_pc_only_setting_flags_without_pc():
    m = machine()
    m.settings["identifyOn"] = "pc"
    m.pc.online = False
    r = m.identify_card(b"jpeg")
    assert r.get("offline") and "flagged" in r["error"]


def test_machine_only_setting_never_asks_pc():
    m = machine()
    m.settings["identifyOn"] = "machine"
    m.pc.identify = lambda j: (_ for _ in ()).throw(AssertionError("asked the PC"))
    assert m.identify_card(b"jpeg")["source"].startswith("This machine")


def test_machine_not_ready_flags_honestly():
    m = machine()
    m.pc.online = False
    m.local.ready = False
    m.local.status = lambda: {"state": "no catalog", "detail": "No card catalog on the machine yet.", "catalog": "",
                              "lastMs": None, "avgMs": None}
    r = m.identify_card(b"jpeg")
    assert r.get("offline") and "isn't ready" in r["error"]


def test_whole_run_pc_unplugged_partway():
    """A full session in the simulator: the PC is switched off after a few cards, then hangs, then comes back.
    Every card still gets identified (none left unidentified), and the sorting never stops."""
    m = machine(pc_give_up_s=1.0)
    m.sim_cards = 24
    setup = rules.apply_preset(rules.normalize({"by": "Price", "priceBreaks": [1, 5]}, m.bins_in_use), "Price")
    assert m.start("Failover test", "Catalog", setup)["ok"]
    s = m.session
    m.pc.delay = 0.05
    events = {4: lambda: app.tool(m, "sim-pc-off", {}), 10: lambda: (app.tool(m, "sim-pc-on", {}), setattr(m.pc, "hang_s", 3)),
              16: lambda: app.tool(m, "sim-pc-on", {})}
    done = set()
    t_end = time.monotonic() + 120
    while len(s.cards) < 24 and time.monotonic() < t_end:
        n = len(s.cards)
        if n in events and n not in done:
            done.add(n)
            events[n]()
        time.sleep(0.02)
    m.stop()
    while m.state not in ("stopped", "idle", "error") and time.monotonic() < t_end:
        time.sleep(0.05)
    assert len(s.cards) == 24, len(s.cards)
    sources = [c["ident"].get("source") or "" for c in s.cards]
    offline = [c for c in s.cards if c["offline"]]
    assert not offline, [c["ident"] for c in offline]
    assert any(x == "Simulator" for x in sources) and any(x.startswith("This machine") for x in sources), sources
    assert sources[-1] == "Simulator"           # PC back: it's used again
    print("    sources:", " ".join("PC" if x == "Simulator" else "Pi" for x in sources))


def test_real_engine_on_a_drawn_card():
    cat = os.environ.get("MTG_CATALOG")
    if not cat:
        print("    (skipped: set MTG_CATALOG to a folder with the published catalog files)")
        return
    import cv2
    import numpy as np
    from engine.local import LocalIdentifier
    card = np.full((680, 488, 3), 20, np.uint8)               # a drawn card: frame, title, art, text box
    cv2.rectangle(card, (22, 22), (465, 657), (150, 190, 210), -1)
    cv2.rectangle(card, (34, 34), (453, 80), (225, 235, 240), -1)
    cv2.putText(card, "Lightning Bolt", (44, 66), cv2.FONT_HERSHEY_DUPLEX, 0.95, (10, 10, 10), 2, cv2.LINE_AA)
    cv2.rectangle(card, (40, 100), (447, 360), (60, 90, 140), -1)
    cv2.circle(card, (240, 230), 70, (30, 160, 230), -1)
    cv2.rectangle(card, (40, 400), (447, 610), (225, 235, 240), -1)
    cv2.putText(card, "Deal 3 damage to any target.", (52, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 1, cv2.LINE_AA)
    photo = np.full((1500, 2000, 3), (60, 120, 70), np.uint8)   # on the green scan floor, a little crooked
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [487, 0], [487, 679], [0, 679]]),
                                    np.float32([[660, 270], [1340, 290], [1320, 1240], [640, 1220]]))
    warped = cv2.warpPerspective(card, m, (2000, 1500), flags=cv2.INTER_CUBIC)
    mask = cv2.warpPerspective(np.full((680, 488), 255, np.uint8), m, (2000, 1500))
    photo[mask > 127] = warped[mask > 127]
    photo = cv2.GaussianBlur(photo, (3, 3), 0)
    jpeg = cv2.imencode(".jpg", photo)[1].tobytes()
    li = LocalIdentifier(tempfile.mkdtemp(), catalog_dir=cat, auto_download=False)
    assert li.wait_ready(120), li.status()
    r = li.identify(jpeg)
    assert r["ok"] and r["card"]["name"] == "Lightning Bolt" and r["source"] == "This machine", r
    print(f"    real engine: {r['card']['name']} {r['card']['setCode']} #{r['card']['number']} in {r['ms']} ms")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            t = time.monotonic()
            f()
            print(f"ok {k} ({time.monotonic() - t:.1f} s)")
