# Display-Debug (Pi-Kiosk Bildschirm schwarz)

Status: **Root Cause gefunden 2026-05-12** — der HDMI-Tunnel war eine
Sackgasse, der echte Bug saß im XFCE-Session-Start. Diese Datei
dokumentiert Symptom, Befund, Fix und das dabei entstandene
Diagnose-Tooling.

## Symptom

Pi 3 B (Bookworm, KMS/vc4) zeigte:

- Boot: kurzer Vollbild-Farbverlauf (KMS-Modeset, 1920x1080) ✓
- Konsole im `multi-user.target` ✓
- Sobald `lightdm` / X startet → **Monitor schwarz** (Backlight an)
- Nach `systemctl stop lightdm` → **bleibt schwarz**, erst Reboot
  setzt KMS-Konsole zurueck

## Root Cause

**`xfce4-session` startet auf dem Pi unvollstaendig**: weder `xfwm4`
(Window Manager) noch `xfdesktop` (Desktop-Renderer) werden
automatisch hochgezogen. Ohne WM und ohne Desktop-Renderer malt
keine App auf das Root-Window — X gibt deshalb einen schwarzen
Frame raus, der HDMI-Encoder schickt ihn brav an den Monitor.

Indizien:

- `pgrep -af xfce` zeigt nur `xfce4-session` + `xfce4-panel`,
  **kein** `xfwm4`, **kein** `xfdesktop`
- `~/.xsession-errors`:
  - `/usr/bin/startxfce4: X server already running on display :0`
  - `Failed to fetch _NET_NUMBER_OF_DESKTOPS; assuming 1`
  - `Failed to get _NET_WORKAREA; using full screen dimensions`
  - `Failed to fetch _NET_CURRENT_DESKTOP; assuming 0`
  (die `_NET_*` werden vom WM gesetzt — fehlen weil xfwm4 nicht läuft)
- System-`/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml`
  hat die Failsafe-Komponenten (xfwm4, xfsettingsd, xfce4-panel,
  Thunar, xfdesktop) korrekt drin — aber xfce4-session greift sie
  beim Auto-Login nicht
- `~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml`
  fehlt (User-Session-Konfig nicht angelegt)
- `~/.cache/sessions/` ist leer (keine gespeicherte Session, die wir
  loeschen muessten)

Beweis dass HDMI nicht das Problem ist:

- **Xvfb-Test**: Firefox-ESR + ZENTRALE-Dashboard rendern auf Pi 3B
  bei 1920x1080 korrekt (Screenshot via scrot bestaetigt)
- **X-Display-Screenshot bei laufendem lightdm**: komplett schwarz
- **Nach manuellem `xfwm4 --replace && xfdesktop`**: voller
  XFCE-Desktop sichtbar (Applications-Menu, Panel, Icons, Maus-Logo)

## Fix

`scripts/install_xfce_autostart.sh` legt zwei
XDG-Autostart-`.desktop`-Files in `~/.config/autostart/` an:

- `xfwm4.desktop` — startet xfwm4 nach XFCE-Session-Start
- `xfdesktop.desktop` — startet xfdesktop

Damit umgehen wir die Frage warum xfce4-session die Failsafe-Defaults
nicht selbst lädt; autostart-Files greifen unabhängig davon.

Anwenden:

```bash
# auf dem Pi, als sasha (NICHT root):
cd /opt/zentrale && git pull
bash scripts/install_xfce_autostart.sh

# testen:
sudo systemctl start lightdm
# Monitor sollte XFCE-Desktop zeigen
sudo systemctl stop lightdm

# Wenn ok: Kiosk-Autostart reaktivieren
mv ~/.config/autostart/zentrale.desktop.disabled \
   ~/.config/autostart/zentrale.desktop
sudo reboot
# Beim Boot startet jetzt lightdm -> XFCE -> xfwm4 + xfdesktop
# -> Firefox-Kiosk auf localhost:5000
```

## Bekannte Folge-Probleme

- **Dashboard-Layout zerquetscht auf 1920x1080**: das CSS rendert
  nur in den linken ~1260px, rechts daneben ein schwarzer Streifen.
  Vermutlich feste `max-width` ohne fluid responsive Skalierung.
  Nicht kritisch — Kiosk wirkt nur wie ein hoehlerer Slot.
  Siehe Task „Dashboard CSS für 1920x1080 fluid machen".

## Diagnose-Tooling

Beim Debugging entstanden, weiter nuetzlich falls am Pi was am
Display-Stack umgebaut wird.

### `scripts/display_debug.sh`

Snapshot des Display-States in `~sasha/zentrale-display-debug.log`:

- systemd-Status lightdm/zentrale + Xorg-Prozessliste
- DRM/KMS connector-State (sysfs: status, enabled, modes)
- Framebuffer (`fbset -i`)
- Pi-Firmware-View (`vcgencmd display_power | get_throttled | ...`)
- X-Display via xrandr + xset
- dmesg-Tail (drm/hdmi/vc4)
- Xorg.0.log Fehler/Warnungen

Manueller Aufruf (jeder Label-String erlaubt):

```bash
./scripts/display_debug.sh                  # Label "manual"
./scripts/display_debug.sh vor_fix          # eigenes Label
```

Auto-Modus (`autostart` als erstes Argument) macht 3 Snapshots im
Abstand T+0 / T+5s / T+15s — wird vom lightdm-Hook genutzt.

### `scripts/install_display_debug.sh`

Installiert den lightdm-Hook fuer den Auto-Modus. Einmalig auf dem
Pi als root:

```bash
sudo bash /opt/zentrale/scripts/install_display_debug.sh
```

Legt `/etc/lightdm/lightdm.conf.d/60-zentrale-display-debug.conf` an
mit `display-setup-script=...display_debug.sh autostart`.

Deinstallation:
`sudo rm /etc/lightdm/lightdm.conf.d/60-zentrale-display-debug.conf`

### Render-Verifikation via Xvfb

Wenn man das Frontend isoliert vom HDMI testen will:

```bash
sudo apt install -y xvfb scrot
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 firefox-esr --kiosk http://localhost:5000 &
sleep 20
DISPLAY=:99 scrot -z ~/kiosk-test.png
pkill firefox-esr; pkill Xvfb
```

PNG anschauen — wenn das Dashboard rendert, ist Frontend + Browser +
Backend okay und das Problem sitzt im X-/Session-Stack.

## Lehren

Die Fehlsuche hat ~einen Tag gefressen, weil zu lange in der
HDMI/KMS/vc4-Richtung gegraben wurde, ohne die Grundannahme
„X rendert irgendwas und der Encoder schickt es schwarz an den
Monitor" zu verifizieren. Ein einzelner Screenshot von Display :0
am Anfang haette die Richtung sofort umgelenkt.

Faustregel fuer naechstes Mal: **bevor man tief in die Hardware-
oder Treiber-Schicht graebt, einen Screenshot von dem was die
Software rendert, an den Tisch legen.** Das ist 1 Befehl (`scrot`)
und entscheidet zwischen „X-/UI-Schicht" vs. „Display-Output-
Schicht" — zwei voellig verschiedene Bug-Klassen.
