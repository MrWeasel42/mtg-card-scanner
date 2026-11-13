"""python3 -m pytest machine/sorter (or python3 test_sim.py): the whole cycle on pretend hardware."""
import os, sys, yaml
sys.path.insert(0, os.path.dirname(__file__))
import hw, pc, sorter

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "config.yaml")))

def make(cards, **kw):
    m = hw.SimMachine(cards=cards, **kw)
    return m, sorter.Sorter(CFG, m, m, m, m, m, pc.SimPc(), "/tmp/sorter_test_logs", sleep=lambda _: None)

def test_every_card_lands_in_a_bin():
    m, s = make(30)
    s.run()
    assert sum(s.bin_counts.values()) == 30 and m.hopper == 0

def test_jam_stops():
    m, s = make(5, jam_at=2)
    try:
        s.run(); assert False
    except sorter.Stop:
        pass

def test_rules():
    r = CFG["rules"]
    assert sorter.pick_bin(r, {"ok": True, "pinned": True, "finishUnsure": False})[0] == 1
    assert sorter.pick_bin(r, {"ok": True, "pinned": True, "finishUnsure": True})[0] == 2
    assert sorter.pick_bin(r, {"ok": False})[0] == 3

if __name__ == "__main__":
    for f in (test_every_card_lands_in_a_bin, test_jam_stops, test_rules):
        f(); print("ok", f.__name__)
