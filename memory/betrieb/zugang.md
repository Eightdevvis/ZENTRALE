# Zugang — der Schlüssel fürs Backend

**Stand 2026-10-08.** Das Backend (Flask, Port 5000) lauscht im ganzen Netz.
Bis heute konnte jeder im WLAN Chat, Kalender, Gedächtnis und Mail lesen und
schreiben. Jetzt steht eine Tür davor:

- **Von diesem Rechner aus** (die TUI am PC, die TUI am Laptop, der
  SSH-Tunnel vom Laptop zum PC) geht alles wie bisher — kein Schlüssel nötig.
- **Von einem anderen Gerät** (heute: der Pi an der Wand) braucht es den
  **Zugangsschlüssel**. Die Programme schicken ihn von selbst mit, sobald er
  auf dem Gerät liegt.

Code: `core/zugang.py` (Schlüssel), `ui/routen/zugang.py` (die Tür vor allen
Routen), `scripts/zugang.py` (der Befehl), Klienten:
`tui/ansichten/zugang_klient.py` (TUI; das Zimmer lädt dieselbe Datei über
`tutor/room_zugang.py`), `scripts/pi_sensor_bridge.py`, die Devtools.
Tests: `tests/test_zugang.py`.

## Die drei Stellungen

Die Einstellung `zugang`:

| Stellung | Was passiert |
|---|---|
| `aus` | Keine Prüfung, wie früher. |
| `melden` | **Vorgabe.** Alle kommen rein; wer ohne passenden Schlüssel kommt, steht im Log („ZUGANG: … durchgelassen"). |
| `an` | Ohne Schlüssel kein Zugang von anderen Geräten. Dieser Rechner bleibt frei. |

**Warum „melden" als Vorgabe:** der Pi braucht den Schlüssel, und den kann
nur Sasha dort ablegen. Mit „an" stünde die Wand sonst schwarz da. Erst wenn
das Log ein paar Tage lang still ist (niemand kommt mehr ohne Schlüssel),
auf „an" stellen.

Ein Tippfehler in der Einstellung zählt als „an" — der Rechner selbst bleibt
ja immer frei, aussperren kann man sich so nicht.

## Der Schlüssel

Eine Zeile aus 43 Zeichen, zufällig erzeugt. **Ein Schlüssel für alle
Rechner** (wie beim Abgleich): der Pi spricht das PC-Backend an, das Laptop
später vielleicht auch. Er liegt auf jedem Gerät in
`~/.config/zentrale/zugang.schluessel`, nur für Sasha lesbar — **nie in
`data/`, nie im Repo, nie im Abgleich** (die Mitte und der alte rsync-Weg
sehen den Ordner gar nicht). Als Sicherung in KeePass.

Anders als beim Abgleich-Schlüssel ist ein Verlust harmlos: einfach einen
neuen anlegen und auf die Geräte bringen. Es geht nichts verloren.

### Der Befehl

`scripts/zugang.py` mit dem venv-Python. Was die Zusätze tun:

| Zusatz | Wirkung |
|---|---|
| (keiner) / `status` | Stellung der Tür, ob ein Schlüssel da ist, wer zuletzt ohne kam |
| `anlegen` | neuen Schlüssel anlegen (weigert sich, wenn schon einer da ist) |
| `erneuern` | neuen statt des alten (fragt nach); alle Geräte brauchen ihn dann neu, alte Browser-Kekse gelten nicht mehr |
| `zeigen` | die Zeile ausgeben — für KeePass |
| `eingeben` | Zeile aus KeePass auf diesem Gerät ablegen (wird beim Tippen nicht angezeigt) |
| `link` + Adresse | Browser-Link, 10 Minuten gültig (unten) |
| `modus aus` / `melden` / `an` | die Tür umschalten; läuft ZENTRALE, sofort, sonst ab dem nächsten Start |

## Einrichten (einmal)

1. **Am PC** (dort läuft das Backend, das der Pi anspricht): den Befehl mit
   `anlegen` aufrufen, dann mit `zeigen`.
2. **In KeePass** einen Eintrag „ZENTRALE Zugang" anlegen, die Zeile ins
   Passwort-Feld. Zwischenablage danach leeren.
3. **Auf dem Laptop:** den Befehl mit `eingeben` aufrufen und die Zeile aus
   KeePass einfügen. (Nötig erst, wenn das Laptop ein fremdes Backend direkt
   anspricht — über den SSH-Tunnel ist es ohnehin „von diesem Rechner".)
4. **Auf dem Pi** — dort gibt es den Befehl nicht (kein venv, kein core/).
   Die Zeile muss als Datei hin:
   - für die **TUI und das Zimmer**: in den Home-Ordner des Benutzers, der
     an der Wand angemeldet ist, unter `.config/zentrale/zugang.schluessel`.
     Rechte so, dass nur dieser Benutzer lesen und schreiben darf.
   - für die **Sensor-Bridge**: die läuft als Dienst unter root. Entweder
     dieselbe Datei auch in roots Home-Ordner legen, oder in ihrer
     Einstellungsdatei (`/etc/zentrale-bridge.env`) die Variable
     `ZENTRALE_ZUGANG_SCHLUESSEL` auf den Pfad der Datei oben setzen.
   - Zum Hinbringen: per SSH vom Laptop/PC aus eine Datei anlegen und die
     Zeile hineinschreiben — **ohne** dass die Zeile in der Befehls-Historie
     landet (also nicht als Teil eines Befehls tippen, sondern in einen
     Editor oder eine Eingabe einfügen). ⚠ Kein Zeilenumbruch-Müll und keine
     Leerzeichen davor: die Zeile muss genau so drinstehen.
5. Ein paar Tage **beobachten**: der Befehl ohne Zusatz zeigt, wer ohne
   Schlüssel kam. Kommt nichts mehr (vor allem nicht von `192.168.50.10`,
   dem Pi): auf `an` stellen.

## Das Handy

Die Handy-App (ZEN-MOBILE, [../system/zen_mobile.md](../system/zen_mobile.md))
spricht das Backend **gar nicht** an — sie ruft die KI selbst auf und gleicht
über die Mitte ab. Sie braucht den Zugangsschlüssel heute nicht und merkt
von der Tür nichts. Wenn sie später einmal ein Backend direkt fragen soll:
die Zeile aus KeePass in den sicheren Speicher der App, mitschicken als Kopf
`Authorization: Bearer <zeile>` (siehe API-Doku).

Will man eine Seite des Backends im **Handy-Browser** öffnen (z. B. ein
Dokument aus der Ablage): am PC den Befehl mit `link` und der Adresse
aufrufen, den Link aufs Handy bringen und dort öffnen. Er gilt 10 Minuten;
der Browser merkt sich den Zugang danach 30 Tage (als Keks). Im Link steht
nicht der Schlüssel selbst, sondern eine kurzlebige Marke — er ist nach 10
Minuten wertlos und landet nicht dauerhaft im Verlauf (die Seite leitet
sofort auf die Adresse ohne Marke um).

## Was frei bleibt (bewusst)

- **Alles von diesem Rechner** — erkannt an der Adresse (127.0.0.1/::1)
  **und** daran, dass die Anfrage an „localhost" ging. Sonst könnte eine
  Webseite im eigenen Browser über einen umgebogenen Namen (DNS-Rebinding)
  als „lokal" durchkommen.
- **Das Code-Paket des Pi** (`/api/aussenposten/manifest` und `/paket`):
  nur Code aus dem Repo, keine Daten. Wäre es gesperrt, käme ein Pi ohne
  Schlüssel nie an die Fassung, die den Schlüssel mitschickt.
- **Die Morgenblick-Knöpfe** gehen weiterhin **nur** auf dem Rechner selbst
  — auch mit Schlüssel nicht von draußen (eigene, strengere Prüfung).
- **Die Tür umschalten** (`/api/zugang`) geht nur vom Rechner selbst — ein
  abgegriffener Schlüssel darf sie nicht abschalten.

## Grenzen

- Das LAN spricht **unverschlüsseltes HTTP**. Wer im selben Netz mitlauscht,
  kann den Schlüssel sehen. Gegen den neugierigen Gast im WLAN hilft die
  Tür, gegen einen Lauscher im Netz nicht — dafür bräuchte es HTTPS oder
  das VPN aus [../system/heimnetz.md](../system/heimnetz.md).
- `find-pc` (Laptop, `~/.local/bin`, nicht im Repo) erkennt den PC als
  Notlösung an der Antwort von `/api/state`. Mit „an" bekommt es dort eine
  Abweisung und findet ihn auf diesem Weg nicht mehr (der normale Weg über
  die MAC-Adresse bleibt).
- Der Weck-Test `scripts/wake_pc.sh` fragt `/` ab — das gibt es seit dem
  Abschied von der Browser-Front nicht mehr; die Tür ändert daran nichts.
