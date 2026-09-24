# Wachplan: wann der PC wach ist, wer ihn weckt

**Stand 2026-09-24:** Der PC läuft **dauerhaft** — tags, nachts, wenn Sasha
unterwegs ist. Er ist das **Gehirn**: dort stehen GPU, Modelle und Daten, alle
anderen Geräte sind Knoten, die sich von außen dranhängen
(Zielbild: `../system/heimnetz.md`). Der Suspend-Plan vom 2026-09-14 (daheim
an, nachts/unterwegs schlafen, WoL vom Pi) ist damit abgelöst.

## Jetzt

| Lage | PC |
|---|---|
| immer | **an.** KI und Backend jederzeit erreichbar, kein Einschlafen. |

Der Auslöser des Einschlafens war `cosmic-idle` mit COSMIC-Defaults — in den
COSMIC-Einstellungen unter Energie ist der automatische Suspend am Netzteil
aus. (Kommt ein anderes OS drauf: dort genauso abschalten.)

## Was als Reserve bleibt

- **Dropbear-Unlock** (`auto_unlock.md`) — nach **echtem Aus** (Stromausfall,
  Reboot) wartet der PC auf die LUKS-Passphrase. Dauerbetrieb macht das zum
  wichtigsten Rettungsweg.
- **Wake-on-LAN vom Pi** (`deployment.md` → Wake-on-LAN) — fertig gebaut, im
  Dauerbetrieb nur noch Reserve, falls der PC doch mal schläft.
- **SSH weckt den PC NICHT.** Geprüft 2026-09-14: LAN-Karte steht auf `magic`
  (nur Magic-Packet), der WLAN-USB-Stick hat Wake-on-WLAN aus. Ein schlafender
  PC ist per SSH schlicht nicht da.

## Router

Kommt mit dem Heimnetz-Umbau: Adressen, VPN von draußen und Übergang
stehen in `../system/heimnetz.md`.
