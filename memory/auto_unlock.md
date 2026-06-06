# Remote-LUKS-Unlock via Dropbear im Initramfs

**Status: ANGEWENDET 2026-06-01, Reboot-Test noch offen.**
Die drei sudo-Schritte sind durchgelaufen: init-premount-Skript
`zentrale-lan-unlock` liegt + ist `+x`, `ip=off` steht im gepflegten
cmdline (`/etc/kernelstub/configuration`), `update-initramfs -u` ohne
Fehler durch. Was noch fehlt: der **Reboot + ssh-Unlock vom Pi**
(Schritt 4 unten). Solange ungetestet gilt: der lokale LUKS-Prompt am
PC funktioniert normal weiter, der Boot ist nicht brickbar.

Zugehöriges Bedrohungsmodell + Design-Entscheidungen: `sicherheit.md`.

---

## Pi-Komfort: `zentrale-unlock` + Auto-Terminal (2026-06-03)

Auf dem **Pi** liegt ein Bequemlichkeits-Wrapper, damit Sasha vom Sofa
nicht die volle `ssh`-Zeile tippen muss:

- **`/usr/local/bin/zentrale-unlock`** — ist „literally nur" der ssh an
  den Dropbear: `ssh -p 2222 root@192.168.50.1 cryptroot-unlock`. Die
  LUKS-Passphrase fragt das `cryptroot-unlock` auf der PC-Seite
  interaktiv ab → **kein Passwort im Skript**, sicherheitstechnisch
  sauber.
- **`~/.config/autostart/zentrale-unlock.desktop`** — xfce-Autostart-
  Launcher, öffnet bei **jedem Pi-Start** automatisch ein xterm mit dem
  Skript: `Exec=xterm -hold -e zentrale-unlock`. So poppt die
  Passphrase-Frage von allein auf, ohne Terminal-öffnen + Tippen.
  - `-e` = Kommando *im* xterm ausführen; `-hold` = Fenster offen lassen
    (zeigt Erfolg/Fehler). Wenn's zuverlässig läuft, `-hold` raus →
    Fenster schließt sich nach erfolgreichem Unlock von selbst.
  - Poppt auch auf, wenn der PC schon läuft → dann `connection refused`
    (Dropbear lauscht nur im Initramfs, nicht im gebooteten System).

**Stolperstein 2026-06-03:** `zentrale-unlock` gab `permission denied` —
dem Skript fehlte das Execute-Bit. Fix: `sudo chmod +x
/usr/local/bin/zentrale-unlock`.

**⚠️ Nicht im Repo:** Beide Dateien liegen Pi-lokal (`/usr/local/bin/`
+ `~/.config/autostart/`), nicht im versionierten Repo → kein Backup.
Bei Pi-Neuaufsetzung von Hand neu anlegen (Inhalte stehen oben).

---

## Ziel

Pi weckt den PC per WoL → PC bootet → bleibt am LUKS-Prompt stehen →
Pi (oder Sasha vom Sofa) ssht ins Initramfs und tippt die Passphrase.
Der PC entsperrt *nicht* von allein, nur der **Eingabe-Ort** wandert
(Pi statt direkt am PC). So bleibt der Klauschutz erhalten.

---

## Ist-Zustand (was schon da ist) — 2026-06-01 verifiziert

| Baustein                          | Status | Fundstelle |
|-----------------------------------|--------|------------|
| `dropbear-initramfs` installiert  | ✅     | `dpkg -s dropbear-initramfs` |
| `cryptsetup-initramfs` (liefert `cryptroot-unlock`) | ✅ | `dpkg -s` |
| Pi-SSH-Key hinterlegt             | ✅     | `/etc/dropbear/initramfs/authorized_keys` (192 B, `-rw-------` root) |
| Dropbear-Optionen / Port          | ✅     | `dropbear.conf`: `DROPBEAR_OPTIONS="-I 60 -j -k -p 2222 -s"` |
| NIC-Treiber im Initramfs          | ✅     | `r8169`, von `MODULES=most` abgedeckt |
| **Netzwerk-Bringup im Initramfs** | ❌     | **DAS ist die Lücke — siehe unten** |

### Die eine fehlende Sache

`cat /proc/cmdline` zeigt **kein** `ip=`, `initramfs.conf` hat `DEVICE=`
leer, `conf.d/` ist leer. Heißt: am LUKS-Prompt kommt **enp4s0 nie hoch**
→ der PC hat in dem Moment **keine IP** → der Pi kann Port 2222 nicht
erreichen. Dropbear *läuft*, lauscht aber auf einer toten Leitung.

Genau deshalb „kommt der Pi nicht durch LUKS".

---

## Warum nicht einfach `ip=<adresse>` setzen?

Das wäre der Standard-Weg von `dropbear-initramfs` — und genau der hat
uns bei der LAN-Migration einen ganzen Tag „Internet kaputt" gekostet
(siehe `topologie.md` + Memory `feedback_no_kernel_ip_param`). Ein
`ip=<ip>:::<mask>::enp4s0:off` mit leerem Gateway-Feld lässt den
Kernel-IP-Stack eine bogus `default dev enp4s0 scope link`-Route
schreiben, die ARP killt. **Nie wieder.**

Der Trick hier: wir umgehen das komplett. Aus den echten Skripten
(`/usr/share/initramfs-tools/scripts/`) ergibt sich:

1. **`ip=off`** ist der *gefahrlose* Sentinel: `configure_networking()`
   hat einen expliziten `case off) Do nothing`-Zweig → **kein DHCP,
   keine Route, keine IP.** `ip=off` ≠ das alte böse `ip=<adresse>` —
   es ist das exakte Gegenteil, „mach NICHTS am Netz".
2. Den NIC bringen **wir selbst** in einem kleinen init-premount-Skript
   hoch — nur die lokale `192.168.50.1/24`, **kein Default-Gateway,
   keine Default-Route.** Damit ist die kaputte Route strukturell
   unmöglich (man kann keine Default-Route leaken, die nie existiert).
3. **Teardown ist gratis:** `init-bottom/dropbear` macht vor dem Pivot
   ins echte System eh `ip link down` + `ip address flush` +
   `ip route flush` auf *allen* Interfaces → NetworkManager startet
   sauber. Wir brauchen kein eigenes Teardown-Skript.

→ Drei Ebenen Sicherheit: keine Kernel-Route (`ip=off`), keine
Default-Route (unser Skript), Flush vor Boot (dropbear). Die kaputte
Route von damals kann hier an keiner Stelle entstehen.

**⚠️ Offene Mini-Entscheidung für Sasha:** `ip=off` ist trotzdem ein
`ip=`-Eintrag im Kernel-Cmdline. Wenn dir das gegen den Strich geht
(verständlich nach dem Drama), Alternative siehe ganz unten. Default-
Empfehlung bleibt `ip=off`, weil sauber begründet und vom Skript belegt.

---

## Schritt-für-Schritt (morgen, mit sudo)

### 1. Netz-Bringup-Skript anlegen

```bash
sudo tee /etc/initramfs-tools/scripts/init-premount/zentrale-lan-unlock >/dev/null <<'EOF'
#!/bin/sh
# Bringt enp4s0 im Initramfs mit statischer LAN-IP hoch, damit der Pi
# den PC am LUKS-Prompt per SSH (Port 2222) erreichen kann.
# BEWUSST nur die lokale /24, KEIN Default-Gateway, KEINE Default-Route
# — sonst droht die bogus "default scope link"-Route von der LAN-Migration.
# Teardown passiert automatisch in init-bottom/dropbear (flush vor Pivot).
PREREQ="udev"
prereqs() { echo "$PREREQ"; }
case "$1" in
    prereqs) prereqs; exit 0 ;;
esac

DEV=enp4s0
modprobe r8169 2>/dev/null || true      # i.d.R. via MODULES=most schon geladen
ip link set dev "$DEV" up

# kurz auf das Interface warten (max 10s), dann statische IP setzen
i=0
while [ $i -lt 10 ]; do
    [ -e "/sys/class/net/$DEV" ] && break
    sleep 1
    i=$((i + 1))
done

ip addr add 192.168.50.1/24 dev "$DEV" 2>/dev/null || true
EOF

sudo chmod +x /etc/initramfs-tools/scripts/init-premount/zentrale-lan-unlock
```

### 2. `ip=off` setzen (neutralisiert das DHCP von configure_networking)

```bash
sudo kernelstub --add-options "ip=off"
# Kontrolle (zeigt das gepflegte cmdline, NICHT das laufende):
grep -A20 kernel_options /etc/kernelstub/configuration
```

### 3. Initramfs neu bauen (sonst zählt nichts davon)

```bash
sudo update-initramfs -u
```

### 4. Reboot + Test

- PC neu starten, am LUKS-Prompt **stehen lassen** (nicht lokal tippen).
- Vom Pi aus:
  ```bash
  ssh -p 2222 root@192.168.50.1
  # → landet in der Initramfs-Mini-Shell
  cryptroot-unlock
  # → fragt nach der LUKS-Passphrase, tippen
  ```
- Erwartung: Platte entsperrt, SSH-Session bricht ab (gewollt —
  init-bottom killt dropbear + flusht das Netz), PC bootet durch,
  `zentrale-pc.service` startet.

Einzeiler-Variante vom Pi (ohne extra Shell):
```bash
ssh -p 2222 root@192.168.50.1 cryptroot-unlock
```

---

## Erste-Verbindung-Gotcha (Host-Key)

Der Initramfs-Dropbear hat **eigene Host-Keys**
(`dropbear_*_host_key` in `/etc/dropbear/initramfs/`), die sich vom
normalen SSH des laufenden PC unterscheiden. Beide hören auf dieselbe
IP `192.168.50.1`, aber verschiedene Ports (22 vs. 2222) und
verschiedene Keys. Beim ersten `ssh -p 2222` kommt also die
„unknown host key"-Frage — auf dem Pi einmal mit `yes` bestätigen.
Falls SSH wegen „host key mismatch" *blockt*, ist das nur die
Port-22-vs-2222-Verwechslung im `known_hosts` — dann den 2222-Eintrag
gezielt setzen, nicht den 22er löschen.

---

## Wenn der Test fehlschlägt — Debug-Pfad

| Symptom | Erste Vermutung | Check |
|---------|-----------------|-------|
| `ssh: connect ... No route` / Timeout | NIC kommt nicht hoch | am PC lokal entsperren, dann `journalctl -b | grep -i dropbear`; ist `zentrale-lan-unlock` im Initramfs? `lsinitramfs /boot/initrd.img | grep zentrale` |
| `Connection refused` auf 2222 | Dropbear läuft nicht | `lsinitramfs /boot/initrd.img | grep dropbear`; `dropbear.conf` Port stimmt? |
| Verbindung ok, aber `cryptroot-unlock` fehlt | cryptsetup-Hook nicht drin | `lsinitramfs /boot/initrd.img | grep cryptroot` |
| Internet nach Reboot kaputt | wider Erwarten doch Route geleakt | `ip route show default` — zeigt's auf enp4s0? Dann `ip=off` raus: `sudo kernelstub --delete-options "ip=off"` + `update-initramfs -u` |

`lsinitramfs` braucht evtl. `sudo` (das `/boot/initrd.img` ist root-only).

---

## Rollback (falls's nervt oder bricht)

Nichts davon ist gefährlich — der **lokale** LUKS-Prompt am PC
funktioniert die ganze Zeit weiter, der Remote-Unlock ist nur ein
*zusätzlicher* Eingang. Komplett zurückbauen:

```bash
sudo rm /etc/initramfs-tools/scripts/init-premount/zentrale-lan-unlock
sudo kernelstub --delete-options "ip=off"
sudo update-initramfs -u
```

Wichtig: Kann den **Boot nicht bricken** — ein fehlerhaftes
init-premount-Skript blockiert den LUKS-Prompt nicht (läuft nebenläufig,
`run_dropbear &`). Schlimmstenfalls klappt der Remote-Unlock nicht und
du tippst wie bisher am PC.

---

## Alternative ohne jeglichen `ip=`-Eintrag (falls gewünscht)

Wenn `ip=off` partout nicht ins Cmdline soll: dann das DHCP von
`configure_networking()` anders ausbremsen. Ohne `ip=off` läuft beim
Boot `dhcpcd` (4 Runden bis ~5 min) gegen den dummen Switch — findet
keinen DHCP-Server, scheitert, und könnte dabei unsere statische IP
wieder wegflushen. Sauber lösbar nur mit einem zweiten init-premount-
Skript, das nach dem DHCP-Fehlschlag die IP (re-)setzt — fummelig und
race-anfällig. **Empfehlung bleibt `ip=off`** (der harmlose Sentinel),
die saubere Variante. Nur dokumentiert, falls die Reflex-Abneigung
gegen alles-was-`ip=`-heißt überwiegt.
