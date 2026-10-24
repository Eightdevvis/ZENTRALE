# Bauteile und Geräte — was in Sashas Werkstatt liegt

**Stand 2026-10-24** (Katalog von Sasha, „nicht alles drin"). Grundlage für
die Hardware-Karte ([../leitbild.md](../leitbild.md), Etappe 2): erst
nachsehen, was da ist, dann kaufen. Sasha ist knapp bei Kasse — **0 € zuerst**.

## Für ZENTRALE besonders wichtig

| Teil | taugt für |
|---|---|
| RFID-RC522 + weiße Karte + blauer Anhänger (Arduino-Starterkit) | Heimkommen per Antippen (Etappe 1) |
| Arduino Nano ×6 (Klone, AZ-Delivery), Uno ×2 | Sensor-Knoten per USB/Kabel — **kein WLAN** |
| LED-Streifen adressierbar (vermutl. WS2812B), LED-Filamente | „Licht an" mit Kleinspannung, ohne 230 V |
| Relaismodul 1-Kanal 5 V (10 A/250 V), 2N2222 ×11, 1N4007 ×6, Optokoppler 4N35 | Schalten lernen; Treiberstufe |
| LCD 1602 + I²C, 2,4" TFT-Touch, 7-Segment, LED-Matrix | kleine Anzeige an der Tür |
| DHT11, LDR ×5, Neigungsschalter, IR-Empfänger + Fernbedienung | Raum-Sinne (Temperatur, Licht, …) |
| Buzzer ×9 | Ton ohne Pi |
| RTC DS1302, Adafruit PiRTC PCF8523 (Buchse nicht angelötet) | Uhr für Pi/Arduino ohne Netz |
| HP-Drucker mit Scanner | Szenen „Drucker gehört ihr" |
| Bambu Lab A1 | Gehäuse für Knoten drucken |
| **Keller:** alter Laptop (≥1), alte Handys (3–4), Elektroschrott | kostenlose Knoten: Laptop an der Tür, Handys als Mikro/Kamera/Bildschirm je Raum |

## Vollständiger Katalog

**Mikrocontroller:** Arduino Uno R3 original ×1, Uno R3 Klon (ATmega328P-PU
DIP) ×1, Nano Klon rot (Micro-USB, Pins gelötet) ×1, Nano AZ-Delivery blau
(Mini-USB, Pins gelötet) ×1, Nano Klon USB-C schwarz (Pins lose) ×4.

**Displays:** LCD 1602 ×1, I²C-Adapter HW-61 (PCF8574) ×1, 2,4" TFT-Touch (SPI)
×1, 7-Segment 1-stellig ×3, 4-stellig ×2 (eine SH5461AS), LED-Matrix 8×8 rot ×2.

**Licht:** flexible LED-Filamente (Neon-Effekt) mehrere; LED-Streifen
adressierbar (vermutl. WS2812B) 1 Rolle.

**Sensoren:** DHT11 ×1, Wasserstand HW-038 ×1, Neigungsschalter SW-520D ×4,
NTC (vermutl. 10 kΩ) ×1, LDR ca. 5, IR-Empfänger (vermutl. VS1838B) ×1;
RFID-RC522 mit Karte und Anhänger.

**Eingabe:** 4×4-Tastenmatrix, Joystick, Taster 6×6 ca. 15, 12×12 ca. 10,
Mini-Kippschalter ca. 10, Drehpoti ×2, Daumenrad-Poti ×1, IR-Fernbedienung.

**Motoren:** 28BYJ-48 + ULN2003, SG90 ×5, Vibrationsmotor ×2. **Ton:** Buzzer ca. 9.

**Strom:** MB102-Breadboard-Netzteil (3,3/5 V), 9-V-Clip, Batterien gemischt
(viele leer), INIU USB-C-Netzteil (bis 20 V, für den Mini-PC).

**Module/ICs:** RTC DS1302, PiRTC PCF8523, Relais 1-Kanal 5 V, 74HC595 ×3, 4N35 ×1.

**Passive/Halbleiter:** Widerstands-Sortiment (25 Werte, 1000 St.), Elkos
100 µF/50 V ×5 und 10 µF/50 V ×5, Keramik 22 pF/100 nF ca. 20, 2N2222 ca. 11,
1N4007 ca. 6, Brückengleichrichter B80C1500.

**Draht:** Kupferlackdraht 0,2 mm (2×100 m), 0,08 mm, 0,06 mm; Schaltdraht,
Litze, Schaltlitze 0,14 mm² 25 m, Dupont-Kabel, Drahtbrücken, Breadboards.

**Zubehör/Werkzeug:** Stift-/Buchsenleisten, Schrumpfschlauch, Lötzinn,
Kupferklebeband, Isolierband, Nylonschnur; Glasfaser-Pigtails FC/APC ×5;
Lötkolben, Multimeter (nur U + R), Abisolierzange, Isopropanol,
Werkzeugkoffer, Akkuschrauber, Schleifgerät, Feilen, Goldschmiede-Werkzeug,
Heißkleber, Bunsenbrenner; Gasmaske, Nitrilhandschuhe.

**Maschinen/Geräte:** Bambu Lab A1, HP-Drucker mit Scanner, Nähmaschine;
Desktop-PC, Laptop, Tablet, Bigme-Handy, MeLE Mini-PC, XREAL Air 2 Pro,
Tastaturen, Powerbank; Plasmakugel; Kabel gemischt.

**Schlafzimmer (fest):** Raspberry Pi 3B, Monitor, Lüfter, kleiner
Lautsprecher, kleines Mikro.

**Keller:** alte Laptops (≥1), alte Handys (3–4), Elektroschrott.

## Historie

- **2026-10-24** — angelegt aus Sashas Katalog.
