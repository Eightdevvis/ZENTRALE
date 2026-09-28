# Heimnetz: PC als Gehirn, alles andere Knoten

**Stand 2026-09-28 — Plan, noch nicht gebaut.** Zuerst wird das **Heimnetz**
aufgestellt; der Glasfaser-Vertrag ist **geparkt** bis später im Jahr (siehe
»Glasfaser — geparkt« unten). Glasfaser (Telekom-Netz) kommt voraussichtlich
**ab Februar 2027**. Der heutige Ist-Zustand
(dummer Switch, Handy-Hotspot, `find-pc`) steht in `topologie.md`. Diese Datei
ist das **Zielbild** und der **Weg dahin**. Wenn etwas davon gebaut ist:
dort abhaken und `topologie.md` nachziehen.

## Zielbild

Der PC hängt ohne eigenen Bildschirm im Heimnetz. Er schläft nach festen
Zeiten und wenn der Pi aus ist; der Router weckt ihn, auch von draußen
(`../betrieb/wachplan.md`). Man bedient ihn von den Knoten aus so, als säße
man davor. Ein Monitor bleibt jederzeit ansteckbar.

```
                    Internet (Glasfaser, eigene öffentliche IPv4)
                         │
                   Glasfaser-Modem (ONT, selbst gekauft)
                         │
┌────────────────── eigener Router ─────────────────────────────┐
│  Firewall: von außen NUR der VPN-Port offen                   │
│  VPN-Server (WireGuard) · lokaler DNS · DHCP mit festen IPs    │
└───────┬───────────────────────────────────────────────────────┘
        │ LAN 192.168.50.0/24 (Switch dahinter, wenn Ports knapp)
        ├── PC        192.168.50.1   Gehirn: KI, Backend, Sunshine, SSH
        ├── Pi        192.168.50.10  Außenposten: ZENTRALE, Tutor, Kiosk
        ├── Pi 2      192.168.50.11  Medienknoten: Lautsprecher (später)
        ├── Laptop    192.168.50.20  am Kabel, wenn daheim
        └── Mini-PC   192.168.50.21  am Kabel, wenn daheim

   unterwegs: Laptop · Mini-PC (AR-Brille) · Handy
        └── WireGuard → Router → dasselbe LAN, dieselben Adressen
```

**Der Kern der Idee:** Ein Knoten im VPN sieht das Heimnetz genauso wie ein
Knoten am Kabel. `pc` ist überall dieselbe Adresse, egal ob daheim, im
Café oder mit der AR-Brille. `find-pc`, das Suchen nach der MAC im Hotspot und
die umgeschriebenen SSH-Config-Blöcke fallen weg.

### Drei Sorten Knoten

| Sorte | Wer | Wie er ans Gehirn kommt |
|---|---|---|
| **Vollknoten** | Laptop, Mini-PC mit AR-Brille | LAN oder VPN → SSH, Moonlight (ganzer Desktop), TUI direkt gegen das Backend. Beide gleichwertig. |
| **Außenposten** | Pi mit ZENTRALE/Tutor | LAN; holt sich sein Paket selbst (`topologie.md` → Aussenposten) |
| **Medienknoten** | Lautsprecher-Pi, weitere | LAN; der PC streamt hin (Audio übers Netz, auch mehrere Räume synchron) |

### Adressplan

- **Das Subnetz bleibt `192.168.50.0/24`.** PC `.1` und Pi `.10` bleiben, wie
  sie sind. So muss am Pi-Paket, am Kiosk und am Updater nichts umgebogen
  werden.
- **Der Router nimmt `.254`**, nicht `.1`, weil die `.1` der PC hat.
- **Feste IPs als DHCP-Reservierung im Router** (nach MAC), nicht mehr von
  Hand auf jedem Gerät. So stehen alle Adressen an einem Ort.
- **Freier DHCP-Bereich `.100–.199`** für Gäste und Kleinkram.
- **Namen statt Nummern:** Der Router macht lokalen DNS (`pc`, `pi`, …). Die
  VPN-Knoten nutzen ihn mit, also gehen die Namen auch von unterwegs.
- **VPN-Subnetz eigenes, z.B. `10.50.0.0/24`.** Das sind nur die Adressen der
  Tunnel selbst; über den Router erreichen die Knoten darüber das ganze LAN.

### Grafisch auf den PC

- **Sunshine** (PC) → **Moonlight** (Laptop, Mini-PC). Das Bild wird über die
  Grafikkarte kodiert und ist flüssig.
- **Normalbetrieb ohne Monitor → HDMI-Dummy-Stecker bleibt dauerhaft drin**,
  sonst hat die Karte keinen Ausgang, den Sunshine aufnehmen kann. Soll
  gelegentlich ein echter Monitor dran: Dummy ziehen und Monitor an HDMI, oder
  Monitor an einen freien DisplayPort (beide gleichzeitig geht auch).
- **Autologin**, weil Sunshine eine laufende Sitzung braucht. Vertretbar,
  weil die Platte per LUKS verschlüsselt ist.
- **Zweite Spur: RDP**, eingebaut in KDE/GNOME, robust, weniger flüssig.
- Sunshine und RDP **nie ins Internet öffnen**, nur über LAN oder VPN.

### PC-Betriebssystem

Empfehlung: **Ubuntu-LTS-Basis mit KDE Plasma** (z.B. Kubuntu LTS).
- KDE unter Wayland ist für Sunshine besser erprobt als COSMIC.
- Die Ubuntu-Basis hat dasselbe Initramfs-System wie Pop!_OS, also bleibt der
  **Dropbear-Unlock (`../betrieb/auto_unlock.md`) fast 1:1 übertragbar**.
  Bei Fedora müsste er neu gebaut werden.
- Der NVIDIA-Treiber ist einfach zu bekommen, und LTS heißt rund 5 Jahre
  Updates ohne Umbau.

## Router: eigener, ja

**Empfehlung: einen eigenen Router kaufen, mit OpenWrt.** Den Router des
Anbieters nicht mieten.

Warum:
1. **Man kann ihn JETZT kaufen und das Heimnetz komplett aufbauen**, lange
   bevor der Anschluss da ist. Ein Anbieter-Router kommt erst mit dem Vertrag.
2. **Sicherheit in eigener Hand:** Updates kommen vom OpenWrt-Projekt statt
   irgendwann vom Anbieter. Nichts ist offen, was man nicht selbst geöffnet
   hat, und es gibt keine Fernwartung durch den Anbieter.
3. **Kann alles, was der Plan braucht:** WireGuard-Server, lokaler DNS,
   DHCP-Reservierungen, eine Firewall mit Regeln pro Gerät und später VLANs
   (Netz-Trennung).
4. **Lernwert:** Es ist ein echtes Linux, per SSH erreichbar, und passt zum
   Shell-Lernen.

Kandidaten (vor dem Kauf aktuelle OpenWrt-Unterstützung prüfen):
- **GL.iNet Flint 2 (GL-MT6000):** OpenWrt-basiert ab Werk, reines OpenWrt
  aufspielbar, verbreitet. Der naheliegende Kandidat.
- **FritzBox** als bequeme Alternative: gute Updates, WireGuard eingebaut,
  aber weniger Kontrolle und keine echte Netz-Trennung.

**Voraussetzung auf der Anbieter-Seite:** In Deutschland gilt Routerfreiheit.
Bei der Bestellung den Miet-Router abwählen, dafür bekommst du die
**Zugangsdaten** (O2 im Telekom-Netz: PPPoE mit **VLAN 7**, Zugangsdaten unter
»Vertrag verwalten«). **Das Glasfaser-Modem (ONT) kauft man bei O2 im
Telekom-Ausbaugebiet selbst** (Stand 2026, »Glasfaser-Modem 2«, ca. 50 €); der
Techniker bringt keins mit. Seine Modem-ID wird bei O2 hinterlegt
(Einrichtungslink). Der Router hängt per LAN-Kabel dahinter und braucht also
kein eingebautes Glasfaser-Modem — OpenWrt am Telekom-ONT ist ein gut
dokumentierter Aufbau.

### Sicherheits-Grundregeln

- **Von außen offen ist genau ein Port: WireGuard.** WireGuard antwortet
  unbekannten Absendern gar nicht, von außen ist der Port praktisch
  unsichtbar. SSH, Sunshine, RDP, Backend `:5000` und die Router-Oberfläche
  sind **nie** direkt aus dem Internet erreichbar.
- **SSH am PC nur mit Schlüssel**, Passwort-Login und Root-Login aus.
- **Router-Oberfläche nur aus dem LAN/VPN**, eigenes starkes Passwort.
- **Pro Knoten ein eigener VPN-Schlüssel.** Geht ein Gerät verloren (z.B. der
  Mini-PC in der Tasche), sperrst du genau diesen Schlüssel, und die anderen
  bleiben unberührt.
- **Später VLANs:** Kern (PC, Laptops) getrennt von Außenposten/Medien
  (Pis, Lautsprecher) und Gästen. Ein gekaperter Lautsprecher kommt dann nicht
  an den PC. Anfangs flach lassen und erst trennen, wenn alles läuft, damit
  nicht zwei Baustellen auf einmal offen sind.
- **Secrets** (VPN-Schlüssel, Zugangsdaten) wie immer nicht ins Repo.

## Übergangsplan: alles bauen, bevor das Internet da ist

### Einkaufsliste
- Router mit OpenWrt (Internet per WLAN-Repeater **und** USB-Tethering vom Handy)
- LAN-Kabel (Cat 6); der alte Switch hinter den Router, falls die Ports nicht reichen
- Dummy-Stecker (HDMI oder DP, je nachdem, welcher Ausgang an der Grafikkarte frei ist)
- USB-Stick ≥ 8 GB (OS-Installation), externe Platte (Backup vor dem OS-Wechsel)
- USB-Kabel fürs Handy (Tethering, lädt dabei)
- bis Februar: Glasfaser-Modem 2 (ONT, ca. 50 €; bei O2 im Telekom-Netz selbst zu besorgen)

### Was vor dem Router hängt, je nach Phase
| Phase | Uplink | Von draußen rein? |
|---|---|---|
| A — jetzt | Handy-Hotspot / USB-Tethering. **Datenvolumen im Blick**, große Downloads (OS, Modelle) möglichst woanders | nein (Mobilfunk = keine eigene IPv4) |
| B — falls Zwischenanschluss | VDSL: **separates VDSL-Modem** vor dem Router (der OpenWrt-Router hat keins). LTE/5G-Box: davor hängen | VDSL ja, LTE/5G nein |
| C — Glasfaser | Glasfaser-Modem (ONT, selbst gekauft) → WAN-Port | ja |

Das Heimnetz hinter dem Router bleibt in allen Phasen dasselbe.

Idee: **Der Router bekommt sein Internet übergangsweise vom Handy-Hotspot**
(WLAN als Uplink oder USB-Tethering, das kann OpenWrt). Das ganze Netz
dahinter ist dann schon das endgültige. Am Glasfaser-Tag wechselt nur die
Leitung, über die der Router ins Internet geht.

### Phase 0 — Entscheiden
- [ ] Router-Modell wählen und kaufen
- [ ] Dummy-Stecker für die Grafikkarte kaufen (passend zum Ausgang: HDMI oder DP)
- [ ] PC-OS festlegen (Empfehlung oben)
- [ ] Glasfaser-Vertrag — geparkt, siehe unten

### Phase 1 — Router aufsetzen (ohne Internet möglich)
- [ ] OpenWrt aktuell machen, Router-Passwort, Oberfläche nur von innen
- [ ] LAN auf `192.168.50.254/24`, DHCP `.100–.199`
- [ ] DHCP-Reservierungen: PC `.1`, Pi `.10`, Laptop `.20`, Mini-PC `.21`
- [ ] lokale Namen (`pc`, `pi`, …) im Router-DNS
- [ ] Uplink übergangsweise übers Handy (Hotspot oder USB)
- [ ] eigenes WLAN des Routers für Laptop/Handy daheim

### Phase 2 — Knoten umhängen
- [ ] PC und Pi an den Router (bzw. an den Switch dahinter)
- [ ] PC und Pi: LAN-Verbindung wird die **Standard-Route**. Heute steht dort
      „nie Standard-Route", weil das Internet übers WLAN kam, das muss
      umgedreht werden. Danach das WLAN auf beiden aus.
- [ ] prüfen: Pi erreicht das Backend, holt sein Paket, der Kiosk läuft
- [ ] Laptop: SSH auf `pc` per Name statt `find-pc`

### Phase 3 — VPN (schon vorher realistisch testbar)
- [ ] WireGuard auf dem Router, ein Schlüssel pro Knoten: Laptop, Mini-PC, Handy
- [ ] VPN-Knoten bekommen Zugriff aufs LAN und den Router-DNS
- [ ] **Test vor der Glasfaser:** Laptop in den Handy-Hotspot, Router-Uplink
      auch im Hotspot → Laptop verbindet sich zur Hotspot-Adresse des Routers.
      Das ist derselbe Weg wie später von draußen, nur ohne echtes Internet
      dazwischen.
- [ ] Dropbear-Unlock vom Laptop aus testen (übers LAN/VPN), nicht nur vom Pi

### Phase 4 — PC neu aufsetzen (wenn das OS wechselt)
- [ ] **vorher sichern:** `data/`, Schlüssel (SSH-Host-Keys, damit die Knoten
      nicht Alarm schlagen; Dropbear-Keys), systemd-Units, Netzwerk-Profile,
      Ollama-Modelle (mehrere GB, übers Handy neu laden ist mühsam)
- [ ] Installationsmedium vorher bereitlegen (braucht einmal Internet)
- [ ] LUKS + Dropbear-Unlock wieder einrichten, von Pi und Laptop testen
- [ ] ZENTRALE-Dienste, SSH nur mit Schlüssel
- [ ] Suspend aus (`../betrieb/wachplan.md`)

### Phase 5 — Grafisch
- [ ] Sunshine am PC; erst mit Monitor testen, dann mit Dummy-Stecker
- [ ] Autologin
- [ ] Moonlight auf Laptop (und später Mini-PC), im LAN testen
- [ ] RDP als zweite Spur

### Phase 6 — Glasfaser-Tag (soll nur noch Anstecken sein)
- [ ] Glasfaser-Modem (ONT) an die Glasfaser-Dose, Modem-ID über den O2-Einrichtungslink hinterlegen, Router-WAN per Kabel dran
- [ ] Zugangsdaten (PPPoE, VLAN 7) im Router eintragen, Uplink vom Handy auf Glasfaser umstellen
- [ ] prüfen: bekommt der Router eine **echte öffentliche IPv4**? (die WAN-Adresse
      im Router muss dieselbe sein, die eine „Wie ist meine IP"-Seite zeigt)
- [ ] **DynDNS** einrichten: die IPv4 ist dynamisch, also braucht das VPN einen
      Namen, der ihr folgt
- [ ] VPN-Endpunkt auf den DynDNS-Namen umstellen, Port-Weiterleitung für WireGuard
- [ ] Test von draußen: Laptop übers Handy-Netz (nicht Heim-WLAN) → VPN → SSH → Moonlight

### Später
- [ ] Medienknoten (Lautsprecher-Pi)
- [ ] VLANs trennen
- [ ] Handy als Knoten (siehe Handy-Plan)

## Glasfaser — geparkt (Stand 2026-09-28)

Sasha klärt das bis Jahresende. **Frist:** Der Hausanschluss ist nur **während
der Bauphase** kostenlos, danach kostet er 600–800 €. Also im Blick behalten,
wann in der Straße gebaut wird.

- **Favorit bisher:** O2 Home M 150 (Telekom-Netz, 150/75 Mbit, eigene IPv4,
  PPPoE/VLAN 7). Datenblatt: normal = minimal = 150/75.
- **Flex-Angebot für die Adresse (2026-09-28):** 25 €/Monat im 1. Jahr, dann
  39,99 €; **+4,99 € Zusatzoption, nicht abwählbar** (was genau, noch
  unklar); **Erschließungspreis 599,99 €** + Anschluss 9,99 € → einmalig
  609,98 €, über 2 Jahre ca. 1.390 €.
- **Die 600 € vermeiden:**
  - **A — O2 mit 24 Monaten:** Erschließung entfällt laut mehreren Quellen,
    nur 9,99 € Anschluss. Die Laufzeit beginnt erst mit der Schaltung.
  - **B — Hausanschluss »ohne Produkt« direkt bei der Telekom** während des
    Ausbaus (auf telekom.de/glasfaser die Adresse prüfen), danach Flex ohne
    Erschließung. **Unbestätigt**, ob O2 dann wirklich nichts berechnet; die
    Option gibt es womöglich nur an geförderten Adressen. Bei Miete muss der
    Eigentümer beauftragen.
- Das Glasfaser-Modem (ONT, ca. 42–55 €) kauft man bei O2 selbst.
- Vergleichsstand der Anbieter: congstar 50 (30 €, 16 Mbit Upload, monatlich
  kündbar, eigene IPv4), easybell ab 39,95 €, Telekom Glasfaser 150 45,95 €
  mit 24 Monaten, 1&1 ungeeignet (DS-Lite).

## Offene Entscheidungen

- Router-Modell (Empfehlung: OpenWrt, z.B. Flint 2)
- OS-Wechsel am PC ja/nein (Empfehlung: Kubuntu LTS)
- Wann VLANs kommen
