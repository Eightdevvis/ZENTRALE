# Ablage und Anhänge

Stand 2026-10-07, Claude-Web-Plan Phase 5 ([claude_web_plan.md](claude_web_plan.md)).
Claude-Webs „Artefakte" in Terminal-Form: die KI legt Dokumente für Sasha ab,
Sasha gibt der KI Dateien mit.

## Was es gibt

- **Ablage** (`core/ablage.py`, Schicht 2): Dokumente der KI (Markdown, Text,
  Code, CSV), Dateien aus einem Sandbox-Lauf, Kopien von Anhängen (auch Bilder).
- **Anhänge** (`core/anhang.py`, Schicht 2): `/anhang <pfad>` im Chat; Text,
  Code, PDF (als Text) und Bilder (nur Cloud).
- **Zug** (`core/zug.py`, Schicht 1): was zum laufenden Chat-Zug gehört —
  Gesprächs-id für die Werkzeuge und Ereignisse, die ein Werkzeug an die TUI
  melden will. Die Chat-Route öffnet ihn, holt die Ereignisse nach jedem
  Werkzeug ab und schickt sie als SSE mit.
- **Routen** (`ui/routen/ablage.py`): `GET /api/ablage`, `GET /api/ablage/<id>`,
  `POST /api/ablage/<id>/archiv`, `POST /api/anhang`
  ([../system/api_endpoints.md](../system/api_endpoints.md)).
- **TUI**: `/ablage` (Liste + Lesen, `tui/ansichten/ablage.py`), Zeile
  „▤ Titel — enter öffnet" im Verlauf, `/anhang` (`tui/ansichten/chat_ablage.py`).

## Auf der Platte

```
data/ablage/<id>/kopf.json               titel, art, erstellt, gespraech,
                                         herkunft (ki|sandbox|anhang),
                                         archiviert, sprache?, quelle?
data/ablage/<id>/v<n>-<rechner><endung>  eine Fassung, nie überschrieben
```

- id = `<JJJJMMTT>-<titel-slug>-<4 hex>`, lesbar im Ordner.
- **Neue Fassung = neue Datei**, der Rechnername steht im Namen: legen PC und
  Laptop gleichzeitig eine zweite Fassung an, liegen nach dem Sync beide da
  (gezählt nach n, dann Zeit) — „neueste gewinnt" kann keine verschlucken.
- **Nie löschen**, nur archivieren (Flag im Kopf). Der Sync ist additiv;
  Gelöschtes käme vom anderen Rechner zurück.
- Atomar geschrieben (`dateien.atomar_schreiben`), nach jedem Schreiben
  `datasync.notify_change()`.
- `data/ablage/` **synct gewollt** (Sasha will alles überall), steht in
  `.gitignore` und in der Positivliste von `scripts/daten_sichern.py`.
- Umlenkbar per Einstellung `ablage_dir` (Env `ZENTRALE_ABLAGE_DIR`);
  Tests: `tests/conftest.py` (+ pro Test ein frischer Ordner), Wächter in
  `tests/test_keine_seiteneffekte.py`.
- Grenzen: Text 200.000 Zeichen, Bild 5 MB (mehr nimmt Anthropic pro Bild nicht),
  Titel 120 Zeichen.

## Die Werkzeuge (nur `gross`)

| Werkzeug | Was | Gate |
|---|---|---|
| `create_document(titel, inhalt, art?, sprache?)` | neues Dokument, art markdown/text/code/csv | frei |
| `read_document(id)` | Inhalt lesen (für eine Änderung nötig) | frei |
| `update_document(id, inhalt)` | neue Fassung, die alte bleibt | frei |
| `save_from_sandbox(lauf, datei, titel?)` | Datei aus einem `run_code`-Lauf in die Ablage | frei |

**Ungegatet** (Entscheidung 07.10.): geschrieben wird nur in `data/ablage/`,
nie überschrieben, nie gelöscht, nichts geht nach draußen; das Dokument
erscheint sofort als Zeile im Chat. Ein Ja/Nein vor jedem Dokument wäre wie
bei `write_note` eine Zumutung.

Jedes neue Dokument und jede neue Fassung meldet sich per
`zug.melden({"ablage": {id, titel, art, fassung}})`. Die Route schickt das
als SSE-Event `ablage` direkt hinter dem `werkzeug`-Ende und speichert die
Liste mit der Antwort (`dokumente` im Gespräch). Beim nächsten Zug steht in
der Antwort für die KI „[In der Ablage: "Titel" (id …)]" — sonst wüsste sie
die id nicht mehr, um das Dokument später zu ändern.

### Sandbox → Ablage

- `run_code` benennt seinen Arbeitsordner nach dem Gespräch:
  `<gesprächs-id>--<zeit>-<hex>` (`sandbox.lauf_kennung`). Hat ein Lauf neue
  Dateien, steht im Ergebnis „Lauf: <kennung> — mit save_from_sandbox …".
- `save_from_sandbox` nimmt **nur Läufe dieses Gesprächs** (Präfix) und liest
  über `sandbox.datei_lesen`: kein absoluter Pfad, kein `..`, **kein Verweis**
  (weder die Datei noch ein Ordner davor — ein Programm kann einen Symlink auf
  `/home/…` anlegen, draußen würde er aufgelöst), nur normale Dateien, Größe
  begrenzt. Text oder Bild; Binäres wird abgelehnt.
- Gewählt statt „automatisch alles in die Ablage": ein Lauf hinterlässt oft
  Zwischendateien; die KI entscheidet, was Sasha behalten soll.

## Anhänge

1. **Die TUI liest die Datei** auf ihrem Rechner — unterwegs spricht der
   Laptop über den Tunnel mit dem PC-Backend, dort gibt es den Pfad nicht. Sie
   schickt aufgelösten Pfad + Bytes (base64) an `POST /api/anhang` (≤ 10 MB).
2. **Das Backend prüft** den Pfad gegen `context.anhang_gesperrt`
   ([../betrieb/sicherheit.md](../betrieb/sicherheit.md)), erkennt die Art
   (Bild an den ersten Bytes, PDF → `gedaechtnis.pdf_text` = derselbe
   `pdftotext`-Weg wie `fetch_document`, sonst Text/Code; Binäres abgelehnt)
   und legt eine **Kopie in die Ablage** (Herkunft `anhang`). Zurück: die id.
3. Die nächste Nachricht trägt `anhaenge: [id]`. Im Gespräch steht nur der
   **Verweis** `{id, titel, art, fassung}` — nie der Inhalt, nie ein Bild als
   base64.
4. `anhang.verlauf_einsetzen(verlauf, cloud)` setzt beim Bauen des Verlaufs
   den Inhalt ein: Cloud → Schlüssel `anhaenge` mit Text (≤ 30.000 Zeichen,
   gekappt mit Hinweis) bzw. Bild (mime + base64); lokal → Text an den Inhalt
   (≤ 8.000), Bild nur als Hinweis „sieht nur die Cloud-KI".
5. Die Adapter formen daraus Blöcke: Anthropic `image`/base64 + `text`, vor
   dem Text der Nachricht (`cloud._anhang_bloecke`); OpenAI-kompatibel Inhalt
   als Liste mit `text` und `image_url` (data:-URL), das Wechselnde hängt als
   letzter Teil dran (`cloud_openai._anhang_teile`). `kappen()` gilt nur für
   den Text der Nachricht — der Anhang hat seinen eigenen Deckel.
   Devtools zeigen ein Bild als `[bild …]`, nie die Bytes.

- **Bild + lokale KI**: `/api/chat` antwortet 400 „Bilder gehen nur mit der
  Cloud-KI — /cloud schaltet um"; die TUI behält die Anhänge vorgemerkt.
- Die Anhänge gehen **bei jedem Zug** wieder mit (wie in Claude Web; bei
  Anthropic gecacht). Der Verweis trägt die Fassung, damit dieselbe Nachricht
  in jedem Zug dieselben Bytes ergibt.
- **Wiederholen** und **Bearbeiten** behalten die Anhänge der Nachricht.

## TUI

- `/ablage`: Liste im Chat-Kasten (Titel, Fassung, Gespräch wenn breit genug,
  rechts Art bzw. Herkunft · Alter). ↑↓ Bild↑↓, Enter lesen, `a` archivieren
  (im Archiv: zurückholen), `z` Archiv, Esc zu.
- Lesen: im Kasten, mit dem Markdown der Antworten (Code/CSV wörtlich), ↑↓
  Bild↑↓ Leertaste Pos1 Ende, ←→ Fassungen, Esc eine Stufe zurück. Bilder:
  Größe und Ort auf dem Backend-Rechner.
- Im Verlauf: „▤ Titel — enter öffnet" für das neueste Dokument (Enter bei
  leerer Eingabe), ältere „— in /ablage". Anhänge als „▤ anhang: name" unter
  der eigenen Nachricht; wartende Anhänge in der Statuszeile.
- Kein externer Pager, keine Zwischenablage (die TUI hat beides nicht; offen).

## Offen

- Kopieren in die Zwischenablage (xclip/wl-copy) — gibt es in der TUI noch nicht.
- Bilder in der TUI zeigen (Pixel-Baustein?), Bilder aus der Ablage an die KI
  geben (`/anhang` nimmt nur Pfade).
- Grenze für Dokumente pro Zug, falls die KI zu viel ablegt.
- Anhänge bei sehr langen Gesprächen: bleiben im Fenster von 50 Nachrichten
  und kosten jeden Zug (gecacht) — bei Bedarf nur die letzten N mitschicken.
