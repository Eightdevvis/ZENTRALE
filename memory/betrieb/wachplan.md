# Wachplan: wann der PC wach ist, wer ihn weckt

**Stand 2026-09-28 — Entscheidung, noch nicht gebaut.** Der PC ist das
**Gehirn** (GPU, Modelle, Daten), alle anderen Geräte sind Knoten
(Zielbild: `../system/heimnetz.md`). Er läuft **nicht** dauerhaft: schlafen
kostet ~1–3 W statt 50–80 W, und aufwecken geht mit dem eigenen Router auch von
draußen. (Bis dahin — Stand 2026-09-24 — lief er dauerhaft.)

## Entscheidung (Sasha, 2026-09-28)

| Lage | PC | Pi |
|---|---|---|
| **feste Schlafenszeit** (nachts) | schläft (Suspend) | aus / schläft |
| Sasha **geht raus** | schläft ein, sobald der Pi weg ist | Sasha schaltet ihn **von Hand aus** |
| Sasha **daheim** | wach | an (Wandbild, Tutor) |
| **von draußen** gebraucht (SSH, Moonlight) | per VPN → Router → Magic-Packet wecken | bleibt aus |
| **Heimkommen angekündigt** / **eingetragene Weckzeit** | wird rechtzeitig vorher geweckt | wird mit hochgefahren |

**Reihenfolge:** erst das Heimnetz grob aufstellen (`../system/heimnetz.md`),
dann dieser Wachplan, dann der Schlüssel (unten).

## Was dafür zu bauen ist

- [ ] **Feste Schlafenszeit PC:** Suspend zur Uhrzeit, Wecken morgens
      (Weckzeit im PC selbst oder Magic-Packet von Router/Pi).
- [ ] **Feste Schlafenszeit Pi:** aus bzw. Bildschirm/Kiosk aus zur Uhrzeit.
- [ ] **»Pi weg → PC schläft«:** Der PC merkt, dass der Pi nicht mehr da ist.
      Das Backend sieht das schon heute: Die Pi-Telemetrie kommt alle ~30 s und
      gilt nach >90 s als veraltet (`../system/topologie.md`). Er schläft aber
      **nur, wenn gerade niemand von draußen dran ist** (keine SSH-, keine
      Moonlight-Sitzung). Die beiden Bedingungen sind unabhängig: Der Pi steht
      für »Sasha ist daheim«, SSH/Moonlight für »Sasha arbeitet gerade von woanders«.
- [ ] **Wecken:** Router (OpenWrt-Paket für Wake-on-LAN) schickt das
      Magic-Packet; von draußen erst VPN, dann über den Router. Der Pi-Wecker
      (`deployment.md` → Wake-on-LAN) bleibt als Reserve.
- [ ] **Pi an → PC wach:** Schaltet Sasha den Pi daheim ein, weckt der Pi den
      PC (gibt es schon: `zentrale-wake-pc.service`).

## Hochfahren vor dem Heimkommen

Zentrale soll **schon laufen, wenn Sasha zur Tür reinkommt**, statt erst dann
hochzufahren. Zwei Wege, die sich ergänzen:

- [ ] **Ankündigen von draußen:** Ist Sasha von draußen verbunden (VPN, z.B.
      Laptop, Mini-PC, später Handy), sagt er ZENTRALE, wann er heim ist
      (»bin um 18:30 da«). Zentrale merkt sich die Zeit und fährt rechtzeitig
      vorher hoch (PC wecken, Pi an), damit Wandbild und Tutor bereitstehen.
      Wo die Ankündigung landet, ist noch offen. Naheliegend: im Backend, das
      der PC ja schon ist, solange er gerade wach ist.
- [ ] **Eingetragene Zeiten:** feste Weckzeiten (z.B. werktags 17:30), zu denen
      ZENTRALE von selbst hochfährt, ohne Ansage. Verwandt mit der festen
      Schlafenszeit oben; zusammen ergeben sie den Tagesplan.
- **Der Knackpunkt:** Wer weckt zur gemerkten Zeit, wenn der PC schläft? Der PC
  kann sich selbst eine Weckzeit stellen, bevor er einschläft. Alternativ
  weckt ihn der Router, der immer läuft. Den Pi schaltet dann der PC (oder der
  spätere Schlüssel) wieder ein. Das ist beim Bauen zu klären.

## Später: Schlüssel für »ich bin daheim«

Eine Chipkarte oder ein Schlüsselanhänger (RFID/NFC; Leser am Arduino oder
direkt am Pi) aktiviert ZENTRALE: Pi an, PC wecken. Umgekehrt beim Gehen: alles
schläft. Das ersetzt das Pi-von-Hand-Ausschalten. **Erst nach dem
Heimnetz-Setup.**

## Fakten, die bleiben

- **SSH weckt den PC NICHT.** Geprüft 2026-09-14: Die LAN-Karte steht auf `magic`
  (nur Magic-Packet), der WLAN-USB-Stick hat Wake-on-WLAN aus. Ein schlafender
  PC ist per SSH schlicht nicht da. Geweckt wird nur per Magic-Packet über LAN,
  also muss der PC am LAN-Kabel hängen.
- **Nach Suspend gibt es keinen LUKS-Prompt**, der RAM bleibt erhalten.
  Dropbear-Unlock (`auto_unlock.md`) braucht es nur nach **echtem Aus**
  (Stromausfall, Reboot).
- Der Auslöser für automatisches Einschlafen war `cosmic-idle` (COSMIC,
  Energie-Einstellungen). Er ist aus, gewollt ist Einschlafen nur nach den
  Regeln oben, nicht nach Tastatur-Leerlauf. Kommt ein anderes OS drauf: dort
  ebenso.
