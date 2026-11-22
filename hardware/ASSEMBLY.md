# Assembly, piece by piece

The order matters in a few places: some parts can't be reached once the next one is on. Those steps are marked
**⚠ before**. Sizes are mm (in). Every cable, its route and its length is in [WIRING.md](WIRING.md), and what to print
for each stage is in [PRINT_PLAN.md](PRINT_PLAN.md).

## 0. Inserts first (all parts, before anything is bolted together)

Press every M3 heat-set insert with the Pinecil insert tip, straight down, flush or 0.2 mm below the surface. Let
each part cool before you load it.

| Part | Inserts |
|---|---|
| feeder_base | 2 tower screws (hopper floor, entry side), 4 bay-cover screws (front), 4 feed-motor screws (back wall), 2 post tops (pressure bridge) |
| scan_side_back | 4 inlet plate, 2 panel bosses, wall top 2, belt-home sensor (underside of the strip) |
| bin_side_back (each) | 4 back panel (outside, round the window), 2 panel bosses, wall top 2 |
| bin_side_front (each) | 2 panel bosses, wall top 2 |
| tie_bar (each) | one in each end |
| end_side_back | 4 track motor, wall top 2, 2 ramp flange (under the strip) |
| hood | 2 sheen cap (back), feet use plain M3 into the wall-top inserts |
| camera_plate | 2 in the tabs |
| screen_cradle | 4 in the ears |
| pod_cover | 2 for the 5 V converter |

## 1. Frame

1. Cut the 2020 rails (9-bin build: back rail 1470 mm, second back rail 1090 mm from X 355 to 1443; front rail
   360 mm under the feeder + scanner only). Join lengths with the straight plates. Stage A uses the same back rail
   (it just sticks out past the end module until the other 6 modules go in) or a shorter cut for now.
2. Drop M5 T-nuts in the slots: 2 per foot, counting the feet of every module you'll bolt on.

## 2. Feeder base

1. **Tower-ID hall sensors ⚠ before the tray.** Bend each A3144's legs down 90° right at the body. Branded (flat,
   lettered) face UP, legs down the 3 mm hole, body flat in its 6.2 mm pocket; a drop of CA under it. Slide a 30 cm
   female jumper onto each leg underneath and heat-shrink each one. The pocket by the front of the hopper is sensor 1
   (Z-STOP), the back one is sensor 2 (E0-STOP).
2. Feed shaft: two 685ZZ in the inner ribs, the 625 in the back wall, shaft in from the back, the 20T pulley for the
   122 mm loop on its front end. Exit shaft: 625 bearings in the wall slots, exit roller and its 20T pulley.
   Loop on, push the exit bearings to tension it. **⚠ Tighten both 20T pulley grub screws now**: later you can only
   reach them through the bay window with a long ball-end key.
3. Feed roller onto the feed shaft (grub on the flat), O-rings on both rollers (3 + 2).
4. Feed motor: standoff onto the back wall (4 x M3 x 10), motor onto the standoff (4 x M3 x 8), coupler: tighten
   through the open top of the standoff.
5. Start idlers: two 685ZZ in each idler pulley, onto the 5 mm stubs in the post slots, M3 tension screws in from
   the end face (belts go on in step 6 of the track).
6. Card-clear TCRT5000 into its pocket under the floor (the window over it must be clear: no tape over it).
7. Electronics tray: SKR Pico on its 4 bosses (M2.5 x 6), slide the tray in from the front. 6 V step-down on the
   left inner wall (foam tape + a zip tie). Wire the bay now (WIRING.md: 24 V, motors, sensors, hall sensors to
   Z-STOP / E0-STOP with 5 V from the probe header's 5 V pin, LEDs, sheen, fan, UART + I2C from the Pi, the bin bus).
8. Bay cover: 4 x M3 x 8.
9. Pressure bridge: top roller on 40 mm of 5 mm shaft (grub on the flat), a collar outside each hanger, drop the
   axle into the slots, bridge onto the post tops (2 x M3 x 10). The roller should rest on the exit roller and lift
   freely. Optional: a small O-ring from each axle end to the hook under the slot for more grip.
10. Tower: magnets into the skirt pockets first (press with a flat bolt head; **south pole down**: if the tower
    reads wrong in Tools → Which tower?, flip the magnet). Raw tower = front pocket only, single-sleeved = back,
    double = both. Gate plate (silicone pad under its foot) into the tower's track, M3 adjust screw from the top.
    Set the tower on the floor and fit its 2 thumb screws. Gate gap: a raw card slides under, two don't (about
    0.45 mm); sleeved towers about 0.7.

## 3. Scan module

1. PSU on its cradles, terminals toward the bay. Inlet in the inlet plate, plate on the back wall (4 x M3 x 8).
   Mains to the PSU (the inlet's own leads, ferrules, earth to the PSU's earth screw). **Check twice: L, N, earth.**
2. Belt-home TCRT5000 under the back strip (M3 x 6 into its insert), wires out the back hole.
3. Scan floor between the walls, tie bar 0 at its far end (it bridges the floor into bin module 1).
4. Bolt the module to the feeder base (end-face M3s) and to the rails.

## 4. Hood, lid and camera

1. Hood LED channels: COB strip into each aluminum channel, channels on the front and back ledges, wires joined inside
   along the back and out through the LED hole. Sheen LED: one piece of the same strip (cut it at a marked cut line,
   up to 52 mm long) in the sheen cap, cap on the back wall (2 x M3 x 8), its wires down beside the LED pair.
2. Hood onto the scan module's wall tops (4 x M3 x 10).
3. Camera: 4 x M2.5 x 6 to the camera plate, **connector facing LEFT** (toward the hopper). Plate onto the lid's ribs
   (2 x M3 x 10 through the slots), lens 115 mm above the card to start.
4. Camera ribbon: Pi end first, then out the pod's back, across the gap just above the conveyor walls, up the
   outside of the hood's left wall (let it roll over gently on the way up: never crease it, never fold it sideways),
   under the L-rails, over through the slot and straight into the camera. Contacts face the camera board's contacts.
5. Lid on (the key at the back only fits one way). Lift it off to adjust height and focus with the live view.

## 5. Bin modules (do each one complete before bolting on the next)

Each module: back side, front side, tie bar at its start, door, servo, link, back panel, bin.

1. **Servo ⚠ before the door.** Centre the servo (Tools → Test doors sets the closed pulse; or a servo tester at
   1500 µs), feed its lead through, slide it into the bracket inside the back wall from the hopper side, top
   (horn side) toward the hopper, and screw its tabs to the bracket (2 x M2 x 8).
2. Horn: single-arm horn on the spline pointing down and toward the FRONT (the same angle as the door's lever when the
   door is closed), its 12 mm hole opened to 1.6 mm.
3. **Door ⚠ before the next module is bolted on** (the hinge pin goes in from the module's end). Door in from below,
   barrels up into the strip notches, push the 2 mm x 100 mm pin through the first frame knuckle, both barrels and
   the other knuckles until it's flush both ends. The door should swing freely and rest on the front ledge.
4. Link: M2 x 8 through the link into the door's lever, M2 x 8 through the link into the horn. Both snug, not
   tight: the link has to turn. Tools → Test doors: the door should open to 60° and close flat. Tune `closed_us` /
   `open_us` in config.yaml (Tools → door at a pulse width).
5. Beam emitter (back) and receiver (front) into their pockets, lens to the window; their leads come inside through the
   slot beside each pocket.
6. Bin-level sensor (VL53L1X carrier, headers soldered on) into its pocket under the front strip, sensor facing down.
7. Front looms (receiver + level sensor) along under the front strip to the tie bar, across the tie bar's hopper-side
   face (zip ties through the slot pairs), then along the back wall to the module's window and down into the back
   channel. Back looms (servo, emitter) straight down through the window into the channel. Everything goes to the hub
   on bin module 2.
8. Back panel over the window (4 x M3 x 8). Bin module 2 gets the **hub panel**: PCA9685 on its 4 bosses
   (M2.5 x 6), MCP23017, the two TCA9548A (bridge A0 on the first, A1 on the second) and the 3.3 V regulator on the
   pads (foam tape + a zip tie through each slot pair). Wire the hub before the panel goes on.
9. Tie bar for the next module at this module's end, bolt to the next module, bin in from the front.

## 6. End module

1. Drive shaft through the end walls (625 in the back wall), drive pulleys (hubs facing the track), track motor on its
   standoff on the back wall.
2. End ramp under the back strip (2 x M3 into its flange inserts). End cap on the end. End bin.

## 7. Belts and fins

1. Drill the belts with the drill jig: a 2 mm hole on the belt's centre line every 61 teeth (122 mm): 10 per belt for
   the 3-bin build (1220 mm loops), 22 per belt for 9 bins (2684 mm loops).
2. Fins on: M2 x 6 from the tooth side into each fin (mirrored fins on the front belt), silicone square in each face.
3. Belts round the start idlers and drive pulleys, tension with the idler screws. Fin gauge: both fins of a pair must
   drop into its notches together; if not, loosen one drive pulley's grub, turn it, tighten.

## 8. Screen pod

1. Pi 5 on the back of the display, display ribbon and power jumpers as in the display's box.
2. Display into the cradle (Pi's port edge up), 5 V converter on its bosses in the pod cover, USB-C into the Pi.
3. Pod cover on (4 x M3 x 10), mount_wall across the front walls at the hopper/scanner gap, pod onto it (M5
   thumbscrew), tilt about 15° back.

## 9. First power-up

Follow [machine/README.md](../machine/README.md) step 3 ("Set up and test, one part at a time") before the first run.

## Going from 3 bins to 9

1. Unplug the end module's cables at the hub and the bay (track motor, end bin's level sensor), unbolt the end module.
2. Bolt bin modules 3-8 on in order (each complete, as in section 5), then the end module back on.
3. New belts: 2684 mm welded loops with 22 fins each.
4. Longer rails if you cut them short for stage A.
5. config.yaml: `bins: in_use: 9`. Tools → Test doors, Bin levels.
