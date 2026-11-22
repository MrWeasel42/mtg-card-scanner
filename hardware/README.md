# Card sorter hardware (3-bin prototype, rev A)

- `cad/sorter.py`: parametric CadQuery model of every printed part. `python sorter.py` regenerates `stl/` and `step/`.
- `stl/`: print files (one per part; quantities in the print list).
- `step/`: editable solids for any CAD program (Fusion, FreeCAD, Onshape).
- `sheets/`: drawing sheet per part (views, overall dimensions mm (in), quantity, material, print notes).
- `renders/`: final-look and prototype renders.

Machine coordinates: X along the card path, Y across (front = -Y), Z up. Card floor at Z = 205 mm.
First design pass: nothing printed yet. Test-print the gate plate and an exit roller first to check fits.

## Screen pod

![screen](renders/asm_screen.png)

* The touchscreen sits in front of the gap between the hopper tower and the hood, on `mount_wall` (bolted across
  the front walls), tilted back 15°, M5 thumbscrew through the GoPro-style prongs.
* `screen_cradle` (lips round the glass) + `pod_cover` (black) hide the Pi 5. Vents over the Pi's fan.
* Pi's port edge UP. The camera ribbon only ever bends across its width (never sideways, never folded): out of
  the pod's back, straight back across the gap above the conveyor, a soft bend upward, then up beside the hood's
  left wall, twisting 90 degrees gently over ~60 mm until it lies flat on the wall under two pairs of L-rails, and
  over through the slot at camera height straight into the camera. The camera is turned so its connector faces
  left; the hanger ribs are on the front and back so nothing is in the way. Run ~325 mm: 500 mm (20 in) cable.
  ![ribbon route](renders/ribbon_route.png)
* The 5 V USB-C converter sits in the pod beside the Pi; only its 24 V pair, bundled with the Pi's jumper loom in a
  braided sleeve, hangs free from the pod's bottom notch into the bay-cover slot.
* Picture the right way up: `bash ~/mtg-card-scanner/machine/screen-rotate.sh 90` (or 270).

## Hood and lid

![hood inside](renders/hood_cutaway.png)

* The camera sits 4.5 in (115 mm) above the card, adjustable 100-135 mm. Close up the 6 mm lens bows the picture
  (fisheye); the machine straightens it in software after a one-time lens calibration (Tools -> Calibrate lens).
* The roof is a **lid** (`hood_lid`) with the camera hanging from it: lift it off and set height and focus with
  the camera in your hands, watching the live view. A tongue on the hood sits in a groove between the lid's two
  skirts (light can't get past two right-angle turns) and a key on the back means it only goes on one way.
* LED channels on the front and back walls, 55 mm (2.2 in) above the card, so a glossy card or sleeve reflects them
  away from the lens. Sheen LED: 20 mm of the same strip in `sheen_cap` on the back wall, shining in low.
* Every cable, its route and its length: [WIRING.md](WIRING.md).

![lid off](renders/hood_lid_off.png)
