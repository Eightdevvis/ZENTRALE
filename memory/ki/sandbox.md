# Sandbox — `run_code` und `core/sandbox.py`

**Stand 2026-10-11:** `run_code` (nur `gross`) ist immer gegatet und läuft in
**bubblewrap**: nur `/usr` lesbar, beschreibbar nur `/arbeit`, kein Netz, keine
Keys, Zeitlimit 30 s (bis 120 s mit normalem Ja, länger nur nach eigener Frage),
Stoppen tötet die ganze Prozessgruppe. Ohne bwrap läuft nichts. Skill-Skripte
sehen ihren Skill-Ordner nur lesend unter `/skills/<name>`.

**Warum:** Grundlage dafür, dass der Assistent später „wie ein Coder" arbeitet
(Phase 7, [claude_web_plan.md](claude_web_plan.md)) — ohne dass ein Programm
der KI an Repo, `data/`, Keys oder Netz kommt. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).
Sicherheits-Abwägung: [../betrieb/sicherheit.md](../betrieb/sicherheit.md).

## Sandbox — `run_code` und `core/sandbox.py` (seit 2026-10-07)

Grundlage dafür, dass der Assistent später „wie ein Coder" arbeitet (Phase 7,
[claude_web_plan.md](claude_web_plan.md)). Das Werkzeug `run_code` (nur
`gross`, Parameter `code`, `sprache` python|shell, `zeitlimit`, `skill`) ist
**immer** gegatet; die Frage zeigt Sprache und die ersten vier Zeilen.
Ausgeführt wird über `sandbox.ausfuehren(code, sprache, zeitlimit_s, dateien,
lauf_id, abbruch, skill_ordner)` mit **bubblewrap** (`/usr/bin/bwrap`, unprivilegiert).

**Skill-Skripte (seit 2026-10-07):** mit `skill="<name>"` hängt die Sandbox
den Ordner dieses Skills **nur lesend** unter `/skills/<name>` ein (wie
Claudes `/mnt/skills/…`) — die einzige Ausnahme von „nichts von Sasha", und
nur für einen **aktiven** Skill (`skills.skript_ordner`); sonst läuft nichts.
Die Frage nennt den Skill („… dazu sieht es den Skill „x" (nur lesen)").
Geschrieben wird weiter nur nach `/arbeit`. Geprobt mit `quick_validate.py`
und `package_skill.py` des skill-creator (`tests/test_skill_skripte.py`).

**Zeitlimit (seit 2026-10-07, Sasha):** Standard 30 s, bis 120 s mit dem
normalen Ja (auch „immer"/„für dieses Gespräch"). Länger (bis 30 min,
`ZEITLIMIT_MAX_S`) nur nach **eigener** Frage mit der Dauer im Text („… und
darf bis zu 10 Minuten laufen"), die NUR „ja, nur dieses mal" anbietet —
Register-Feld `nur_einmal`; ein altes „immer" deckt das nicht.

**Stoppen (seit 2026-10-07):** das Stopp-Signal des Zugs geht über
`core/zug.py` (`zug.beginnen(gid, abbruch=…)`, `zug.abbruch()`) an
`run_code`; `sandbox._warten` schaut alle 0,1 s nach und tötet dann die ganze
Prozessgruppe (SIGKILL). Ergebnis: „[Abgebrochen: vom Nutzer gestoppt.]",
Kopf „VOM NUTZER GESTOPPT", Feld `gestoppt`.

**Abgeschottet:**
- Dateisystem: nur `/usr` (+ `/bin` `/lib` … als Verweise) nur-lesend, eigenes
  `/proc` `/dev`, `/tmp` im Speicher (64 MB, wo bwrap `--size` kann), die
  Wurzel nur-lesend, `/etc/localtime` (Zeitzone). Beschreibbar ist **nur**
  `/arbeit` = der Arbeitsordner des Laufs. **Nicht sichtbar:** `/home` (Repo,
  `data/`, `~/.ssh`, Keys), `/etc`, `/var`, `/run`, `/root`.
- Netz: `--unshare-all` → nur ein eigenes, totes loopback.
- Umgebung: leer bis auf `PATH`, `HOME=/arbeit`, `LANG` — keine API-Keys.
- Prozesse: eigener PID-Namensraum, `--die-with-parent`, `--new-session`
  (kein Terminal-Einschleusen), keine weiteren Benutzer-Namensräume.
- Grenzen: Zeitlimit (Standard 30 s, s. o.; danach SIGKILL an die ganze
  Gruppe, der PID-Namensraum nimmt alles mit), 512 MB Adressraum, 64 Prozesse
  (in der Sandbox gesetzt — vor bwrap ließe RLIMIT_NPROC schon die
  Namensräume scheitern), 50 MB je Datei, nice 10, Ausgabe je Strom 20.000
  Zeichen (Kopf + Schwanz, beim Lesen gekappt).
- **Nie ohne Sandbox:** fehlt bwrap oder startet es nicht (bwrap meldet kein
  `child-pid` über `--json-status-fd`), kommt `rc=None` + Klartext-Fehler;
  das Programm läuft dann gar nicht.

**Nicht abgeschottet / bewusst offen:**
- CPU-Last bis zum Zeitlimit (nur nice), und `/arbeit` hat keine
  Gesamtgröße (nur je Datei 50 MB).
- Was in `/usr` liegt, ist lesbar und ausführbar — also auch System-Pakete
  unter `/usr/lib/python3/dist-packages` (hier PIL, bs4, lxml, yaml;
  **kein** numpy/pandas). Seit 2026-10-07 sagt die Beschreibung von
  `run_code` dem Modell genau das (vorher „nur Standardbibliothek").
  Die venv des Projekts liegt im Repo und ist NICHT drin.

**Arbeitsordner:** `~/.cache/zentrale/sandbox/<lauf-id>/` (Einstellung
`sandbox_dir`, Env `ZENTRALE_SANDBOX_DIR`; Tests → tmp). Bewusst NICHT
`data/sandbox/`: `zentrale-sync` spiegelt alles Ungetrackte unter dem Repo
(auch `data/`), additiv — KI-Erzeugnisse wanderten sonst auf den anderen
Rechner und kämen nach dem Aufräumen zurück. Jeder `run_code`-Lauf bekommt
einen frischen Ordner; Ordner älter als 7 Tage löscht `aufraeumen()` vor
jedem Lauf. Neue Dateien meldet das Ergebnis mit Name und Größe (Verweise
werden nicht verfolgt). Das Modell sieht nie den echten Pfad, nur `/arbeit`.
Behalten über 7 Tage hinaus = `save_from_sandbox` in die Ablage — seit
2026-10-07 **gegatet** und nur auf Sashas Wunsch (steht so in der
Beschreibung; „immer" wird dafür nicht angeboten).

## Historie

- **2026-10-07** — Sandbox, Skill-Skripte, Zeitlimit-Stufen, Stoppen,
  `save_from_sandbox` gegatet.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
