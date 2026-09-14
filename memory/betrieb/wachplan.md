# Wachplan: wann der PC wach ist, wer ihn weckt

**Stand 2026-09-14** (ersetzt den „Always-on"-Plan vom selben Tag — 24/7
durchlaufen ist nicht nötig, siehe unten). Der PC ist der **Kern zuhause**:
dort steht die Hardware (GPU, Modelle, Daten), von dort kommt alles, was Pi
und Laptop anzeigen.

## Jetzt

| Lage | PC | Wer entscheidet |
|---|---|---|
| Sasha **daheim** | **durchgehend an.** KI immer verfügbar, der Tutor kann jederzeit anquatschen. | vorerst: Auto-Suspend am PC ist einfach aus |
| **nachts** | schläft mit Sasha (Suspend-to-RAM). | vorerst manuell; später Pi-gesteuert |
| Sasha **unterwegs** | darf schlafen (Suspend, ~1–3 W statt 50–80 W). | — |

**Wecken von unterwegs = über den Pi** („Satelliten-Umweg": Pi erreichen →
Pi schickt Magic-Packet → PC wach → SSH rein). Etwas umständlich, aber es
geht, und es ist fertig gebaut (`deployment.md` → Wake-on-LAN).

**SSH weckt den PC NICHT.** Geprüft 2026-09-14: LAN-Karte steht auf
`magic` (nur Magic-Packet), der WLAN-USB-Stick hat Wake-on-WLAN aus und
verliert im Suspend ohnehin die Hotspot-Verbindung. Ein schlafender PC ist
per SSH schlicht nicht da. Was sich früher wie „SSH hat ihn geweckt"
anfühlte, war ein wacher PC.

**Dropbear-Unlock** (`auto_unlock.md`) braucht es nur nach **echtem Aus**
(Stromausfall, Reboot, bewusst abgeschaltet) — nach Suspend gibt es keinen
LUKS-Prompt, der RAM bleibt.

**Erster Schritt (Prio 1, Pi↔PC-Pipe):** den Auslöser des Einschlafens
abstellen. Das ist `cosmic-idle` mit COSMIC-Defaults
(`~/.config/cosmic/com.system76.CosmicIdle/` ist leer) → in den
COSMIC-Einstellungen unter Energie den automatischen Suspend am Netzteil
ausschalten. logind hat keine Idle-Aktion, Sleep-Targets sind nicht maskiert
— mehr ist nicht dran.

## Später: Router (kommt so oder so)

PC und Pi hängen dann per **Ethernet an einem richtigen Router**, Internet
läuft über den Router statt über den Handy-Hotspot. Das ändert:

- **Adressen:** heute definieren PC/Pi `192.168.50.x` selbst am dummen Switch.
  Mit Router vergibt der — feste IPs als DHCP-Reservierung neu planen,
  `../system/topologie.md` neu schreiben.
- **WAN-Zugang zum PC:** Port-Forward + DynDNS **oder** VPN-Tunnel — nicht
  entschieden.
- **Wecken, zwei Optionen** (offen, welche):
  1. **Pi als Wecker** (wie jetzt) — fertig, keine Spontan-Wecker.
  2. **Wake-on-any auf der LAN-Karte** (`u` unicast **plus** `a` ARP — der
     Router muss den schlafenden PC erst per ARP-Broadcast wiederfinden).
     Dann weckt SSH direkt. Kosten: Treiber-Support (`r8169`) mit Root prüfen;
     **der Pi weckt ihn sonst dauernd** (pollt jede Sekunde, sein ARP läuft
     aus → Broadcast → PC wach) → Pi muss sich zurückhalten, wenn der PC
     schläft; jedes scannende Gerät im Netz (Handy, Router-App) weckt ihn
     ebenfalls.

**Reihenfolge, verbindlich:** die Pipe von draußen zum PC kommt **1.** erst
wenn der Router da ist, **2.** erst nachdem der Sprach-Tutor läuft
(`../ueberblick.md` → Prioritäten). Bis dahin: daheim an, nachts schlafen,
unterwegs Pi-Umweg.
