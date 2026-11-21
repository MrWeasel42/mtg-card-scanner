"""Waits (up to 2 minutes) for the sorter app to answer before the touchscreen browser opens."""
import time, urllib.request
for _ in range(120):
    try:
        urllib.request.urlopen("http://localhost:8080/api/hello", timeout=1)
        break
    except Exception:
        time.sleep(1)
