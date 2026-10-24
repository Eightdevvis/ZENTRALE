# Etappe 1 — Heimkommen: der Bauplan

**Stand 2026-10-24: Plan.** Die Ursprungsszene des Leitbilds
([../leitbild.md](../leitbild.md), Etappe 1): *ich komme heim, zentrale
schaltet die lampe an, begrüßt mich und nimmt mir im small talk ein paar
datenpunkte ab.* Vorgaben von Sasha: **0 €** (knapp bei Kasse), **kein WLAN**
für Wohnungsdinge (das Netz ist der Handy-Hotspot — ist er weg, wäre alles
weg), **nichts an 230 V selbst bauen**. Teile: [../betrieb/bauteile.md](../betrieb/bauteile.md).

## Der Ablauf

1. Sasha tippt an der Tür mit dem **blauen Anhänger** auf den Leser.
2. Der **Tür-Knoten** meldet `tag <uid>`; der Kern macht daraus
   `HOMECOMING` (Ereignis gibt es seit 14.05.2026 in `core/events.py`) —
   nur für bekannte Anhänger.
3. **Licht:** der LED-Streifen an der Tür geht an (sofort, lokal), und im
   Wohnzimmer drückt ein **Servo den Schalter der Stehlampe**.
4. **Begrüßung** über einen Lautsprecher.
5. **Small Talk:** zwei, drei Fragen („wie war dein Tag?", „wie hast du
   geschlafen?"); die Antworten werden zu Werten in den Messreihen
   (Graphen). Sasha kann jederzeit „nicht jetzt" sagen — ZENTRALE drängt nie.

Fertig, wenn: Antippen → Licht an → Gruß → Fragen → die Antwort steht im Graphen.

## Die Hardware (alles vorhanden)

| Teil | Wo | Aus dem Bestand |
|---|---|---|
| **Tür-Knoten:** Arduino Nano + RFID-RC522 + LED-Streifen (WS2812B, 5 V) | an der Wohnungstür | Nano, RC522 + Anhänger, Streifen |
| **Lampen-Knoten:** Arduino Nano + Servo SG90 in gedruckter Halterung am Lampenschalter | Wohnzimmer | Nano, SG90, Bambu A1 |
| Kabel zum Wirt | — | USB-Kabel / altes mehradriges Kabel |

Sicherheit: die Lampe bleibt unverändert, der Servo drückt nur ihren
eigenen Schalter — **kein Eingriff in 230 V**. Der RC522 läuft an **3,3 V**
(nie 5 V). Der Streifen zieht viel Strom: bei mehr als ein paar LEDs eigenes
5-V-Netzteil, nicht über den Nano.

## Wer die Knoten trägt (offen)

Ein Nano braucht ein Gerät, das immer an ist (USB oder Serien-Kabel):

| Wirt | dafür | dagegen |
|---|---|---|
| **alter Laptop** aus dem Keller, an der Tür | immer an, USB, Lautsprecher + Mikro für Gruß und Fragen | **Stromversorgung defekt** — zuerst durchchecken |
| Pi 3B im Schlafzimmer + langes Kabel (Serien-Leitung, Spannungsteiler 5 V → 3,3 V) | läuft schon, hat Lautsprecher + Mikro | > 5 m zur Tür; Gruß käme aus dem Schlafzimmer |

Der Lampen-Knoten braucht seinen eigenen Wirt in Wohnzimmernähe — oder später
Zigbee (Steckdose), wenn Geld da ist.

## Die Software (Claude baut, Sasha lötet)

Grenze: die **Schaltungen** baut Sasha selbst (er will Elektronik lernen);
Firmware und ZENTRALE-Seite schreibt Claude, sofern Sasha es nicht selbst
will.

1. **Nano-Firmware** (Tür + Lampe): eine Zeile pro Ereignis über Seriell
   (`tag 04a1b2c3`), Befehle zurück (`licht an`, `streifen farbe 255 180 80`,
   `servo druecken`). Text-Protokoll, damit jeder Wirt es versteht.
2. **App `wohnung`** im Hub (eigener Prozess wie Tutor/Karte): liest die
   Serien-Schnittstellen, meldet Ereignisse an den Hub
   (`hub_ereignisse`), nimmt Befehle an. Bekannte Anhänger stehen in ihren
   Daten (gleichen ab).
3. **Kern:** `HOMECOMING` → Licht-Befehle → Begrüßung → Small-Talk-Runde.
4. **Stimme:** TTS läuft heute auf dem PC (schläft nach Plan) — für den Gruß
   muss eine Stimme auf dem Wirt laufen (Piper ist leicht genug) oder der PC
   geweckt werden. Entscheiden, wenn der Wirt feststeht.
5. **Datenpunkte:** Antworten → Messreihen (`graphs`), z. B. Stimmung 1–5,
   Schlaf; die Fragen sind Daten der App, nicht im Prompt.

## Reihenfolge

1. Alten Laptop durchchecken (Netzteil? Akku?) → Wirt entscheiden.
2. Tür-Knoten auf dem Breadboard: Nano + RC522 liest den Anhänger, Streifen leuchtet.
3. Firmware + App `wohnung` + `HOMECOMING` am Laptop/Mini-PC testen (Nano per USB am Schreibtisch).
4. Begrüßung + Small Talk + Graph.
5. Lampen-Knoten: Halterung drucken, Servo drückt den Schalter.
6. Einbauen an Tür und Lampe.

## Historie

- **2026-10-24** — Plan nach Sashas Werkstatt-Katalog (0 €, kein WLAN, Servo statt 230 V).
