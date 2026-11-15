"""python3 -m pytest machine/sorter (or python3 test_sim.py): the whole cycle on pretend hardware."""
import copy, os, sys, yaml
sys.path.insert(0, os.path.dirname(__file__))
import hw, pc, sorter

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "config.yaml")))

def make(cards, cfg=CFG, pc_=None, **kw):
    m = hw.SimMachine(cards=cards, **kw)
    return m, sorter.Sorter(cfg, m, m, m, m, m, pc_ or pc.SimPc(), "/tmp/sorter_test_logs", sleep=lambda _: None)

def test_every_card_lands_in_the_bin_the_pc_chose():
    m, s = make(30)
    s.run()
    assert sum(s.bin_counts.values()) == 30 and m.hopper == 0

def test_empty_hopper_waits_then_session_stop_ends_it():
    p = pc.SimPc(idle_polls_to_stop=5)
    m, s = make(4, pc_=p)
    s.run()
    assert p.polls > 5 and sum(s.bin_counts.values()) == 4

def test_cards_added_while_waiting_are_sorted():
    p = pc.SimPc(idle_polls_to_stop=6)
    m, s = make(3, pc_=p)
    real = p.status
    refilled = []
    def status():
        if p.polls == 2 and not refilled:       # someone refills the hopper once while it waits
            m.hopper += 5; refilled.append(1)
        return real()
    p.status = status
    s.run()
    assert sum(s.bin_counts.values()) == 8

def test_nine_bins():
    cfg = copy.deepcopy(CFG); cfg["bins"]["in_use"] = 9
    p = pc.SimPc(bins_in_use=9)
    m, s = make(40, cfg=cfg, pc_=p)
    s.run()
    assert sum(s.bin_counts.values()) == 40 and len(s.bin_counts) == 9 and s.bin_counts[4] > 0

def test_pc_bin_out_of_range_goes_to_the_end():
    p = pc.SimPc(bins_in_use=9)               # PC set to 9 bins, machine only has 3
    m, s = make(30, pc_=p)
    s.run()
    assert set(s.bin_counts) == {1, 2, 3} and sum(s.bin_counts.values()) == 30

def test_jam_stops():
    m, s = make(5, jam_at=2)
    try:
        s.run(); assert False
    except sorter.Stop:
        pass

if __name__ == "__main__":
    for f in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        f(); print("ok", f.__name__)
