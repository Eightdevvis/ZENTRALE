# Pi: check after it is back on the network

**Stand 2026-10-30:** Open, **waits for Sasha** (Pi is offline). Since the Pi
went offline, releases 37–41 changed `deploy/RELEASE`; its autopull
(`scripts/pi_autopull.sh`) will update as soon as it is online.

Check then: kiosk/TUI start, the outpost package (`deploy/aussenposten.txt`,
now with `core/app_prozess.py`), sensor bridge. The map moved out (Pi never
used it). Stage 1 may use the Pi as host (`memory/system/heimkommen.md`).
