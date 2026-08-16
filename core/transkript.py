# core/transkript.py
#
# Was gesagt wurde — die Schicht UNTER dem Konzept-Graphen.
#
# ── Warum es das braucht ────────────────────────────────────────────────
# Der Graph merkt sich, DASS eine Beziehung besteht: `Sasha ─[besitzt]─►
# Falter`. Er merkt sich nicht, WAS gesagt wurde. Das ist als Gedächtnis-
# Struktur richtig (assoziativ, klein, schnell aktivierbar), aber es ist
# eine Einbahnstraße: aus „Sasha besitzt Falter" kommt nie wieder heraus, dass
# es ein blaues Klapprad ist und dass der Name von einem Falter kommt, den er
# an dem Tag gesehen hat. Der Extraktor destilliert, und was er wegwirft, ist
# weg.
#
# Also legen wir das Rohmaterial daneben. Append-only, nach Monat getrennt,
# und der Graph merkt sich pro Knoten nur die IDs der Zeilen, aus denen er
# stammt (`quellen`).
#
# ── Was das ausdrücklich NICHT ist ──────────────────────────────────────
# Kein zweiter Suchindex. Hier wird nie gesucht, nie embedded, nie etwas in
# den Prompt geladen. Die Datei ist ein Archiv, auf das der Graph zeigt —
# nachschlagen kann man sie, wenn man wissen will, woher ein Knoten kommt.
# Würde sie durchsucht, hätten wir zwei konkurrierende Gedächtnisse mit
# unterschiedlichen Antworten; genau das soll der Graph verhindern.
#
# ── Trennung der Graphen ────────────────────────────────────────────────
# Der Cloud-Graph bekommt eigene Dateien (`cloud-YYYY-MM.jsonl`). Beide
# bleiben im Haus — aber welcher Turn zu welchem Gedächtnis gehört, darf
# nicht verwischen, sonst ist die Isolations-Invariante nur noch halb wahr.
#
# ── Form ────────────────────────────────────────────────────────────────
#   {"id": "2026-08:17", "zeit": "2026-08-16T14:33:02", "user": "…", "ai": "…"}
#
# Die id ist Monat + Zeilennummer. Damit findet man die Zeile ohne Index und
# ohne Zufallszahl — und sie sortiert von allein.

import json
import os
from datetime import datetime
from threading import Lock

_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                     'data', 'ai_transcripts'))
_lock = Lock()

# So viele Quell-IDs behält ein Knoten. Ein oft erwähntes Konzept sammelt
# sonst hunderte, und der Graph soll klein bleiben — die ältesten fallen raus,
# die jüngsten sind die, nach denen man fragt.
MAX_QUELLEN = 20


def _monat() -> str:
    return datetime.now().strftime("%Y-%m")


def datei(store: str | None = None, monat: str | None = None) -> str:
    """Pfad der Transkript-Datei für diesen Graphen und Monat."""
    praefix = "cloud-" if store else ""
    return os.path.join(_DIR, f"{praefix}{monat or _monat()}.jsonl")


def _zeilen(pfad: str) -> int:
    if not os.path.exists(pfad):
        return 0
    with open(pfad, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def schreiben(turns, store: str | None = None) -> list[str]:
    """
    Turns anhängen. `turns` ist [(user, ai), …]. Liefert die IDs.

    Schluckt Fehler und gibt dann [] zurück: ein volles Dateisystem oder ein
    kaputter Pfad darf die Konsolidierung nicht abreißen lassen. Lieber ein
    Knoten ohne Quelle als ein verlorener Knoten.
    """
    if not turns:
        return []
    try:
        with _lock:
            os.makedirs(_DIR, exist_ok=True)
            monat = _monat()
            pfad  = datei(store, monat)
            n     = _zeilen(pfad)
            jetzt = datetime.now().isoformat(timespec="seconds")
            ids   = []
            with open(pfad, "a", encoding="utf-8") as f:
                for user, ai in turns:
                    n += 1
                    tid = f"{monat}:{n}"
                    f.write(json.dumps({"id": tid, "zeit": jetzt,
                                        "user": user, "ai": ai},
                                       ensure_ascii=False) + "\n")
                    ids.append(tid)
            return ids
    except Exception:
        return []


def lesen(tid: str, store: str | None = None) -> dict | None:
    """Eine Zeile nach ihrer id nachschlagen. Für den Menschen und für
    spätere Werkzeuge — der Chat-Pfad ruft das nicht auf."""
    try:
        monat, nummer = tid.split(":")
        nummer = int(nummer)
    except (ValueError, AttributeError):
        return None
    pfad = datei(store, monat)
    if not os.path.exists(pfad):
        return None
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            for i, zeile in enumerate(f, 1):
                if i == nummer:
                    return json.loads(zeile)
    except Exception:
        return None
    return None
