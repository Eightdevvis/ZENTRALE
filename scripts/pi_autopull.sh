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

# systemd-Service der nach Deploy neu gestartet wird.
SERVICE_NAME="${SERVICE_NAME:-zentrale.service}"

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
# Schritt 3: Brauchen wir pip install?
# -----------------------------------------------------------------------------
# `pip install -r requirements.txt` dauert auf dem Pi gerne 30+ Sekunden,
# auch wenn nichts neu ist. Wir machen das daher nur dann, wenn sich die
# requirements.txt zwischen lokalem HEAD und origin/$BRANCH ueberhaupt
# geaendert hat.
#
# `git diff --quiet A B -- pfad` -> Exit 0 wenn keine Aenderung, sonst 1.
NEEDS_PIP=0
if ! git diff --quiet "HEAD" "origin/$BRANCH" -- requirements.txt; then
  NEEDS_PIP=1
  log "requirements.txt geaendert -> pip install noetig"
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
    log "Installiere Python-Dependencies (.venv/bin/pip install -r requirements.txt)..."
    if ! .venv/bin/pip install -r requirements.txt >>"$LOG_FILE" 2>&1; then
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
# Schritt 6: Service neu starten
# -----------------------------------------------------------------------------
# `sudo -n` -> non-interactive: wenn ein Passwort verlangt wuerde, schlaegt
# das sofort fehl statt zu haengen. Damit das im Cron klappt braucht der
# ausfuehrende Pi-User passwordless sudo fuer EXAKT diesen Befehl
# (siehe memory/deployment.md, Abschnitt "Auto-Update via RELEASE-Marker").
if sudo -n systemctl restart "$SERVICE_NAME" >>"$LOG_FILE" 2>&1; then
  log "Deploy fertig. Service '$SERVICE_NAME' neu gestartet."
else
  log "ERROR: systemctl restart fehlgeschlagen. Sudoers-Eintrag pruefen."
  exit 1
fi
