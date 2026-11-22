# Card sorter hardware (3-bin prototype, rev A)

- `cad/sorter.py`: parametric CadQuery model of every printed part. `python sorter.py` regenerates `stl/` and `step/`.
- `stl/`: print files (one per part; quantities in the print list).
- `step/`: editable solids for any CAD program (Fusion, FreeCAD, Onshape).
- `sheets/`: drawing sheet per part (views, overall dimensions mm (in), quantity, material, print notes).
- `renders/`: final-look and prototype renders.

Machine coordinates: X along the card path, Y across (front = -Y), Z up. Card floor at Z = 205 mm.
First design pass: nothing printed yet. Test-print the gate plate and an exit roller first to check fits.

## Screen + Pi mount (to design)

* The Pi 5 is screwed to the back of the Touch Display 2; the display ribbon is short, so they stay one block.
* The camera ribbon (Pi CAM/DISP 0 → HQ camera in the hood) is **305 mm (12 in)** long. It must lie flat and
  shouldn't twist: route it in a flat channel along the frame with gentle folds only, and keep the screen block
  close enough to the camera tower that 305 mm reaches with slack. If the layout needs more, swap for a longer
  Pi 5 camera cable (500 mm / 20 in).
