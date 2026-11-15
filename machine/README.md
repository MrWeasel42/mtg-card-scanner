# Machine software (Raspberry Pi 5)

The Pi runs the motors and sensors. Recognition happens in the PC app, the same way the phone app works:
the Pi takes the photo, sends it to the PC's **Phone link**, and drops the card in the bin the PC chose.

```
PC app (Windows) <--Wi-Fi--  sorter.py (Pi) --Moonraker--> Klipper --UART--> SKR Pico --> 2 steppers, 2 TCRT, LEDs
                                  |--I2C--> PCA9685 (door servos) + 3 x VL53L1X (bin levels)
                                  |--GPIO-> 2 break-beams (drop check), 3 x XSHUT
                                  '--CSI--> HQ camera
```

## 1. Pi setup (once)

1. Flash **Raspberry Pi OS Lite (64-bit, Bookworm)** with Raspberry Pi Imager. In its settings set the user to `pi`,
   your Wi-Fi, and turn on SSH.
2. `sudo raspi-config` → Interface Options → **I2C on**, **Serial Port: login shell NO, hardware YES**.
3. Add to `/boot/firmware/config.txt`: `dtparam=uart0=on`, then reboot.
4. Install Klipper + Moonraker with KIAUH:
   `git clone https://github.com/dw-0/kiauh.git && ./kiauh/kiauh.sh` → Install → Klipper, then Moonraker.
5. Get this repo: `git clone https://github.com/MrWeasel42/mtg-card-scanner.git`
6. `sudo apt install -y python3-picamera2 python3-pip` then
   `pip install --break-system-packages -r mtg-card-scanner/machine/sorter/requirements.txt`

## 2. SKR Pico firmware (once)

```
cd ~/klipper && make menuconfig
  Micro-controller: Raspberry Pi RP2040
  Bootloader offset: No bootloader
  Communication interface: UART0 on GPIO1/GPIO0
make
```
Hold the SKR's **BOOT** button, plug it into the Pi's USB, and copy `out/klipper.uf2` to the drive that appears.
Unplug the USB (the board talks to the Pi over the 3-wire UART from then on).

Copy the config: `cp ~/mtg-card-scanner/machine/klipper/printer.cfg ~/printer_data/config/printer.cfg`
and restart Klipper (`sudo systemctl restart klipper`).

## 3. Set up and test, one part at a time

| Step | How | Good when |
|---|---|---|
| Sensors | Mainsail/Fluidd console: `QUERY_BUTTON BUTTON=card_clear` with and without a card on the floor slot | it changes; turn the blue pot on the TCRT module if not |
| Feed motor | `MANUAL_STEPPER STEPPER=feed MOVE=50 SPEED=40` | the roller turns forward (swap one coil pair if backwards) |
| Track motor | `MANUAL_STEPPER STEPPER=track MOVE=122 SPEED=60` | the fins move one station toward the bins |
| Home | `python3 sorter.py --home-only` | a fin stops exactly on the scan station (use the fin gauge); otherwise change `home_to_station_mm` |
| Doors | edit `closed_us` / `open_us` in `config.yaml` until each door shuts flush and opens fully | |
| Feeding | `python3 sorter.py --limit 1` with 5 cards in the hopper | one card at a time, none doubled |
| Full run | PC app open with **Phone link** on, then `python3 sorter.py` | cards land in the right bins; the PC shows each scan |

`python3 sorter.py --sim 20` runs the whole cycle with pretend hardware, anywhere (no Pi needed).

## Bins

The PC app decides the bin. Start a session on the PC (**▶ Start session**): name, Catalog or Sort, **Bins in use**,
and what to sort by (price brackets, colour, letters, rarity or set). The machine joins it when `sorter.py` starts.
Bins count from the feeder; the last bin in use is the end ramp and also takes the Flagged cards (not identified,
not sure, no price). Set `bins.in_use` in `config.yaml` to the bins actually built (prototype: 3, full build: 9) and
the same number on the PC; anything the PC sends to a bin the machine doesn't have goes to the end bin.

An empty hopper never ends the run: the track is cleared and the machine waits for more cards. **Stop** on the PC
ends it; the PC then shows the flagged cards to review and writes the ManaBox and Moxfield CSVs.

Each run also writes `~/sorter_logs/sort_<date>.csv` (card, bin, bin label, wanted bin, why, name, set, number, price).
