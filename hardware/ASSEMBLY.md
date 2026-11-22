# Assembly, piece by piece

The order matters in a few places: some parts can't be reached, or can't get past something, once the next one is on.
Those steps are marked **⚠ before**. Sizes are mm (in). Every cable, its route and its length is in [WIRING.md](WIRING.md),
what to print for each stage is in [PRINT_PLAN.md](PRINT_PLAN.md), and every screw is listed at the end.

Every screw below was checked in the CAD on its real axis: the holes line up, the length reaches the thread without
bottoming out or hitting anything behind it, the head has room, and a key reaches it **at the point in this order where
you fit it** (`audit/joints.py`). Every install move (tray, PSU, servo, door, pin, hub panel, bins) was swept through
its path against the parts already in place (`audit/motion.py`).

## 0. Inserts first (all parts, before anything is bolted together)

Press every M3 heat-set insert (Ruthex M3 x 5.7) with the insert tip, straight in, flush or 0.2 mm below the surface.
Let each part cool before you load it.

| Part | Inserts |
|---|---|
| feeder_base | 2 tower screws (hopper floor), 4 bay cover (front, beside the window), 4 feed-motor standoff (back wall: 2 low, 2 in the tab above the floor), 2 post tops (pressure bridge), 2 tray hold-downs (top of the front of each ledge, from inside the bay) |
| idler_slider (x2) | 1 each, in the hopper-side face |
| gate_plate | 1 in the top |
| scan_side_back | 4 inlet plate, 2 wall top (hood feet, X 228 and 349), 1 belt-home sensor (underside of the strip) |
| scan_side_front | 2 wall top (hood feet), 2 screen mount (outer face) |
| bin_side_back (each) | 4 back panel (outer face round the window), 2 joint plates (outer face, just under the floor line) |
| bin_side_front (each) | 2 joint plates |
| tie_bar (each) | one in each end boss |
| end_side_back | 4 track-motor standoff, 2 ramp flange (underside of the strip), 1 joint plate, 2 end cap (in the end face) |
| end_side_front | 1 joint plate, 2 end cap (end face) |
| hood | 2 sheen cap (back bosses) |
| camera_plate | 2 in the tabs |
| screen_cradle | 4 in the ears |
| pod_cover | 2 for the 5 V converter |
| pod_standoff | 2 in the face that meets the pod |

## 1. Frame

1. Cut the 2020 rails (9-bin build): back rail 1462 mm (X 0 to the end cap), second back rail 976 mm (X 355 to 1331,
   under the doors of bin modules 1-8), front rail 355 mm (under the feeder base and scan module only). Stage A uses
   the same back rail (it sticks out past the end module until modules 3-8 go in) or a shorter cut for now.
2. Drop M5 T-nuts in the top slots: 2 per foot, for every foot you'll bolt down. Feet are counterbored, so the
   screws are **M5 x 10** everywhere (4 mm of foot + the slot's 1.8 mm lip leaves 4.2 mm in the T-nut).

## 2. Feeder base

1. **Tower-ID hall sensors ⚠ before the tray.** Bend each A3144's legs down 90° at the body. Branded (flat,
   lettered) face UP, legs down the 3 mm hole, body flat in its 6.2 mm pocket; a drop of CA under it. A 30 cm female
   jumper on each leg underneath, heat-shrink each. The pocket by the front of the hopper is sensor 1 (Z-STOP), the
   back one is sensor 2 (E0-STOP).
2. Feed shaft: two 685ZZ in the inner ribs, the 625 in the back wall, shaft in from the back, the 20T pulley for the
   122 mm loop on its front end. Exit shaft: 625 bearings in the wall slots, exit roller and its 20T pulley.
   Loop on, push the exit bearings back to tension it. **⚠ Tighten both 20T pulley grub screws now**: later you can
   only reach them through the bay window with a long ball-end key.
3. Feed roller onto the feed shaft (grub on the flat), O-rings on both rollers (3 + 2).
4. Feed motor: standoff onto the back wall (4 x M3 x 10; the upper two go into the tab above the hopper floor), motor
   onto the standoff (4 x M3 x 8), coupler. Both sets of screw heads sit inside the standoff: use an L-key through its
   open top or bottom (19 mm of room for the short arm). Tighten the coupler through the open top.
5. Start idlers (one each post): drop an **idler_slider** into the pocket in the post top (insert toward the hopper).
   Two 685ZZ in the idler pulley. Hold the pulley between the posts and push a 23 mm piece of the 5 mm shaft in from
   **outside** the post: through the outer slot, the slider (press fit: a vise or a few light taps), the inner slot and
   the pulley. M3 x 20 tension screw from the post's hopper-side face (X 115) into the slider's insert, snug for now.
6. Card-clear TCRT5000 into its pocket under the floor (moved to X 124.5: the window over it must be clear).
7. **Electronics tray.** SKR Pico on its 4 bosses with **4 x M2 x 8** (self-tapping through the board's 2.7 mm holes;
   there are no M2.5 screws in the kit and the bosses are drilled for M2). Slide the tray in through the front window
   (it's 122 wide, the window 126) onto the two ledges, and hold it with 2 x M3 x 8 into the ledge inserts at the
   front corners. 6 V step-down on the left inner wall (foam tape + a zip tie). Wire the bay (WIRING.md): 24 V, motors,
   sensors, hall sensors to Z-STOP / E0-STOP with 5 V from the probe header's 5 V pin, LEDs, sheen, fan, UART + I2C from
   the Pi, the bin bus. Everything for the bins leaves the bay through the opening in the back wall at X 115-146,
   straight into the back wire channel.
8. Bay cover: the 30 mm fan on it (4 x M3 x 12 + nuts), cover on (4 x M3 x 8). It now spans the whole base front.
9. Pressure bridge: top roller on 40 mm of 5 mm shaft (grub on the flat), a collar outside each hanger, drop the
   axle into the slots, bridge onto the post tops (2 x M3 x 10). The roller rests on the exit roller and lifts freely.
   Optional: a small O-ring from each axle end to the hook under the slot for more grip.
10. Tower: magnets into the skirt pockets first (press with a flat bolt head; **south pole down**). Raw tower = front
    pocket only, single-sleeved = back, double = both.
    **Gate (v4):** silicone pad under its foot; slide the gate up into the track **from below** (tower off the
    machine), M3 x 12 cap screw down through the boss into the gate's insert, then an M3 nut on the screw on top of
    the boss as a jam nut. The gate hangs on the screw: turn it to set the gap, lock the nut. It can lift for a thick
    card but never drops below the setting.
    Set the tower on the floor and fit its 2 x M3 x 16 cap screws (they replace the "thumb screws").
    Gate gap at the foot's exit end: raw 0.45 mm (one card slides under, two don't), single-sleeved 0.70, double 0.85.

## 3. Scan module

1. PSU cradles: drop an M3 nut into the slot in each cradle's end tab. Hold each cradle between the walls and screw it
   on from outside: front wall low (Z 40), back wall high (Z 135, above the inlet plate), M3 x 12 into the nuts.
2. **PSU ⚠ before the module goes next to the feeder base.** Slide the Mean Well in from the feeder end, over the
   cradles, terminals toward the feeder, vented cover facing the back of the machine. A zip tie round the PSU and
   each cradle's base (through the slots beside the PSU).
3. Inlet: the IEC inlet snaps into the plate (the plate is thinned to 2.5 mm round the cutout for its clips). Plate on
   the back wall (4 x M3 x 8). Mains to the PSU with the inlet's own leads (ferrules, earth to the PSU's earth screw).
   **Check twice: L, N, earth.**
4. Belt-home TCRT5000 under the back strip: M3 x 6 into its insert (or an M3 x 8 with a washer under the head).
   Wires out of the hole in the back wall.
5. Scan floor: it sits on the ledges along both strips (no screws). Tie bar 0 goes at the start of bin module 1.
6. Stand the module on the rails against the feeder base and bolt it down: 2 x M5 x 10 front, 2 back (the back ones
   through the gaps in the wire channel).

## 4. Hood, lid and camera

1. Hood LED channels: COB strip into each aluminum channel, channels on the front and back ledges, wires joined
   inside along the back and out through the LED hole. Sheen LED: one piece of the strip (cut at a marked line, up to
   52 mm) in the sheen cap, cap on the back bosses (2 x M3 x 12 in its counterbores).
2. Hood onto the scan module's wall tops: 4 x M3 x 10 (X 228 and X 349). Its right end overhangs bin module 1 by
   17 mm without fixings.
3. Camera: **4 x M2 x 8** self-tapping into the camera plate, **connector facing LEFT** (toward the hopper). Plate onto
   the lid's ribs (2 x M3 x 10 through the slots), lens 115 mm above the card to start.
4. Camera ribbon: Pi end first, then out of the pod's back, across the gap just above the conveyor walls, up the
   outside of the hood's left wall (let it roll over gently: never crease it, never fold it sideways), under the
   L-rails, over through the slot and straight into the camera.
5. Lid on (the key at the back only fits one way). Lift it off to adjust height and focus with the live view.

## 5. Bin modules (do each one complete before the next one goes on)

Each module: back side, tie bar, front side, door, servo, link, sensors, looms, back panel, joint plates, bin.

1. Back side on the rails: 2 x M5 x 10 into the back rail (through the channel gaps) and 2 into the second rail
   (reach them from the front, through the bin bay).
2. Tie bar at the module's start: M3 x 12 through the back wall into its insert. Front side: hang it on the tie
   bar's other end (M3 x 12). The front wall stops above the bin; its other end is carried by the joint plate (step 9).
3. **Door ⚠ before the servo, and ⚠ before the next module goes on.** Bin out. Bring the door up from underneath:
   its barrels go up into the strip's notches (they're open underneath). Push the 2 mm x 100 mm pin in from the
   module's open end through the first frame knuckle, both barrels and the other knuckles until it's flush.
   The door should swing freely. (Nothing holds it shut until the servo is on: the old front ledge was in the
   way of the door opening, so it's gone; the servo holds the door closed.)
4. **Servo.** Centre it (Tools → Test doors, or a servo tester at 1500 µs). With the door hinged and closed, slide
   the servo into its bracket from the hopper side (top / horn side toward the hopper), lead first, and screw its tabs
   to the bracket (2 x M2 x 8; the screws in the servo's bag are the same size).
5. Horn: single-arm horn on the spline pointing down and toward the FRONT (the same angle as the door's lever when
   the door is closed), its 12 mm hole opened to 1.6 mm.
6. Link: **M2 x 8** through the link into the door's lever; **M2 x 6** through the link into the horn (an M2 x 8 there
   runs 1 mm into the servo case: use a 6, or cut an 8 down). Both snug, not tight: the link has to turn.
   Tools → Test doors: open 60°, close flat (the link would touch at about 64°). Tune `closed_us` / `open_us`.
7. Beam emitter (back) and receiver (front) into their pockets, lens to the window; leads in through the slot
   beside each pocket. Bin-level sensor (VL53L1X carrier, headers soldered) into its pocket under the front strip.
8. Looms: front ones (receiver, level sensor) along the front wall's inner face under the strip's gusset to the
   module's start, across **under** the tie bar (clear of both doors), down the back wall into the window and out
   into the back channel. Back ones (servo, emitter) down the back wall into the window and the channel. Everything
   runs to the hub on bin module 2; its own looms go straight to the boards.
9. Back panel over the window (4 x M3 x 8). Bin module 2 gets the **hub panel**: PCA9685 on its 4 bosses (**M2 x 8**),
   MCP23017, the two TCA9548A (bridge A0 on the first, A1 on the second) and the 3.3 V regulator on the pads (foam tape
   + a zip tie through each slot pair). Clip the header solder tails under those four boards flush first (or use two
   layers of foam tape), so they sit flat instead of rocking on the tails. Wire the hub before the panel goes on.
10. Next module on its rails, then the **joint plates** across the joint, front and back (2 x M3 x 8 each, just under
    the floor line): they line the walls up and carry the front wall's end.
11. Bin in from the front, between the two fingers under the front wall.

## 6. End module

1. Back side on the rail (2 x M5 x 10), tie bar 8, front side, joint plates to bin module 8 (or 2 in stage A).
2. Drive shaft through the end walls (625 in the back wall), drive pulleys (hubs facing the track), track motor on
   its standoff on the back wall (4 x M3 x 10 into the wall, 4 x M3 x 8 into the motor).
3. End ramp under the back strip: 2 x M3 x 8 up through its flange into the inserts. End cap on the end: 4 x M3 x 8
   into the inserts in both walls' end faces (it ties the two walls together at the far end). End bin.

## 7. Belts and fins

1. Drill the belts with the drill jig: a 2 mm hole on the belt's centre line every 61 teeth (122 mm): 10 per belt for
   the 3-bin build (1220 mm loops), 22 per belt for 9 bins (2684 mm loops).
2. Fins on: M2 x 6 from the tooth side into each fin (mirrored fins on the front belt), silicone square in each face.
3. Belts round the start idlers and drive pulleys; tension with the two M3 x 20 screws in the post faces. Fin gauge:
   both fins of a pair must drop into its notches together; if not, loosen one drive pulley's grub, turn it, tighten.

## 8. Screen pod

1. Pi 5 on the back of the display, display ribbon and power jumpers as in the display's box.
2. GoPro standoff onto the pod cover first, while the cover is empty: 2 x M3 x 12 from inside the cover, through the
   pad on its back wall, into the standoff's inserts.
3. Display into the cradle (Pi's port edge up), 5 V converter on its bosses in the pod cover (2 x M3 x 8), USB-C in.
4. Pod cover on (4 x M3 x 10). Wall mount flat on the scan module's front wall (2 x M3 x 8 into its inserts), pod onto
   it (M5 thumbscrew), tilt about 15° back.

## 9. First power-up

Follow [machine/README.md](../machine/README.md) step 3 ("Set up and test, one part at a time") before the first run.

## Going from 3 bins to 9

1. Unplug the end module's cables at the hub and the bay (track motor, end bin's level sensor), take the joint plates
   off and unbolt the end module.
2. Bolt bin modules 3-8 on in order (each complete, as in section 5), then the end module back on.
3. New belts: 2684 mm welded loops with 22 fins each. Longer rails if you cut them short for stage A.
4. config.yaml: `bins: in_use: 9`. Tools → Test doors, Bin levels.

## Every screw

From the kit (M2 / M3 / M4 / M5, socket cap) unless noted. Stage A = the 3-bin machine; 9 bins adds the rest.

| Screw | Stage A | 9 bins | Where |
|---|---|---|---|
| M5 x 10 + 2020 T-nut | 18 | 42 | every foot (counterbored): base 4, scan 4, each bin module 4, end 2 |
| M3 x 20 | 2 | 2 | start-idler tension (post faces) |
| M3 x 16 | 2 | 2 | tower to base |
| M3 x 12 | 19 | 31 | tie bars 2 each (3 / 9 bars), PSU cradles 4 (+ 4 M3 nuts), bay fan 4 (+ 4 nuts), gate 1 (+ M3 jam nut), sheen cap 2, GoPro standoff 2 |
| M3 x 10 | 20 | 20 | motor standoffs 8, pressure bridge 2, hood 4, camera plate 2, pod cover 4 |
| M3 x 8 | 44 | 92 | bay cover 4, tray 2, motors 8, inlet 4, ramp 2, end cap 4, screen mount 2, converter 2, back panels 4 per bin module, joint plates 4 per joint |
| M3 x 6 | 1 | 1 | belt-home sensor (or an M3 x 8 + washer) |
| M2 x 8 | 18 | 36 | SKR Pico 4, camera 4, PCA9685 4, per bin module: servo tabs 2 + door lever 1 |
| M2 x 6 | 22 | 52 | servo horn 1 per bin module, fins (20 / 44) |
| M3 x 4 grub + M3 nut | 2 | 2 | drive pulleys |
| M3 heat-set insert (5.7 long) | 74 | 134 | see section 0 |

No M2.5 screws anywhere any more: the SKR Pico, the camera and the PCA9685 take M2 x 8 self-tapping through their
2.7 mm holes into 2.1 mm pilots. If your kit has no M2 x 6, cut M2 x 8s down (side cutters, then run a nut off to
clean the thread).
