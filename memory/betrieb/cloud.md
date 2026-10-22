# Cloud — Login, Mitte, Pakete (Cloudflare)

**Stand 2026-10-22: gebaut und lokal getestet, noch nicht ausgerollt.**
Der Vertrag steht in [../hub/knoten_beitritt.md](../hub/knoten_beitritt.md)
(„Bauplan v1"), die Routen in `cloud/openapi.yaml`, Befehle und Ablauf auf
Englisch in `cloud/README.md`.

## Was es ist

Ein Cloudflare Worker (`cloud/`, TypeScript) mit

- **D1** (SQLite): Konten, Sitzungen, Einladungscodes, Fehlversuch-Zähler,
  Kopf + Geschichte der Mitte, Knoten-Beschreibungen, Besitz.
- **R2**: die verschlüsselten Dateien der Mitte (`mitte/<konto>/<sha256>`,
  gleicher Inhalt liegt nur einmal), Pakete (`pakete/<version>.tar.gz`,
  `pakete/neueste.json`) und `install.sh`.

Der Server sieht nie Passwort, Schlüssel oder Klartext. Er speichert nur
PBKDF2-Hashes (600 000 Runden, eigenes Salz je Konto) über das, was das
Gerät aus Passwort und Notfallschlüssel ableitet.

## Die Mitte über HTTP

Dieselben vier Handgriffe wie [abgleich.md](abgleich.md), nur als Routen:
`holen` = `GET /v1/mitte` (+ einzelne Dateien), `vorbereiten` + `senden` =
EIN `POST /v1/mitte/stand` mit Compare-and-Swap auf den Kopf (sonst 409
`jemand_schneller`), `enthaelt` = „war dieser Stand je der Kopf". Jeder
Stand ist eine volle Liste Name → Datei; die Listen der letzten 10 Stände
bleiben, die Kennungen aller Stände für immer.

## Sicherheit in Kürze

- Sitzung 90 Tage, nur als Hash gespeichert, an den Gerätenamen gebunden:
  ein Gerät schreibt nur seine eigene Beschreibung.
- 5 Fehlversuche je 15 min — je Mail und je IP — bei Login und Notfall.
- Unbekannte Mail bei `vorab`: erfundene, aber feste Werte (Geheimnis
  `VORAB_GEHEIMNIS`), damit niemand Konten abfragen kann.
- Notfall gibt nur eine 15-Minuten-Sitzung, die allein das Passwort neu
  setzen darf; danach sind alle Sitzungen des Kontos weg.
- Einladungscode: verbraucht beim Konto-Anlegen, nicht beim Download.
  Gespeichert nur als Hash; Codes zeigt das Skript genau einmal.
- Jede Abfrage filtert nach Konto; ein Test prüft, dass Konto B nichts von A sieht.

## Fallen

- **Workers Paid nötig.** Ein Login kostet einen PBKDF2 mit 600 000 Runden —
  weit über den 10 ms CPU des Gratis-Plans.
- **Ein Stand darf höchstens 24 MiB groß sein** (die ganze Anfrage liegt im
  Speicher des Workers, 128 MB). Der allererste Abgleich mit allen Daten
  kann darüber liegen.
- Alte Dateien in R2 räumt noch niemand weg (kein Aufräumen nach Prüfsumme).
- Der allererste Ausrollen-Schritt braucht das Geheimnis gleich mit, weil
  es den Worker vorher nicht gibt (Weg in `cloud/README.md`).

## Tests

Laufen ganz lokal im Workers-Laufzeitsystem (Miniflare), ohne
Cloudflare-Konto: im Ordner `cloud/` die npm-Tests starten.
