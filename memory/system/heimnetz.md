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

### Jetzt: Schritt 1 (Stand 2026-09-28)

**A — bestellen**
- [ ] Router **GL.iNet Flint 2 (GL-MT6000)**, ~139 €
- [ ] **HDMI-Dummy 4K** (4K@60, 1440p/1080p@120), ~12 €; er steckt im
      Normalbetrieb **dauerhaft** im HDMI-Ausgang der 4070
- [ ] ein paar **Cat-6-Kabel**, ~15 €
- [ ] USB-Kabel fürs Handy-Tethering, falls keins da ist

**B — bis der Router kommt (ohne neue Hardware)**
- [ ] **Bestandsaufnahme:** Von jedem Gerät, das ans Heimnetz kommt (PC, Pi,
      Laptop, Mini-PC), die **MAC-Adresse der LAN-Karte** notieren. Die braucht
      der Router für die festen Adressen (DHCP-Reservierung).
- [ ] **Grafikkarte:** nachsehen, welche Ausgänge frei sind (erwartet: 1× HDMI,
      3× DP) und woran der Monitor gerade hängt.
- [ ] **Wake-on-LAN am PC:** prüfen, dass die LAN-Karte weiterhin auf
      Magic-Packet steht (`../betrieb/wachplan.md`).
- [ ] **Datenvolumen** vom Handy-Tarif nachsehen, weil bis Februar alles über
      den Hotspot läuft.
- [ ] **O2 anrufen:** 24-Monats-Angebot M 150 für die Adresse (Erschließung?
      Was ist die Zusatzoption?), dabei auch »Hausanschluss ohne Produkt« bei
      der Telekom fragen (siehe »Glasfaser — geparkt«).

**C — wenn der Router da ist** → Phase 1 unten.

### Einkaufsliste (gesamt)
- Router mit OpenWrt: **GL.iNet Flint 2** (Internet per WLAN-Repeater **und**
  USB-Tethering vom Handy; 2× 2,5G + 4× 1G, USB; WireGuard ~900 Mbit/s)
- LAN-Kabel (Cat 6); der alte Switch hinter den Router, falls die Ports nicht reichen
- **HDMI-Dummy 4K** (DP-Dummies können 4K oft nur mit 17–30 Hz)
- USB-Stick ≥ 8 GB (OS-Installation), externe Platte (Backup vor dem OS-Wechsel)
- USB-Kabel fürs Handy (Tethering, lädt dabei)
- bis Februar: **Glasfaser-Modem 2 / 2b** (ONT, 42–55 €; bei O2 im Telekom-Netz selbst zu besorgen)
- **Kosten grob:** einmalig ~220 € (ohne Stick/Platte); laufend Tarif
  (~25–46 €) + PC-Strom. Der Strom sinkt stark, weil der PC nach Plan schläft
  (`../betrieb/wachplan.md`).

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

Sasha klärt das bis Jahresende. **Was der Hausanschluss kostet:** während der
Bauphase **0 € nur mit 24-Monats-Vertrag**, mit Flex **599,99 €**; nach der
Bauphase mindestens **799 €**. »Kostenlos« heißt also: kostenlos gegen zwei
Jahre Bindung. Im Blick behalten, wann die Bauphase in der Straße endet.

- **Favorit bisher:** O2 Home M 150 (Telekom-Netz, 150/75 Mbit, eigene IPv4,
  PPPoE/VLAN 7). Datenblatt: normal = minimal = 150/75.
- **Flex-Angebot für die Adresse (2026-09-28):** 25 €/Monat im 1. Jahr, dann
  39,99 €; **+4,99 € Zusatzoption, nicht abwählbar** (was genau, noch
  unklar); **Erschließungspreis 599,99 €** + Anschluss 9,99 € → einmalig
  609,98 €, über 2 Jahre ca. 1.390 €.
- **Die Wahl:** **24 Monate** → Erschließung entfällt (laut mehreren Quellen),
  nur 9,99 € Anschluss; die Laufzeit beginnt erst mit der Schaltung. **Oder
  Flex** → 599,99 € Erschließung. **Versuch wert:** Telekom-Hausanschluss »ohne
  Produkt« während des Ausbaus (telekom.de/glasfaser, Adresse prüfen), danach
  Flex ohne Erschließung. Nur in Ratgebern/Community belegt, Sasha rechnet
  kaum damit, fragen kostet aber nichts.
- **Telekom direkt (Sasha angefragt, 2026-09-28):** günstigste Option 46 €/Monat,
  24 Monate → ~1.100 € über 2 Jahre. Zum Vergleich O2 Flex ~1.500 € (inkl.
  Erschließung + Zusatzoption), O2 mit 24 Monaten hochgerechnet ~910 € — dafür
  noch das echte 24-Monats-Angebot für die Adresse holen.
- Das Glasfaser-Modem (ONT, ca. 42–55 €) kauft man bei O2 selbst.
- Vergleichsstand der Anbieter: congstar 50 (30 €, 16 Mbit Upload, monatlich
  kündbar, eigene IPv4), easybell ab 39,95 €, Telekom Glasfaser 150 45,95 €
  mit 24 Monaten, 1&1 ungeeignet (DS-Lite).

## Offene Entscheidungen

- OS-Wechsel am PC ja/nein (Empfehlung: Kubuntu LTS)
- Glasfaser-Vertrag (geparkt, oben)
- Wann VLANs kommen

(Entschieden: Router = GL.iNet Flint 2 mit OpenWrt; Dummy = HDMI 4K;
Reiserouter = nein, der Mini-PC macht WireGuard selbst.)

## Quellen (recherchiert 2026-09-24 bis 09-28)

**Router & OpenWrt**
- [Geizhals: GL.iNet Flint 2](https://geizhals.de/gl-inet-flint-2-gl-mt6000-a3168078.html)
- [GL.iNet: Flint 2 Produktseite](https://www.gl-inet.com/en-us/products/gl-mt6000)
- [wu-ftpd.org: Best OpenWrt Routers (Sept. 2026)](https://www.wu-ftpd.org/best-openwrt-routers/)
- [rottenwifi: Best OpenWrt Routers 2026](https://rottenwifi.com/best-router-for-openwrt/)
- [smarthomereview: Best WireGuard Router 2026](https://smarthomereview.org/best-wireguard-router/)
- [teltarif: VPN-Router im Angebot](https://www.teltarif.de/router-reise-vpn-sicherheit-openwrt/news/105089.html)

**Glasfaser-Technik (ONT, PPPoE, VLAN 7, OpenWrt am Telekom-FTTH)**
- [GitHub: Telekom FTTH mit OpenWrt](https://gist.github.com/madduci/8b8637b922e433d617261373220be44c)
- [OpenWrt Forum: OpenWrt mit Glasfaser-Modem 2](https://forum.openwrt.org/t/openwrt-with-glasfasermodem2-telekom-glasfaser/240711)
- [Telekom hilft: OpenWrt-Router am FTTH-Anschluss](https://telekomhilft.telekom.de/conversations/festnetz-internet/wie-openwrt-router-am-ftth-anschluss-betreiben/66871c914ae73561dac32297)
- [glasfaserforum: Speedport mit O2 Glasfaser (VLAN 7)](https://www.glasfaserforum.de/forum/thread/2890-funktioniert-telekom-speedport-smart-4-mit-o2-glasfaser-vertrag-ftth-telekomnetz/)
- [O2 Community: ONT nötig im Telekom-Ausbaugebiet](https://hilfe.o2online.de/dsl-kabel-glasfaser-router-software-internet-telefonie-34/glasfaser-bei-o2-bestellt-telekom-ausbaugebiet-neues-glasfaser-modem-ont-noetig-647402)
- [O2 Community: Einrichtungslink, Modem 2 + FritzBox](https://hilfe.o2online.de/dsl-kabel-glasfaser-router-software-internet-telefonie-34/einrichtungslink-o2-glasfaser-ueber-telekom-infrastruktur-modem-2-und-fritz-box-7580-625701)
- [Geizhals: Telekom Glasfaser Modem 2b](https://geizhals.de/telekom-glasfaser-modem-2b-40824527-a3766098.html)
- [Geizhals: Telekom Glasfaser Modem 2](https://geizhals.de/telekom-glasfaser-modem-2-40823382-a2601735.html)

**Tarife & IPv4**
- [o2 Produktinformationsblatt M 100/150 Flex](https://static2.o9.de/resource/blob/1838600/5bf68aa4e7df62ef2f9feb95b2e2a0b2/o2-home-m-150-flex_20260610-download-data.pdf)
- [o2: Home M 150 Glasfaser](https://www.o2online.de/e-shop/tarif/o2-home-m-150mbits-glasfaser)
- [o2: Home Flex ohne Laufzeit](https://www.o2online.de/internet-festnetz/ohne-vertragslaufzeit/)
- [mytopdeals: o2 Home Flex Aktion](https://www.mytopdeals.net/allgemein/o2-home-flex/)
- [O2 Community: öffentliche IPv4 bei Glasfaser über Telekom](https://hilfe.o2online.de/dsl-kabel-glasfaser-router-software-internet-telefonie-34/oeffentliche-ipv4-bei-o2-home-glasfaser-ueber-telekom-665627)
- [O2 Community: Dual Stack oder DS-Lite](https://hilfe.o2online.de/dsl-kabel-glasfaser-router-software-internet-telefonie-34/o2-glasfaser-ftth-telekom-reseller-dual-stack-od-ds-lite-606997)
- [congstar-Forum: Public IP bei Glasfaser](https://forum.congstar.de/thread/71257-public-ip-bei-glasfaser-verf%C3%BCgbar-kaufbar/)
- [stadt-bremerhaven: congstar Glasfaser](https://stadt-bremerhaven.de/congstar-startet-mit-glasfaser-fuer-zuhause-das-sind-die-details/)
- [teltarif: easybell Glasfaser](https://www.teltarif.de/easybell-glasfaser-tarife-ftth/news/95497.html)
- [ComputerBase: 1&1 Glasfaser DS-Lite](https://www.computerbase.de/forum/threads/1-1-glasfaser-ds-lite-fragen.2260516/)
- [Vodafone Community: DS-Lite / IPv4](https://forum.vodafone.de/t5/Ger%C3%A4te/IPv4-IPv6-und-DS-Lite/td-p/3058741)
- [teltarif: Telekom-Glasfaser-Aktion](https://www.teltarif.de/telekom-glasfaser-internet-cashback/news/103845.html)
- [Telekom: Glasfaser 150](https://www.telekom.de/festnetz/tarife-und-optionen/internet/glasfaser-150)
- [inside-digital: Tarife im Telekom-Netz im Vergleich](https://www.inside-digital.de/kaufberatungen/deutsche-telekom-glasfaser-tarife-im-vergleich)

**Hausanschluss & Erschließung**
- [dslweb: o2 Glasfaser Kosten](https://www.dslweb.de/o2-glasfaser-kosten.php)
- [glasfaser-anschluss.de: o2 Home M Glasfaser](https://glasfaser-anschluss.de/o2-home-m-glasfaser-tarif)
- [Verbraucherzentrale: Glasfaseranschluss Abläufe](https://www.verbraucherzentrale.de/wissen/digitale-welt/fernsehen/glasfaseranschluss-das-muessen-sie-zu-ablaeufen-und-vertraegen-wissen-84389)
- [Telekom hilft: Hausanschluss ohne Tarif](https://telekomhilft.telekom.de/conversations/festnetz-internet/glasfaser-hausanschluss-ohne-tarif/67e2e35b8669ae2e987ef768)
- [Finanztip: Glasfaser-Anschluss Kosten](https://www.finanztip.de/internetanbieter/glasfaser/)
- [dealdoktor: Telekom Glasfaser kostenlos ins Haus](https://www.dealdoktor.de/magazin/kostenlos-glasfaser-telekom/)
- [kostenlupe: Glasfaseranschluss Kosten 2026](https://www.kostenlupe.de/artikel/glasfaseranschluss-kosten)

**Telekom erreichen**
- [Telekom: Kontakt Glasfaser](https://www.telekom.de/hilfe/internet-telefonie/glasfaser/kontakt?samChecked=true)
- [Telekom hilft: Hotline ohne Nummer](https://telekomhilft.telekom.de/conversations/festnetz-internet/die-service-hotline-ist-ohne-festnetznummer-nicht-erreichbar/6687e1dd4ae73561da1ea26a)
  — Bestell-Hotline Glasfaser 0800 2266100; bei der Telefon-KI »keine« sagen.

**Dummy-Stecker**
- [Amazon: FUERAN HDMI Dummy 4K](https://www.amazon.com/FUERAN-Plug-Virtual-Emulator-3840x2160-60-3840x2160/dp/B0C174243H)
- [Amazon: FUERAN HDMI Dummy 4K HDR](https://amazon.com/FUERAN-Plug%EF%BC%8CVirtual-3840x2160-HDMI-Compatible-Acceleration/dp/B0732S6KG4)
