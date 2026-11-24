# Kit plan (phase 2: after the first machine sorts cards end to end)

Goal: a sorter someone else can build from a box of parts with no soldering and no hand-routed wiring.
The Pi plus **one main board**, and every cable is a ready-made plug-in cable.

## Why wait
The first machine (breakout boards + jumper wires) proves the circuit. Every wiring change found while
building it is a re-solder now but a new board order later. So: get machine #1 sorting first, then turn its
final wiring into the board.

## Main board ("sorter hub"): a Pi HAT or a carrier the Pi plugs into
On the board (same chips we're using now as breakouts):
- 2 x TCA9548A I2C switch (distance sensors), or none if we move to XSHUT address assignment (see below)
- MCP23017 (break-beams, plus XSHUT lines if used)
- PCA9685 (door servos)
- 24 V -> 6 V servo regulator, 3.3 V regulator for the sensors
- MOSFET channels (whatever the MOSFET boards drive now)
- 24 V input terminal with fuse and reverse-polarity protection
- one keyed, labeled connector per bin: distance sensor, break-beam, servo
- a header or socket for the motor controller

### Motors
- v1: keep the BTT SKR Pico (cheap, proven), so the hub has a plug for it.
- v2: put the motor controller on the hub: RP2040 running Klipper + TMC2209 drivers. One board total.

### Open question: drop the I2C switches?
Each VL53L1X can get its own address at boot by holding the others in reset (XSHUT), using one extra wire
per sensor from the MCP23017. That's fewer chips, but a long shared I2C bus with ~9 sensors. The switches
also isolate cable capacitance. Decide after measuring bus behavior on machine #1 with full-length cables.

## Off the board (they have to sit at the bins)
- VL53L1X distance sensors and break-beam emitter/receiver: small modules or tiny custom boards with the
  same keyed connector, mounted in the printed pockets
- LRS-100-24 PSU and AC inlet (pre-wired harness in the kit)

## Cables
- Pre-made, keyed (JST-PH/XH or similar), cut to the lengths the CAD gives per bin position
- one cable type per job, color-coded, so nothing can be plugged in wrong
- Pi to hub: a short ribbon, or direct HAT stacking

## Manufacturing
- PCBWay assembled boards (already using them). First run ~5 boards to prove it; expect 1-2 revisions.
- Design in KiCad. Inputs: hardware/WIRING.md, machine/sorter/config.yaml addresses, the CAD's bin pitch for
  cable lengths.
- Printed parts need connector cutouts and board mounts updated to match.

## Kit contents (target)
Printed parts (or STLs) · Pi 5 + touchscreen · hub board · sensor/beam boards · servos · motors · belts,
bearings, shafts, hardware bag · PSU harness · pre-made cable set · assembly guide.
