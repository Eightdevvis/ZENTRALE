# Display-Debug (Pi-Kiosk Bildschirm schwarz)

**Status: GELOEST am 2026-05-12.** Echte Ursache war ein vc4-KMS-Bug
auf Pi 3 B + diesem Monitor, NICHT die xfce4-Session-Geschichte aus
dem ersten Anlauf. Fix dokumentiert unten — diese Datei in dieser
Reihenfolge lesen, sonst geht man wieder in die Sackgassen die wir
schon abgelaufen haben.

## Der echte Fix

`/boot/firmware/config.txt`:

```diff
- dtoverlay=vc4-kms-v3d
+ dtoverlay=vc4-fkms-v3d
```

Backup vorher: `cp /boot/firmware/config.txt /boot/firmware/config.txt.bak-kms`.

`fkms` = „fake KMS" — andere Pipeline auf Pi 3 B, gibt das Framebuffer-
Setup an die Firmware/VideoCore zurueck statt den vollen KMS-Stack
durch den vc4-Treiber zu fahren. Auf Pi 4/5 ist Full-KMS Default,
auf Pi 3 B mit Bookworm hat es bei dieser Monitor-Kombination dazu
gefuehrt dass X einen Frame in den Framebuffer rendert (Screenshot
zeigt vollen Desktop), aber der vc4-HDMI-Encoder am Output diesen
Frame nicht an den Monitor weitergibt — schwarzer Frame mit
korrektem Sync, Backlight bleibt an. **Nach `fkms`-Wechsel und
Reboot kommt das Bild direkt sauber raus.**

## Symptom

Pi 3 B (Bookworm, vc4-kms-v3d) zeigte:

- Boot: kurzer Vollbild-Farbverlauf (KMS-Modeset, 1920x1080) ✓
- Konsole im `multi-user.target` ✓
- Sobald lightdm/X startet → **Monitor schwarz** (Backlight an,
  Sync valid, „aktives schwarzes Signal" — kein „No Signal"
  und kein „Out of Range")
- Nach `systemctl stop lightdm` → bleibt schwarz, erst Reboot
  setzt KMS-Konsole zurueck
- `scrot` vom Display :0 zeigt **vollen XFCE-Desktop bzw. Kiosk** —
  X rendert korrekt, der Bruch sitzt zwischen Framebuffer und
  HDMI-Encoder

## Wie diagnostiziert

Schluessel-Erkenntnis war: **Screenshot per `scrot -d :0` zeigt was
X intern gerendert hat, unabhaengig vom HDMI-Output.** Wenn der
Screenshot was Sinnvolles zeigt aber der Monitor schwarz ist, ist
es zu 100 % eine Output-Layer-Sache (vc4/fkms/EDID/Pixel-Format)
und keine X-/WM-/Session-Geschichte.

Ausgeschlossene Theorien (alle in mehreren Sessions getestet,
NICHT erneut angehen):

- light-locker, DPMS, Screensaver
- xfwm4-Compositor an/aus
- 1024x768@99.97 Hz Mode-Issue (Mode-Switch zu 1280x720@60 oder
  1920x1080@60 aenderte am Monitor-Output nichts)
- Broadcast RGB Auto/Full/Limited
- xrandr-Force fuer beliebige Modes
- Pixel-Clock / Refresh-Rate-Hypothesen
- xorg.conf.d Force-Mode
- xfce4-session ohne xfwm4/xfdesktop (war zwischenzeitlich auch
  ein Bug, autostart-Files gefixt — aber das war nicht die
  Ursache des schwarzen Monitors, X rendert auch ohne WM was
  Sinnvolles in den Framebuffer)
- Strom/Throttling (`vcgencmd get_throttled = 0x0`)
- HDMI-Kabel, Monitor, Adapter (mehrere getestet)

## Komplette Workflow zum Reproduzieren des Setups

Auf einem frischen Pi 3 B mit Bookworm + ZENTRALE deployed:

```bash
# 1. config.txt auf fkms umstellen
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak-kms
sudo sed -i 's/^dtoverlay=vc4-kms-v3d/dtoverlay=vc4-fkms-v3d/' \
    /boot/firmware/config.txt

# 2. XFCE-Autostart-Files (xfwm4 + xfdesktop) wegen unrelated
#    session-Bug auch noch noetig
cd /opt/zentrale && git pull
bash scripts/install_xfce_autostart.sh

# 3. Kiosk-Autostart aktivieren falls disabled
mv ~/.config/autostart/zentrale.desktop.disabled \
   ~/.config/autostart/zentrale.desktop 2>/dev/null || true

# 4. Boot ins X-Target setzen
sudo systemctl enable lightdm
sudo systemctl set-default graphical.target

# 5. Reboot — Pi kommt mit Kiosk im Vollbild hoch
sudo reboot
```

## Diagnose-Tooling (bleibt nuetzlich)

### `scripts/display_debug.sh`

Snapshot des kompletten Display-States in
`~sasha/zentrale-display-debug.log`. Was rein geht:

- systemd-Status lightdm/zentrale + Xorg-Prozessliste
- DRM/KMS connector-State (sysfs: status, enabled, modes)
- Framebuffer (`fbset -i`)
- Pi-Firmware-View (`vcgencmd display_power | get_throttled | ...`)
- X-Display via xrandr + xset
- dmesg-Tail (drm/hdmi/vc4)
- Xorg.0.log Fehler/Warnungen

Aufruf manuell mit beliebigem Label:

```bash
./scripts/display_debug.sh
./scripts/display_debug.sh nach_aenderung_x
```

Auto-Modus (`autostart`) macht 3 Snapshots T+0/T+5s/T+15s, wird
vom lightdm-Hook genutzt.

### `scripts/install_display_debug.sh`

Installiert den lightdm-Hook fuer den Auto-Modus.

### `scripts/install_xfce_autostart.sh`

**Aktuelles Setup (Stand 2026-05-12, nach Kiosk-Lockdown):**
Schreibt eine minimale `~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml`
die nur `xfwm4` + `xfsettingsd` startet (kein Panel, kein xfdesktop,
kein Thunar). Plus `xfwm4`-XDG-autostart als Backup. xfdesktop ist
ABSICHTLICH WEG — wir wollen das Root-Window schwarz haben, damit
zwischen lightdm-Login und Firefox-Kiosk nichts sichtbar ist.

Historischer Kontext: in einer früheren Variante hatten wir
xfdesktop hier mit drin, weil unter dem alten vc4-KMS-Display-Bug
das Root-Window sonst „komplett schwarz" blieb (HDMI gab leeren
Frame raus). Mit fkms-Fix ist das geheilt → schwarzes Root-Window
zeigt der Monitor jetzt korrekt als schwarz an, was wir wollen.

### Schneller Diagnose-Workflow bei neuen Display-Problemen

**Erste Frage: Screenshot vom Display :0** machen, BEVOR HDMI/KMS-
Theorien aufgestellt werden:

```bash
sudo DISPLAY=:0 XAUTHORITY=/home/sasha/.Xauthority scrot -z /tmp/x.png
```

- **Screenshot zeigt erwarteten Inhalt + Monitor schwarz**
  → Output-Layer (vc4, HDMI, fkms vs kms, EDID). Fkms ausprobieren.
- **Screenshot ist komplett schwarz + Monitor schwarz**
  → X-/WM-/Session-Schicht. xfwm4 + xfdesktop checken (`pgrep`).
- **Screenshot zeigt was Erwartet + Monitor zeigt es auch**
  → kein Problem.

Das spart Stunden vs. „in Treiber-Theorien graben ohne Output-vs-
Render-Trennung".

## Beobachtungen die wir VOR-Tunneling nicht ernst genommen haben

Der User hatte zwei Beobachtungen, die spaeter exakt die Loesung
bestaetigt haben — beim naechsten Mal ernster nehmen:

1. „Falsche Aufloesung wuerde quetschen, nicht komplett schwarz machen."
   Stimmt: out-of-range gibt OSD-Message oder „No Signal", nicht
   schwarz mit valider Sync. → Mode-Theorie war damit eigentlich
   schon entschaerft.
2. „Monitor geht aus, dann an, dann schwarz" beim X-Start. Aus =
   Mode-Switch (no-sync kurz), an = neuer Mode-Sync etabliert,
   schwarz = aktiver schwarzer Frame. Genau der Output-Layer-Bug.

Verwandte Lehre: `[[feedback-debug-tunnel-vision]]` (Claude-Memory).

## Bekannte Folge-Probleme

- **Dashboard-Layout auf 1920x1080**: das CSS rendert nur in den
  linken ~1260 px, rechts daneben schwarzer Streifen. Auf dem
  echten Pi-Monitor (1024x768) faellt das nicht stark auf weil
  da gerade fast passt. Auf einem 1920x1080-Monitor offensichtlich
  hässlich. Task „Dashboard CSS für 1920x1080 fluid machen".
