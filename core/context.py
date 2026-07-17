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

# Absoluter Pfad zum Projektroot (ZENTRALE/)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Welche Dateien darf die KI lesen?
# Glob-Patterns relativ zum Projektroot.
_WHITELIST_PATTERNS = [
    'data/*.json',          # geloggte Daten (Schlaf, etc.)
    'core/*.py',            # eigener ZENTRALE-Code
    'ui/app.py',            # Flask-Backend
    'notes.md',             # deine persönlichen Notizen
]

# ── SECRET-SPERRE (gewinnt IMMER, vor der Whitelist) ─────────────────────
# Die Whitelist ist bewusst breit (`data/*.json` deckt alle Logs ab) — und
# genau dadurch fiel bis 2026-07-17 der API-Key-Store `data/ai_config.json`
# mit hinein: die lokale KI konnte per read_file den DASHSCOPE-Key im Klartext
# lesen (nachgestellt). Keys müssen ISOLIERT sein, nicht KI-lesbar.
# Darum: eine harte Denylist, die VOR der Whitelist greift und nach BASENAME
# matcht — ortsunabhängig, damit ein Verschieben oder ein Unterordner nichts
# aufweicht (read_file nutzt fnmatch, dessen `*` sowieso über `/` matcht).
# Deny-by-default für Secrets: neue Secret-Dateien hier eintragen, nicht
# darauf hoffen, dass die Whitelist sie zufällig nicht trifft.
_SECRET_BASENAMES = {
    'ai_config.json',       # core/ai_config.py: Kill-Switches + API-KEY-Store
    'tutor_config.json',    # Legacy-Key-Heimat (+ heute Tutor-Wahl)
}
_SECRET_SUFFIXES = (
    '.enc',                 # verschlüsselter Mail-Blob (core/mail_secrets.py)
    '.key', '.pem',         # generische Schlüssel-/Zertifikatsdateien
)


def _is_secret(rel_path: str) -> bool:
    base = os.path.basename(rel_path).lower()
    return base in _SECRET_BASENAMES or base.endswith(_SECRET_SUFFIXES)

# Maximale Dateigröße die an die KI geschickt wird.
# Größere Dateien werden abgeschnitten um den Context-Limit nicht zu sprengen.
_MAX_CHARS = 8000


def list_available_files() -> list:
    """
    Gibt alle aktuell vorhandenen lesbaren Dateien zurück.
    Wird von der KI über das list_files-Tool aufgerufen.
    """
    files = []
    for pattern in _WHITELIST_PATTERNS:
        full_pattern = os.path.join(_ROOT, pattern)
        for match in glob.glob(full_pattern):
            rel = os.path.relpath(match, _ROOT)
            if _is_secret(rel):      # Secrets nie auflisten (Existenz nicht verraten)
                continue
            files.append(rel)
    return sorted(files)


def read_file(relative_path: str) -> str:
    """
    Liest eine Datei wenn sie auf der Whitelist steht.

    Sicherheit:
      1. Pfad wird zu absolutem Pfad aufgelöst (verhindert .. Traversal)
      2. Muss innerhalb des Projektrootverzeichnisses liegen
      3. Muss einem Whitelist-Pattern entsprechen

    Rückgabe: Dateiinhalt als String, oder Fehlermeldung.
    """
    # Absoluten Pfad bestimmen und normalisieren
    abs_path = os.path.abspath(os.path.join(_ROOT, relative_path))

    # Sicherheitscheck 1: Datei muss im Projektroot liegen
    # os.sep am Ende verhindert dass "/home/sasha/codicus/ZENTRALE_evil" durchkommt
    if not abs_path.startswith(_ROOT + os.sep) and abs_path != _ROOT:
        return "[Zugriff verweigert: außerhalb des Projektverzeichnisses]"

    rel_path = os.path.relpath(abs_path, _ROOT)

    # Sicherheitscheck 2: SECRET-SPERRE (vor der Whitelist — Keys sind tabu,
    # egal ob ein Whitelist-Pattern sie zufällig träfe).
    if _is_secret(rel_path):
        return "[Zugriff verweigert: Secret-Datei ist für die KI gesperrt]"

    # Sicherheitscheck 3: Whitelist
    allowed = any(fnmatch.fnmatch(rel_path, p) for p in _WHITELIST_PATTERNS)
    if not allowed:
        return f"[Zugriff verweigert: '{rel_path}' ist nicht auf der Whitelist]"

    if not os.path.exists(abs_path):
        return f"[Datei nicht gefunden: {rel_path}]"

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Zu große Dateien kürzen (LLM-Context-Limit schützen)
        if len(content) > _MAX_CHARS:
            content = content[:_MAX_CHARS] + f"\n\n... [nach {_MAX_CHARS} Zeichen abgeschnitten]"

        return content

    except Exception as e:
        return f"[Lesefehler bei '{rel_path}': {e}]"
