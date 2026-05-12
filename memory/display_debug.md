# Display-Debug (Pi-Monitor schwarz)

Hintergrund + Tooling fuer das laufende Debugging des schwarzen
Pi-Monitors. Ergaenzt das memory-File
`~/.claude/projects/-home-sasha-codicus-ZENTRALE/memory/project_pi_display_debug.md`
(Claude-Memory, ausserhalb des Repos).

## Symptom

Pi 3 B (Bookworm, KMS/vc4) zeigt:

- Boot: kurzer Vollbild-Farbverlauf (KMS-Modeset, 1920x1080) ✓
- Konsole im multi-user.target ✓
- Sobald `lightdm` / X startet → **Monitor schwarz** (Backlight an)
- Nach `systemctl stop lightdm` → **bleibt schwarz**, erst Reboot
  setzt zurueck

## Stand der Diagnose (2026-05-12)

- KMS-Framebuffer ist auf **1920x1080** (preferred Mode laut EDID)
- X (modesetting-Treiber) waehlt **1024x768 @ 99.97 Hz**, Pixel-Clock
  113.274 MHz — ein ungewoehnlicher Mode aus der EDID, den der HDMI-
  Encoder oder der Monitor offenbar nicht sauber ausgibt
- Nach dem fehlgeschlagenen Mode-Set bleibt der vc4-HDMI-Encoder im
  broken State haengen — Konsole bleibt schwarz bis Reboot
- Xorg.0.log keine `(EE)`, nur harmlose Warnungen
- `vcgencmd display_power=1`, `throttled=0x0` (Strom OK)
- `/etc/X11/xorg.conf.d/` ist leer (keine Force-Mode-Config aktiv)

Volle Liste der ausgeschlossenen Theorien siehe Claude-Memory
`project_pi_display_debug.md`.

## Tooling

### `scripts/display_debug.sh`

Snapshot-Skript. Schreibt vollstaendigen Display-State nach
`~sasha/zentrale-display-debug.log`. Erfasst:

- systemd-Status lightdm/zentrale + Xorg-Prozessliste
- DRM/KMS connector-State (sysfs: status, enabled, modes)
- Framebuffer (`fbset -i`)
- Pi-Firmware-View (`vcgencmd display_power | get_throttled | ...`)
- X-Display via xrandr + xset (probiert lightdm-auth UND user-auth)
- dmesg-Tail (drm/hdmi/vc4)
- Xorg.0.log Fehler/Warnungen

**Manueller Aufruf** (jeder Label-String erlaubt, landet im Header):

```bash
./scripts/display_debug.sh                  # Label "manual"
./scripts/display_debug.sh vor_fix          # eigenes Label
```

**Auto-Modus** (`autostart` als erstes Argument) macht 3 Snapshots
im Abstand T+0/T+5s/T+15s — wird vom lightdm-Hook genutzt, sollte
manuell selten gebraucht werden.

### `scripts/install_display_debug.sh`

Installiert den lightdm-Hook. Einmalig auf dem Pi als root:

```bash
sudo bash /opt/zentrale/scripts/install_display_debug.sh
```

Legt `/etc/lightdm/lightdm.conf.d/60-zentrale-display-debug.conf` an
mit `display-setup-script=/opt/zentrale/scripts/display_debug.sh autostart`.
Damit triggert jeder `systemctl start lightdm` automatisch das
Snapshot-Triple.

Deinstallation: `sudo rm /etc/lightdm/lightdm.conf.d/60-zentrale-display-debug.conf`.

### Log abgreifen

```bash
# Vom Entwicklungs-Rechner aus:
ssh zentrale "tail -200 ~/zentrale-display-debug.log"

# Live mitlesen waehrend Test:
ssh zentrale "tail -F ~/zentrale-display-debug.log"
```

## Workflow fuer einen Debug-Cycle

1. Pi rebooten (Encoder zuruecksetzen, Konsole wieder da)
2. Pi pullen: `cd /opt/zentrale && git pull` (kein RELEASE-Bump
   noetig, wir wollen den Service nicht restartet bekommen)
3. Wenn neu: `sudo bash scripts/install_display_debug.sh` (einmal)
4. `sudo systemctl start lightdm`
5. ~20 Sekunden warten (T+15s-Snapshot ist drin)
6. `sudo systemctl stop lightdm` falls wir was aendern wollen
7. Log abgreifen, naechste Hypothese, Loop
