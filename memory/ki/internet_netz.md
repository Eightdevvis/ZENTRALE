# Internet-Pipe und Netz-Transparenz

**Stand 2026-10-11:** `web_search`/`fetch_url` (auf `klein`: `web_suche`/`hole_url`)
sind die bewusst gegateten Wege nach draußen; gesucht wird über SearXNG
self-hosted (`localhost:8888`), Rückfall DuckDuckGo. Aller HTTP-Verkehr läuft
durch `core/net.py` und steht im Terminal; Internet-Verkehr zusätzlich im
eigenen Kanal.

**Warum:** ZENTRALE war bis 2026-06-07 vollständig offline; jedes Paket, das
das LAN verlässt, soll sichtbar und gefragt sein. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Internet-Pipe – `web_suche` + `hole_url` (seit 2026-06-07)

ZENTRALE war bis hierhin vollständig offline (außer lokalem Ollama). Diese
zwei Tools sind das einzige, was bewusst nach draußen telefoniert:

- **`web_suche(query)`** – sucht im Internet, liefert die Top-Treffer als
  Liste (Titel, URL, Snippet). Für aktuelles Wissen, News, Wetter, Fakten,
  die nicht im Graphen/in Dateien stehen.
- **`hole_url(url)`** – lädt eine konkrete Seite und gibt den Textinhalt
  zurück (HTML→Text, gekürzt auf ~4000 Zeichen, damit `num_ctx=8192` nicht
  überläuft). Typischer Ablauf: erst `web_suche`, dann `hole_url` auf einen
  Treffer.

**Implementation:** [`core/web.py`](../../core/web.py). Die eigentliche Such-
Quelle steckt bewusst in **einer** Funktion: seit 2026-06-08 ist das primär
**SearXNG self-hosted** (`_searxng_search`, lokaler Docker-Container auf
`localhost:8888`, JSON-Modus). SearXNG ist ein Meta-Such-Aggregator – ER
fragt im Hintergrund Google/Bing/DDG/… ab und liefert uns sauberes JSON.
Vorteil gegenüber dem alten Scraping: stabiles Format statt fragiler HTML-
Regexe, keine Anti-Bot-Landingpage (DDG hatte uns geblockt), Upstream-Suchen
laufen unter SearXNGs Identität. **Fallback:** läuft der Container nicht,
fällt `suche()` automatisch auf das alte `_ddg_search` zurück (DuckDuckGo
keyless, HTML-Endpoint gescraped, mit Ad-Filter gegen `y.js`-Werbung) –
dann ist wenigstens nichts komplett tot. Quelle wechseln = weiterhin nur
diese eine Funktion tauschen, `suche()`/`hole()`/`ai.py` bleiben unangetastet.

> **SearXNG-Container:** `sudo docker run -d --name searxng --restart
> unless-stopped -p 8888:8080 -v ~/searxng:/etc/searxng searxng/searxng`.
> Konfig in `~/searxng/settings.yml` (`use_default_settings: true`,
> `secret_key`, `limiter: false`, `formats: [html, json]`). `docker` braucht
> `sudo` (Sasha nicht in der docker-Gruppe). Test:
> `curl 'localhost:8888/search?q=test&format=json'`.

**Recherche auf gross (seit 2026-10-22):** Werkzeug-Texte, Ergebnis-Kopf der
Suche, Prompt-Abschnitt „## Recherche", Skill `recherche` und der Prüfer-
Befund `ungelesen` folgen der KI-Bibel, [bibel/recherche.md](bibel/recherche.md).

**Gating:** beide Tools stehen in `PERMISSION_REQUIRED_TOOLS` → **jeder**
Call löst den JA/NEIN-Knopf-Dialog aus (Sasha sieht die Suchanfrage / die
URL, bevor das Paket rausgeht). Konsequent zur Transparenz-Philosophie.
Frage-Vorlagen in `_permission_question` (z.B. »Soll ich im Internet nach
"…" suchen?«).

**Transparenz:** Aller HTTP-Verkehr läuft durch `core/net.py`. `hole_url` und
der DDG-Fallback treffen echte Internet-Ziele → leuchten **automatisch** im
orangen Internet-Panel auf. **SearXNG ist der Sonderfall:** der Call geht an
`localhost:8888`, also stuft `net._is_internet` ihn als lokal ein und das
Panel bliebe leer – OBWOHL SearXNG dahinter echtes Internet anfasst. Damit
die Tripwire-Linie hält, loggt `_searxng_search` die Suchanfrage **explizit**
in den Internet-Channel (`state.push_internet_log("NET → SUCHE „…" (via
SearXNG)")`). Man sieht im Panel also weiterhin, dass + wonach gesucht wurde.

**KI-Selbstbild:** Die Internet-Limits im Identity-Graphen (»auf das Internet
zugreifen«, »Web-Suche durchführen«, »Echtzeit-News/Wetter abrufen«) wurden
zu Fähigkeiten (»im Internet suchen«, »Webseiten abrufen«). Code:
`graph._SEED_CAPABILITIES`/`_SEED_LIMITS` (frische Installs) +
`graph.migrate_internet_access()` (zog bereits geseedete Graphen nach). Der
Graph ist seit 2026-10-31 aus dem Code; was die KI kann, sagen heute ihre
Werkzeuge und die Meta-Regeln der Schiene.

## Network-Transparenz

Alle HTTP-Requests werden im Dashboard-Terminal sichtbar geloggt
(via `core/net.py`):

```
NET →  POST http://localhost:11434/api/chat
NET ←  200 http://localhost:11434/api/chat (2341 B)
STT →  POST http://localhost:5050/transcribe (48 KB)
STT ←  '我很好' (Konfidenz: 94%)
TTS →  POST http://localhost:5051/speak '你好！'
TTS ←  62 KB WAV
```

Plus die Tool-Use-Zeilen (`AI → TOOL ...` / `AI ← TOOL ...`).

### Zwei stdout-Channels: Voll-Stream vs. Internet-Monitor

Der Footer im Dashboard ist in zwei Terminals gesplittet:

- **Links** = voller `state._logs`-Stream (alles oben Gezeigte).
- **Rechts** = nur Internet-Traffic. Quelle: `state._internet_logs`,
  gespiegelt aus `net.py` wenn `net._is_internet(url)` True liefert.

`_is_internet(url)` klassifiziert defensiv:

- localhost / `127.0.0.1` / `::1` / `0.0.0.0` → False (lokal)
- Private-Ranges (`10/8`, `172.16/12`, `192.168/16`) → False (LAN)
- Link-local (`169.254/16`) → False
- `*.local` Hostnames (mDNS) → False
- IPv6-Loopback / -Link-local / -Private → False
- Alles andere (Public-IPs, normale Hostnames) → True

**Philosophie-Update 2026-06-07:** Das rechte Panel sollte ursprünglich
**leer** bleiben (Alarm-der-nie-feuern-darf), weil ZENTRALE vollständig
offline war. Seit der Internet-Pipe (`web_suche`/`hole_url`) ist es bewusst
ein **Transparenz-Monitor**: es zeigt **genau, was rein- und rausgeht**.
Jeder gegatete Such-/Lade-Call leuchtet hier auf – das ist jetzt der
erwartete, gewollte Beleg „Paket hat das LAN verlassen", nicht mehr ein
Alarm. (Nicht-gegateter Internet-Traffic hier wäre weiterhin verdächtig.)
Implementation: `core/net.py` (`_is_internet`, plus Spiegel-Calls in
`_log_out/_log_in/_log_err`), `core/state.py` (`_internet_logs`,
`push_internet_log`), die Browser-Front (`ui/templates/monolith.html` unter `/zentrale`, `#term-net`, Box »outbound · tripwire«; damals `index.html` mit `.terminal-row` +
`.terminal-net` mit orangefarbenem Akzent).

Tests: `scripts/test_net_internet.py` (48 Cases, untracked).

## Historie

- **2026-06-07** — Internet-Pipe mit hartem Gate; rechtes Panel wird
  Transparenz-Monitor statt Alarm.
- **2026-06-08** — SearXNG statt DDG-Scraping.
- **2026-10-11** — Suche ehrlich: SearXNG aus + Ausweichsuche leer/Fehler = ABGEBROCHEN `I-SUCHE-AUS` (nicht „Keine Treffer"); danach 60 s lang sofort derselbe Abbruch ohne Netz (`web.suche`). „Keine Treffer" nur, wenn SearXNG lief.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
