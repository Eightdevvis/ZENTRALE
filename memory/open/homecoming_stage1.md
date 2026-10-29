# Stage 1 "Heimkommen": next hardware steps

**Stand 2026-10-30:** Open, **waits for Sasha** (hardware). Blueprint:
`memory/system/heimkommen.md` (0 €, no WiFi, no 230 V).

1. Check the old laptop from the cellar (power supply broken?) → decide the
   host for the door node (old laptop vs. Pi + long serial cable).
2. Breadboard: Nano + RC522 reads the blue tag (RC522 on **3.3 V**), LED strip
   lights up.
3. Then Claude builds: Nano firmware (text protocol), app `wohnung`,
   `HOMECOMING` → light → greeting → small talk → graphs.
4. Voice: TTS runs on the PC (sleeps) — decide where the greeting voice runs.
5. Lamp: print a servo mount (SG90) for the living-room lamp switch.

Parts: `memory/betrieb/bauteile.md`. Later with money: Zigbee stick + plug +
motion sensor; a small own router so home devices don't depend on the hotspot.
