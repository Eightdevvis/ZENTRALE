# Setup & Installation

**Neues Gerät ohne Checkout (seit 2026-10-22):** `deploy/install.sh`, unten
„Installieren mit install.sh". Der Rest dieser Datei gilt für Sashas
Entwickler-Checkouts (Laptop, PC).

**Stand 2026-09-18:** Ein Backend-Knoten (der PC) braucht venv +
`requirements.txt` + Test-Riegel (`scripts/zentrale-venv-guard`), Ollama mit
`qwen3.5:9b`, Whisper (lädt sich beim ersten Start selbst) und die TTS-Modelle
für **drei** Sprachen (`zh` sherpa-onnx, `de` Piper, `es` sherpa-onnx mit
Piper-Voice) unter
`data/tts_model/`. Der Pi bekommt nichts davon — er ist Aussenposten (siehe
`memory/betrieb/deployment.md`). Der Riegel hängt sich beim TUI-Start selbst
ein, falls er fehlt.

## Installieren mit install.sh (Vollknoten, seit 2026-10-22)

Für ein neues Gerät ohne Git-Checkout (Mini-PC mit **EndeavourOS**, später
jeder Kunde) — Bauplan: [../hub/knoten_beitritt.md](../hub/knoten_beitritt.md),
„Bauplan v1". Sasha tippt die Befehle selbst; hier in Worten:

1. `install.sh` von der Cloud laden (öffentlich, `<cloud>/install.sh`) und mit
   bash ausführen, den **Einladungscode** als Argument oder auf Nachfrage.
2. Das Skript prüft Python ≥ 3.11, das venv-Modul und curl. Fehlt etwas,
   nennt es die Pakete je Paketverwaltung und hört auf — es installiert nie
   etwas mit Root:

   | Familie | erkannt an | fehlt typischerweise |
   |---|---|---|
   | apt | Debian, Ubuntu, Pop!_OS | `python3-venv`; optional `libportaudio2` (Ton) |
   | pacman | Arch, **EndeavourOS**, Manjaro | nichts (Python bringt venv mit); optional `portaudio` |
   | sonst | — | allgemeiner Hinweis |

3. Es holt `GET /v1/paket?code=…`, lädt das Paket, **prüft sha256**, entpackt
   nach `~/.local/share/zentrale/hub/<fassung>/`, baut dort ein venv mit
   `requirements-basis.txt` (ohne Whisper/TTS/sherpa/Piper/pygame), dreht
   `hub/aktuell` auf die Fassung und verlinkt `~/.local/bin/zentrale`.
4. **Keeper (since 2026-10-30, build step 1 of
   [../hub/building_kit_plan.md](../hub/building_kit_plan.md)):** right after
   linking it runs `zentrale timers install`, before any login — the timers
   then simply exit 0 until the device is set up. If that fails, one warning
   line; the install still finishes.
5. Ist `~/.local/bin` nicht im PATH, sagt es, wie es für bash, zsh und fish
   dazukommt. Dann `zentrale welcome`, and — when a terminal is attached
   (since 2026-10-30, also under `curl … | bash`, it reads /dev/tty) — the
   setup wizard right away. Otherwise the first `zentrale` starts it.

Developer and test runs only: `ZENTRALE_REUSE_VENV=<venv>` makes install.sh
(and `zentrale update`) link that venv instead of building one — used by
`zentrale dev` ([dev_mode.md](dev_mode.md)) and the tests.

**The setup wizard `zentrale setup`** (since 2026-10-30, build steps 2 and 3
of [../hub/building_kit_plan.md](../hub/building_kit_plan.md), 5.1;
`zentrale_cli/wizard.py`). One guided dialog, steps as data (`STEPS`), each
question with its default on Enter and `b` = back:

| # | Step | Asked when | Answer goes to |
|---|---|---|---|
| 1 | account: log in / create / stay local | not logged in | `konto.json` |
| 2 | cloud folder (~/Zentrale/Cloud), default yes | logged in | `abgleich_apps.cloud_folder` |
| 3 | auto-update, default on | installed by install.sh (channel `script`) | setting `auto_update` |
| 4 | keep syncing when logged out (linger), default yes | logged in and systemd + loginctl there | `loginctl --no-ask-password enable-linger <own user>`; never sudo; refused → one sentence how |
| 5 | what is this device for: apps with data (all / pick / none) | logged in | `abgleich_apps` ([cloud_app.md](../hub/cloud_app.md)) |

Then (with an account): cloud on, device registered, one sync, **timers**
(next section). Every answer is applied right away (idempotent); where an
unfinished first setup stopped is the setting `setup_wizard_at`, and the
next `zentrale setup` picks up there. On a set-up device `zentrale setup`
re-opens the wizard from the start (logged in → no account question). The
TUI has no setup of its own yet; a second front uses the same `STEPS`.
`zentrale status` shows `Auto-update` and `Background` (keeps syncing when
logged out / only while logged in). Tests: `tests/test_setup_wizard.py`,
`tests/test_dev_mode.py` (real install, wizard to the end, step *n*).

## Timer (seit 2026-10-24)

Ohne Timer gleicht ein Gerät nur bei `zentrale sync` ab und nimmt nie die
Kalender-Brücke ([../hub/adapter.md](../hub/adapter.md)). Zwei
systemd-**User**-Timer, gerendert von `zentrale_cli/timer.py` nach
`~/.config/systemd/user/`:

| Timer | wann | ruft |
|---|---|---|
| `zentrale-abgleich` | alle 5 min | `zentrale sync --automatic` (nur mit Weg `mitte`, still, nie eine Frage) |
| `zentrale-kalender-sync` | alle 3 min | `zentrale adapter run` (= `scripts/kalender_sync.py zentrale`) |
| `zentrale-update` (since 2026-10-30) | daily, `RandomizedDelaySec=1h` | `zentrale update --automatic` (below, „Updates") |

- **Pfad in der Einheit je Kanal**, überlebt jedes Update: install.sh →
  `~/.local/share/zentrale/hub/aktuell/bin/zentrale`; apt/pacman →
  `/usr/bin/zentrale` (Starter); Checkout → `<checkout>/bin/zentrale`.
- **Installed by the installer** (install.sh, since 2026-10-30), again by
  `zentrale setup`, and **again after every `zentrale update`** — by the NEW
  release's `zentrale timers install`, so a unit added in a later release
  reaches every node that updates. Idempotent; a failure never undoes the
  update (one line: run `zentrale timers install`). Ohne systemd --user ein
  Satz, die Einrichtung geht weiter. Nie sudo.
- `zentrale timers` zeigt Dateien, an/aus, nächster Lauf, letztes Ergebnis;
  `zentrale timers install` repariert (idempotent, schreibt nur Geändertes),
  `zentrale timers remove` schaltet ab und löscht nur eigene Dateien
  (erkannt an der Kopfzeile „Rendered by `zentrale timers install`").
- **Self-heal** (since 2026-10-30): every successful `timers install` writes
  its release to `~/.local/share/zentrale/keeper.json`; `sync --automatic`
  (new code via `aktuell`) runs `timers install` once when the release
  differs — so a node updated by an old release without the keeper still
  gets new units within 5 minutes. Not in a developer checkout.
- Without lingering they run only while the user is logged in (User-systemd);
  the wizard asks for lingering (above), `status` says which.
- `adapter run` ohne Kalender-Anschluss und ohne eigene
  vdirsyncer-Konfiguration: still nichts. Ohne vdirsyncer bleibt das Gerät
  Verbraucher; `setup`, `status` und `timers` nennen das Paket
  (pacman: `vdirsyncer`, apt: `vdirsyncer`), installiert wird nichts.
- **Sashas Laptop (Umstieg):** die alten Einheiten in `deploy/` (Pfad
  `%h/codicus/ZENTRALE`) heißen genauso. `zentrale timers install` ersetzt den
  Verweis nach `deploy/` durch die gerenderte Datei (nie durch den Verweis
  hindurch) und schaltet den Timer neu ein (`reenable`). Wer nichts tut,
  behält die alten — sie laufen weiter wie bisher.
- Tests: `tests/test_timer.py` (falsches systemctl: `devkit/fake_systemd.py`,
  the same one `zentrale dev` uses), `tests/test_dev_mode.py` (real install.sh
  and update with it); conftest setzt `ZENTRALE_SYSTEMCTL=aus`, unter pytest
  ohne Umlenkung gilt systemd als nicht da.

**Aufbau auf dem Gerät:**

```
~/.local/share/zentrale/
  data/                  die Daten — überleben jede neue Fassung
  hub/<fassung>/         Programm + venv; data → ../../data
  hub/aktuell            Verweis auf die laufende Fassung
  abgleich/              Basis, Vorhaben, Hinweise (wie bisher)
~/.local/bin/zentrale    → hub/aktuell/bin/zentrale
~/.config/zentrale/konto.json   Benutzername, Sitzung, Kontoschlüssel (600), nur nach Login — keine Mail
```

- **Schutz für Sashas Laptop:** Liegt in `~/.local/bin/zentrale` schon etwas,
  das KEIN Verweis nach `~/.local/share/zentrale` ist, bricht das Skript ab
  und fasst es nicht an.
- **Updates:** `zentrale update` holt die neue Fassung daneben, prüft sha256,
  baut ihr venv, runs its **self-test** (`<new>/bin/zentrale version --check`:
  imports, reads settings, reaches the cloud) und dreht erst dann `hub/aktuell`
  um, then the new release's keeper and a restart of a running
  `zentrale-kern.service`. Self-test fails → stays, the new folder is removed,
  one note. Die alte bleibt bis zum nächsten Update liegen (Rückweg: den
  Verweis zurückdrehen).
- **Automatic (since 2026-10-30):** the `zentrale-update` timer runs
  `zentrale update --automatic`: nothing new → quiet; new and setting
  `auto_update` on (default) → as above, a release that failed its self-test
  is not tried again automatically. Off, or apt/pacman → only remembered:
  `status` and the line before the TUI say "Update available: X → Y". State:
  `~/.local/share/zentrale/update.json`. Switch: `zentrale update auto on|off`.
  Tests: `tests/test_auto_update.py`, `tests/test_dev_mode.py`. Im
  Entwickler-Checkout weigert sich `update` (dort gilt git), bei apt/pacman
  verweist es auf die Paketverwaltung ([verteilung.md](verteilung.md)).
- **Die Cloud-Adresse** steht an einer Stelle: `VORGABE` in
  `core/cloud_api.py`; `deploy/install.sh` bekommt sie beim Rendern
  (`CLOUD_VORGABE`). Env `ZENTRALE_CLOUD` überstimmt beide.
- **`deploy/install.sh` ist gerendert** aus `deploy/install.sh.in` nach dem
  Schalter `deploy/verteilung.toml` — nie von Hand ändern
  ([verteilung.md](verteilung.md)).
- **Paket bauen:** `scripts/paket_bauen.py` aus der Positivliste
  `deploy/paket.txt` (nur eingecheckte Dateien) → `dist/zentrale-<fassung>.tar.gz`
  + `dist/neueste.json` (`{version, sha256, groesse}` wie `GET /v1/paket`).
  Fassung aus `deploy/RELEASE`. Hochladen in die Cloud macht der Server-Teil.
  .deb, PKGBUILD und install.sh aus demselben tar.gz: [verteilung.md](verteilung.md).
- **Ohne lokale KI geprüft (22.10.):** Backend (`core/main.py`, `ui/app.py`
  mit allen Routen) und TUI importieren sauber, wenn faster-whisper,
  sherpa-onnx, piper, webrtcvad, keyboard und pygame fehlen. Ein ganzer Lauf
  auf einem frischen Gerät steht noch aus.

## Python-Umgebung (Entwickler-Checkout)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
scripts/zentrale-venv-guard
```

Der dritte Schritt hängt den Test-Riegel ins venv (Symlink auf
`scripts/zentrale_testguard.py` plus `.pth`-Zeile) und **gehört nach jedem
venv-Neubau dazu**: ohne ihn schaltet ein Testlauf aus einer älteren
Arbeitskopie Sashas echtes Theme um — die Erklärung steht in
`memory/system/dashboard.md` („Warum das Theme trotzdem noch sprang"). Der
Aufruf ist idempotent.

**Auf JEDEM Knoten nötig, und deshalb automatisiert.** Der Riegel lebt im venv,
das venv liegt nicht in git — ein `git pull` bringt ihn also nicht mit.
`start_tui.sh` hängt ihn deshalb beim Start selbst ein, falls er fehlt (still,
idempotent) — der TUI-Start ist die eine Stelle, die auf jedem Knoten läuft.
Der Aufruf oben bleibt für Maschinen, die die TUI nie starten. (Warum das
nötig wurde: siehe Historie.)

## Ollama + Modell

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:9b
```

Standardmäßig erwartet ZENTRALE Ollama unter `http://localhost:11434`
und greift auf das Modell `qwen3.5:9b` zu (siehe `memory/betrieb/starten.md` für
Env-Override `OLLAMA_MODEL`). Andere Tool-Use-fähige Ollama-Modelle
funktionieren ohne Code-Änderung, einfach pullen und Env-Var setzen.

## Whisper-Modell

Wird beim ersten Start des `whisper_service.py` automatisch geladen
(Default-Größe `small`, ca. 500 MB). Nichts zu tun – aber Geduld beim
ersten Run.

Modellgröße via Env-Var wechseln (Trade-off Größe vs. Qualität):

```bash
WHISPER_MODEL=tiny   venv/bin/python services/whisper_service.py  # ~75 MB
WHISPER_MODEL=base   venv/bin/python services/whisper_service.py  # ~150 MB
WHISPER_MODEL=small  venv/bin/python services/whisper_service.py  # ~500 MB (default)
WHISPER_MODEL=medium venv/bin/python services/whisper_service.py  # ~1.5 GB
```

## TTS-Modelle (sherpa-onnx + Piper)

Eine Engine je Sprache, alle werden parallel von `tts_service.py` geladen
(Engine-Registry `_engines[<code>]`):

- `zh` – sherpa-onnx, Stimme der Persona Ling Ling. `_try_load_sherpa_zh` lädt das
  beste vorhandene Modell: **`matcha-icefall-zh-baker` (22 kHz) > MeloTTS
  `vits-melo-tts-zh_en` (44.1 kHz) > `vits-zh-aishell3` (~120 MB, 8 kHz, Fallback)**.
- `es` – sherpa-onnx mit einer Piper-Voice (dieselbe Library wie zh, kein
  separates `piper-tts`), Stimme der Persona Lucía, Voice via Env
  `TUTOR_ES_VOICE` (Default `vits-piper-es_ES-sharvard-medium-int8`,
  Sprecher `TUTOR_ES_SPEAKER` Default 1 = weiblich).
- `de` – Piper, Voice via Env `PIPER_DE_VOICE` (Default `de_DE-kerstin-low`,
  ~20 MB; Haupt-Chat und die Persona Lena).

Einmaliger Download nach `data/tts_model/<voice>/`:

```bash
sudo chown -R $USER:$USER data/   # falls data/ root gehört
venv/bin/python services/download_tts_model.py        # alle laden
# oder gezielt:
venv/bin/python services/download_tts_model.py zh
venv/bin/python services/download_tts_model.py de
venv/bin/python services/download_tts_model.py es
```

Neue Sprache hinzufügen: Modell-Loader in `services/tts_service.py`
ergänzen (`_try_load_<lang>()`) und in `download_tts_model.py` einen
neuen `download_<lang>()` anlegen. Was sonst noch zu einer neuen
Tutor-Sprache gehört: Repo `language-tutor`, `docs/bauplan.md` Abschnitt 4 (Checkliste).

## System-Pakete (für Pi)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

Für Audio-Output am Pi: siehe `memory/betrieb/hardware.md` (Audio am Pi).

## Historie

- **2026-08-18** — Test-Riegel fehlte auf dem Laptop (venv nicht in git):
  auf einem Knoten scharf, auf dem anderen sprang das Theme weiter, während
  die erste Maschine „bewiesen ruhig" war. Seither hängt `start_tui.sh` ihn
  selbst ein.
- **2026-07-23** — `es` (sherpa-onnx, Piper-Voice es_ES-sharvard, weiblich) als Stimme für
  Lucía; bis dahin gab es nur `zh` + `de`.
- **2026-09-18** — `de` auch als Tutor-Sprache (Lena), nutzt die
  Haupt-Chat-Stimme.
