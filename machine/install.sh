#!/bin/bash
# Sets up the card sorter on the Pi: the machine service, the touchscreen kiosk and the screen settings.
# Run once from the repo:   bash ~/mtg-card-scanner/machine/install.sh
# Safe to run again (after big updates it re-applies everything).
set -e
cd "$(dirname "$0")"
MACHINE=$(pwd)
echo "== Packages (camera, Python bits, kiosk browser)"
sudo apt-get update -qq
sudo apt-get install -y python3-picamera2 python3-pil python3-yaml python3-pip git cage chromium
pip install -q --break-system-packages -r sorter/requirements.txt

echo "== Services"
sudo cp systemd/card-sorter.service systemd/sorter-screen.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable card-sorter.service sorter-screen.service
sudo systemctl disable getty@tty1.service 2>/dev/null || true
sudo systemctl set-default graphical.target

echo "== Screen: Touch Display 2 in landscape, backlight dimmable by the app"
CFG=/boot/firmware/config.txt
if ! grep -q "vc4-kms-dsi-ili9881-7inch" $CFG; then
  echo "# Raspberry Pi Touch Display 2, landscape (use rotation=270 if it's upside down)" | sudo tee -a $CFG >/dev/null
  echo "dtoverlay=vc4-kms-dsi-ili9881-7inch,rotation=90" | sudo tee -a $CFG >/dev/null
fi
echo 'SUBSYSTEM=="backlight", RUN+="/bin/chmod 666 /sys/class/backlight/%k/brightness /sys/class/backlight/%k/bl_power"' \
  | sudo tee /etc/udev/rules.d/90-sorter-backlight.rules >/dev/null

echo "== Done. Reboot to start the touchscreen:  sudo reboot"
echo "   Any browser on your Wi-Fi: http://$(hostname).local:8080"
