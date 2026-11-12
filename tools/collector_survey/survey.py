"""
Where is the collector number printed? Samples real card images from every frame era and special
layout on Scryfall, OCRs the whole bottom strip of each card, and records where the collector number
(and set code) was found, as fractions of the card's width/height.

Output: survey.json (every card) and survey.md (one row per group).
"""
import json, re, sys, time, urllib.parse, urllib.request
import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR

GROUPS = {
    # Real old-frame printings
    "1993 frame (Alpha-Mirage)": "frame:1993 -is:reprint game:paper (set:lea or set:3ed or set:ice or set:mir)",
    "1997 frame (Exodus-Scourge)": "frame:1997 (set:uds or set:7ed or set:ody or set:ons or set:pcy)",
    "Time Spiral timeshifted": "set:tsb",
    "2003 frame (8th-M14)": "frame:2003 (set:8ed or set:m10 or set:zen or set:rtr or set:ths)",
    "2003 frame planeswalkers": "frame:2003 t:planeswalker",
    "Kamigawa flip cards": "is:flip set:chk",
    "Future Sight futureshifted": "frame:future set:fut",
    # Modern frame
    "2015 frame (M15-2022)": "frame:2015 (set:ori or set:dom or set:eld or set:neo)",
    "2023+ collector line": "frame:2015 (set:mom or set:dsk or set:blb)",
    "Planeswalkers (modern)": "frame:2015 t:planeswalker",
    "Sagas": "t:saga frame:2015",
    "Battles": "t:battle",
    "Split / aftermath": "is:split frame:2015",
    "Adventures": "layout:adventure",
    "Showcase frames": "frame:showcase",
    "Borderless": "border:borderless frame:2015 -t:land",
    "Full-art basics": "t:basic is:fullart frame:2015",
    "Extended art": "frame:extendedart",
    "Etched foils (Commander Legends)": "set:cmr is:etched frame:etched",
    "Secret Lair": "set:sld frame:2015",
    "The List": "set:plst",
    "Prerelease / stamped promos": "is:prerelease frame:2015",
    "Universes Beyond": "set:ltr frame:2015",
    "Un-sets (Unfinity)": "set:unf -t:attraction",
    "Attractions": "t:attraction",
    "Mystery Booster playtest": "set:cmb1",
    # Retro-frame reprints of modern cards
    "Retro: MH2": "set:mh2 frame:1997",
    "Retro: H2R (MH2 timeshifts)": "set:h2r",
    "Retro: MH3": "set:mh3 frame:1997",
    "Retro: BRR (Brothers' War artifacts)": "set:brr",
    "Retro: DMR": "set:dmr frame:1997",
    "Retro: TSR timeshifted": "set:tsr frame:1997",
    "Retro: Secret Lair": "set:sld frame:1997",
    "Retro: Mystery Booster 2": "set:mb2 frame:1997",
    "Retro: other sets": "frame:1997 date>=2021 -set:mh2 -set:h2r -set:mh3 -set:brr -set:dmr -set:tsr -set:sld -set:mb2",
    "Retro 1993 frame reprints": "frame:1993 date>=2021",
}
PER_GROUP = int(sys.argv[1]) if len(sys.argv) > 1 else 6
UA = {"User-Agent": "mtg-card-scanner-survey/1.0", "Accept": "application/json"}


def get(url, raw=False):
    time.sleep(0.12)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if raw else json.loads(data)


def search(q, n):
    url = "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode({"q": q, "order": "random", "unique": "prints"})
    try:
        res = get(url)
    except Exception as e:
        print("  search failed:", e)
        return []
    return res.get("data", [])[:n]


ocr = RapidOCR()


def survey(card):
    face = card if "image_uris" in card else card["card_faces"][0]
    img = cv2.imdecode(np.frombuffer(get(face["image_uris"]["large"], raw=True), np.uint8), cv2.IMREAD_COLOR)
    img = cv2.resize(img, (976, 1360))
    y0 = int(1360 * 0.80)
    strip = cv2.resize(img[y0:], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    res, _ = ocr(strip)
    num = card["collector_number"].lstrip("0").lower()
    setc = card["set"].upper()
    lines, num_at, set_at = [], None, None
    for box, text, conf in res or []:
        b = np.array(box) / 2
        x0, x1 = b[:, 0].min() / 976, b[:, 0].max() / 976
        y = (b[:, 1].mean() + y0) / 1360
        lines.append({"text": text, "x0": round(x0, 3), "x1": round(x1, 3), "y": round(y, 3), "conf": round(float(conf), 2)})
        up = text.upper().replace("O", "0")
        m = re.search(r"(?<![0-9])0*" + re.escape(num.upper().replace("O", "0")) + r"(?![0-9])", up)
        if m and num_at is None:
            # Where in the line is the number? Estimate by character position.
            f = (m.start() + 0.5 * len(m.group())) / max(len(text), 1)
            num_at = {"x": round(x0 + f * (x1 - x0), 3), "y": round(y, 3), "line": text}
        if setc in text.upper() and set_at is None:
            set_at = {"x0": round(x0, 3), "y": round(y, 3), "line": text}
    return {"name": card["name"], "set": card["set"], "number": card["collector_number"], "frame": card.get("frame"),
            "frame_effects": card.get("frame_effects", []), "border": card.get("border_color"), "released": card.get("released_at"),
            "number_at": num_at, "set_at": set_at, "lines": lines}


out, rows = {}, []
for group, q in GROUPS.items():
    print(f"== {group}: {q}", flush=True)
    cards = search(q, PER_GROUP)
    results = []
    for c in cards:
        try:
            r = survey(c)
        except Exception as e:
            print("  ", c.get("name"), "failed:", e)
            continue
        results.append(r)
        na = r["number_at"]
        print(f"   {r['name'][:28]:28} {r['set']:5} #{r['number']:6} num@{(na['x'], na['y']) if na else None} set@{(r['set_at']['x0'], r['set_at']['y']) if r['set_at'] else None}", flush=True)
    out[group] = results
    found = [r for r in results if r["number_at"]]
    xs = sorted(r["number_at"]["x"] for r in found)
    ys = sorted(r["number_at"]["y"] for r in found)
    sets = sum(1 for r in results if r["set_at"])
    rows.append(f"| {group} | {len(results)} | {len(found)} | {xs[0] if xs else '-'}–{xs[-1] if xs else '-'} | "
                f"{ys[0] if ys else '-'}–{ys[-1] if ys else '-'} | {sets} | {found[0]['number_at']['line'] if found else ''} |")

json.dump(out, open("survey.json", "w"), indent=1)
with open("survey.md", "w") as f:
    f.write("| Group | Cards | Number found | Number x (0=left,1=right) | Number y | Set code found | Example line |\n|---|---|---|---|---|---|---|\n")
    f.write("\n".join(rows) + "\n")
print(open("survey.md").read())
