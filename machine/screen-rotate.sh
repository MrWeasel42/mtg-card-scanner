#!/bin/bash
# Turns the touchscreen picture AND the touch input together.
#   bash ~/mtg-card-scanner/machine/screen-rotate.sh 270        picture rotation 90 or 270 (180 / 0 also work)
#   bash ~/mtg-card-scanner/machine/screen-rotate.sh 270 flip   same picture, touch turned the other way
#                                                               (use if taps land in the mirror-image spot)
set -e
ROT=${1:-$(cat ~/sorter_data/rotation 2>/dev/null || echo 90)}
FLIP=$2
mkdir -p ~/sorter_data && echo "$ROT" > ~/sorter_data/rotation
# libinput calibration matrices: touch panel coordinates -> rotated screen
case "$ROT" in
  90)  M="0 -1 1 1 0 0";  MF="0 1 0 -1 0 1" ;;
  270) M="0 1 0 -1 0 1";  MF="0 -1 1 1 0 0" ;;
  180) M="-1 0 1 0 -1 1"; MF="1 0 0 0 1 0" ;;
  *)   M="1 0 0 0 1 0";   MF="-1 0 1 0 -1 1" ;;
esac
[ "$FLIP" = "flip" ] && M=$MF
echo "ENV{ID_INPUT_TOUCHSCREEN}==\"1\", ENV{LIBINPUT_CALIBRATION_MATRIX}=\"$M\"" \
  | sudo tee /etc/udev/rules.d/99-sorter-touch.rules >/dev/null
echo "$FLIP" > ~/sorter_data/touchflip
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=input
sudo systemctl restart sorter-screen
echo "Screen $ROT, touch matrix $M"
