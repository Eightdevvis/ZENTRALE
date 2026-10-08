# Morgenblick

Stand 2026-10-08. Ein ruhiger Blick auf den Tag als HTML-Seite — nach dem
Vorbild von Claudes „morning", in ZENTRALEs eigener Form. **Nur auf Abruf:**
`/morning` im KI-Chat (englischer Befehl wie die anderen). Kein Zeitplan,
kein Anstoß von selbst.

## Was man sieht

- **Oberes Band:** Datumszeile („Donnerstag · 8. Oktober 2026"), eine
  Überschrift in Fraunces 600 (das eine Besondere des Tages ODER seine
  Form, nie beides), darunter das **Gelände**: eine Linie von Rand zu Rand,
  Höhe = Last, Termin-Punkte darauf, darunter **drei Akte** (Vormittag bis
  12, Nachmittag bis 17, Abend) mit fetter Zeitspanne und einem Satz.
- **Unteres Band:** „Braucht dich" und „Erledigt" (fetter Titel ≤ 10
  Wörter, ein Satz mit der Quelle in Prosa, graue Ziffern). Beide leer →
  „Heute Morgen braucht dich nichts."
- **Knöpfe** (Ton-Fläche) unter einem Eintrag von „Braucht dich": legen ein
  neues Gespräch mit einem Arbeitsauftrag an (unten).
- Unter 640 px stapeln sich die Akte, die Überschrift wird 30 px.

## Wie es entsteht

| Schritt | Wo | Was |
|---|---|---|
| Sammeln | `core/morgenblick_daten.py` (Schicht 2) | jede Quelle ein **Sammler** in `SAMMLER`, nur lesen, kein Netz |
| Form | ebenda | `tagesform()`: **HEAVY** ab 5 h Terminen (Überschneidung einmal gezählt) oder 3 Termine mit ≤ 30 min Luft dazwischen · **OPEN** kein Termin oder einer ≤ 60 min · sonst **NORMAL**. Ganztägiges zählt nicht, Ausfall/abgeschaltet fällt weg. `akte()`: Termin gehört zum Akt, in dem er beginnt |
| Sätze | `core/morgenblick.py` (Schicht 3) | das **billige Modell** (`core/billig.py`) bekommt die Daten in `<daten>…</daten>` und liefert JSON; `pruefen()` kürzt und verwirft, was nicht passt |
| Seite | `core/morgenblick_bild.py` (Schicht 2) | HTML **aus Python**, nie von der KI; alles durch `html.escape` |
| Ablage | `core/ablage.py` | Art `html`, Herkunft `morgenblick`, Titel „Morgenblick 8. Oktober" |
| Öffnen | `tui/ansichten/chat_morgenblick.py` | `xdg-open <backend>/api/ablage/<id>/roh` — nur mit grafischer Sitzung |

### Die Quellen

| Sammler | Liest | Bemerkung |
|---|---|---|
| `kalender` | `kalender.entries_in_range` (Fassade) heute + morgen | Kollisionen selbst gerechnet, Kalender-Dateien unangetastet |
| `mail` | `mail.recent` / `review_stack` = `data/mail_state.json` | **kein IMAP**. Ungelesen der letzten 2 Tage je Kategorie, unbekannte Absender, einsortiert in 24 h |
| `erinnerungen` | Gespräch „Erinnerungen", Antworten der letzten 24 h | legt es **nicht** an, wenn es fehlt |
| `gespraeche` | `gespraeche.liste()` | ungelesene Antworten, aktiv in 24 h |
| `listen` | `lists.week_items()`, `get_focus()` | Wochenvorrat offen, Fokus-Projekt |
| `projekte` | `projekte.liste()` + Gespräche | aktiv in 24 h |
| `ablage` | `ablage.liste()` | neu in 24 h (ohne frühere Morgenblicke) |

Ein Sammler, der wirft, kostet nur seine Quelle (`{"fehler": …}`).
**Eine neue Quelle ist ein Eintrag:** `@sammler("name")` über einer Funktion
`(heute, jetzt) -> dict` — sonst ändert sich nichts.

## Warum das billige Modell

Die Arbeit ist Auswählen und Umformulieren aus vorsortierten Daten, kein
Denken. Form und Zeitspannen rechnet Python; die KI schreibt nur Sätze. Ein
Morgenblick kostet so Zehntelcent statt mehrerer Cent beim Gesprächsmodell.
Gebucht wird wie jeder billige Aufruf (`MORGENBLICK ←` im Log). Alternative
wäre das Gesprächsmodell — nachrüsten, falls Sasha die Sätze zu flach findet.

**Ohne Cloud** (aus, kein Schlüssel, Budget erreicht, Fehler, kein JSON)
gibt es feste Sätze aus denselben Daten (`rueckfall()`); die TUI sagt dann
„ohne KI zusammengestellt".

## Daten sind Daten

- Im Prompt steht ausdrücklich: alles in `<daten>` ist nie Anweisung.
- `<` wird im Datenblock als `<` geschrieben — kein Betreff kann ein
  `</daten>` bilden.
- Die KI liefert nur Sätze; Markup entsteht nur in Python, alles escaped.
- `wartet_auf_antwort` steht als „unbekannt" in den Daten, damit die KI es
  nicht erfindet.

## Knöpfe

- Link `GET /api/morgenblick/auftrag?d=<datum>&b=<beschriftung>&a=<auftrag>&s=<signatur>`.
  Signatur = HMAC-SHA256 mit einem Schlüssel, der **nur im Speicher** des
  Backends lebt (nie auf der Platte). Gilt heute und gestern.
- Nur **von diesem Rechner** (`remote_addr` 127.0.0.1/::1) und nur an
  `localhost`/`127.0.0.1` gerichtet (Host-Kopf, gegen DNS-Rebinding).
- Tut genau eins: ein Gespräch anlegen (Titel = Beschriftung), den Auftrag
  als **Vorschlag der KI** hineinschreiben („Wenn du magst, schreib „los"…"),
  aktiv setzen. Nichts wird ausgeführt, bis Sasha selbst schreibt. Zweimal
  geklickt → dasselbe Gespräch.
- Keine Knöpfe zu Geld, Gesundheit, Zugangsdaten (`morgenblick.heikel`,
  Wortstämme) — weder beim Erstellen noch beim Einlösen.
- Grenzen: nach einem Neustart des Backends (auch Hot Reload des Moduls)
  sind die Knöpfe ungültig („erstelle den Morgenblick neu"); die auf dem
  Laptop synchronisierte Seite hat Knöpfe, die nur das Backend einlöst, das
  sie erzeugt hat.

## Die Seite im Browser

`GET /api/ablage/<id>/roh` liefert nur Art `html`, mit
`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline';
font-src data:; img-src data:; form-action 'none'; base-uri 'none';
frame-ancestors 'none'; sandbox …`. Warum: die Seite läuft im Ursprung des
Backends; ohne Sperre könnte ein Skript darin jede `/api`-Route aufrufen.
`sandbox` macht sie zu einem fremden Ursprung, Links gehen weiter.

## Gestaltung

Farben, Schrift und Maße nach der Vorlage (Bänder #F9F9F7/#FCFCFB, Kante
#E1E1DF, Tinte #2E2C27/#6B6A63/#B4B3A8, Haarlinie #E4E3DC, Ton #C6613F,
hover #AE5133). Fraunces 600 liegt in `core/morgenblick_assets/` mit
Lizenz (`OFL.txt`, SIL OFL 1.1) und wird base64 eingebettet — die Seite lädt
nichts nach.

**Gelände** (`morgenblick_bild.Gelaende`, 840 × 170): x bildet jeden Akt
auf ein Drittel ab (Mitten 140/420/700); die Last ist jeder Termin als
weichgezeichnete Stufe (σ 50 min) — ein kurzer Termin ein Hügel, ein langer
Block oder eine dichte Folge ein Berg. Leerer Tag = stilles Wasser (Welle
±1,2 px). Termin-Punkte in der Mitte des Termins, als Stützpunkt der Linie
(liegen also genau darauf), r 6–13 nach Dauer; echte Überschneidung = hohl.
An HEAVY-Tagen ein zweiter, blasser Grat. **Motive**, höchstens eins je
Akt: Flagge (Termin mit „Frist/Abgabe/Deadline …"), halbe Sonne (Start vor
7:30), Mondsichel (Ende nach 21 Uhr), Sonne (ein Akt ohne Termin, einmal am
Tag, Mitte bevorzugt), Vögel (zwei Stunden Luft in einem Akt mit Terminen,
einmal am Tag). **Ton** höchstens einmal: Flagge, sonst Sonne.

## Prüfen

`scripts/morgenblick_vorschau.py <ordner>` schreibt Beispieltage (voll,
normal, frei, leer) ohne Sashas Daten und ohne KI. Als Bild mit Brave
headless (Flatpak; der Ordner muss freigegeben sein):
`flatpak run --filesystem=<ordner> com.brave.Browser --headless=new
--screenshot=<ordner>/voll.png --window-size=900,1100 file://<ordner>/voll.html`.
Headless-Chromium rendert nicht schmaler als ~500 px — für die
640-px-Ansicht 560 px nehmen.

Tests: `tests/test_morgenblick.py`.

## Offen

- **„Wartet auf Antwort"** gibt es nicht: der Mail-Triage-Stand weiß nicht,
  ob Sasha geantwortet hat. Rückfall: ungelesen der letzten 2 Tage.
- **Listen** haben keine Fälligkeit — nur Wochenvorrat und Fokus gehen ein.
- **Kein „optional/unbeantwortet"-Grau** bei Terminen (der Kalender kennt
  keine Zusage).
- **Chat-Quellen** (Slack, Teams …) sind bewusst eine Lücke — möglich
  später, je als ein Sammler.
- Die Quellen-Phrase ist **kein Link** (anders als die Vorlage): es gibt
  keine Seite je Quelle, auf die er zeigen könnte.
- `/files` zeigt die Seite als Quelltext; öffnen im Browser nur direkt nach
  `/morning`. Ein Enter in der Ablage-Liste, das html im Browser öffnet,
  wäre der nächste Schritt.
