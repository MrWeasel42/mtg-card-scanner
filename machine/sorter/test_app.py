"""Checks for the bin rules and machine sessions (no hardware needed):  python3 test_app.py"""
import csv, io, os, tempfile, zipfile
import rules
from sessions import Store


def card(name="Lightning Bolt", price=2.0, rarity="common", setc="M10", colors="R", foil=None):
    return {"id": name.lower().replace(" ", "-"), "name": name, "setCode": setc, "setName": setc, "number": "1",
            "rarity": rarity, "colors": colors, "typeLine": "Instant", "finishes": ["nonfoil", "foil"],
            "prices": {"nonfoil": price, "foil": foil}}


def ident(c, pinned=True, **kw):
    d = {"id": "m1", "noCard": False, "pinned": pinned, "card": c, "candidates": [c], "finish": "nonfoil",
         "finishes": [{"key": "nonfoil", "label": "Regular"}], "source": "sim"}
    d.update(kw)
    return d


def test_price_bins():
    s = rules.apply_preset(rules.normalize({"by": "Price", "priceBreaks": [1, 5]}, 3), "Price")
    f = lambda p: rules.choose(s, {"name": "X", "price": p})["bin"]
    assert f(0.5) == 1 and f(3) == 2
    assert f(20) == rules.flagged_bin(s)            # top bin shares the end bin with Flagged
    assert rules.choose(s, {"name": "X", "price": None})["label"] == "Flagged"
    assert rules.choose(s, {"name": "X", "price": 1}, flagged=True)["wanted"] == 0


def test_letters_and_colors():
    s = rules.normalize({"by": "Alphabet", "alphaRanges": ["A-M", "N-Z"]}, 3)
    s = rules.apply_preset(s, "Alphabet")
    assert rules.choose(s, {"name": "Bolt"})["bin"] == 1
    assert rules.choose(s, {"name": "Zap"})["bin"] == 2
    assert rules.first_letter("Æther Vial") == "A"


def test_session_flow():
    with tempfile.TemporaryDirectory() as d:
        st = Store(d)
        sess = st.new("Test box", "Catalog", rules.apply_preset(rules.normalize({"by": "Price", "priceBreaks": [1]}, 3), "Price"))
        a = sess.add_card(b"\xff\xd8jpeg", ident(card(price=0.25)))
        b = sess.add_card(b"\xff\xd8jpeg", ident(card("Black Lotus", 9000, "rare"), pinned=False))
        nc = sess.add_card(b"\xff\xd8jpeg", {"noCard": True})
        assert not a["flagged"] and a["bin"] == 1
        assert b["flagged"] and nc["flagged"]
        assert [c["n"] for c in sess.to_review()] == [2, 3]
        sess.review(2, "ok")
        assert not sess.cards[1]["flagged"] and sess.cards[1]["bin"] == rules.flagged_bin(sess.setup)  # bin stays put
        sess.review(3, "wrong")
        files = sess.finish()
        assert files, "no CSVs written"
        rows = list(csv.DictReader(open(os.path.join(sess.folder, files[0]), encoding="utf-8")))
        names = sorted(r.get("Name") or r.get("name") for r in rows)
        assert names == ["Black Lotus", "Lightning Bolt"], names
        z = zipfile.ZipFile(io.BytesIO(sess.zip_bytes()))
        assert any(n.endswith(".csv") for n in z.namelist())
        assert st.get(sess.id) and st.delete(sess.id) and not st.get(sess.id)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
