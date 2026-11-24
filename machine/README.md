# Machine software (Raspberry Pi 5)

The Pi runs the whole machine on its own: the touchscreen app, sessions, bins, review and the ManaBox/Moxfield
CSVs all live on the Pi, and so does a copy of the card recognition engine. While the PC app is connected it
identifies the cards (it's faster): the Pi sends it each photo. When the PC isn't there, or drops out partway
through a card, the Pi identifies the card itself and sorting carries on (see **Identifying** below). The PC copies
every finished session to `Sessions\Machine\`. Any phone or PC on the Wi-Fi can open the same app at **http://sorter.local:8080**
(download CSVs, review cards, watch a run).

```
PC app (Windows) <--Wi-Fi--  sorter.py (Pi) --Moonraker--> Klipper --UART--> SKR Pico --> 2 steppers, 2 TCRT,
                                  |                                                       2 tower-ID hall sensors, LEDs
                                  |--I2C (4-wire bin bus)--> bin hub on bin module 2:
                                  |        PCA9685 (8 door servos), MCP23017 (8 break-beams), 2 x TCA9548A (9 VL53L1X)
                                  |--CSI--> HQ camera (lens distortion corrected after calibration)
                                  '--engine/ (on-machine identifying: same catalog, AI model, text reader and rules)
```

## 1. Pi setup (once)

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In its settings set the user to `pi`,
   your Wi-Fi, and turn on SSH.
2. `sudo raspi-config` → Interface Options → **I2C on**, **Serial Port: login shell NO, hardware YES**.
3. Add to `/boot/firmware/config.txt`: `dtparam=uart0=on`, then reboot.
4. Install Klipper + Moonraker with KIAUH:
   `git clone https://github.com/dw-0/kiauh.git && ./kiauh/kiauh.sh` → Install → Klipper, then Moonraker.
5. Get this repo: `git clone https://github.com/MrWeasel42/mtg-card-scanner.git`
6. `sudo apt install -y python3-picamera2 python3-opencv python3-pip` then
   `pip install --break-system-packages -r mtg-card-scanner/machine/sorter/requirements.txt`

## 1b. Touchscreen app (once)

The touchscreen has the same features as the Windows app (see [docs/apps.md](../docs/apps.md)); the PC app has a
**Card sorter** page with the machine's run, controls, tools and settings.

`bash ~/mtg-card-scanner/machine/install.sh` then `sudo reboot`. It installs two services:

* `card-sorter` runs `sorter/app.py` (the machine + the web app on port 8080), restarted if it ever stops.
* `sorter-screen` opens it full screen on the Touch Display 2 (Chromium kiosk in `cage`, landscape).

The screen dims and sleeps after the minutes set in Settings; touch to wake. **Update** on the screen pulls the new
version from GitHub and restarts the app. Logs: `journalctl -u card-sorter -f`. Try it without hardware on any
computer: `python3 sorter/app.py --sim --port 8080` and open http://localhost:8080.

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
| Tower ID | Touchscreen Tools → **Which tower?** with each tower on the feeder | Raw / Single-sleeved / Double-sleeved; flip a magnet if a tower reads wrong (south pole must face down) |
| Bin hub | `i2cdetect -y 1` | 0x27 (MCP23017), 0x40 (PCA9685; 0x70 too until the app starts: its all-call), 0x71 + 0x72 (the two switches) |
| Lens calibration | Print `machine/calibration_board.pdf` at 100%, check a square is 10.0 mm, glue it to card. Lid on, lights on. Tools → **Lens photo** 8–12 times, moving and tilting the board each time, then **Finish lens calibration** | "error" under 0.5 px; card edges look straight in the Camera view |
| Home | `python3 sorter.py --home-only` | a fin stops exactly on the scan station (use the fin gauge); otherwise change `home_to_station_mm` |
| Doors | edit `closed_us` / `open_us` in `config.yaml` until each door shuts flush and opens fully | |
| Feeding | `python3 sorter.py --limit 1` with 5 cards in the hopper | one card at a time, none doubled |
| Full run | Start a session on the touchscreen (PC app open with **Phone link** on, or not) | cards land in the right bins; the screen shows who identified each one |

`python3 sorter.py --sim 20` runs the whole cycle with pretend hardware, anywhere (no Pi needed).

## Identifying

Settings → **Identify cards on**:

| Setting | What happens |
|---|---|
| **PC, else this machine** (default) | The PC app identifies while it's connected. If the PC goes away (app closed, PC asleep, off the Wi-Fi) or hasn't answered a card within `identify.pc_give_up_s` (15 s), the Pi identifies that same photo and whichever answers first is used; the next cards go to the Pi until the PC is back, then the PC again. |
| **PC only** | No PC: each card's photo is kept and the card goes to the Flagged bin (identify it later with **↻ Identify again** in review). |
| **This machine only** | The Pi identifies every card and never asks the PC. |

The engine on the Pi (`sorter/engine/`) is a Python copy of the PC app's C# engine: the same published catalog
(`catalog-latest`), the same AI model (`model-v1`), the same text-reader models (`src/CardScanner.Core/OcrModels`)
and the same scoring, pinning and flagging rules, plus the checks the PC runs after it (crop straightening against the
top match, the ★/• mark, the close-up compare of look-alike printings). The **Pi engine** GitHub check runs both on the
same photos of real cards and compares every answer, on 64-bit ARM with Raspberry Pi OS's Debian (bookworm and trixie).
Change one engine, change the other.

* First start: the Pi downloads the catalog once (about 220 MB, `~/sorter_data/catalog`) and checks for a new one every
  12 hours; it swaps it in only while nothing is sorting. Loading it takes a few seconds after power-on.
* Slower than the PC: Settings shows the Pi's time per card. It uses about 1.2 GB of the Pi 5's 4 GB.
* The close-up checks use card pictures from Scryfall (cached in `~/sorter_data/cache/thumbs`). With no internet
  the Pi still identifies; a few more look-alike printings get flagged for you to check.
* Reviews of cards the Pi identified are logged in `~/sorter_data/logs/machine_identify_feedback.csv` (the PC keeps
  its own accuracy log for the cards it identified).
* Try it anywhere: `python3 sorter/app.py --sim` has a pretend PC you can switch off or make hang from Tools; add
  `--sim-engine --sim-photos <folder of card photos>` to run the real engine. Tests: `python3 sorter/test_identify.py`
  (`MTG_CATALOG=<catalog folder>` also runs the real engine).

## Bins

Start a session on the touchscreen (**Start**): name, Catalog or Sort, and the bins: last time's, the setup saved
on the PC, a saved setup, or a preset (price brackets, colour, letters, rarity, set), each bin editable.
Bins count from the feeder; the last bin in use is the end ramp and also takes the Flagged cards (not identified,
not sure, no price). Set `bins.in_use` in `config.yaml` to the bins actually built (prototype: 3, full build: 9) and
the same number on the PC; anything the PC sends to a bin the machine doesn't have goes to the end bin.

An empty hopper never ends the run: the track is cleared and the machine waits for more cards. **Stop** ends it;
then review the flagged cards on the screen (or any browser) and **Finish** writes the ManaBox and Moxfield CSVs.
The red **STOP** in the bottom-right corner is the emergency stop (motors off at once); **Reset** brings it back.

Each run also writes `~/sorter_logs/sort_<date>.csv` (card, bin, bin label, wanted bin, why, name, set, number, price).
