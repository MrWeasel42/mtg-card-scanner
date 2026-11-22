# Design audit, rev H (Nov 22, 2026)

Every printed part, every screw, every cable, every moving part and every install step, checked against the real CAD
before more filament goes into the prototype. All the checks are scripts in `hardware/audit/` (run them all with
`audit/run_all.sh`); they run again after every change until everything passes.

## What is checked

| Check | Script | Result |
|---|---|---|
| Every placed part against every other part (173 parts + bought bodies), boolean overlap | `pairs.py` | 0 unexpected overlaps |
| Every screw on its real axis: holes line up, clearance in the clamped parts, thread engagement (insert / pilot / nut / T-nut / motor), tip doesn't bottom out or hit anything, head has room, a key reaches it **with only the parts that are on at that step** | `joints.py` + `joint_table.py` | 51 / 51 joint groups pass |
| Wall round every heat-set insert and M2 pilot | `insert_walls.py` | all >= 1.15 mm (inserts >= 1.6) |
| Every cable route (50) through real openings only, never through material | `wires.py` (routes in `cad/wiring.py`) | 50 / 50 clear |
| Doors 0-65 deg, links + horns + screw heads 0-63 deg, against every part and every cable | `motion.py` | pass |
| Install moves: tray in/out, tower off, gate lift, pressure roller float, lid off with the camera, PSU slide-in, servo into its bracket, door up from below, hinge pin in, hub boards through the window, bins out | `motion.py` | pass |
| Raw, single-sleeved and double-sleeved card: every pose from the hopper to the bottom of a bin | `sim.py` | no collisions |
| Every printed part in its print orientation: bed fit, islands, overhangs, bridges, thin walls, sealed voids | `printability.py` | see the print notes |
| The original fit check (bought parts at datasheet size, fin path, card lane, belt loop, cable lengths) | `cad/fitcheck.py` | 207 / 207 |
| Pictures and a video from the same meshes | `render_stills.py`, `video.py` | `renders/` |

## What was wrong, and what changed

Nothing below has been printed yet except where it says so. **Already printed and still good:** fit coupon, both motor
standoffs, and all of plate 1 (screen cradle, 9 servo links, wall mount, exit rollers, feed roller) are unchanged.
**Reprint:** the gate (v3 could never be adjusted, see 1).

1. **Gate couldn't work.** Its nut trap was 4 mm wide (an M3 nut is 5.5), its screw hole was 1.5 mm off the tower's,
   it could slide out of the open track, and there was ~0 travel. The 3 deg lean also tipped the foot 1.4 mm across
   the card, so two cards could slip under the high side. **v4:** the gate hangs on an M3 x 12 (insert in its top,
   clearance hole + jam nut on the tower boss), slides in a closed track with a 45 deg underside, and its underside is
   cut level across the card (the gap is now even: 1.03 at the entry, 0.48 at the exit end, the same on both sides).
   Travel 1.3 mm. Gaps: raw 0.45, single 0.70, double 0.85.
2. **Rail screws couldn't go in.** The base's walls sat over the M5 heads, the back wire channel covered every
   module's back rail screws, and an M5 x 10 only reached 2.2 mm into the T-nut. Feet are now counterbored (4.2 mm in
   the T-nut), the base walls are notched round the heads, and the channel has a gap at every back screw.
3. **PSU cradles were inside the scan module's feet** (2 cm3 overlap each) and screwed into the PSU's vented cover.
   New U cradles hang between the walls (M3 x 12 from outside into captive nuts), the PSU slides in from the feeder end
   and is held by a zip tie. It moved toward the front: the IEC inlet's body and lead bend needed the room behind it.
4. **Screen wall mount floated 9 mm off the wall** and its holes lined up with nothing. It now sits flat on the scan
   module's front wall on 2 inserts (the pod's standoff grew 9 mm so the screen is where it was).
5. **Hood feet:** the front pair had no inserts under them, the back pair was 1 mm off. Feet now land on inserts at
   X 228 (scan walls) and X 363 (bin module 1). Wall-top inserts had 0.9 mm of wall: outward bosses, inserts moved out.
6. **Bay cover holes didn't line up** with the base's inserts; fan holes had no clearance. Full-width cover, fan moved
   clear of the SKR's plugs, cover raised above the rail screw heads.
7. **Feed motor standoff:** 2 of its 4 inserts were above the top of the base; the rest had 4 mm of wall. The back
   wall is thickened and a tab rises above the hopper floor for the upper pair.
8. **Start-idler tension screws were in the base's end face**, hidden behind the scan module's wall. The stub now
   sits in an `idler_slider` in a pocket in each post; the screw comes from the hopper side.
9. **Electronics tray couldn't go in**: wider than the window, narrower than the rails. 122 mm tray on two ledges,
   2 hold-down screws; SKR moved 4 mm so the left screw can be reached.
10. **Scan floor had nothing holding it up.** It now rests on ledges along both strips.
11. **Module end-face screws couldn't be fitted** (blind holes both sides); **the end cap had no screws.** Removed;
    the end cap screws into end-face inserts; **joint plates** tie each module's walls to the next.
12. **Side walls couldn't print as noted.** On their outer face the wall floated 17 mm above the bed (huge supports),
    and the front sides (245 tall) didn't fit the bed. Back and scan walls now print **upright** with a 45 deg gusset
    under the strip and pointed window roofs; bin/end front sides lost their posts (they made them too tall), hang
    from the tie bar + joint plate, and print flat. Bins are located by two fingers under the front wall.
13. **Doors couldn't open.** The front "rest ledge" was right under the door's free edge, which swings down. Removed:
    the servo holds the door shut.
14. **Doors couldn't be fitted.** The barrels had to come up through the strip (notches were closed underneath) and
    the second barrel and the door's edge passed through the servo bracket. Notches open underneath, second barrel
    shorter, a notch in the door at the bracket. Order is now door, then servo.
15. **Servo couldn't slide into its bracket** (its tabs hit the strip): the gusset is notched over its path.
16. **Tie bar's insert hole (4.7) was in a 4 mm bar** (broke out both faces). 8 mm bosses at the ends.
17. **End ramp ran into the back strip.** Trimmed.
18. **Card-clear sensor housing hit the exit shaft** (which slides 2 mm to tension the loop). Sensor moved to X 124.5;
    `after_clear_mm` 10 -> 13 in config.yaml so the tail still clears the nip before a fin comes down.
19. **Snap-in IEC inlet needs a 1-2.5 mm panel**, the plate was 4: thinned to 2.5 round the cutout.
20. **M2.5 screws** (SKR, camera, PCA9685) aren't in the kit, and the camera plate's holes were too big to thread.
    All M2 x 8 self-tapping into 2.1 pilots now.
21. **Sheen cap:** an M3 x 8 couldn't reach through it, and the hood's insert holes were 5.4 deep for a 5.7 insert.
    Counterbores + M3 x 12, deeper holes.
22. **Link to horn:** an M2 x 8 runs 1 mm into the servo case. M2 x 6.
23. **Fin lanes ran out to the door/floor edges**, leaving a 7 mm unsupported strip when printed face down. Lanes stop
    0.9 mm short; fin fingers 0.5 mm narrower.
24. **Hopper floor was a 112 mm bridge.** Two webs underneath: 32 / 42 / 32 mm spans.
25. Small ones: sealed void in the tray ledges, O-ring hooks that started in mid-air, the bin-level sensor's view
    clipping the front wall's edge, bearing seats in upright walls (now teardrops), track-motor insert 0.65 mm from
    the end face (end module 3 mm longer), hub boards re-laid out under the new window, bins offset 0.75 mm so raw (88)
    and sleeved (91) cards both clear their walls.
26. **Cables:** many routes in WIRING.md went through walls and motors (they were straight-line estimates). All 50
    are re-routed through real openings; the feeder base now has a stub of the back channel, so the looms go from the
    bay straight into it.

## What the simulation can't prove (check on the prototype)

* Feeding: friction of the O-rings vs the gate pad, and how the stack weight behaves near empty.
* Belt tension and fin timing (set with the fin gauge), servo holding torque with a card on the door.
* Bearing seats printed sideways (now teardrops): if a 625/685 is loose or tight, ream or shim; the fit coupon tested
  these sizes printed flat.
* Supports are still needed under: the card-clear sensor pocket (base), the hood's pads and LED ledges, the scan back
  wall's strip over the belt-home sensor, the end back wall's strip over the ramp flange. Turn on elephant-foot
  compensation (0.15 mm) for the parts that slide (gate, slider, tray).
