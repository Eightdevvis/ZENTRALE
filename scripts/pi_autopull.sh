#!/usr/bin/env bash
# =============================================================================
# pi_autopull.sh
# -----------------------------------------------------------------------------
# Wird per cron (alle 5 Minuten, siehe deploy/zentrale-autopull.cron) auf dem
# Raspberry Pi ausgefuehrt.
#
# GRUNDIDEE:
# Nicht jeder `git push` soll automatisch deployen. Das waere zu nervig –
# kleine Code-Experimente wuerden sofort live gehen. Stattdessen gibt es im
# Repo die Datei `deploy/RELEASE`. Solange ihr Inhalt sich nicht aendert,
# tut dieses Script gar nichts. Erst wenn der Inhalt von RELEASE im Remote
# anders ist als lokal (= du hast bewusst gebumpt und gepusht), wird der
# Pi gepullt + neu gestartet.
#
# WORKFLOW BEIM USER:
#   1. Code aendern, committen, pushen.        -> Pi ignoriert.
#   2. Wenn man deployen will: deploy/RELEASE  -> Zahl hochziehen, commit,
#      push.                                       Pi zieht beim naechsten
#                                                  Cron-Tick und restartet.
#
# DAS SCRIPT WURDE NOCH NICHT AUF EINEM PI GETESTET! Bitte nach Ersteinrichtung
# einmal manuell ausfuehren und Log pruefen, bevor man cron aktiviert.
# =============================================================================

# `set -e` -> Script bricht ab sobald irgendein Befehl mit Exit-Code != 0
# zurueckkommt. `-u` -> ungenutzte Variablen werfen Fehler.
# `-o pipefail` -> wenn in einer Pipeline irgendein Glied failt, faillt die
# ganze Pipeline. Zusammen: laute, ehrliche Fehler statt stiller Korruption.
set -euo pipefail

# -----------------------------------------------------------------------------
# Konfiguration (alle ueber Env-Vars ueberschreibbar)
# -----------------------------------------------------------------------------

# Wo das Repo auf dem Pi liegt. Standardpfad aus deploy_pi.sh.
REPO_DIR="${REPO_DIR:-/opt/zentrale}"

# systemd-Services die nach Deploy neu gestartet werden. Reihenfolge
# matters: zentrale (Core) zuerst, whisper/tts danach (die haben ein
# After=zentrale.service in ihren Unit-Files).
#
# Seit der PC↔Pi-Topologie-Migration (siehe memory/system/topologie.md) sind
# auf einem reinen Display-Pi die ersten drei `disabled` und nur
# pi_sensor_bridge.service ist aktiv. Wir behalten die alte Liste hier
# fuer Solo-Setups (Pi laeuft auch als Backend) und filtern in Schritt 7
# nach `systemctl is-enabled` – so wird jedes Setup richtig bedient
# ohne Konfiguration.
SERVICES=(zentrale.service whisper.service tts.service pi_sensor_bridge.service)

# Branch der ueberwacht wird. Aktuell: main.
BRANCH="${BRANCH:-main}"

# Datei deren Inhalt als Deploy-Trigger dient. Wenn sich diese im Remote
# vom lokalen unterscheidet -> Deploy. Sonst nichts.
RELEASE_FILE="deploy/RELEASE"

# Log-Datei. Default: im Home des ausfuehrenden Users (Pi-User).
LOG_FILE="${LOG_FILE:-$HOME/.zentrale_autopull.log}"

# Wenn AUTOPULL_VERBOSE=1 gesetzt ist, loggen wir auch No-Op-Ticks. Sonst
# bleibt das Log ruhig und wird nur bei tatsaechlichen Aktionen voll.
VERBOSE="${AUTOPULL_VERBOSE:-0}"

# -----------------------------------------------------------------------------
# Logging-Helfer
# -----------------------------------------------------------------------------

# Jede Zeile bekommt einen Timestamp damit man im Nachhinein nachvollziehen
# kann wann der Cron getickt hat und ob er was getan hat.
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Log-Datei auf max ~100 KB begrenzen damit sie nicht ewig waechst.
# `tail -c N` schneidet die letzten N Bytes raus, die schreiben wir zurueck.
# Wir machen das nur wenn die Datei existiert und tatsaechlich zu gross ist.
if [[ -f "$LOG_FILE" ]] && [[ $(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0) -gt 102400 ]]; then
  tail -c 50000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

# Wenn das Repo-Verzeichnis nicht existiert ist die Installation kaputt –
# wir wollen NICHT stillschweigend nichts tun, sondern laut werden.
if [[ ! -d "$REPO_DIR/.git" ]]; then
  log "FATAL: $REPO_DIR ist kein git-Repo. Erstdeployment via scripts/deploy_pi.sh fehlt?"
  exit 1
fi

# Ab hier arbeiten wir im Repo.
cd "$REPO_DIR"

# -----------------------------------------------------------------------------
# Schutz: lokale Aenderungen
# -----------------------------------------------------------------------------
# Wenn jemand auf dem Pi direkt Files editiert hat (z.B. zum Debuggen),
# wuerde `git pull` entweder mergen oder failen. Beides will man nicht
# stillschweigend vom Cron erledigt sehen. Wir brechen daher ab und werden
# laut im Log – der Mensch muss dann manuell entscheiden.
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "ABORT: Working Tree hat lokale Aenderungen. 'git status' im Repo pruefen."
  exit 1
fi

# -----------------------------------------------------------------------------
# Schritt 1: fetch (aendert nichts am Working Tree)
# -----------------------------------------------------------------------------
# `git fetch` holt nur die neuen Refs vom Remote. Unser HEAD bleibt wo er
# ist, keine Datei auf der Platte aendert sich. Erst spaeter, wenn wir
# entschieden haben dass deployt werden soll, kommt der echte `git pull`.
if ! git fetch origin "$BRANCH" 2>>"$LOG_FILE"; then
  log "ERROR: git fetch origin $BRANCH fehlgeschlagen. SSH-Key oder Netz pruefen."
  exit 1
fi

# -----------------------------------------------------------------------------
# Schritt 2: RELEASE-Diff – das eigentliche Trigger-Kriterium
# -----------------------------------------------------------------------------
# `git show <ref>:<pfad>` liest eine Datei direkt aus einem Git-Objekt aus,
# ohne sie auszuchecken. Genau was wir brauchen, weil wir noch nicht
# pullen wollen.
#
# Wir vergleichen:
#   HEAD:deploy/RELEASE              <- Stand der gerade auf dem Pi laeuft
#   origin/main:deploy/RELEASE       <- Stand der gerade gepusht ist
# Sind die identisch -> kein bewusster Bump -> wir beenden ohne Aktion.

CURRENT_RELEASE=$(git show "HEAD:$RELEASE_FILE" 2>/dev/null || echo "")
REMOTE_RELEASE=$(git show "origin/$BRANCH:$RELEASE_FILE" 2>/dev/null || echo "")

if [[ "$CURRENT_RELEASE" == "$REMOTE_RELEASE" ]]; then
  # Haeufigster Pfad: nichts zu tun. Wir loggen das nicht jeden Tick,
  # sonst wird das Log voll. Nur im Verbose-Mode sichtbar.
  if [[ "$VERBOSE" == "1" ]]; then
    log "no-op (RELEASE unveraendert: '$CURRENT_RELEASE')"
  fi
  exit 0
fi

log "RELEASE-Bump erkannt: '$CURRENT_RELEASE' -> '$REMOTE_RELEASE'. Deploy startet."

# -----------------------------------------------------------------------------
# Schritt 3: Brauchen wir pip install? Service-Files geaendert?
# -----------------------------------------------------------------------------
# `pip install -r requirements.txt` dauert auf dem Pi gerne 30+ Sekunden,
# auch wenn nichts neu ist. Wir machen das daher nur dann, wenn sich die
# requirements.txt zwischen lokalem HEAD und origin/$BRANCH ueberhaupt
# geaendert hat.
#
# Genauso bei den systemd-Unit-Files: wenn eines der deploy/*.service-
# Files sich geaendert hat, muss install_pi_services.sh laufen damit das
# Patch nach /etc/systemd/system/ + daemon-reload + enable durchkommt.
# Sonst ruft systemctl restart das alte Unit-File ab und neue Features
# (z.B. die low-prio whisper/tts-Units) wuerden nie wirklich starten.
#
# `git diff --quiet A B -- pfad` -> Exit 0 wenn keine Aenderung, sonst 1.
# Welche Requirements-Datei gilt auf DIESEM Knoten? Ein Aussenposten (Marker
# .aussenposten, gesetzt von deploy_pi.sh) hostet kein Backend und bekommt die
# kurze Liste. Wuerde er die grosse nehmen, zoege ein Backend-only-Paket
# (faster-whisper, sherpa-onnx, piper-tts) per Cron einen minutenlangen
# Quellcode-Build auf den 32-bit-Pi — fuer Code, der dort nie laeuft.
if [[ -f ".aussenposten" ]]; then
  REQ_FILE="deploy/requirements-aussenposten.txt"
else
  REQ_FILE="requirements.txt"
fi

NEEDS_PIP=0
if ! git diff --quiet "HEAD" "origin/$BRANCH" -- "$REQ_FILE"; then
  NEEDS_PIP=1
  log "$REQ_FILE geaendert -> pip install noetig"
fi

NEEDS_UNIT_RELOAD=0
if ! git diff --quiet "HEAD" "origin/$BRANCH" -- 'deploy/*.service' 'deploy/lightdm-*.conf'; then
  NEEDS_UNIT_RELOAD=1
  log "systemd-Unit oder lightdm-Drop-in geaendert -> install_pi_services.sh wird gefeuert"
fi

# -----------------------------------------------------------------------------
# Schritt 4: pull (jetzt erst!)
# -----------------------------------------------------------------------------
# `--ff-only` heisst: nur Fast-Forward erlauben. Falls aus irgendeinem
# Grund auf dem Pi ein lokaler Commit existiert (sollte nicht, aber
# trotzdem), wird der pull verweigert statt zu mergen. Sicherheit vor
# Bequemlichkeit – wir wollen keine Auto-Merges aus dem Cron.
if ! git pull --ff-only origin "$BRANCH" >>"$LOG_FILE" 2>&1; then
  log "ERROR: git pull --ff-only fehlgeschlagen. Manuell aufloesen im Repo-Verzeichnis."
  exit 1
fi

# -----------------------------------------------------------------------------
# Schritt 5: pip install (nur wenn Requirements sich geaendert haben)
# -----------------------------------------------------------------------------
if [[ $NEEDS_PIP -eq 1 ]]; then
  if [[ -x .venv/bin/pip ]]; then
    log "Installiere Python-Dependencies (.venv/bin/pip install -r $REQ_FILE)..."
    if ! .venv/bin/pip install -r "$REQ_FILE" >>"$LOG_FILE" 2>&1; then
      log "ERROR: pip install fehlgeschlagen. Service wird trotzdem NICHT neu gestartet."
      exit 1
    fi
  else
    # deploy_pi.sh nutzt .venv; falls die Installation aelter ist und
    # noch venv (ohne Punkt) verwendet wird, geben wir einen Hinweis
    # statt blind weiterzumachen.
    log "WARN: .venv/bin/pip nicht gefunden – pip-Schritt uebersprungen."
  fi
fi

# -----------------------------------------------------------------------------
# Schritt 6: Unit-Files sync (nur falls geaendert)
# -----------------------------------------------------------------------------
# install_pi_services.sh patcht User= in den drei Unit-Files, kopiert
# nach /etc/systemd/system/, macht daemon-reload + enable. Wird per
# passwordless sudo aufgerufen — der Pfad ist in
# /etc/sudoers.d/zentrale freigegeben (install_pi_sudoers.sh).
if [[ $NEEDS_UNIT_RELOAD -eq 1 ]]; then
  if sudo -n "$REPO_DIR/scripts/install_pi_services.sh" >>"$LOG_FILE" 2>&1; then
    log "Service-Units synchronisiert + daemon-reload."
  else
    log "ERROR: install_pi_services.sh fehlgeschlagen — sudoers-Eintrag pruefen."
    exit 1
  fi
fi

# -----------------------------------------------------------------------------
# Schritt 7: Services neu starten
# -----------------------------------------------------------------------------
# `sudo -n` -> non-interactive: wenn ein Passwort verlangt wuerde, schlaegt
# das sofort fehl statt zu haengen. Damit das im Cron klappt braucht der
# ausfuehrende Pi-User passwordless sudo fuer EXAKT diese Restart-Befehle
# (siehe scripts/install_pi_sudoers.sh).
#
# Reihenfolge: zentrale zuerst, dann whisper/tts. Whisper/TTS haben
# After=zentrale.service in den Units, beim Boot ist das wichtig.
# Beim Restart ist die Reihenfolge "nice to have" — wenn whisper start
# bevor zentrale wieder da ist, faellt es einfach zurueck (Restart=always).
# Nur enabled-Services werden restartet. Damit haut der Autopull nach
# einer Topologie-Migration nicht die disabled-Services wieder hoch.
RESTART_FAIL=0
for SVC in "${SERVICES[@]}"; do
  if ! systemctl is-enabled --quiet "$SVC" 2>/dev/null; then
    # Disabled (oder gar nicht installiert) -> ueberspringen, kein Warning.
    # Dieser Pi nutzt diesen Service einfach nicht.
    continue
  fi
  if sudo -n systemctl restart "$SVC" >>"$LOG_FILE" 2>&1; then
    log "$SVC neu gestartet."
  else
    log "WARN: systemctl restart $SVC fehlgeschlagen (sudoers-Eintrag fuer $SVC?)."
    RESTART_FAIL=1
  fi
done

if [[ $RESTART_FAIL -eq 0 ]]; then
  log "Deploy fertig. Alle Services neu gestartet."
else
  log "Deploy fertig — aber mindestens ein Restart hat gewarnt, siehe oben."
fi
