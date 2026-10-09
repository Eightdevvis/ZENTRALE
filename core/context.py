# core/context.py
#
# Whitelist-basierter Dateizugriff für die ZENTRALE-KI.
#
# Die KI darf nur Dateien lesen die explizit erlaubt sind.
# Verhindert Path-Traversal-Angriffe (z.B. "../../etc/passwd").
#
# Whitelist: Glob-Patterns relativ zum Projektroot.
# Neue Dateitypen einfach in _WHITELIST_PATTERNS eintragen.

import os
import glob
import fnmatch

import nutzer_ordner
import werkzeug_befund

# ── ZWEI REICHWEITEN (seit 2026-10-09) ───────────────────────────────────
# Sasha: der Assistent arbeitet nur mit dem Nutzerordner (~/Zentrale: Input/,
# Output/) und seinem Gedächtnis; Datei- und Code-Zugriff auf ~/codicus gehört
# später zur Coder-App „Codicus". Auf der gross-Schiene (der laufende
# Werkzeug-Aufruf sagt sie, werkzeug_befund.schiene) gilt deshalb NUR Input/
# und Output/ — für read_file, read_pdf/read_docx und fetch_document, die alle
# hier fragen. klein behält vorerst die alte Reichweite (ZENTRALE-Whitelist +
# ~/codicus): das qwen ist darauf gemessen, es zieht später nach.
AUSSERHALB = "Z-AUSSERHALB: liegt nicht in Input/ oder Output/ des Nutzerordners"


def nur_nutzer_ordner() -> bool:
    """Gilt für den laufenden Werkzeug-Aufruf die enge Reichweite?"""
    return werkzeug_befund.schiene() == "gross"


# Absoluter Pfad zum Projektroot (ZENTRALE/)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Sashas Projekt-Wurzel. ZENTRALE liegt darin; sie ist seit 18.08.2026 die
# eigentliche Reichweite der KI ("die ai brauch zugriff auf alles unter
# /codicus/"). Per Env verschiebbar, damit ein anderer Rechner nicht am
# Pfad haengt.
_CODICUS = os.path.abspath(os.path.expanduser(
    os.environ.get('ZENTRALE_CODICUS', '~/codicus')))

# Wurzeln in der Reihenfolge, in der ein relativer Pfad probiert wird.
_WURZELN = [_ROOT, _CODICUS]

# ── VERZEICHNISSE, DIE NIE AUFGEHEN ──────────────────────────────────────
# Nach SEGMENTNAME, nicht nach Pfad — dann greift es auch in Unterordnern.
# Gilt fuer Lesen UND Auflisten: eine Liste, die etwas verschweigt, das
# read_file trotzdem hergibt, waere schlimmer als beides einzeln.
#
# `learning` ist der einzige Eintrag, der keine technische Begruendung hat,
# sondern eine inhaltliche: dort lernt Sasha bewusst OHNE KI-Beteiligung.
# Ihn hier zu fuehren ist eine Entscheidung, keine Notwendigkeit — eine
# Zeile loeschen genuegt, wenn er es anders will.
_GESPERRTE_ORDNER = {
    '.git', '.hg', '.svn',          # Versionsverwaltung: Innereien, kein Inhalt
    'node_modules', 'venv', '.venv', '__pycache__', '.mypy_cache',
    '.pytest_cache', 'site-packages', 'dist', 'build', '.cache',
    'worktrees',                    # Arbeitskopien: dieselben Dateien nochmal
    'learning',                     # Sashas Lernzone — bewusst ohne KI
}

# Welche Dateien darf die KI lesen? Glob-Patterns je Wurzel.
# Unter codicus ist alles frei, was nicht oben gesperrt oder unten Secret
# ist — das war Sashas ausdrueckliche Ansage.
_WHITELIST_PATTERNS = [
    'data/*.json',          # geloggte Daten (Schlaf, etc.)
    'core/*.py',            # eigener ZENTRALE-Code
    'ui/app.py',            # Flask-Backend
    'notes.md',             # deine persönlichen Notizen
]

# Auflistung deckeln: unter einem ganzen Projektbaum waere sie sonst
# tausende Zeilen lang und im Prompt unbezahlbar.
_MAX_LISTE = 300

# ── SECRET-SPERRE (gewinnt IMMER, vor der Whitelist) ─────────────────────
# Die Whitelist ist bewusst breit — und genau dadurch fiel bis 2026-07-17 der
# API-Key-Store `data/ai_config.json` mit hinein: die lokale KI konnte per
# read_file den DASHSCOPE-Key im Klartext lesen (nachgestellt). Keys müssen
# ISOLIERT sein, nicht KI-lesbar.
# Darum: eine harte Denylist, die VOR der Whitelist greift und nach BASENAME
# matcht — ortsunabhängig, damit ein Verschieben oder ein Unterordner nichts
# aufweicht.
#
# Seit die Reichweite ein ganzer Projektbaum ist, traegt diese Liste
# ungleich mehr: in fremden Repos liegen .env-Dateien, Deploy-Keys und
# Token-Caches, an die vorher niemand denken musste. Deny-by-default fuer
# Secrets: neue Secret-Dateien hier eintragen, nicht darauf hoffen, dass die
# Whitelist sie zufaellig nicht trifft.
_SECRET_BASENAMES = {
    'ai_config.json',       # core/ai_config.py: Kill-Switches + API-KEY-Store
    'tutor_config.json',    # Legacy-Key-Heimat (+ heute Tutor-Wahl)
    '.netrc', '.npmrc', '.pypirc', '.git-credentials',
    'credentials', 'credentials.json', 'secrets.json',
}
_SECRET_SUFFIXES = (
    '.enc',                 # verschlüsselter Mail-Blob (core/mail_secrets.py)
    '.key', '.pem', '.p12', '.pfx', '.jks',
)
# Namensmuster, die fast immer ein Geheimnis tragen. Nach Basename.
_SECRET_MUSTER = ('.env', 'id_rsa', 'id_ed25519', 'id_ecdsa',
                  'secret', 'token', 'passwor', 'apikey', 'api_key')


def _is_secret(rel_path: str) -> bool:
    base = os.path.basename(rel_path).lower()
    if base in _SECRET_BASENAMES or base.endswith(_SECRET_SUFFIXES):
        return True
    return any(m in base for m in _SECRET_MUSTER)


def _gesperrt(pfad: str) -> bool:
    """Liegt der Pfad in einem gesperrten Ordner? Nach Segmentnamen."""
    teile = os.path.normpath(pfad).split(os.sep)
    return any(t in _GESPERRTE_ORDNER for t in teile)


def erlaubt(abs_pfad: str) -> str:
    """Darf die KI diese Datei sehen? -> "" wenn ja, sonst der Grund.

    EINE Instanz fuer die Frage: read_file fragt hier, und
    gedaechtnis.dokument_holen fragt beim Ablegen lokaler Dateien
    ebenfalls hier. Zwei Antworten auf dieselbe Frage waeren die Sorte
    Sicherheitsluecke, die niemand bemerkt.
    """
    abs_pfad = os.path.abspath(abs_pfad)
    if nur_nutzer_ordner() and not nutzer_ordner.im_unterordner(abs_pfad):
        return AUSSERHALB
    # Sashas Nutzerordner (Input/, Output/; core/nutzer_ordner.py, seit
    # 2026-10-09): dort liegt, was er der KI gibt — lesbar bis auf Secrets
    # und Verstecktes. Verweise werden aufgelöst: wer von dort hinauszeigt,
    # ist nicht drin.
    if nutzer_ordner.ist_drin(abs_pfad):
        rel = os.path.relpath(os.path.realpath(abs_pfad), nutzer_ordner.wurzel(anlegen=False))
        if any(t.startswith('.') for t in rel.split(os.sep)) or _is_secret(rel):
            return "Secret- oder versteckte Datei, fuer die KI gesperrt"
        return ""
    innen = next((w for w in _WURZELN
                  if abs_pfad == w or abs_pfad.startswith(w + os.sep)), None)
    if innen is None:
        return "ausserhalb von ZENTRALE und ~/codicus"
    rel = os.path.relpath(abs_pfad, innen)
    if _gesperrt(rel):
        return "liegt in einem gesperrten Ordner"
    if _is_secret(rel):
        return "Secret-Datei, fuer die KI gesperrt"
    if innen == _CODICUS:
        return ""                      # unter codicus ist der Rest frei
    return ("" if any(fnmatch.fnmatch(rel, p) for p in _WHITELIST_PATTERNS)
            else "nicht auf der Whitelist")

# ── ANHÄNGE: was Sasha selbst in den Chat gibt (seit 2026-10-07) ─────────
# `/anhang <pfad>` im Chat (core/anhang.py). Anders als read_file darf ein
# Anhang von ÜBERALL kommen (~/Downloads, ein USB-Stick) — Sasha nennt ihn ja
# selbst. Gesperrt bleibt, was nie zu einem Anbieter gehen darf, auch nicht
# aus Versehen: die Secret-Sperre oben (nach Dateiname) und Orte, an denen
# Schlüssel, Passwörter und Sashas Rohdaten liegen.
_ANHANG_ORDNER = ('.git', '.hg', '.svn', 'learning')   # nach Segmentname
_ANHANG_ORTE_HOME = (
    '.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.password-store',
    '.config/gcloud', '.config/gh', '.config/rclone', '.local/share/keyrings',
    '.mozilla', '.thunderbird', '.config/google-chrome', '.config/chromium',
    '.config/BraveSoftware', '.local/share/zentrale',   # dort liegt die Datensicherung
)
_ANHANG_ORTE_SYSTEM = ('/proc', '/sys', '/dev', '/root', '/etc/shadow',
                       '/etc/gshadow', '/etc/ssl/private')
_ANHANG_MUSTER = ('credential',)            # z. B. ~/.claude/.credentials.json


def _unter(pfad: str, ort: str) -> bool:
    return pfad == ort or pfad.startswith(ort.rstrip(os.sep) + os.sep)


def anhang_gesperrt(pfad: str) -> str:
    """Darf diese Datei als Anhang zur KI? -> "" wenn ja, sonst der Grund
    (Alltagssprache, Sasha liest ihn in der Statuszeile).

    Gesperrt: Secret-Dateinamen (wie für read_file), jedes data/ und
    tutor/data/ von ZENTRALE (Schlüssel, Mail-Zugänge, Gedächtnis), Lernzone
    und Versionsverwaltung, Schlüssel- und Browser-Ordner im Home, System-
    Innereien. Der Pfad wird vorher aufgelöst (Verweise, `..`)."""
    roh = os.path.expanduser(str(pfad or "").strip())
    if not roh:
        return "kein Pfad"
    voll = os.path.realpath(roh)
    if _is_secret(voll) or any(m in os.path.basename(voll).lower()
                               for m in _ANHANG_MUSTER):
        return "das sieht nach einem Schlüssel oder Passwort aus"
    teile = os.path.normpath(voll).split(os.sep)
    if any(t in _ANHANG_ORDNER for t in teile):
        return "der Ordner ist für die KI gesperrt"
    # ZENTRALEs Daten — in diesem Checkout UND in jedem anderen (Worktrees,
    # eine zweite Kopie): erkannt an data/ neben core/.
    for i in range(len(teile) - 1, 0, -1):
        if teile[i] == "data":
            eltern = os.sep.join(teile[:i]) or os.sep
            if os.path.isdir(os.path.join(eltern, "core")) or \
                    os.path.basename(eltern) == "tutor":
                return "Dateien aus ZENTRALEs data/ gehen nicht als Anhang"
    for daten in (os.path.join(_ROOT, "data"), os.path.join(_ROOT, "tutor", "data")):
        if _unter(voll, os.path.realpath(daten)):
            return "Dateien aus ZENTRALEs data/ gehen nicht als Anhang"
    home = os.path.realpath(os.path.expanduser("~"))
    for ort in _ANHANG_ORTE_HOME:
        if _unter(voll, os.path.join(home, ort)):
            return "der Ordner enthält Schlüssel oder Zugangsdaten"
    for ort in _ANHANG_ORTE_SYSTEM:
        if _unter(voll, ort):
            return "Systemdatei — geht nicht als Anhang"
    return ""


# Maximale Dateigröße die an die KI geschickt wird.
# Größere Dateien werden abgeschnitten um den Context-Limit nicht zu sprengen.
_MAX_CHARS = 8000


def list_available_files() -> list:
    """
    Alle lesbaren Dateien. Wird von der KI über das list_files-Tool gerufen.

    Unter ZENTRALE weiter nach Whitelist-Pattern; unter ~/codicus wird der
    Baum abgelaufen — mit Pruning an den gesperrten Ordnern, sonst zaehlt
    man .git und node_modules durch. Gedeckelt auf _MAX_LISTE: eine
    Auflistung, die tausend Zeilen lang ist, hilft niemandem und kostet im
    Prompt echtes Geld.
    """
    eigen, fremd = [], []
    for pattern in _WHITELIST_PATTERNS:
        for match in glob.glob(os.path.join(_ROOT, pattern)):
            rel = os.path.relpath(match, _ROOT)
            if _is_secret(rel) or _gesperrt(rel):
                continue
            eigen.append(rel)

    if os.path.isdir(_CODICUS):
        for wurzel, ordner, dateien in os.walk(_CODICUS):
            ordner[:] = [o for o in ordner
                         if o not in _GESPERRTE_ORDNER and not o.startswith('.')]
            for name in dateien:
                rel = os.path.relpath(os.path.join(wurzel, name), _CODICUS)
                if _is_secret(rel) or name.startswith('.'):
                    continue
                fremd.append(rel)

    # ZENTRALEs eigene Dateien ZUERST, und zwar vollstaendig. Sonst frisst
    # ein alphabetisch fruehes Fremdprojekt den Deckel auf und ausgerechnet
    # das, was sie taeglich braucht, faellt heraus.
    eigen = sorted(set(eigen))
    fremd = sorted(set(fremd))
    rest = max(0, _MAX_LISTE - len(eigen))
    aus = eigen + fremd[:rest]
    if len(fremd) > rest:
        aus.append(f"… [{len(fremd) - rest} weitere unter ~/codicus nicht "
                   f"gelistet — read_file erreicht sie trotzdem]")
    return aus


def pfad_aufloesen(roh: str) -> str:
    """Ein Pfad, wie die KI ihn nennt → absoluter Pfad (noch NICHT
    erlaubt-geprüft). gross (2026-10-09): relativ zum Nutzerordner
    („Input/x.md", „Output/y.pdf"; ein bloßer Name meint Input/). klein:
    relativ zu ZENTRALE, dann ~/codicus, zuletzt der
    Nutzerordner („Input/x.md", seit 2026-10-09 — zuletzt, damit kein
    bisheriger Pfad etwas anderes trifft); der erste, den es gibt, sonst der
    erste überhaupt (für die Fehlermeldung). Eine Stelle für read_file,
    read_pdf/read_docx und fetch_document (2026-10-09: vorher drei Kopien,
    und nur read_file kannte Input/)."""
    roh = os.path.expanduser(str(roh or "").strip())
    if os.path.isabs(roh):
        return os.path.abspath(roh)
    if nur_nutzer_ordner():
        # gross: relativ heißt im Nutzerordner, ein bloßer Name in Input/.
        return nutzer_ordner.pfad(roh)
    kandidaten = [os.path.join(w, roh) for w in _WURZELN]
    kandidaten.append(os.path.join(nutzer_ordner.wurzel(anlegen=False), roh))
    return os.path.abspath(next((k for k in kandidaten if os.path.exists(k)), kandidaten[0]))


def read_file(relative_path: str) -> str:
    """
    Liest eine Datei, wenn die KI sie sehen darf.

    Der Pfad darf relativ (pfad_aufloesen: auf gross zum Nutzerordner, auf
    klein zu ZENTRALE bzw. ~/codicus) oder absolut sein. Ueber die Erlaubnis entscheidet allein `erlaubt()` — dort stehen
    Wurzeln, gesperrte Ordner und Secret-Sperre an einer Stelle.

    `..` braucht keine eigene Pruefung mehr: der Pfad wird aufgeloest und
    muss danach INNERHALB einer Wurzel liegen. Wer hinausklettert, faellt
    aus der Wurzel und damit durch.
    """
    roh = (relative_path or "").strip()
    if not roh:
        return "[Kein Pfad angegeben]"

    abs_path = pfad_aufloesen(roh)

    grund = erlaubt(abs_path)
    if grund:
        return f"[Zugriff verweigert: {grund}]"
    if not os.path.exists(abs_path):
        if nur_nutzer_ordner():
            # Sagen, WO gesucht wurde: „core/x.py" heißt hier Input/core/x.py.
            return f"[Datei nicht gefunden: {nutzer_ordner.anzeige(abs_path)}]"
        return f"[Datei nicht gefunden: {roh}]"
    if os.path.isdir(abs_path):
        return f"[{roh} ist ein Verzeichnis — nutz list_files]"

    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(_MAX_CHARS + 1)
        if len(content) > _MAX_CHARS:
            content = (content[:_MAX_CHARS]
                       + f"\n\n... [nach {_MAX_CHARS} Zeichen abgeschnitten]")
        return content
    except Exception as e:
        return f"[Lesefehler bei '{roh}': {e}]"
