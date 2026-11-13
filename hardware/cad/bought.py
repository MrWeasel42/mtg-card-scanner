"""
Bought parts at their real (datasheet) size, for test-fitting against the printed parts.
Each entry: dimensions in mm, the source, and a function that returns the part's envelope in its own frame.
Envelopes include the parts that stick out (shafts, connectors, terminal screws) plus the space a cable
or plug needs ("keep-out"), so a clearance check catches a plug that can't be plugged in, not just solids
that touch.
"""
import cadquery as cq
from sorter import box, cyl_x, cyl_y, cyl_z

SPEC = {
    # name: (dimensions, source)
    "NEMA 17 StepperOnline 17HS19-2004S1": ("42.3 x 42.3 x 48 body; pilot boss D22 x 2; shaft D5 x 24 (D-flat 15 long);"
                                            " 4 x M3 on 31 mm square, 4.5 deep; 1 m cable, 4-pin 2.54 mm plug",
                                            "StepperOnline 17HS19-2004S1 datasheet"),
    "Mean Well LRS-100-24 (replaces LRS-150-24)": ("129 x 97 x 30 case; terminal block on one 97 mm end, wires enter along the length;"
                                                   " M3 mounting holes, 3-5 mm max screw depth", "Mean Well LRS-100 / LRS-150 datasheets"),
    "Raspberry Pi 5 + Active Cooler": ("85 x 56 x 1.6 PCB; 4 x M2.5 (2.7 mm) holes on 58 x 49, 3.5 from the edge;"
                                       " ~19 mm tall over the PCB with the USB/Ethernet stack", "Raspberry Pi 5 mechanical drawing"),
    "BTT SKR Pico v1.0": ("85 x 56 PCB; 4 holes on 58 x 49, 3.5 from the edge (same as the Pi);"
                          " JST-XH headers overhang up to ~5 mm on the long edges", "BTT SKR Pico V1.0-SIZE.pdf"),
    "Adafruit PCA9685 (815)": ("62.5 x 25.4 x 3 PCB, headers 12 mm tall; 4 x 2.5 mm holes", "Adafruit product 815"),
    "EMAX ES08MA II servo": ("23.0 x 11.5 x 24.0 body; tabs 32.5 long overall, holes 27.8 apart; 25 cm lead", "ServoDatabase / retailer listings"),
    "Pi HQ Camera + 6 mm CS lens": ("38 x 38 PCB, 4 x M2.5 on 30 x 30; lens D30 x 34; minimum focus 200 mm; 63 deg field",
                                    "Raspberry Pi HQ camera docs, PT361060M3MP12 spec"),
    "Adafruit IR break-beam 2168": ("each half 20 x 10 x 8 housing; 250 mm leads; 3.3-5.5 V; ~50 cm range", "Adafruit 2168 listing"),
    "Raspberry Pi Touch Display 2 (7 in)": ("189.5 x 120 x 15", "Raspberry Pi Touch Display 2 docs"),
    "625-2RS bearing": ("5 ID x 16 OD x 5", "ISO 625"),
    "GT2 20T pulley, 5 mm bore, 6 mm belt": ("flange D16, teeth D12.2, 16 long incl. 7 mm hub with 2 M3 set screws", "typical GT2 pulley"),
    "5 x 5 mm flexible coupler": ("D19 x 25", "typical 'D19L25' coupler"),
    "GT2 belt 6 mm": ("6 wide x 1.38 thick, 2 mm pitch", "Gates 2GT"),
    "Nitrile O-rings": ("feed: 24 ID x 3.5 CS; exit: 16 ID x 3.5 CS", "metric O-ring sizes"),
    "M3 heat-set insert (Ruthex M3x5.7)": ("4.6 OD, 5.7 long; hole 4.0 mm, at least 6 deep; 1.6 mm wall around it", "Ruthex"),
    "M3 socket cap screw": ("head D5.5 x 3", "ISO 4762"),
    "M5 socket cap screw / 2020 T-nut": ("head D8.5 x 5; 6 mm slot", "ISO 4762 / 2020 profile"),
    "M8 washer (stack weight)": ("8.4 ID x 16 OD x 1.6", "ISO 7089"),
    "Hookup wire (silicone)": ("22 AWG: 1.6 mm OD; 18 AWG: 2.3 mm OD", "typical silicone wire"),
    "Servo / sensor leads": ("26 AWG conductors ~1.1 mm OD each; Dupont 1x3 plug 7.6 x 2.6 x 14", "typical"),
    "IEC C14 inlet, fuse + switch": ("panel cutout 47.5 x 27.5; 35 mm deep behind the panel", "typical snap-in module"),
    "30 mm fan": ("30 x 30 x 10; screw holes 24 mm apart", "typical 3010 fan"),
}

# ---------------------------------------------------------------------------------------------- envelopes
def nema17():
    """Motor in its own frame: mounting face at y=0, body toward +y, shaft toward -y, axis along Y at x=z=0."""
    m = box(-21.15, 21.15, 0, 48, -21.15, 21.15)
    m = m.union(cyl_y(0, 0, 11, -2, 0)).union(cyl_y(0, 0, 2.5, -24, 0))
    m = m.union(box(-8, 8, 48, 60, -21.15, -10))   # plug + cable bend keep-out on the back
    return m

def lrs100():
    """PSU on its side: 129 (x) x 30 (y) x 97 (z); terminal block at x = 0 end with a 25 mm wire keep-out."""
    p = box(0, 129, -15, 15, 0, 97)
    return p.union(box(-25, 0, -15, 15, 5, 92))

def pi5():
    """PCB on z=0, ports at the -x end (USB/Ethernet) and the power/HDMI on the -y edge."""
    b = box(0, 85, 0, 56, 0, 1.6).union(box(0, 85, 0, 56, 1.6, 20.6))
    b = b.union(box(-12, 0, 2, 54, 1.6, 18))          # finger room at the USB/Ethernet end (SKR Pico talks over the UART header, no USB cable)
    return b

def skr_pico():
    b = box(0, 85, 0, 56, 0, 1.6).union(box(0, 85, -5, 61, 1.6, 15))
    b = b.union(box(0, 85, -25, 0, 1.6, 12)).union(box(0, 85, 56, 81, 1.6, 12))   # plugs + cable bends
    return b

def servo():
    """ES08MA II with its output shaft on +y (into the wall), body centred on x."""
    s = box(-11.5, 11.5, -24, 0, -5.75, 5.75)
    s = s.union(box(-16.25, 16.25, -6, -3.5, -5.75, 5.75))   # mounting tabs
    s = s.union(cyl_y(-5.75, 0, 2.5, 0, 4))                     # spline
    return s

def beam_half():
    """Break-beam emitter or receiver housing, lens facing +y."""
    return box(-10, 10, -8, 0, -5, 5)

def hq_camera():
    """PCB at z=0 (facing down), lens hanging down to z = -34 - mount."""
    c = box(-19, 19, -19, 19, 0, 1.6).union(box(-19, 19, -19, 19, 1.6, 12))
    c = c.union(cyl_z(0, 0, 18, -10, 0)).union(cyl_z(0, 0, 15, -44, -10))
    return c

def display():
    return box(-94.75, 94.75, -15, 0, 0, 120)
