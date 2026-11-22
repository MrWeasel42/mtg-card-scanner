"""Compares the Pi engine's answers with the PC app's on the same photos (CI).

    python compare.py <truth.json> <pc.json> <pi.json> [label]

Prints a table (and the GitHub step summary) and fails if the two engines disagree too often.
"""
import json
import os
import sys

MIN_SAME_CARD = 0.95      # same top printing
MIN_SAME_PIN = 0.95       # same pinned / not pinned


def corners(s):
    return [tuple(map(float, xy.split(","))) for xy in (s or "").split()]


def maxdiff(a, b):
    if not a or not b or len(a) != len(b):
        return None if (not a and not b) else float("inf")
    return max(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q))


def main():
    truth = json.load(open(sys.argv[1]))
    pc = {r["file"]: r for r in json.load(open(sys.argv[2]))["results"]}
    pi_doc = json.load(open(sys.argv[3]))
    pi = {r["file"]: r for r in pi_doc["results"]}
    label = sys.argv[4] if len(sys.argv) > 4 else "Pi engine"
    files = sorted(set(pc) & set(pi))
    n = len(files)
    same = dict(top=0, pinned=0, pin_reason=0, flag=0, cands=0, name=0, coll=0, border=0, updown=0)
    right_pc = right_pi = right_pc_name = right_pi_name = 0
    worst = dict(corners=0.0, score=0.0, sim=0.0, refine=0.0, star=0.0, detail=0.0)
    rows = []
    for f in files:
        a, b = pc[f], pi[f]
        t = truth.get(f, {})
        ta, tb = (a["candidates"] or [{}])[0], (b["candidates"] or [{}])[0]
        checks = {
            "top": ta.get("id") == tb.get("id"), "pinned": a["pinned"] == b["pinned"], "pin_reason": a["pinReason"] == b["pinReason"],
            "flag": a["flagReason"] == b["flagReason"], "cands": [c["id"] for c in a["candidates"]] == [c["id"] for c in b["candidates"]],
            "name": a["nameRead"] == b["nameRead"], "coll": a["collector"]["raw"] == b["collector"]["raw"],
            "border": a["border"] == b["border"], "updown": a["upsideDown"] == b["upsideDown"],
        }
        for k, v in checks.items():
            same[k] += v
        right_pc += ta.get("id") == t.get("id")
        right_pi += tb.get("id") == t.get("id")
        right_pc_name += ta.get("name") == t.get("name")
        right_pi_name += tb.get("name") == t.get("name")
        d = maxdiff(corners(a["corners"]), corners(b["corners"]))
        if d is not None:
            worst["corners"] = max(worst["corners"], d)
        if checks["cands"]:
            for x, y in zip(a["candidates"], b["candidates"]):
                worst["score"] = max(worst["score"], abs(x["score"] - y["score"]))
                worst["sim"] = max(worst["sim"], abs(x["sim"] - y["sim"]))
        if a.get("refine") and b.get("refine"):
            worst["refine"] = max(worst["refine"], maxdiff(a["refine"], b["refine"]))
        if a.get("star") and b.get("star"):
            worst["star"] = max(worst["star"], max(abs(x - y) for x, y in zip(a["star"], b["star"])))
        if a.get("detail") and b.get("detail"):
            da, db = {x["id"]: x["score"] for x in a["detail"]}, {x["id"]: x["score"] for x in b["detail"]}
            for k in set(da) & set(db):
                worst["detail"] = max(worst["detail"], abs(da[k] - db[k]))
        if not all(checks.values()):
            rows.append(f"| {f} | {t.get('name', '?')} {t.get('set', '')} #{t.get('number', '')} ({t.get('kind', '')}) | "
                        f"{ta.get('name')} {ta.get('set')} #{ta.get('number')}{' PIN' if a['pinned'] else ''} | "
                        f"{tb.get('name')} {tb.get('set')} #{tb.get('number')}{' PIN' if b['pinned'] else ''} | "
                        f"{', '.join(k for k, v in checks.items() if not v)} | "
                        f"`{a['nameRead']}` / `{b['nameRead']}`; `{a['collector']['raw']}` / `{b['collector']['raw']}` |")
    pct = lambda k: same[k] / max(n, 1)
    pc_ms = sorted(r["ms"] for r in pc.values())
    pi_ms = sorted(r["ms"] for r in pi.values())
    mach = pi_doc.get("machine") or []
    mach_ms = sorted(r["ms"] for r in mach)
    med = lambda xs: xs[len(xs) // 2] if xs else 0
    out = [f"### {label} vs the PC app ({n} photos, catalog {pi_doc.get('catalog')})", "",
           f"- Same top printing: **{same['top']}/{n}**, same pinned: **{same['pinned']}/{n}**, same pin reason: {same['pin_reason']}/{n}, "
           f"same flag: {same['flag']}/{n}, same candidate list: {same['cands']}/{n}",
           f"- Same name read: {same['name']}/{n}, same collector line: {same['coll']}/{n}, same border: {same['border']}/{n}, "
           f"same way up: {same['updown']}/{n}",
           f"- Right printing: PC {right_pc}/{n}, Pi {right_pi}/{n}. Right card: PC {right_pc_name}/{n}, Pi {right_pi_name}/{n}",
           f"- Largest differences: corners {worst['corners']:.2f} px, score {worst['score']:.4f}, picture {worst['sim']:.4f}, "
           f"refine {worst['refine']:.2f} px, star/dot {worst['star']:.4f}, detail {worst['detail']:.4f}",
           f"- Time per photo (median): PC engine on the Windows runner {med(pc_ms)} ms, Pi engine here {med(pi_ms)} ms "
           f"(recognizer only); whole machine answer incl. picture checks {med(mach_ms)} ms; catalog load {pi_doc.get('loadSeconds')} s", ""]
    if rows:
        out += ["| Photo | Card | PC | Pi | Differs in | Read (PC / Pi) |", "|---|---|---|---|---|---|"] + rows
    text = "\n".join(out)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write(text + "\n\n")
    ok = n > 0 and pct("top") >= MIN_SAME_CARD and pct("pinned") >= MIN_SAME_PIN
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
