# One app, two screens

The Windows app and the sorter's touchscreen (also at **http://sorter.local:8080** on any phone or PC) are the same
app on two kinds of screen. They share the recognition engine, the card catalog, the bin rules, the review answers
and the export files. Each has the same features, laid out for its screen: a mouse and a big monitor on the PC,
fingers on the 7″ touchscreen.

| Feature | Windows app | Machine screen / its web page |
|---|---|---|
| Start a session: name, Catalog or Sort, bins | Start a session | Start sorting |
| Set lock (only these sets) | ✓ | ✓ |
| Continue an unfinished session | Continue session | Start sorting → Or continue a session; Sessions → ⏯ Keep scanning |
| Bin editor: 7 rule kinds, presets | ✓ | ✓ |
| Saved bin setups (★ Save these bins as…) | ✓ (also offered on the machine as "★ name (PC)") | ✓ |
| Identify photos (drop / pick photos, no machine) | Scan page | 🖼 Identify photos (web page) |
| Review tabs: to check / pinned / reviewed, search | ✓ | ✓ |
| ✓ Correct · ≈ printing not listed · ✗ wrong · pick another printing | ✓ | ✓ |
| Every printing of the card, search a name | ✓ | ✓ |
| Finish, condition, Altered, Misprint, note | ✓ | ✓ |
| Identify again / turned around (F) | ✓ | ✓ |
| Big side-by-side compare, bottoms only (Z) | ✓ | ✓ (tap the photo) |
| Last card (Backspace), Skip (S), Enter = correct | ✓ | ✓ (keyboard on the web page) |
| Mark all pinned correct | ✓ | ✓ |
| Export: ManaBox, Moxfield, Deckbox, TCGplayer, ROCA, General | ✓ | ✓ (exports.py, same columns) |
| Export formats picked in Settings | ✓ | ✓ |
| Rename / delete a session | Home → Recent sessions (✎, 🗑 to the Recycle Bin) | Sessions → a session |
| Assume non-foil when the photo can't tell | ✓ | ✓ |
| Look: Dark / Light / System | ✓ | ✓ |
| The machine's run, pause / stop / emergency stop | Card sorter page | ✓ |
| Machine tools (home, doors, levels, tower, feed, motors off, lights) | Card sorter page | Tools |
| Identify on (PC / machine), price while sorting, updates, shut down | Card sorter page | Settings |

Only on one side, because of the hardware:

* **Windows only:** phone link and firewall, the data folders, the card database download (the machine keeps its
  own copy up to date), the compare-view layout.
* **Machine only:** the live camera view and lens calibration (they need the checkerboard under the camera), screen
  sleep and brightness, the on-screen keyboard.

When you add a feature to one side, add it to the other (or to the list just above, with the reason).
