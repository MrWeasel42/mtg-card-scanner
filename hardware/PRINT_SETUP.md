# Printer and OrcaSlicer setup (Neptune 4 Pro, 0.4 mm stainless nozzle)

The plan for the fresh OrcaSlicer setup, built from the old profiles (backed up 2026-11-22) and the tips in the 19
videos (see AUDIT.md, round 2). Do it in order: the printer first, then the profiles, then the calibrations, then a
Benchy, then the fit-test pieces.

## What the old setup had (the baseline)

| Item | Old value | Note |
|---|---|---|
| Printer | "Elegoo Neptune 4 Pro 0.4 stainless" (+ a duplicate "- Copy") | start G-code has `M220 S80`: every print ran at 80 % speed, so Orca's times were 25 % short |
| PETG (Polymaker) | 245 °C both layers, bed 75 °C, fan 30-40 %, flow ratio 0.95 | temperature tower: 245-250 cleanest. Flow pass 1 / pass 2 disagreed (+5 vs -9), so 0.95 was a compromise: redo it |
| PLA matte black (Polymaker Panchroma), PLA matte green (SUNLU) | stock Generic PLA Matte / SUNLU Matte | no tuning yet |
| Elegoo Rapid PLA+ | 230 °C, max flow 15 mm³/s | |
| MatterHackers gold PLA | 215 °C, flow 0.98, PA 0.04, max flow 12 mm³/s | |
| Processes | Sorter 0.20 PETG (4 walls, gyroid, tree supports at 35°, mouse ears, elephant foot 0.15), Sorter 0.20 PLA, Sorter 0.12 fine (100 % infill), Gold PLA Detailed | |

## 1. Printer (once, before any profile work)

1. **Mechanics:** eccentric nuts snug (each wheel just stops spinning by hand: X carriage 2, bed 3, Z sides 1 each),
   both belts firm (twangs, not spongy), the Z guide screws tight, nothing rubbing the Z screw (extruder cable).
2. **X gantry square:** set two equal blocks on the bed under the gantry ends, loosen the top Z-belt pulleys, press the
   gantry down onto the blocks, retighten.
3. **Nozzle:** hot (245 °C), check it's snug against the heater block (hold the block with a wrench). Don't force it.
4. **Firmware:** check for an Elegoo update (About machine). Then on the screen run **input shaping (X and Y)** and
   **PID** (hotend at 245 °C with the part fan on; bed at 75 °C).
5. **Bed:** wash the PEI sheet with dish soap and hot water and don't touch it after. Heat the bed to 75 °C. Do 3-4
   rounds of paper leveling on the 6 knobs, then switch to **professional leveling** (111 points). Re-run the mesh
   and adjust knobs until every point is within ±0.1 mm (±0.004 in), then **save** it.
6. **Z offset:** set it on a real first layer (live baby-stepping): lines should just touch and look glossy. Ridges =
   too low, gaps = too high.
7. **Extruder check:** mark the filament 70 mm (2.76 in) above the extruder, extrude 50 mm (1.97 in) slowly, re-measure.
   If it's off by more than 1 mm (0.04 in), fix `rotation_distance` in printer.cfg.

## 2. Clean slate in OrcaSlicer

* Delete every user filament profile for a filament you don't have, plus the "- Copy" printer.
* Printer profile **N4Pro 0.4 SS**: from the stock Neptune 4 Pro 0.4, stainless nozzle, host 10.69.1.189. Start
  G-code: `M220 S100` instead of `S80` (set real speeds in the process instead, so print times are right).
* Filament profiles: one per spool you actually have (list to confirm with Eric). Each one: the right base (Generic
  PETG / PLA / PLA Matte / ABS / PA from Elegoo or the brand's own), then the calibrated values below.
* PETG notes: first layer +5 °C (250), bed 75-80 °C. **Bed prep for PETG: thin glue stick on the PEI as a release
  layer, never wipe with alcohol right before PETG** (it can bond and tear the PEI). Let the plate cool under 30 °C
  (85 °F) before flexing the part off.

### Process profiles

| Profile | Use | Key settings |
|---|---|---|
| **Sorter PETG 0.20 Structure** | walls, base, towers, brackets | 0.20 layers, 4 walls, 5 top / 4 bottom, gyroid 15 %, seam aligned and placed at the back, outer wall 60 mm/s, inner 120, precise wall on, elephant foot 0.15, tree supports (build plate only, 40°), max bridge length left at Orca's default 10 mm, z-hop 0.4 |
| **Sorter PETG 0.12 Precision** | pulleys, rollers, fins, gate, slider | 0.12 layers, 100 % infill, outer wall 40 mm/s, seam at the back |
| **Sorter PLA 0.20 Covers** | matte black/green covers | 0.20 layers, 3 walls, 15 % gyroid, seam at the back, PLA fan 100 % + side fan |
| **Prototype (fit checks only)** | quick dimension checks | 2 walls, 5 % infill, fast: never for real parts |

**Bridges and overhangs (the sag):** bridge flow 0.90, bridge speed 25 mm/s, overhang and bridge fan 100 %, "slow down
for overhangs" on. The design changes in round 2 remove the worst bridges (motor standoffs, pod cover). The Benchy
below shows whether these numbers are enough.

**Max bridge length: leave it at Orca's default 10 mm.** I once raised it to 45 mm so a no-support feeder base would slice
clean, but that was based on web research only. Bridges on this printer in PETG came out stringy even over a 10 mm
pocket, so long spans get supports.

**Feeder base: supports ON.** The supported print of the same part came out much cleaner than the unsupported one, so
use tree supports (build plate only, 40°). Keep them out of the bearing seats (below). About 28 h and 119 g of support.

**Keep supports out of bearing seats.** Upright parts have teardrop bearing seats that need no support, but tree
supports still grow into them and leave the seat too small for the bearing (fit test 2). Paint a support blocker
over each bearing seat in Orca before slicing, and check the sliced preview for green inside the holes.

**Brims:** the tall upright walls get an 8 mm brim (their notes say so); broad flat parts with sharp corners get
mouse ears (10-20 mm across, 3-5 layers). Gyroid or crosshatch infill only, no grid (the nozzle clips the crossings).

## 3. Calibrations (Orca → Calibration), PETG, tent open, in this order

1. **Flow ratio:** set flow 1.0, run pass 1 then pass 2. Photograph the top surfaces at a low angle under one lamp
   and send them; pick by eye, not fingernail (that's what gave the conflicting result last time).
2. **Pressure advance** (pattern test): pick the sharpest corner.
3. **Retraction** tower: the lowest length with no strings (direct drive: usually 0.5-1.5 mm).
4. **Max volumetric speed:** where the walls start to look starved, minus 10 %.
5. Temperature: already done (245 °C), skip unless a new brand.
Then the same for PLA (Panchroma black) at 210-220 °C.

## 4. Test prints

1. **One PETG Benchy** with the new profile: send photos of the bow overhang, the roof (bridge), the chimney
   (strings) and the first layer. Tweak, then a second Benchy only if the first shows a problem.
2. **Fit-test pieces** (`stl/test_sections/`, Structure profile, same orientation as the real parts):
   * `test_feeder_seats_and_slider` (~2 h): the 625/685 bearings press in by hand, the idler slider slides in.
   * `test_bin_hinge_and_servo` (~2.5 h): the door hinge pin and the servo drop in.
   * `test_end_bearing_seat` (~1 h): cut out the skin, the 625 bearing presses in and sits flat.
3. Then the feeder base.
