#!/bin/sh
# Runs inside cage on the Touch Display: turns the screen to landscape, then opens the sorter app full screen.
# Picture upside down?  echo 270 > ~/sorter_data/rotation   (or 90), then: sudo systemctl restart sorter-screen
ROT=$(cat "$HOME/sorter_data/rotation" 2>/dev/null || echo 90)
for out in $(wlr-randr | grep -E '^[A-Za-z]' | cut -d' ' -f1); do
  wlr-randr --output "$out" --transform "$ROT"
done
exec /usr/bin/chromium --kiosk --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble \
  --disable-features=Translate --overscroll-history-navigation=0 --disable-pinch --password-store=basic \
  --ozone-platform=wayland "http://localhost:8080/?kiosk=1"
