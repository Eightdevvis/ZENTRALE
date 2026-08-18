# core/gedaechtnis.py
#
# Das Gedächtnis als DATEIEN, die die KI liest und fortschreibt.
#
# ── Warum das den Konzept-Graphen ablöst (18.08.2026) ──────────────────
# Der Graph (core/graph.py) hat lange versucht, jeden Turn in Tripel zu
# zerlegen. Der gemessene Zustand nach Wochen Betrieb: 42 von 104 Kanten
# waren `erwähnt-am` (reine Buchhaltung, WANN geredet wurde), die drei
# bestverbundenen Knoten waren ein Datum, "KI" und "Sasha", und unter den
# Fakten standen Sätze wie `Sasha wohnt-in Universität des Saarlandes`.
# Ein Interesse an Organoiden war zu `arbeitet-an` geworden, eine
# Fähigkeit (`Fahrradfahren`) zu einem `project`.
#
# Die Ursache war nicht die Extraktion, sondern das fehlende Schema: der
# Extraktor erfand pro Turn, welcher Typ und welches Verb passt. Ein
# Wissensgraph ohne Ontologie ist ein Haufen Sätze, denen man die Wörter
# weggenommen hat.
#
# Und genau das ist der Punkt: WEGGENOMMEN. `Sasha zustand Fieber` ist
# das, was von "ich lag drei Tage flach und hab die Vorlesung verpasst"
# übrig bleibt. Das Modell ist gut in Sprache — der Graph hat ihm die
# Sprache abgenommen und Tripel hingelegt. Deshalb fühlte sich ZENTRALE
# dümmer an als dasselbe Modell im nackten Chat.
#
# Hier schreibt sie stattdessen NOTIZEN, wie ein Sekretär Notizen
# schreibt: in Sätzen, absichtlich, wiederlesbar — von ihr und von Sasha.
#
# ── Die vier Speicher ─────────────────────────────────────────────────
#
#   steckbrief   sasha.md       Wer er ist, was gilt. SASHA pflegt das.
#   ziele        ziele.md       Ziele mit Horizont. Sasha pflegt, KI schlägt vor.
#   dossiers     dossiers/*.md  Weltzustand pro laufender Sache. KI schreibt fort.
#   tagebuch     tagebuch/*.md  Was gesagt und getan wurde, chronologisch.
#
# Messreihen (Schlaf, Stimmung, Training) sind der fünfte Speicher und
# liegen NICHT hier — dafür gibt es das Zyklus-Werkzeug (core/graphs.py),
# das Zahlen über Zeit schon kann, inklusive Anzeige.
#
# ── Was in den Prompt geht ────────────────────────────────────────────
# Steckbrief + Ziele + die LISTE der Dossiers, mehr nicht — und zwar im
# GECACHTEN Kopf, weil sich das fast nie ändert. Alles Weitere holt sie
# per Werkzeug. Der alte Graph-Block ging bei JEDEM Turn ungecacht raus
# und kostete damit dauerhaft, während er Rauschen lieferte.

import os
import re
from datetime import date, datetime

_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "data", "gedaechtnis")
STECKBRIEF = "sasha"
ZIELE      = "ziele"

# Obergrenzen. Ein Dossier, das ein Modell vollschreibt, bis es den halben
# Kontext frisst, ist wieder dasselbe Problem in Grün.
MAX_DOSSIER = 20_000     # Zeichen; darüber wird beim Anhängen gewarnt
MAX_NOTIZ   = 4_000      # Zeichen pro einzelnem Eintrag
MAX_TREFFER = 12         # Suchtreffer


def _wurzel() -> str:
    os.makedirs(_DIR, exist_ok=True)
    return _DIR


def _slug(name: str) -> str:
    """Dateiname aus einem Titel. Verhindert nebenbei Pfad-Ausbrüche.

    Ein Modell, das `../../data/ai_config.json` als Dossier-Namen schickt,
    darf damit nicht durchkommen — deshalb wird alles außer Buchstaben,
    Ziffern und Bindestrich weggeworfen, statt den Pfad hinterher zu prüfen.
    """
    s = (name or "").strip().lower()
    s = (s.replace("ä", "ae").replace("ö", "oe")
          .replace("ü", "ue").replace("ß", "ss"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60]


def _pfad(bereich: str, name: str) -> str:
    ordner = _wurzel() if not bereich else os.path.join(_wurzel(), bereich)
    os.makedirs(ordner, exist_ok=True)
    return os.path.join(ordner, f"{name}.md")


def _lesen(pfad: str) -> str:
    try:
        with open(pfad, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _anhaengen(pfad: str, text: str):
    neu = not os.path.exists(pfad)
    with open(pfad, "a", encoding="utf-8") as f:
        if neu:
            f.write(f"# {os.path.basename(pfad)[:-3]}\n\n")
        f.write(text)


# ── Steckbrief & Ziele (Sashas Dateien) ───────────────────────────────

def steckbrief() -> str:
    return _lesen(_pfad("", STECKBRIEF)).strip()


def ziele() -> str:
    return _lesen(_pfad("", ZIELE)).strip()


# ── Dossiers ──────────────────────────────────────────────────────────

def dossier_liste() -> list:
    ordner = os.path.join(_wurzel(), "dossiers")
    if not os.path.isdir(ordner):
        return []
    return sorted(f[:-3] for f in os.listdir(ordner) if f.endswith(".md"))


def dossier_lesen(name: str) -> str:
    return _lesen(_pfad("dossiers", _slug(name))).strip()


def dossier_notieren(name: str, text: str) -> str:
    """Einen datierten Absatz an ein Dossier hängen. Legt es an, wenn nötig.

    ANHÄNGEN, nicht überschreiben: eine KI, die eine Datei ersetzt, löscht
    stillschweigend alles, was sie beim Schreiben nicht im Kopf hatte. Für
    echtes Umschreiben gibt es `dossier_ersetzen`, und das hängt am
    Erlaubnis-Gate.
    """
    schluessel = _slug(name)
    if not schluessel:
        return "[Fehler: kein Dossier-Name]"
    text = (text or "").strip()
    if not text:
        return "[Fehler: leerer Eintrag]"
    if len(text) > MAX_NOTIZ:
        text = text[:MAX_NOTIZ] + " …[gekürzt]"

    pfad = _pfad("dossiers", schluessel)
    war_da = os.path.exists(pfad)
    _anhaengen(pfad, f"\n## {date.today().isoformat()}\n{text}\n")

    zu_lang = len(_lesen(pfad)) > MAX_DOSSIER
    return (f"{'Notiert in Dossier' if war_da else 'Neu angelegt: Dossier'} "
            f"'{schluessel}'."
            + (" ⚠ Das Dossier ist sehr lang geworden — räum es beim nächsten "
               "Mal auf (dossier_ersetzen)." if zu_lang else ""))


def dossier_ersetzen(name: str, inhalt: str) -> str:
    """Ein Dossier komplett neu schreiben. Die alte Fassung bleibt als .bak.

    Das ist der Aufräum-Weg: aus zwanzig angehängten Absätzen wird ein
    sauberer Stand. Destruktiv, deshalb gegatet — und selbst dann mit
    Sicherungskopie, denn Aufräumen ist genau die Tätigkeit, bei der man
    am ehesten versehentlich etwas verliert.
    """
    schluessel = _slug(name)
    if not schluessel:
        return "[Fehler: kein Dossier-Name]"
    pfad = _pfad("dossiers", schluessel)
    alt = _lesen(pfad)
    if alt:
        with open(pfad + ".bak", "w", encoding="utf-8") as f:
            f.write(alt)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write((inhalt or "").strip() + "\n")
    return (f"Dossier '{schluessel}' neu geschrieben"
            + (" (alte Fassung liegt als .bak daneben)." if alt else "."))


# ── Tagebuch ──────────────────────────────────────────────────────────

def tagebuch_notieren(text: str, tag=None) -> str:
    """Eine Zeile ins Tagebuch, mit Uhrzeit.

    Das ist der Speicher, aus dem später "wie war eigentlich Spanien"
    beantwortet wird — und die Grundlage jeder Auswertung über Monate.
    Deshalb SEINE Worte, nicht destilliert.
    """
    text = (text or "").strip()
    if not text:
        return "[Fehler: leerer Eintrag]"
    if len(text) > MAX_NOTIZ:
        text = text[:MAX_NOTIZ] + " …[gekürzt]"
    t = tag or date.today()
    _anhaengen(_pfad("tagebuch", t.isoformat()),
               f"- {datetime.now().strftime('%H:%M')} {text}\n")
    return "Ins Tagebuch geschrieben."


def tagebuch_lesen(tag=None) -> str:
    return _lesen(_pfad("tagebuch", (tag or date.today()).isoformat())).strip()


def suchen(begriff: str, max_treffer: int = MAX_TREFFER) -> str:
    """Volltextsuche über Tagebuch UND Dossiers.

    Stumpfer Substring-Vergleich, absichtlich: er braucht keinen Embedder,
    keine Datenbank und kein Netz, und er findet Eigennamen zuverlässiger
    als jede Ähnlichkeitssuche. Wird er zu grob, kommt ein Index DARÜBER —
    nicht darunter.
    """
    begriff = (begriff or "").strip()
    if len(begriff) < 2:
        return "[Fehler: Suchbegriff zu kurz]"
    nadel = begriff.casefold()
    treffer = []
    for bereich in ("tagebuch", "dossiers"):
        ordner = os.path.join(_wurzel(), bereich)
        if not os.path.isdir(ordner):
            continue
        for datei in sorted(os.listdir(ordner), reverse=True):
            if not datei.endswith(".md"):
                continue
            for zeile in _lesen(os.path.join(ordner, datei)).splitlines():
                if nadel in zeile.casefold():
                    treffer.append(f"[{bereich}/{datei[:-3]}] {zeile.strip()}")
                    if len(treffer) >= max_treffer:
                        break
            if len(treffer) >= max_treffer:
                break
    if not treffer:
        return f"Nichts zu {begriff!r} gefunden (Tagebuch und Dossiers durchsucht)."
    return f"{len(treffer)} Treffer zu {begriff!r}:\n" + "\n".join(treffer)


# ── Was in den gecachten Prompt-Kopf geht ─────────────────────────────

def kopf_block() -> str:
    """Steckbrief + Ziele + die Dossier-TITEL. Sonst nichts.

    Bewusst nur die Titel: sie soll SEHEN, dass es ein Umzugs-Dossier
    gibt, und es lesen, wenn es um den Umzug geht. Alle Dossiers in den
    Prompt zu kippen wäre derselbe Fehler wie der Graph-Block — viel
    Kontext, wenig Bezug, bei jedem Turn bezahlt.

    Byte-stabil, solange sich die Dateien nicht ändern, und gehört deshalb
    in den gecachten Teil (10 % des Preises).
    """
    teile = []
    s, z = steckbrief(), ziele()
    if s:
        teile.append("## Über Sasha\n" + s)
    if z:
        teile.append("## Seine Ziele\n" + z)
    liste = dossier_liste()
    if liste:
        teile.append(
            "## Dossiers (Stand der laufenden Sachen)\n"
            + ", ".join(liste)
            + "\n\nDas sind Titel, nicht Inhalte. Geht es um eines davon, lies "
              "es mit read_note — rate nicht aus dem Titel. Was du Neues "
              "erfährst, hältst du mit write_note dort fest.")
    if not teile:
        return ""
    return "\n\n".join(teile)
