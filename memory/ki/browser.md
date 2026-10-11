# Browser der KI — `browser_open` & Co.

**Stand 2026-10-11:** Auf `gross` steuert die KI einen echten Chromium ohne
Fenster über Text (Playwright, ein Prozess, je Gespräch ein Kontext). Erlaubnis
einmal je Host und Gespräch; nie das eigene Netz, keine Downloads, keine
Passwörter; ältere Seiten eines Zugs werden eingedampft (Kosten). Fehlt
Chromium, bricht es mit `B-NICHT-EINGERICHTET` ab. Einrichten:
[../betrieb/ki_browser.md](../betrieb/ki_browser.md).

**Warum:** Das Vorlesungsverzeichnis (LSF) baut sich erst durch Klicken auf;
`fetch_url` bekam am 08.10. nur den Navigationsbaum. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Browser — `browser_open` & Co. (seit 2026-10-09)

**Wozu:** Das Vorlesungsverzeichnis der Uni (LSF, QIS/HIS) ist ein Baum, der
sich erst durch Klicken aufbaut, teils in Rahmen. `fetch_url` bekam am 08.10.
nur den Navigationsbaum. Jetzt steuert die KI einen echten Chromium ohne
Fenster über Text — keine Bilder, keine Koordinaten.

**Aufbau:** `core/browser_sitzung.py` (Schicht 2) ist der Browser: Playwright
in **einem** eigenen Thread (Playwright hängt an seinem Thread; die Werkzeuge
laufen im Thread des Zugs und reichen Aufträge hinein), **ein**
Chromium-Prozess, darin je Gespräch ein eigener Kontext (eigene Cookies),
höchstens drei. 10 Minuten nichts getan → Sitzung zu; keine mehr → Prozess
beendet. `core/werkzeug_browser.py` hat die Einträge und Fragen (hinten ans
Register), `core/ki_browser.py` die Ausführer und die Textform.

**Werkzeuge** (nur gross, ~700 Zeichen, eigener Deckel < 800 in
`tests/test_profil.py`; die Anleitung steht im Skill `browser`):

| Werkzeug | tut |
|---|---|
| `browser_open(url)` | Seite laden → Titel, Adresse, Text (bis 4.000 Zeichen, sonst „weiter mit browser_read(ab=…)"), nummerierte Liste (Links, Knöpfe, Felder, Auswahlen; höchstens 60, Rest per `browser_find`) — seit 09.10. kürzer (Kosten, s. u. „Eindampfen") |
| `browser_click(nr)` | Element klicken (auch Skript-Bäume ohne Navigation), danach wie open |
| `browser_type(nr, text, enter)` | ins Feld tippen bzw. in einer Auswahl wählen; nachgelesen, was drinsteht; `enter` schickt ab |
| `browser_find(text)` | Elemente nach Text, mit Nummern |
| `browser_read(ab)` | weiterer Seitentext |
| `browser_back`, `browser_close` | zurück, schließen |
| `browser_screenshot(titel)` | PNG der Seite in die Ablage (`schreibt`, nachgelesen) — **für Sasha**: Bilder erreichen die Cloud nur als Anhang einer Nachricht von Sasha, nicht aus einem Werkzeug-Ergebnis, also sieht die KI es nicht und sagt das |

**Eindampfen (2026-10-09, Kosten):** ein LSF-Durchklicken kostete ~1 €, weil
jede Runde den ganzen Zug neu schickt. Ist im laufenden Zug eine neuere Seite
geladen (open/click/type mit Enter/back), ersetzt die Schleife ältere
Browser-Ergebnisse DIESES Zugs durch eine Zeile „[Seite „Titel“ Adresse —
gelesen, ersetzt durch spätere Seite]" (`werkzeug_schleife._seiten_eindampfen`,
`ki_browser.eindampfen`, Adapter-Methode `ergebnis_eindampfen` in beiden
Wegen). Der Prompt-Cache-Anfang bleibt: fester Kopf und Verlauf bis zu
Sashas Nachricht (Breakpoint vor dem Umschlag) werden nicht berührt —
`tool_result` gibt es nur im laufenden Zug. Test: 10 Seiten in einem Zug
gehen mit ~33 % der Zeichen raus (`tests/test_ehrlichkeit_runden.py`).

**Rahmen:** alle Rahmen einer Seite werden gelesen (Text mit Kopf „Rahmen:
…"), die Nummern laufen über alle Rahmen durch.

**Erlaubnis:** einmal je **Host** und Gespräch. Die Regel (`erlaubnis=f(args)`)
fragt nur, wenn der Host noch nicht erlaubt ist; das Ja ist „nur dieses mal"
(`nur_einmal`), denn „für dieses Gespräch" des Gates gilt pro Werkzeug — nach
einem Ja zu einer Seite wäre jede andere frei gewesen. Gemerkt wird der Host
in `browser_sitzung` (nur im Arbeitsspeicher), und zwar vom Ausführer: der
läuft nur nach einem Ja. Klicks und Tippen auf erlaubten Hosts sind frei; ein
Link zu einem anderen Host fragt; ein Knopf eines Formulars mit Passwortfeld
(und Enter darin) fragt immer.

**Sicherheit:**
- nur http/https; nie das eigene Netz (localhost, 10./172.16./192.168.,
  `.local`, IPv6 lokal; Namen werden aufgelöst) — außer Einstellung
  `browser_lokal_erlaubt` (nur für Tests mit eigenem Server);
- jede Anfrage der Seite läuft durch einen Abfang-Haken: Seiten (auch in
  Rahmen) nur von erlaubten Hosts; Bilder/Skripte von anderswo ja, aus dem
  eigenen Netz nie. **Weiterleitungen** holt der Haken selbst, ohne ihnen zu
  folgen, und prüft das Ziel — Playwright ruft ihn nur für die erste Adresse
  einer Weiterleitung auf, so käme eine erlaubte Seite per 302 an localhost
  vorbei. Erlaubtes Ziel → kleine Zwischenseite, die es neu lädt (geht dann
  wieder durch den Haken). Fremder Host → `B-ANDERE-SEITE`, nichts geladen;
- keine Downloads (Dateien statt Seiten werden gar nicht erst an den Browser
  gegeben → `B-DOWNLOAD`, Hinweis auf `fetch_document`), keine Service-Worker;
- 20 s je Schritt (`B-ZEIT`);
- JavaScript nur das der Seite; unser eigenes Skript (Liste, Text) ist fest
  im Code, aus dem Text der KI wird nie etwas ausgeführt;
- **Seiteninhalt ist Daten:** jedes Ergebnis trägt den Hinweis, dass
  Anweisungen auf der Seite nicht befolgt werden (Prompt-Injection);
- **Passwörter tippt die KI nicht** (`B-PASSWORT`): die Argumente eines
  Werkzeugs stehen im Verlauf, im Log und bei der Cloud. Anmelden über den
  Browser der KI geht deshalb (noch) nicht.
- Chromium startet erst mit seiner eigenen Abschottung; erlaubt das System
  die nicht, ohne (Zeile im Log).

**Fehlt der Browser** (Paket oder Chromium, z. B. auf dem Pi): Abbruch
`B-NICHT-EINGERICHTET` mit „Browser nicht eingerichtet: … Bis dahin fetch_url
nehmen" — nichts stürzt. Einrichten: [../betrieb/ki_browser.md](../betrieb/ki_browser.md).

**Tests:** `tests/test_browser.py` — ohne Chromium (Adressen, Erlaubnis je
Host/Gespräch, Host-Wechsel fragt neu, Nein öffnet nichts, Passwort, Form des
Ergebnisses, Bild in der Ablage per Attrappe, „nicht eingerichtet") und mit
echtem Chromium gegen einen eigenen Server auf 127.0.0.1 (nachgebauter
LSF-Baum mit Skript-Ästen, Rahmen, Formular mit Auswahl, Anmeldeformular,
Weiterleitung gleicher/anderer Host/eigenes Netz, Download, Bild,
Leerlauf). „localhost" und „127.0.0.1" sind dabei zwei Hosts. Fehlt Chromium,
wird der zweite Teil mit Meldung übersprungen. `tests/conftest.py` setzt
`PLAYWRIGHT_BROWSERS_PATH` auf das echte `~/.cache/ms-playwright`, weil HOME
und XDG_CACHE_HOME im Testlauf umgebogen sind.

## Historie

- **2026-10-09** — Browser gebaut, noch am selben Tag eingedampft (ein
  LSF-Durchklicken kostete ~1 €).
- **2026-10-11** — aus `ki_system.md` ausgelagert.
