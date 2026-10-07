# Claude-Web im ZENTRALE-Assistenten — der Plan

Stand 2026-10-07. **Geplant und von Sasha entschieden (Abschnitt 6),
noch nichts gebaut.** Sasha hat am 06.10. gesagt: erst aufräumen, dann vor dem
Übertragen anhalten und gemeinsam planen. Das ist am 07.10. geschehen.

Grundregel aus [../claude_hinweise.md](../claude_hinweise.md) („Das
Strukturziel"): nichts hinbauen ohne Plan, wie die Architektur damit skaliert.
Jede Funktion unten hat deshalb eine **Ebene**, in die sie gehört, und die
Ebenen stehen vor den Funktionen.

---

## 1. Was es heute gibt (Bestandsaufnahme 07.10.)

| Bereich | Heute in ZENTRALE |
|---|---|
| **Eingabe** | TUI-Chatfeld (`space`/`a`): eine Zeile, nur ASCII, max. 1000 Zeichen, kein Cursor, keine Slash-Befehle im Chat |
| **Antwort** | SSE von `/api/chat`; Text kommt pro Runde am Stück (nicht Token für Token), Denken läuft live als „denkt: …" mit |
| **Sichtbar** | Werkzeug-Aufrufe (`⚙ … ↳ …`), Denken als Log-Zeile, Markdown (Überschriften, Listen, Code), Modell + € heute im Titel, ⚠ ab 80 % Budget |
| **Verlauf** | EIN Gespräch, nur im RAM (`state._chat_history`, 50 Einträge), weg nach Neustart. Das Transkript (`data/ai_transcripts/`) wird geschrieben, aber nie gelesen |
| **Gedächtnis** | Dateien in `data/gedaechtnis/`: Hausregeln/Steckbrief/Ziele stehen immer im Prompt (nur Cloud), dazu Titel aller Bereiche; Rest per `read_note`/`search_memory` |
| **Werkzeuge** | Kalender, Dateien lesen, News, Mail-Zahlen, Websuche, Webseite holen, Auswahlknöpfe, Gedächtnis, Messreihen. Erlaubnis-Gate für alles Schreibende |
| **Proaktiv** | Takt: Termin-Erinnerung 60/30 min vorher, landet im selben Gespräch |
| **Einstellungen** | Nur `/cloud on|off`, `/local on|off` aus der TUI. Anbieter, Modell, Effort, Budget, Backend: Setter existieren im Kern, aber **kein Kabel** — nur per Hand in `data/ai_config.json` |
| **Fehlt ganz** | Stoppen, Neu, Wiederholen, Bearbeiten, Gesprächsliste, Anhänge, Bilder rein, Kopieren, Ablage/Artefakte, Skills, Projekte |

## 2. Was Claude Web hat — und was davon Sinn ergibt

| Claude Web | Sinn für ZENTRALE? | Ebene (Abschnitt 3) |
|---|---|---|
| Gespräche: Liste, neu, umbenennen, suchen | **ja, Kern** — ohne das keine weiteren Schritte | Gespräch |
| Stoppen während der Antwort | **ja**, billig, spart Geld | Steuerung |
| Antwort neu erzeugen / letzte Nachricht bearbeiten | ja | Steuerung + Gespräch |
| Modell- und Effort-Wahl | **ja** — Kabel liegt schon fast | Steuerung |
| Memory (Claude merkt sich Dinge über Chats hinweg, Nutzer kann es sehen/ändern) | gibt es schon (Kernakten), aber **unsichtbar** in der TUI | Gedächtnis |
| „Frühere Chats durchsuchen" | ja — Transkript liegt schon da, wird nur nie gelesen | Gedächtnis |
| Projekte (eigene Anweisungen + Wissensdateien pro Thema) | später; Dossiers sind fast schon das | Projekt |
| Skills (Anleitungspakete, die nur bei Bedarf geladen werden) | **ja**, passt genau zur Kosten-Logik | Skill |
| Werkzeuge: Websuche, Webseite holen | gibt es | Werkzeug |
| Code ausführen | **Entscheidung Sasha** — Sicherheitsfrage | Werkzeug |
| Artefakte (Dokumente/Seiten neben dem Chat) | ja, als **Ablage** in der TUI | Ausgabe |
| Dateien/Bilder anhängen | ja (Dateipfad; Bilder nur Cloud) | Eingabe |
| Konnektoren (MCP: Drive, Kalender, …) | später, nur als Gedanke | Werkzeug |
| Stile (knapp/ausführlich) | klein, über Skills lösbar | Skill |
| Token-für-Token-Streaming | Sasha 06.10.: „Streaming egal" → hinten | Ausgabe |

## 3. Die Ebenen — wie es zusammenspielt

```
      TUI (tui/ansichten/chat.py)             ← Frontend: zeigt, nimmt Tasten
            │  HTTP + SSE (ein Vertrag: Events)
      ui/routen/ki.py                          ← nur Übersetzung, keine Logik
            │
      kern.chat(gespraech_id, …)               ← der eine Einstieg (gibt es)
            │
   ┌────────┼──────────────┬──────────────┬─────────────┐
 Gespräch  Prompt-Bau      Werkzeug-       Fahrzeug
 (Speicher) = Profil       Schleife        (Anbieter/Modell
            + Gedächtnis-  (gibt es)       = Variablen,
              Kopf          │              gibt es)
            + Projekt       Werkzeug-Register ── Erlaubnis-Gate
            + Skill-Liste   (EINE Tabelle)
```

**Die sechs Ebenen, von außen nach innen:**

1. **Steuerung** — was der Mensch am laufenden Gespräch dreht: stoppen,
   neu, wiederholen, Modell/Effort. Kein eigener Speicher; ruft nur die
   Ebenen darunter. Backend: Routen + ein Abbruch-Signal pro laufendem Strom.
2. **Gespräch** — *das fehlende Fundament.* Ein Gespräch = eine Datei
   `data/gespraeche/<id>.jsonl` (Nachrichten, Werkzeug-Ergebnisse, Titel,
   Anbieter je Antwort). `state._chat_history` wird zum Cache des aktiven
   Gesprächs. Ein Modul `core/gespraeche.py`: `neu`, `liste`, `laden`,
   `anhaengen`, `kuerzen_ab(n)` (für Bearbeiten/Wiederholen), `umbenennen`,
   `archivieren`.
3. **Gedächtnis** — gibt es. Neu nur: (a) in der TUI **sichtbar und
   bearbeitbar** (Kernakten anzeigen, Bestätigungen aus dem Gate), (b) ein
   Werkzeug `search_chats` über Gespräche + Transkript.
4. **Skill** — eine Datei `data/gedaechtnis/skills/<name>.md` mit Kopf
   (`name`, `beschreibung`, wann benutzen). Im Prompt steht **nur die
   Liste** (eine Zeile pro Skill); den Inhalt holt sich das Modell per
   `load_skill(name)`, wenn es ihn braucht. So kostet ein Skill fast nichts,
   solange er nicht dran ist — dasselbe Prinzip wie heute „Titel im Kopf,
   Inhalt per `read_note`". Abgrenzung: **Profil** = wie die Schiene
   grundsätzlich denkt (klein/gross), **Skill** = Anleitung für eine Aufgabe,
   **Projekt** = Rahmen für ein Thema.
5. **Werkzeug** — heute liegen Beschreibung (in `profil/klein.py` +
   `gross.py`), Ausführung (`ki_werkzeuge._verteilen`) und Erlaubnis
   (`erlaubnis.py`) an drei Stellen. Vorher aufräumen: **ein Register**,
   ein Eintrag pro Werkzeug mit Schema, Ausführer, Erlaubnis-Regel, welche
   Schienen es bekommen. Ein neues Werkzeug ist dann *eine* Stelle — dieselbe
   Idee wie die Anbieter-Tabelle („eine Zeile, kein Umbau").
6. **Ausgabe** — die Events sind der Vertrag zwischen Kern und TUI. Neu:
   `ablage` (ein Dokument entstand → TUI zeigt es in einer Liste, öffnet es
   im Pager/Editor), `titel` (Gespräch bekam einen Namen), `gestoppt`.

**Projekt** (später) ist kein eigener Speicher, sondern eine Klammer: ein
Ordner unter `data/gedaechtnis/projekte/<name>/` mit `anweisungen.md` und
Wissensdateien; ein Gespräch gehört optional zu einem Projekt, und der
Prompt-Bau hängt dessen Anweisungen hinter den Gedächtnis-Kopf.

## 4. Die Fallen, die vorher klar sein müssen

- **Sync ist nur additiv** (rsync, neueste Datei gewinnt). Gelöschte
  Gespräche kämen vom anderen Rechner zurück. Deshalb **nie löschen, nur
  archivieren** (Flag in der Datei), und **eine Datei pro Gespräch** — sonst
  überschreiben sich zwei Rechner gegenseitig das ganze Verlaufsbuch.
- **Prompt-Cache.** Der Anthropic-Cache hängt an einem festen Anfang
  (Werkzeuge + Persona + Gedächtnis-Kopf). Skills und Projekt-Anweisungen
  dürfen ihn nicht bei jedem Zug verändern: Skill-*Liste* in den festen Teil,
  geladener Skill-*Inhalt* als Werkzeug-Ergebnis (wandert mit dem Verlauf).
- **Stoppen muss bis in die Schleife reichen.** Verbindung schließen reicht
  nicht: der Kern läuft weiter und bezahlt. Die Werkzeug-Schleife prüft vor
  jeder Runde ein Abbruch-Signal; laufende Anbieter-Ströme werden geschlossen.
- **Das lokale qwen bleibt klein.** Alles Neue erst auf der Cloud-Schiene;
  `klein` bekommt nur, was gegen ein echtes qwen gemessen ist
  ([bench_history.md](bench_history.md)).
- **Code ausführen** heißt: das Modell startet Programme auf Sashas Rechner.
  Nur in einer Sandbox: eigener Arbeitsordner, kein Zugriff auf `data/` und
  Keys, Zeitlimit, Ausgabe gekappt, jeder Lauf über das Erlaubnis-Gate.
- **Gespräche auf zwei Rechnern.** Sasha will EIN Gedächtnis, egal von wo
  (Entscheidung 2). Der Sync kennt aber nur „neueste Datei gewinnt": schreiben
  PC und Laptop in dieselbe Gesprächsdatei, verliert einer. Deshalb ist ein
  Gespräch ein **Ordner** `data/gespraeche/<id>/` mit **einer Datei pro
  Rechner** (`<knoten>.jsonl`, nur anhängen) plus `kopf.json` (Titel, Projekt,
  archiviert; klein, neueste gewinnt ist dort harmlos). Beim Lesen werden die
  Rechner-Dateien nach Zeitstempel zusammengelegt. So kann der Sync nie eine
  Nachricht überschreiben.
- **Der Riese** ist weg: seit 611d186 (07.10.) hat der Chat sein eigenes
  Modul `tui/ansichten/chat.py` (Klasse `Chat`, siehe
  `memory/system/tui_bauplan.md`). Neue Chat-Funktionen gehören dorthin.

## 5. Reihenfolge

| Phase | Was | Warum zuerst | Größe |
|---|---|---|---|
| **0 Fundament** | ~~TUI-Zerlegung~~ (erledigt 07.10.); **Werkzeug-Register** | Ohne ein Register wächst jedes neue Werkzeug an drei Stellen | mittel |
| **1 Steuerung** | Stoppen (bis in die Schleife), mehrzeilige Eingabe mit Cursor, Slash-Befehle im Chat (`/neu`, `/modell`, `/effort`), Kabel für die vorhandenen Setter (Route + TUI) | sofort spürbar, kleines Risiko, Setter liegen schon da | klein |
| **2 Gespräche** | `core/gespraeche.py` (Ordner pro Gespräch, Datei pro Rechner), Gesprächsliste in der TUI, neu/wechseln/umbenennen/archivieren, automatischer Titel, Wiederholen + letzte Nachricht bearbeiten, **Denken mitgespeichert und aufklappbar**, Gespräch „Erinnerungen" | das Fundament für alles Weitere; Verlauf überlebt Neustarts | mittel |
| **3 Gedächtnis sichtbar** | Kernakten in der TUI ansehen/ändern, **`search_chats` über alle Gespräche** | Sasha orientiert sich nach Thema, nicht nach Datum — die Suche quer durch Gespräche ist dafür die Bedingung | klein |
| **4 Skills** | Skill-Dateien, Liste im Prompt, `load_skill`, erste Skills; **`propose_skill`**: die KI schlägt Skills vor, angelegt wird erst nach Bestätigung (Gate) | billig, passt zur Kostenlogik; Grundlage dafür, dass sie sich später selbst weiterentwickelt | klein |
| **5 Ablage + Anhänge** | `ablage`-Event + Ablage-Liste in der TUI; Datei anhängen per Pfad; Bilder an die Cloud | Artefakte in Terminal-Form | mittel |
| **6 Projekte** | Projekt-Ordner, Zuordnung Gespräch→Projekt | erst wenn 2–4 stehen | mittel |
| **7 Sandbox (Grundlage)** | `run_code` in einem abgeschotteten Arbeitsordner (Python + Shell, Zeitlimit, kein `data/`, keine Keys, Gate); Ergebnis als Werkzeug-Ergebnis, Dateien in die Ablage | Sasha: die KI soll später wie ein Coder arbeiten — jetzt nur das Fundament, keine volle Coding-KI | klein |
| später | echtes Token-Streaming, Konnektoren (MCP), Coding-Werkzeuge über die Sandbox hinaus (Repo lesen/ändern), Ollama über denselben OpenAI-Weg (erst messen) | Sasha: Streaming egal; „erstmal wird der Assistent ordentlich" | — |

Jede Phase: eigener Worktree, Tests, Doku hier nachziehen, Leitplanken-Test
(`tests/test_kern_bauplan.py`) bekommt neue Module eingetragen.

## 6. Entscheidungen (Sasha, 07.10.2026)

1. **Viele Gespräche wie im Web**, kein Tagesgespräch. „Mein Kopf kann sich
   thematisch viel besser orientieren als datiert — solang der Assistent eh
   einfach crossgespräche suchen kann wie Claude Web." → `search_chats` ist
   Pflicht, nicht Zugabe.
2. **Gespräche synchron auf allen Rechnern** — als Folge davon, dass das
   Gedächtnis überall gleich sein muss: „der Assistent ist konsistent, egal
   von wo ich ihn anspreche." → Ordner pro Gespräch, Datei pro Rechner
   (Abschnitt 4).
3. **Erinnerungen bekommt der Assistent alle**: Kalender, Zeitplan, gestellte
   Timer und Ähnliches. Das Wort „Takt" verwirrt Sasha und kommt aus allem
   raus, was er sieht. Wo sie landen, hat Sasha offengelassen — angenommen:
   ein eigenes Gespräch „Erinnerungen" oben in der Liste; der Assistent sieht
   es aus jedem Gespräch über die Suche.
4. **Die KI soll Skills vorschlagen**, damit sie sich später selbst
   weiterentwickeln kann. Anlegen nach Bestätigung.
5. **Code ausführen: ja**, als Grundlage — die Idee ist, dass der Assistent
   später coden kann wie Claude Code oder mit ihm zusammen. Jetzt nur das
   Fundament; „Hauptsache der Assistent wird erstmal ordentlich."
6. **Denken mitspeichern**, zum Anschauen. Ob es langfristig gebraucht wird,
   wird später anhand der Nutzung entschieden.
