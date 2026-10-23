# Cloud — Login, Mitte, Pakete (Cloudflare)

**Stand 2026-10-23: online** unter `https://zentrale-cloud.sevendevs.workers.dev`
(Cloudflare-Konto sevendevs@outlook.com, Workers Free, R2 seit 23.10.
freigeschaltet). D1 `zentrale` + R2 `zentrale` angelegt, Migration `0001`
remote, Paket 36 + `install.sh` hochgeladen, ein Einladungscode für Sasha.
Probe von außen: Paket ohne Code 401, falscher Code 403. Eingetragen in
`core/cloud_api.py` (`VORGABE`; `deploy/install.sh` bekommt sie beim Rendern).
Seit 23.10. ist die Cloud nur Konten + Abgleich, nicht die Programmquelle —
Pakete heute noch hier, später öffentlich: [verteilung.md](verteilung.md).
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
HMAC-SHA256 (Schlüssel = 32 zufällige Bytes je Konto) über das, was das Gerät
aus Passwort und Notfallschlüssel ableitet. Kein langsamer Hash auf dem
Server: das Gerät rechnet schon Argon2id mit 64 MiB, und ein abgeleiteter
256-Bit-Schlüssel lässt sich nicht durchprobieren. Deshalb reicht der
**Gratis-Plan** (10 ms CPU je Anfrage).

## Die Mitte über HTTP

Dieselben vier Handgriffe wie [abgleich.md](abgleich.md), nur als Routen:
`holen` = `GET /v1/mitte` (+ einzelne Dateien), `enthaelt` = „war dieser
Stand je der Kopf". `vorbereiten` + `senden` = drei Schritte, damit keine
Anfrage riesig wird:

1. **fehlende** fragen: welche Dateien (nach Prüfsumme) hat der Server noch nicht?
2. jede fehlende einzeln als **Blob** hochladen (bis 24 MiB; der Server prüft
   die Prüfsumme, sonst 400 `pruefsumme`),
3. **Stand** senden: nur Verweise Name → Prüfsumme, Kleines (zusammen bis
   256 KiB) darf direkt mit. Compare-and-Swap auf den Kopf, sonst 409
   `jemand_schneller`; fehlt ein verwiesener Blob → 400 `blob_fehlt`. Jeder
Stand ist eine volle Liste Name → Datei; die Listen der letzten 10 Stände
bleiben, die Kennungen aller Stände für immer.

## Sicherheit in Kürze

- Sitzung 90 Tage, nur als Hash gespeichert, an den Gerätenamen gebunden:
  ein Gerät schreibt nur seine eigene Beschreibung.
- Passwort ändern braucht das alte (gedrosselt wie ein Login); nur die
  Notfall-Sitzung kommt ohne aus.
- 5 Fehlversuche je 15 min — je Mail und je IP — bei Login und Notfall.
- Unbekannte Mail bei `vorab`: erfundene, aber feste Werte (Geheimnis
  `VORAB_GEHEIMNIS`), damit niemand Konten abfragen kann.
- Notfall gibt nur eine 15-Minuten-Sitzung, die allein das Passwort neu
  setzen darf; danach sind alle Sitzungen des Kontos weg.
- Einladungscode: verbraucht beim Konto-Anlegen, nicht beim Download.
  Gespeichert nur als Hash; Codes zeigt das Skript genau einmal.
- Jede Abfrage filtert nach Konto; ein Test prüft, dass Konto B nichts von A sieht.

## Gratis-Grenzen im Blick (seit 23.10.)

Sashas Wunsch: ein Prüfer, wo wir an der Grenze stehen, Warnung bei 50, 80
und 95 %. Nur **R2** kostet über dem Gratis-Kontingent Geld; Workers und D1
hören einfach auf (bis 00:00 UTC).

Die Grenzen stehen an **einer** Stelle, `cloud/src/grenzen.ts` (geprüft
23.10.2026 in der Cloudflare-Doku, GB = 10⁹ Byte, weil die Doku es nicht sagt
und das die kleinere Zahl ist):

| Grenze | Gratis | Zeitraum | Quelle |
|---|---|---|---|
| Worker-Anfragen | 100 000 | Tag (UTC) | developers.cloudflare.com/workers/platform/limits/ |
| D1 Zeilen gelesen | 5 Mio. | Tag (UTC) | developers.cloudflare.com/d1/platform/pricing/ |
| D1 Zeilen geschrieben | 100 000 | Tag (UTC) | ebd. |
| D1 Datenbank-Größe | 500 MB je Datenbank (Konto gesamt 5 GB) | jetzt | developers.cloudflare.com/d1/platform/limits/ |
| R2 Speicher | 10 GB-Monat | jetzt (aktueller Stand) | developers.cloudflare.com/r2/pricing/ |
| R2 Klasse A (put, list, multipart) | 1 Mio. | Monat | ebd. |
| R2 Klasse B (get, head) | 10 Mio. | Monat | ebd. |

**Selbst gezählt** (`cloud/src/nutzung.ts`, Tabellen aus Migration `0002`):
jede Anfrage läuft gegen ein zählendes D1/R2; D1-Zeilen aus `meta`, R2 je
Aufruf, gespeicherte Bytes genau bei put/delete. Danach **ein** Upsert in die
Tageszeile (`ctx.waitUntil`, Fehler nur ins Log). Der Zähler kostet selbst
eine D1-Schreibzeile je Anfrage — bei 100 000 Anfragen am Tag wäre das das
ganze D1-Schreib-Kontingent; die 50-%-Warnung kommt lange vorher. CPU lokal
gemessen: ~5 µs je Anfrage.
Täglicher Cron (03:17 UTC) zählt R2 aus einer Liste nach (fängt auch Pakete,
die `wrangler` am Worker vorbei hochlädt). Monat = Kalendermonat UTC; der
Abrechnungsmonat bei Cloudflare kann verschoben sein.

**Wahrheit von Cloudflare (freiwillig):** Secret `CF_ANALYTICS_TOKEN` + Var
`CF_ACCOUNT_ID` → der stündliche Cron (:47) fragt die GraphQL Analytics API
(kontoweit) und speichert die Zahlen; der Bericht nimmt die größere Zahl und
zeigt beide. Token anlegen: Cloudflare-Dashboard → Konto-API-Tokens →
eigenes Token → Rechte **Account → Account Analytics → Read** (sonst nichts),
nur dieses Konto. Dann das Token als Secret beim Worker hinterlegen und die
Konto-ID (steht im Dashboard rechts in der Übersicht) in `wrangler.jsonc`
unter `vars` eintragen und ausrollen. Ohne Token läuft alles mit
Selbstzählung.

**Anschauen:** `zentrale cloud usage` (Balken je Grenze, Farbe nach Stufe,
Zeitraum, Quelle). Nur Konten aus der Var `BETREIBER_MAILS`
(`jenny_wolff@hotmail.com`); andere bekommen 403 bzw. einen höflichen Satz.
`zentrale status` und der Start von `zentrale` zeigen **eine** Zeile, sobald
eine Grenze ≥ 50 % steht. Die Antwort liegt 1 h in
`~/.local/state/zentrale/nutzung.json` (auch „kein Betreiber" 24 h und
„nicht erreichbar" 1 h) — der Start wartet höchstens 1,5 s, nie ein Fehler.

**Bremse:** käme R2 über 100 % des Gratis-Speichers, lehnen Blob-Upload und
Inline-Dateien mit 507 `speicher_voll` ab; das Paket-Skript genauso (außer
mit `--ohne-bremse`). Aus: Var `BREMSE_SPEICHER` auf `aus`.

## Fallen

- **CPU-Grenze 10 ms.** Lokal gemessen (langsamer Laptop): Login 0,04 ms,
  Stand mit 1 100 Verweisen (≈ Sashas ganzer erster Abgleich) 5 ms, mit
  2 000 knapp 8 ms. Viel mehr neue Namen auf einmal gingen darüber.
- Alte Dateien in R2 räumt noch niemand weg (kein Aufräumen nach Prüfsumme) —
  der Speicher wächst also nur; die Bremse hält ihn unter 10 GB.
- Der allererste Ausrollen-Schritt braucht das Geheimnis gleich mit, weil
  es den Worker vorher nicht gibt (Weg in `cloud/README.md`).

## Tests

Laufen ganz lokal im Workers-Laufzeitsystem (Miniflare), ohne
Cloudflare-Konto: im Ordner `cloud/` die npm-Tests starten.
