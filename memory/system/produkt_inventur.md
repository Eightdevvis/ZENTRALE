# Produkt-Inventur — was ist fertig, was Baustelle (Stand 2026-10-09)

Wozu: ZENTRALE soll vom Dev-Haufen zum installierbaren Produkt werden
(Hub + Apps, siehe [hub_bauplan.md](hub_bauplan.md)). Diese Liste zieht die
Trennlinie. Einschätzung, keine Messung — bei jeder Zeile gilt: erst prüfen,
dann versprechen.

**Status:** ✅ fertig · 🟡 beta (läuft, noch Kanten) · 🔧 Umbau · 🧪 nur Dev
**Lizenz-Ecke (Vorschlag):** frei · Abo (kostet laufend KI) · exklusiv

## Apps (was ein Kunde sieht)

| App | Status | Lizenz | Was zum Fertigsein fehlt |
|---|---|---|---|
| KI-Assistent (Chat) | 🟡 | Abo | Prüfstand 4/5, Prüfer frisch; Mail-Anbindung; Zugriff nur auf Input/Output ✅ seit 09.10. auf der Cloud-Schiene (lokale Schiene liest noch ~/codicus) |
| Kalender | 🟡 | frei | .ics + Kennungen seit 09.10.; Ansichten A/B/C entscheiden |
| Notizen / Listen | 🟡 | frei | eigene App-Grenze, Feature-Tracker `l_zentrale` ist Sashas Privatliste |
| Morgenblick | 🟡 | Abo | erst 08.10.; „im Browser öffnen" aus /files |
| Messreihen / Graphen | 🟡 | frei | wenig benutzt, ungeprüft |
| Mail | 🔧 | frei | Neubau in eigener Sitzung (mbsync/notmuch) |
| News / Briefing | 🟡? | Abo | seit Wochen nicht angefasst — erst testen |
| Karte | 🟡 | frei/exklusiv | Datenlizenzen je Layer (maps_quellen.md) vor Verkauf |
| Zyklus/PMS | 🟡 | frei | Gesundheitsdaten = DSGVO besondere Kategorie → nur lokal, nie Cloud ohne Einwilligung |
| Klavier | 🟡? | frei | Nische; prüfen, ob es überhaupt rein soll |
| Sprach-Tutor (eigenes Repo) | 🟡 | exklusiv/Abo | Mikro + Spracherkennung, Bilder/Umgebung, Server-Dauerbetrieb |
| Handy-App (`mobile/`) | 🔧 | Abo | früher Stand, Sitzung ZEN-MOBIL ruht |
| Codicus (KI-Coder) | — | exklusiv | noch nicht begonnen (Ausblick in claude_web_plan §6b) |

## Hub (Plattform, was alle Apps tragen)

| Teil | Status | Lizenz | Was fehlt |
|---|---|---|---|
| TUI-Rahmen (Seitenleiste, Chat-Frontend, Maus) | ✅ | frei | — |
| Backend/Routen, Werkzeug-Register, Gate | ✅ | frei | — |
| Ehrlichkeit (Belege, Prüfer, Fehlercodes, Trace) | 🟡 | frei | mehr echte Gespräche messen |
| Abgleich über die Mitte | 🟡 | frei | gebaut, nicht in Betrieb (Schlüssel, erstes Füllen) |
| Zugang (Schlüssel für fremde Geräte) | 🟡 | frei | steht auf „melden"; Pi-Schlüssel, dann „an" |
| App-Schnittstelle (`apps.py`, Ereignisse) | 🔧 | frei | nur Start + Anwesenheit; Manifest-Rechte, Sandbox für fremde Apps |
| Modell-Zugang über eigenen Server | — | Abo | Server, Konten, Abrechnung pro Nutzer |
| Installation / Paket / Updates | — | frei | fehlt ganz |
| Sensorik (Pi-Bridge, Anwesenheit, Ring) | 🧪 | frei | an Sashas Hardware gebaut; als optionales Modul fassen |

## Nur für Devs (kommt nie ins Produkt)

Prüfstand, `bench_*`, Devtools, `zentrale_testguard`, Theme-Skripte
(`zentrale-*-theme`, nvim, bat, tmux — Sashas Desktop), Pi-Deploy-Skripte,
`tests/`, `memory/`.

## Was quer über alles fehlt, bevor verkauft wird

1. **Leerer Erststart:** 94× „Sasha" in Prompts/Profilen; Persona, Hausregeln,
   Beispiele sind auf ihn geschrieben → Name/Persona aus Nutzer-Einstellungen.
2. **Code ↔ Nutzerdaten trennen:** Code in einen Installationsordner,
   sichtbar nur `~/Zentrale/` (Input, Output, Daten je App).
3. **Lizenzen prüfen:** alle Abhängigkeiten auf GPL; Apache-/OFL-Hinweise
   mitliefern; Datenquellen der Karte.
4. **Recht:** Urheberrecht an KI-geschriebenem Code klären (Anwalt IT-Recht),
   Datenschutz (Stimme, Gespräche, Gesundheit), Anbieter-Bedingungen.
5. **Repo-Wurzel aufräumen:** Bilder, Zips, Notizdateien (`trying.txt`,
   `zentrale-cloud-plan.md`, `languagetutor.md` …) gehören Sasha — fragen,
   wohin.
