"""Convert ROCA Sorter CSVs (TCGplayer names) to ManaBox CSVs (exact printing by Scryfall ID)."""
import csv, glob, gzip, json, os, re, sys, collections
S = sys.argv[1]            # scratchpad dir with default_cards.jsonl.gz, sets.json, roca/*.csv
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

import unicodedata
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
sets = json.load(open(f"{S}/sets.json"))["data"]
by_set_name = {norm(x["name"]): x["code"] for x in sets}
codes = {x["code"] for x in sets}

by_num = {}; by_name = collections.defaultdict(list)
with gzip.open(f"{S}/default_cards.jsonl.gz", "rt") as f:
    for line in f:
        line = line.strip().rstrip(",")
        if not line.startswith("{"): continue
        c = json.loads(line)
        if c.get("digital"): continue
        if c.get("lang") != "en" and (c["set"], c["collector_number"]) in by_num: continue
        by_num[(c["set"], c["collector_number"].lower())] = c
        names = {c["name"], c["name"].split(" // ")[0]}
        for face in c.get("card_faces") or []: names.add(face.get("name", ""))
        if c.get("flavor_name"): names.add(c["flavor_name"])
        for n in names:
            if n: by_name[norm(n)].append(c)

def set_code(name):
    m = re.search(r"\(([A-Za-z0-9]{2,5})\)\s*$", name)
    if m and m.group(1).lower() in codes: return m.group(1).lower()
    n = name
    if n == "The List Reprints": return "plst"
    ed = {"4th Edition": "4ed", "5th Edition": "5ed", "6th Edition": "6ed", "7th Edition": "7ed", "8th Edition": "8ed",
          "9th Edition": "9ed", "10th Edition": "10e"}
    if n in ed: return ed[n]
    m2 = re.match(r"Commander: (.+): (.+)$", n)
    if m2: n = m2.group(2) + " Commander"
    if n.startswith("Commander: "): n = n[11:] + " Commander"
    if n.startswith("Universes Beyond: "): n = n[18:]
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n).replace("Deck Reprints", "Decks")
    return by_set_name.get(norm(n))

def clean_name(n):
    n = re.sub(r"\s*\[[^\]]*\]\s*$", "", n)
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n)
    if " - " in n: n = n.split(" - ", 1)[1]
    return n

def find(row):
    code = set_code(row["Set Name"]); num = row["Number"].strip().lower(); name = clean_name(row["Card Name"])
    if code:
        for k in (num, num.lstrip("0"), re.sub(r"[a-z]$", "", num)):
            c = by_num.get((code, k))
            if c and norm(name) in {norm(x) for x in [c["name"], c["name"].split(" // ")[0], c.get("flavor_name") or ""]} | {norm(f.get("name","")) for f in c.get("card_faces") or []}:
                return c, "set+number"
        same = [c for c in by_name.get(norm(name), []) if c["set"] == code]
        if same:
            exact = [c for c in same if c["collector_number"].lower() == num]
            raw = row["Card Name"]
            if not exact and "Retro Frame" in raw: exact = [c for c in same if c.get("frame") == "1997"]
            if not exact and "Showcase" in raw: exact = [c for c in same if "showcase" in (c.get("frame_effects") or [])]
            if not exact and "Borderless" in raw: exact = [c for c in same if c.get("border_color") == "borderless"]
            return (exact or same)[0], "set+name"
    cands = by_name.get(norm(name), [])
    if cands:
        exact = [c for c in cands if c["collector_number"].lower() == num]
        pick = exact[0] if exact else sorted(cands, key=lambda c: c.get("released_at", ""))[-1]
        return pick, "name only"
    return None, "not found"

COND = {"Near Mint": "near_mint", "Lightly Played": "lightly_played", "Moderately Played": "moderately_played",
        "Heavily Played": "heavily_played", "Damaged": "damaged"}
HEAD = "Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Signed,Condition,Language,Proxy,Purchase price currency\n"
def q(v): return '"' + str(v).replace('"', '""') + '"'

def write(path, counter):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(HEAD)
        for (cid, finish, cond), n in sorted(counter.items(), key=lambda kv: cards[kv[0][0]]["name"]):
            c = cards[cid]
            f.write(f'{q(c["name"])},{c["set"].upper()},{q(c["set_name"])},{c["collector_number"]},{finish},{c.get("rarity","")},{n},,{cid},,false,false,false,{cond},en,false,\n')

cards = {}; total = collections.Counter(); total_rej = collections.Counter(); report = []
stats = collections.Counter()
for path in sorted(glob.glob(f"{S}/roca/*.csv")):
    tag = re.search(r"(mtg\d*)\.csv", path).group(1)
    acc = collections.Counter(); rej = collections.Counter()
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if row["Card Name"] == "Back of a Magic Card":
            stats["card back (skipped)"] += 1; continue
        if not row["Card Name"]:
            stats["blank (ROCA could not identify)"] += 1; continue
        c, how = find(row)
        stats[how] += 1
        if how != "set+number": report.append((tag, row["Sequence ID"], row["Card Name"], row["Set Name"], row["Number"], how, c and f'{c["name"]} [{c["set"].upper()} #{c["collector_number"]}]'))
        if not c: continue
        cards[c["id"]] = c
        finish = {"Foil": "foil", "Etched": "etched"}.get(row["Finish"], "normal")
        key = (c["id"], finish, COND.get(row["Condition"], "near_mint"))
        (rej if row["Rejected"] == "Y" else acc)[key] += 1
    write(f"{OUT}/{tag} - ManaBox.csv", acc)
    total += acc; total_rej += rej
write(f"{OUT}/ALL accepted - ManaBox.csv", total)
write(f"{OUT}/ALL rejects - ManaBox.csv", total_rej)
with open(f"{OUT}/match report.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["List", "ROCA seq", "ROCA name", "ROCA set", "ROCA number", "How matched", "Matched to"]); w.writerows(report)
print(dict(stats)); print("accepted cards", sum(total.values()), "unique", len(total), "rejects", sum(total_rej.values()))
