# core/erlaubnis.py
#
# Das Erlaubnis-Gate: welche Werkzeuge vor der Ausführung bestätigt werden
# müssen, und die Ja/Nein-Frage, die Sasha dazu sieht.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 stand das
# in core/ai.py, und die Werkzeug-Schleife musste dafür den ganzen lokalen
# Weg importieren — einer der Knoten im Import-Kreis. Aufbau des KI-Kerns:
# memory/ki/kern_aufbau.md.
#
# Seit 2026-10-07 steht WAS bestätigt wird und WIE gefragt wird beim
# Werkzeug selbst, im Werkzeug-Register (core/werkzeug_register.py: Felder
# erlaubnis und frage). Eine zweite Liste hier lief früher neben den Schemas
# her und konnte ein neues Werkzeug still vergessen. Dieses Modul bleibt die
# Tür, durch die die Schleife (werkzeug_schleife.run_tool) fragt.
#
# Das Gate kommt automatisch vor der Ausführung, das Modell weiß nichts davon
# (bewusst NICHT modellgetrieben: ein 9b ruft sowas nicht zuverlässig von
# selbst). Geprüft wird immer gegen den kanonischen Namen, sonst rutschte ein
# Werkzeug unter einem Alias am Gate vorbei — der stillste denkbare Fehler.
#
# ── Geltungsbereiche (2026-10-07, Sasha: „beides einstellbar machen") ──
# Wie bei Claude Code: ein Ja gilt
#   einmal    nur für diesen einen Aufruf (das alte Ja),
#   gespraech bis das Gespräch wechselt — an die Gesprächs-id des Zugs
#             gebunden (core/zug.py), nur im Arbeitsspeicher; ein Neustart
#             fragt wieder. Ohne Gespräch (Erinnerungen vom Takt) gibt es
#             diese Wahl nicht.
#   immer     dauerhaft, in ai_config (Schlüssel immer_erlaubt, Liste von
#             Werkzeug-Namen); zurücknehmen mit /erlaubnis im Chat.
# Was „immer" NICHT bekommt (Kernakten, Löschen/Überschreiben), steht im
# Register (immer_erlaubbar) mit Begründung. Die Regel wird auch beim
# PRÜFEN angewandt: steht so ein Werkzeug von Hand in der Config, wird
# trotzdem gefragt.
# Pro Werkzeug, nicht pro Argument: „run_code immer" heißt jedes Programm.
# Feiner (pro Befehl wie bei Claude Code) wäre bei frei geschriebenem Code
# nicht sinnvoll prüfbar.

import threading

import ai_config
import werkzeug_register
import zug


# Die Werkzeuge, die IMMER bestätigt werden (kanonische Namen). Abgeleitet,
# nur zum Lesen für Skripte und Tests — entschieden wird über
# braucht_erlaubnis, denn write_note hängt von den Argumenten ab.
PERMISSION_REQUIRED_TOOLS = frozenset(werkzeug_register.immer_bestaetigen())


def braucht_erlaubnis(name: str, args: dict | None = None) -> bool:
    """Muss dieser Tool-Call vor der Ausführung bestätigt werden?

    Der Name kommt vom Modell und trägt die Schreibweise seiner Schiene.
    write_note ist frei, ausser es trifft eine Kernakte (Hausregeln,
    Steckbrief, Ziele, Sasha 2026-10-06) — dafür braucht es die Argumente.
    """
    return werkzeug_register.braucht_erlaubnis(name, args)


def frage(name: str, args: dict) -> str:
    """Die menschenlesbare Ja/Nein-Frage für ein gegatetes Tool (wird Sasha
    im Dialog gezeigt + vorgelesen). Vorlage pro Werkzeug im Register,
    allgemeiner Rückfall für eins ohne."""
    return werkzeug_register.frage(name, args)


# ── Geltungsbereiche ───────────────────────────────────────────────────

EINMAL, GESPRAECH, IMMER, NEIN = "einmal", "gespraech", "immer", "nein"

# Die Knopf-Texte, die Sasha sieht. Alle Ja-Knöpfe beginnen mit „ja", der
# Nein-Knopf steht hinten: die TUI nimmt für j den ersten mit j, für n und
# Esc den letzten (tui/ansichten/chat.py) — so bleibt j/n wie bisher.
KNOEPFE = {EINMAL: "ja, nur dieses mal", GESPRAECH: "ja, für dieses gespräch",
           IMMER: "ja, immer", NEIN: "nein"}
# Alte Antworten (bis 2026-10-07 gab es nur ja/nein) und Kurzformen.
_KURZ = {"ja": EINMAL, "j": EINMAL, "einmal": EINMAL, "gespraech": GESPRAECH,
         "gespräch": GESPRAECH, "immer": IMMER, "nein": NEIN, "n": NEIN}

_lock = threading.Lock()
_gespraech = {"id": None, "werkzeuge": set()}


def geltungen(name: str, args: dict | None = None) -> list:
    """Welche Ja-Arten dieser Aufruf anbietet, in Knopf-Reihenfolge.
    Ein Aufruf mit eigenem Ja (Register: nur_einmal, z. B. run_code über
    2 Minuten) bekommt nur „einmal"."""
    raus = [EINMAL]
    if werkzeug_register.nur_einmal(name, args):
        return raus
    if zug.gespraech():
        raus.append(GESPRAECH)
    if werkzeug_register.immer_erlaubbar(name):
        raus.append(IMMER)
    return raus


def optionen(name: str, args: dict | None = None) -> list:
    """Die Knöpfe der Frage: die Ja-Arten, dann „nein"."""
    return [KNOEPFE[g] for g in geltungen(name, args)] + [KNOEPFE[NEIN]]


def deuten(antwort: str) -> str:
    """Knopf-Text (oder alte Kurzform „ja") → EINMAL/GESPRAECH/IMMER/NEIN.
    Alles Unbekannte, auch der Timeout, ist NEIN."""
    a = str(antwort or "").strip().lower()
    for g, text in KNOEPFE.items():
        if a == text:
            return g
    return _KURZ.get(a, NEIN)


def gespraech_beginnt(gid) -> None:
    """Ein Zug in Gespräch `gid` beginnt bzw. Sasha wechselt dorthin. Ist es
    ein anderes als das, für das „für dieses Gespräch" gilt: aufheben."""
    with _lock:
        if _gespraech["id"] != gid:
            _gespraech["id"] = gid
            _gespraech["werkzeuge"] = set()


def immer_liste() -> list:
    """Werkzeug-Namen mit „immer" (kanonisch, sortiert). Unbekannte und
    solche ohne „immer" (von Hand eingetragen) fallen weg — sie gelten
    ohnehin nicht, also zeigt /erlaubnis sie auch nicht."""
    roh = ai_config.setting("immer_erlaubt") or []
    if isinstance(roh, str):          # aus der Umgebung: kommagetrennt
        roh = roh.split(",")
    namen = {werkzeug_register.kanonisch(str(n).strip()) for n in roh if str(n).strip()}
    return sorted(n for n in namen if werkzeug_register.immer_erlaubbar(n))


def gespraech_liste() -> list:
    """Werkzeug-Namen mit „für dieses Gespräch" (für das gerade gemerkte)."""
    with _lock:
        return sorted(_gespraech["werkzeuge"])


def vorab(name: str, args: dict | None = None):
    """Ist dieser Aufruf schon erlaubt? -> IMMER, GESPRAECH oder None.

    „Immer" nur, wenn das Werkzeug es überhaupt darf (s. o.); „Gespräch" nur
    im selben Gespräch, in dem es erteilt wurde; beides nie für einen Aufruf
    mit eigenem Ja (nur_einmal)."""
    kan = werkzeug_register.kanonisch(name)
    if werkzeug_register.nur_einmal(kan, args):
        return None
    if kan in immer_liste():
        return IMMER
    gid = zug.gespraech()
    with _lock:
        if gid and _gespraech["id"] == gid and kan in _gespraech["werkzeuge"]:
            return GESPRAECH
    return None


def merken(name: str, geltung: str, args: dict | None = None) -> None:
    """Ein Ja mit Geltung festhalten. EINMAL/NEIN: nichts zu merken —
    ebenso bei einem Aufruf mit eigenem Ja (nur_einmal), egal was kam."""
    kan = werkzeug_register.kanonisch(name)
    if werkzeug_register.nur_einmal(kan, args):
        return
    if geltung == GESPRAECH:
        gid = zug.gespraech()
        if not gid:
            return
        with _lock:
            if _gespraech["id"] != gid:
                _gespraech["id"], _gespraech["werkzeuge"] = gid, set()
            _gespraech["werkzeuge"].add(kan)
    elif geltung == IMMER and werkzeug_register.immer_erlaubbar(kan):
        liste = immer_liste()
        if kan not in liste:
            ai_config.set_override("immer_erlaubt", sorted(liste + [kan]),
                                   persist=True)


def zuruecknehmen(name: str | None = None) -> list:
    """„Immer" und „für dieses Gespräch" zurücknehmen — für ein Werkzeug,
    oder ohne Namen für alle. -> die Namen, die etwas verloren haben."""
    kan = werkzeug_register.kanonisch(name) if name else None
    liste = immer_liste()
    weg = [n for n in liste if kan in (None, n)]
    if weg:
        rest = [n for n in liste if n not in weg]
        # [] statt None: None löschte nur den Eintrag, und eine Umgebungs-
        # oder Alt-Datei-Liste griffe wieder.
        ai_config.set_override("immer_erlaubt", rest, persist=True)
    with _lock:
        g = [n for n in _gespraech["werkzeuge"] if kan in (None, n)]
        _gespraech["werkzeuge"] -= set(g)
    return sorted(set(weg) | set(g))


def uebersicht() -> dict:
    """Für /api/erlaubnis: was gilt gerade."""
    def zeile(n):
        return {"name": n, "was": werkzeug_register.alltag(n)}
    return {"immer": [zeile(n) for n in immer_liste()],
            "gespraech": [zeile(n) for n in gespraech_liste()],
            "gespraech_id": _gespraech["id"]}
