# Chat in der TUI — Befehle, Darstellung, Bild-Marker, Bewertungen

**Stand 2026-10-11:** Der KI-Chat läuft in der TUI (Thin Client über
`/api/chat`), mit Slash-Befehlen, Gesprächen ([gespraeche.md](gespraeche.md)),
Markdown-Darstellung ohne Inhaltsverlust und Bewertungen „good · bad" unter
jeder Antwort. Die KI zeigt Mimik über Inline-Marker `[[bild: name]]` aus einer
kuratierten ASCII-Bibliothek.

**Warum:** Sasha soll sehen, was die KI meint, ohne Rohtext-Markup; Bewertungen
sind für Sasha und Claude, um das eigene System zu verbessern — sie gehen
nirgendwohin raus. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Chat-Modus

- KI-Chat mit qwen3.5:9b (oder via `OLLAMA_MODEL`), tokenweise gestreamt.
- KI hat Zugriff auf Whitelist-Dateien + Graph-Memory.
- Slash-Befehle im TUI-Chat (seit 2026-10-07, `tui/ansichten/chat_befehle.py`):
  `/neu` (neues Gespräch, früher `/clear` — geht weiter), `/modell [name]`,
  `/anbieter [name|auto]`, `/effort [stufe]`, `/budget [euro|aus]`,
  `/lokal` `/cloud` `/auto`, `/hilfe`, `/erlaubnis` (was ohne Frage
  erlaubt ist, zurücknehmen); seit Phase 2 auch `/liste`,
  `/titel [text]`, `/archiv`, `/wiederholen`, `/bearbeiten`, `/denken`. `//` am Anfang = wörtlicher
  Schrägstrich. Die Einstellungen laufen über `/api/ai/einstellungen`
  (`core/ki_einstellungen.py`). `/modell` zeigt seit 2026-10-07 **alle**
  Chat-Modelle jedes Anbieters mit Schlüssel (`core/modell_liste.py`: vom
  Anbieter geholt — Anthropic `GET /v1/models`, sonst `GET {base_url}/models`
  —, 24 h gecacht in `~/.cache/zentrale/modelle.json` pro Rechner, Fehler
  10 min gemerkt, Rückfall auf `providers.py`; Embedding/Audio/Bild/
  Moderation per Wortliste im Namen herausgefiltert); in der Auswahl filtert
  Tippen. Budget: 0–100 € im Monat (Sasha).
  (`/memory` und `/forget N` sind mit dem Legacy-LTM-Pfad entfallen.)
- Esc schließt den Chat (eine laufende Antwort läuft weiter), Strg+C stoppt
  sie (seit 2026-10-07).
- **Tasten (seit 2026-10-11):** EINE Tastentabelle `Chat.TASTEN`
  (`tui/ansichten/chat.py`, Format `tui/ansichten/tasten.py`) verteilt die
  Tasten UND füllt die Leiste ganz unten; Hinweiszeilen im Kasten gibt es
  nicht mehr. Die Teile mit eigener Tabelle (Seitenleiste, Gesprächsliste,
  rechts, Bewertung, Ablage, Gedächtnis, Projekte, Einstellungen; Mixin
  `chat_teil.py`) kommen über `Tasten.zusammen` dazu („teil:ansicht").
  `Chat.ansicht()` sagt, welche gilt: `frage:N`, `bewertung:…`, `wahl…`,
  Überlagerung, `seite:`/`liste:`/`rechts:`, `verlauf:<ziel-art>`, sonst das
  Eingabefeld `eingabe|antwort|bearbeiten[:dokument|:text|:zeilen]`.
  Listen haben `:eins`/`:leer`, damit ↑↓/Enter nur angezeigt werden, wo sie
  wirken. Strg+C steht in jeder Ansicht. Chat-Befehle sind Freitext; bei
  leerer Eingabe zeigt die Leiste „/ chat commands". Wege zu jeder Ansicht:
  `tests/tasten_zustaende/chat.py`.
- **Gespräche** (seit 2026-10-07, Claude-Web-Plan Phase 2): der Verlauf
  lebt nicht mehr im RAM (`state._chat_history` ist weg), sondern in
  `core/gespraeche.py` — viele Gespräche, Ordner pro Gespräch, Datei pro
  Rechner, synchron auf allen Knoten. An `kern.chat` gehen die letzten 50
  Nachrichten des aktiven Gesprächs; die Antwort wird mit allem Denken des
  Zugs, den Werkzeugen, Anbieter und Modell gespeichert. Kalender-
  Erinnerungen landen im eigenen Gespräch „Erinnerungen". Titel: erst die
  ersten Wörter, dann das billige Modell (`core/billig.py`). Alles Weitere:
  [gespraeche.md](gespraeche.md).

## Wie ihre Antwort im Terminal ankommt

Die KI schreibt Markdown — der Prompt erlaubt ihr Listen ausdrücklich,
Überschriften benutzt sie von selbst. Gezeichnet wurde bis 18.08.2026 der
**Rohtext**: im KI-Kasten stand `**fett**` und `## Titel` als Zeichen.

`tui/ansichten/text.py::md_zeilen(text, breite)` liefert
`[(zeile, stil)]` mit `stil` aus `{"", "kopf", "code", "liste"}`. Der Stil
ist absichtlich ein **Wort** und keine curses-Konstante: so bleibt die
Funktion rein und ohne Terminal testbar, und über Farben entscheidet allein
der Zeichner (`Chat.draw_ai` in `tui/ansichten/chat.py`). Sie liegt auf Modulebene und fällt damit unter
dieselbe „darf NIE werfen"-Eigenschaft wie die übrigen TUI-Helfer.

- Umgesetzt: Überschriften, Aufzählungen (mit **hängendem Einzug** — eine
  umgebrochene Zeile rückt unter den Text, nicht unter das Bullet),
  verschachtelte Listen, Code-Zäune (**nicht** umgebrochen: ein
  umgebrochener Befehl ist ein falscher Befehl), inline `**fett**`,
  `*kursiv*`, `` `code` ``, `[Text](URL)`.
- **Nicht** umgesetzt: Auszeichnung *innerhalb* einer Zeile. Dafür müsste
  eine Zeile in Segmente mit eigenen Attributen zerfallen — quer durch
  `addclip` und jeden Aufrufer. Die Marker werden entfernt, der Text bleibt.
- **Die harte Regel, mit eigenem Test:** es geht nie Inhalt verloren.
  Entfernt werden nur sauber gepaarte Marker; `2 ** 3 = 8`, `snake_case`
  und ein offenes `**` bleiben stehen, bei einem Link bleibt die URL
  erhalten. Ein Renderer, der bei kaputtem Markdown Text verschluckt, ist
  schlimmer als gar keiner — man merkt es nicht.
- Sashas eigene Eingaben laufen **nicht** durch den Renderer: was er tippt,
  soll dastehen, wie er es getippt hat.

Das (geparkte) Browser-Dashboard rendert nichts; dort ist gar kein
Markdown-Renderer eingebunden.

## Visuelle Stimme – Bild-Marker `[[bild: name]]`

Die KI zeigt Mimik/Gesten, *während* sie mit Worten antwortet: ein
passendes ASCII-Bild übernimmt kurz den Dashboard-Kern. Sie **malt nicht
selbst** – ein 9b-Modell ist mies im freien ASCII-Malen (2D-Layout über
1D-Tokenstrom), aber gut im Greppen. Also kuratiert es aus einer hand-
gepflegten Bibliothek (`data/ascii/*.txt`, Modul
[`core/ascii_lib.py`](../../core/ascii_lib.py); Ordner per Env
`ZENTRALE_ASCII_DIR`).

**Kein Tool, sondern ein Inline-Marker.** Das war eine bewusste Kehrt-
wende, gemessen mit [`scripts/bench_ascii.py`](../../scripts/bench_ascii.py):
als Tool (`zeige_ascii`) feuerte die KI bei impliziten Prompts nur **2,7 %**
(N=200) – und tippte den Aufruf oft als Text-Marker `[[zeige_ascii: name]]`
statt einen echten Tool-Call zu machen (Mimikry vom alten `[[emoji:]]`-
Muster). Lehre aus [[feedback_prompt_no_muzzle]]: nicht gegen das Modell
anprompten, sondern es dort treffen wo es hinwill. Umbau auf einen Inline-
Marker hob die Quote auf **~93 %**. Die KI tippt `[[bild: stichwort]]`
mitten in ihre Antwort; das Backend zieht den Marker raus, sucht das Bild
und feuert es separat. Kein „ich kann dir zeigen…"-Ankündigen mehr (ein
Marker wird getippt, nicht angekündigt).

- **Datei-Format:** optionale erste Zeile `# tags: a, b, c`, danach reine
  ASCII-Art. Fehlt die tags-Zeile → Dateiname ist der einzige Tag. Neue
  Bilder einfach als `.txt` reinlegen (Backend neu starten, damit die
  Stichwort-Liste im Prompt `_ASCII_MARKER_PROMPT` aktuell wird).
- **Matching (Hybrid):** Stufe 1 Tag/Keyword (exakt > Substring >
  Token-Überlappung), schnell + vorhersehbar. Greift nichts → Stufe 2
  Embedding-Fallback (bge-m3, Stichwort=query gegen Tags=document) mit
  Cosinus-Schwellwert `0.55`. Auch darunter → **kein Bild** (lieber keins
  als ein falsches). Verfügbare Stichworte stehen im Prompt (wie
  `RANGE_BUCKETS` beim Kalender), damit die KI nicht blind rät.
- **Pipeline:** `_extract_ascii_markers` (Regex, tolerant: `[[bild:]]`,
  `[[ascii:]]`, `[[zeige_ascii:]]`) zieht im regulären Chat die Marker aus
  der finalen Antwort, `ascii_lib.pick` matcht, `chat_stream` yieldet pro
  Treffer ein **Inline-Event** (`dict {"ascii","name"}`); `ui/routen/ki.py` macht
  daraus ein SSE-Event `ascii`. Der bereinigte Text (ohne Marker) wird
  gesprochen/gespeichert. Tutor-Modus kennt die Marker NICHT. Frontend:
  siehe „ASCII-Kern / Bild-Marker" in [memory/system/dashboard.md](../system/dashboard.md).
- **Alt-Namen:** die 15 Namen des früheren `[[emoji:]]`-Kanals (shrug,
  happy, flip, …) sind als englische Alias-Tags in der Bibliothek
  hinterlegt, lösen also weiter auf.

## Bewertungen (seit 2026-10-08)

Unter jeder Antwort im TUI-Chat: „good · bad", optional mit Kommentar
(Bedienung: [../system/tui_bauplan.md](../system/tui_bauplan.md) „Bewerten").
**Wofür:** Sasha und Claude gehen sie gemeinsam durch, um Prompt (`profil/`),
Skills und Werkzeug-Beschreibungen zu verbessern — „bewertungen für uns um
unser eigenes system zu verbessern" (Sasha, 08.10.). Deshalb steht bei jeder
Bewertung, wer geantwortet hat (Anbieter, Modell) und welche Werkzeuge und
Skills die Antwort benutzt hat. **Sie gehen nirgendwohin raus:** kein
Anbieter bekommt sie, sie stehen in keinem Prompt, kein Werkzeug liest sie;
sie liegen nur in `data/rueckmeldungen/<rechner>.jsonl` (gitignored, in der
Datensicherung, synct wie die Gespräche — eine Datei pro Rechner, nur
anhängen, das letzte Ereignis je Antwort gilt). Speicher
`core/rueckmeldungen.py`, Routen `POST /api/rueckmeldung`,
`GET /api/rueckmeldungen` ([../system/api_endpoints.md](../system/api_endpoints.md)).

## Historie

- **2026-06** — Bild-Marker statt Tool `zeige_ascii` (2,7 % → ~93 %).
- **2026-08-18** — Markdown-Renderer in der TUI.
- **2026-10-07** — Slash-Befehle, Gespräche (Phase 2), `/modell` zeigt alle Modelle.
- **2026-10-08** — Bewertungen.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
