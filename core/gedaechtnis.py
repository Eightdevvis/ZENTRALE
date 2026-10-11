# core/gedaechtnis.py
#
# Das Gedächtnis als DATEIEN, die die KI liest und fortschreibt.
#
# ── Warum Dateien statt Konzept-Graph (18.08.2026) ────────────────────
# Der Graph (core/graph.py) zerlegte jeden Turn in Tripel. Nach Wochen
# Betrieb waren 42 von 104 Kanten `erwähnt-am`, und unter den Fakten stand
# `Sasha wohnt-in Universität des Saarlandes`. Ein Wissensgraph ohne Schema
# ist ein Haufen Sätze, denen man die Wörter weggenommen hat — und das
# Modell ist gut in Sprache. Hier schreibt sie deshalb NOTIZEN in Sätzen,
# wiederlesbar von ihr und von Sasha. Ausführlich:
# memory/ki/gedaechtnis_dateien.md.
#
# ── Nach Thema, im Format von Claudes Datei-Gedächtnis (2026-10-11) ───
# Bis dahin lag alles nach Datenformat (dossiers/, kataloge/, notizen/ …).
# Sasha: „wir sollten nach thema sortieren … guck dir einfach dich selbst an,
# was du darfst und kannst in deiner memory und modellier genau danach."
# Jetzt eine Datei pro Sache unter themen/<thema>/, Kopf wie bei Claude
# (name, description, metadata.art), ein INDEX.md wie Claudes MEMORY.md.
# Wie es auf der Platte liegt: core/gedaechtnis_ablage.py. Katalog-Text:
# core/gedaechtnis_katalog.py. Umzug des alten Bestands NUR per Skript
# (scripts/gedaechtnis_umzug.py), nie beim Start.
#
# Bis der Umzug gelaufen ist, LIEST dieses Modul den alten Aufbau mit
# (Steckbrief, Ziele, Hausregeln, Dateien nach Name, Suche) — geschrieben
# wird nur noch in den neuen. So geht nach einem Update nichts verloren und
# die KI ist nicht plötzlich ohne Gedächtnis.
#
# ── Was in den Prompt geht ────────────────────────────────────────────
# Hausregeln + Steckbrief + der INDEX (Titel und Haken, keine Inhalte), im
# GECACHTEN Kopf (cloud._static_system). Alles Weitere holt sie per Werkzeug
# (gross-Schiene; klein kennt das Gedächtnis nicht).

import hashlib
import os
import re
from datetime import date, datetime

import datasync
import dateien
import gedaechtnis_ablage as ablage
import gedaechtnis_katalog as katalog

# ZENTRALE_GEDAECHTNIS_DIR ist eine reine TEST-Umlenkung (tests/conftest.py),
# damit kein Testlauf in Sashas echtes Gedächtnis greift.
_DIR = os.environ.get("ZENTRALE_GEDAECHTNIS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "gedaechtnis")

STECKBRIEF = "steckbrief"
ZIELE = "ziele"
HAUSREGELN = "hausregeln"
PERSON = "person"

# Obergrenzen. Ein Dossier, das ein Modell vollschreibt, bis es den halben
# Kontext frisst, ist wieder dasselbe Problem in Grün.
MAX_DOSSIER = 20_000     # Zeichen; darüber wird beim Anhängen gewarnt
MAX_NOTIZ   = 4_000      # Zeichen pro einzelnem Eintrag
MAX_TREFFER = 12         # Suchtreffer
_MAX_DOKUMENT = 25_000_000   # Bytes Download
_MAX_DOKUMENT_TEXT = 400_000 # Zeichen je abgelegtem Text

STATUS = katalog.STATUS
KATALOG_FELDER = katalog.FELDER
kopf_lesen = katalog.kopf_lesen

# Skills und Projekte liegen unter derselben Wurzel (derselbe Sync, dieselbe
# Test-Umlenkung), aber außerhalb von themen/: write_note erreicht sie nicht.
# Ein Skill ist eine Anleitung der KI an sich selbst (gegatet, core/skills.py),
# Projekt-Anweisungen schreibt Sasha (core/projekte.py).
SKILLS = "ki/skills"
_SKILLS_ALT = "skills"
PROJEKTE = "projekte"

# Der alte Aufbau (bis 2026-10-11): nur noch gelesen, bis der Umzug lief.
ALT_BEREICHE = ("dossiers", "notizen", "kataloge", "quellen", "vorlagen")
_ALT_KERN = {HAUSREGELN: "hausregeln.md", STECKBRIEF: "sasha.md", ZIELE: "ziele.md"}


def _wurzel() -> str:
    os.makedirs(_DIR, exist_ok=True)
    return _DIR


def slug(name: str) -> str:
    """Dateiname aus einem Titel, ohne Pfad-Ausbruch."""
    return ablage.slug(name)


_slug = slug


def bereich_ordner(bereich: str) -> str:
    """Ein Ordner unter der (umlenkbaren) Wurzel. Legt nichts an."""
    return os.path.join(_DIR, bereich)


def skills_ordner() -> str:
    """ki/skills/ — oder, solange der Umzug nicht lief, das alte skills/."""
    neu, alt = bereich_ordner(SKILLS), bereich_ordner(_SKILLS_ALT)
    if not os.path.isdir(neu) and os.path.isdir(alt):
        return alt
    return neu


def _lesen(pfad: str) -> str:
    try:
        with open(pfad, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ohne_titel(text: str) -> str:
    """Führende "# Titel"-Zeile abschneiden — im Prompt steht schon eine
    Überschrift darüber."""
    zeilen = text.lstrip().splitlines()
    if zeilen and zeilen[0].startswith("# "):
        zeilen = zeilen[1:]
    return "\n".join(zeilen).strip()


def _rumpf(pfad: str) -> str:
    return ablage.zerlegen(_lesen(pfad))[1]


def _geaendert(pfad: str, index: bool = False) -> None:
    if index:
        ablage.index_schreiben(_wurzel())
    datasync.notify_change(pfad)


# ── Kernakten: Hausregeln (ki/), Steckbrief und Ziele (themen/person/) ─

KERNAKTEN = {HAUSREGELN: HAUSREGELN, STECKBRIEF: STECKBRIEF, ZIELE: ZIELE}
_KERN_NAMEN = {HAUSREGELN: "Hausregeln", STECKBRIEF: "Steckbrief", ZIELE: "Ziele"}
_KERN_KOPF = {
    HAUSREGELN: ("Verhaltensregeln, die Sasha im Gespräch gesetzt hat — "
                 "stehen in jedem Zug ganz oben", "regel"),
    STECKBRIEF: ("Wer Sasha ist und was für ihn gilt — Sasha pflegt das",
                 "steckbrief"),
    ZIELE: ("Sashas Ziele mit Horizont — Sasha pflegt, KI schlägt vor", "ziel"),
}
MAX_KERNAKTE = MAX_DOSSIER   # Steht ganz im gecachten Kopf — nur gegen Versehen.

# Kopf einer neuen Hausregel-Datei und eine Regel-Zeile — eine Stelle für
# regel_notieren und den Skill-Umzug (core/skill_umzug.py, 2026-10-07).
HAUSREGELN_KOPF = ("# Hausregeln\n\n> Von Sasha im Gespräch gesetzt. Er darf "
                   "hier jederzeit streichen und ändern.\n\n")


def kern_pfad(akte: str) -> str:
    if akte == HAUSREGELN:
        return os.path.join(_DIR, ablage.KI, HAUSREGELN + ".md")
    return os.path.join(_DIR, ablage.THEMEN, PERSON, akte + ".md")


def kernakte_lesen(akte: str) -> str:
    """Der Text einer Kernakte (ohne Datei-Kopf), leer wenn es sie nicht gibt;
    vor dem Umzug aus dem alten Ort. KeyError bei einem anderen Namen."""
    pfad = kern_pfad(KERNAKTEN[akte])
    if os.path.exists(pfad):
        return _rumpf(pfad)
    return _lesen(os.path.join(_DIR, _ALT_KERN[akte]))


def kernakte_stand(text: str) -> str:
    """Fingerabdruck einer Fassung — die TUI schickt ihn beim Speichern mit,
    damit Sasha nicht still überschreibt, was die KI inzwischen schrieb."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def kernakte_schreiben(akte: str, text: str) -> str:
    """Eine Kernakte ganz ersetzen (Sasha von Hand, oder nach Bestätigung).
    Der Datei-Kopf bleibt; die alte Fassung liegt als .bak daneben.
    → der neue Stand. KeyError (unbekannt), ValueError (zu lang)."""
    pfad = kern_pfad(KERNAKTEN[akte])
    text = (text or "").replace("\r\n", "\n")
    if len(text) > MAX_KERNAKTE:
        raise ValueError(f"zu lang ({len(text)} Zeichen, höchstens {MAX_KERNAKTE})")
    alt = _lesen(pfad)
    if alt:
        dateien.atomar_schreiben(pfad + ".bak", alt)
    kopf = ablage.zerlegen(alt)[0] if alt else {}
    if not kopf:
        kopf = ablage.neuer_kopf(akte, *_KERN_KOPF[akte])
    neu = text.rstrip() + "\n" if text.strip() else ""
    ablage.schreiben(pfad, ablage.text_bauen(ablage.kopf_auffrischen(kopf), neu))
    _geaendert(pfad, index=not alt)
    return kernakte_stand(neu)


def _kern_anhaengen(akte: str, zeilen: str, anfang: str = "") -> None:
    """Zeilen an eine Kernakte hängen; vor dem Umzug mit dem alten Inhalt
    als Grundlage (sonst stünde die neue Datei ohne ihn da)."""
    alt = kernakte_lesen(akte)
    basis = alt.rstrip("\n") + "\n" if alt.strip() else anfang
    kernakte_schreiben(akte, basis + zeilen)


def steckbrief() -> str:
    return kernakte_lesen(STECKBRIEF).strip()


def ziele() -> str:
    return kernakte_lesen(ZIELE).strip()


def hausregeln() -> str:
    """Verhaltensregeln, die SASHA gesetzt hat. Die KI darf ihren Kern-Prompt
    nicht umschreiben (sie würde früher oder später genau die Regeln
    entfernen, die sie am Erfinden hindern) — eine getrennte Datei hat
    dieselbe Wirkung und ist in zehn Sekunden zu überprüfen. Steht im Prompt
    VOR allem anderen."""
    return kernakte_lesen(HAUSREGELN).strip()


def _kern_von(name) -> str | None:
    """Welche Kernakte ein Name meint (oder None). 'sasha' ist der alte
    Dateiname des Steckbriefs, 'regeln' eine Kurzform."""
    thema, stamm, _ = ablage.name_zerlegen(str(name or ""))
    if stamm in ("hausregeln", "regeln") and thema in ("", "ki"):
        return HAUSREGELN
    if stamm in ("sasha", "steckbrief") and thema in ("", PERSON):
        return STECKBRIEF
    if stamm in ("ziele", "goals") and thema in ("", PERSON):
        return ZIELE
    return None


def schreibt_kernakte(name) -> str | None:
    """Trifft ein write_note mit diesem Namen eine Kernakte? → ihr Name.
    Sasha, 2026-10-06: Hausregeln und Steckbrief nur mit seiner Bestätigung
    (ohne konnte das Modell sich selbst Vorrang-Regeln setzen)."""
    akte = _kern_von(name)
    return _KERN_NAMEN[akte] if akte else None


def regel_zeile(text: str) -> str:
    return f"- {text}  _(seit {date.today().strftime('%d.%m.%Y')})_\n"


def regel_notieren(text: str) -> str:
    """Eine Hausregel anhängen, mit Datum. Anhängen statt ersetzen — beim
    Neuschreiben verliert ein Modell, was es gerade nicht im Kopf hat."""
    text = (text or "").strip().lstrip("-").strip()
    if not text:
        return "[Fehler: leere Regel]"
    if len(text) > 400:
        return "[Zu lang fuer eine Regel — sag es in einem Satz.]"
    _kern_anhaengen(HAUSREGELN, regel_zeile(text), HAUSREGELN_KOPF)
    return f"Als Hausregel festgehalten: {text}"


# ── Namen auflösen ────────────────────────────────────────────────────

# Welche Art ein neuer Name mit altem Präfix bekommt (dossiers/x → Dossier).
_ALT_ART = {"dossiers": "dossier", "notizen": "notiz", "kataloge": "katalog",
            "quellen": "quelle"}


def _alt_art(name: str) -> str:
    kopf, _, rest = (name or "").strip().strip("/").partition("/")
    return _ALT_ART.get(kopf.lower(), "") if rest else ""


def _bevorzugt(name: str) -> tuple:
    """Alte Bereichs-Präfixe (dossiers/…, kataloge/…) weiter verstehen: das
    Modell kennt sie aus alten Gesprächen. → (name ohne Präfix, Endungen)."""
    roh = (name or "").strip().strip("/")
    kopf, _, rest = roh.partition("/")
    if rest and kopf.lower() in ALT_BEREICHE:
        if kopf.lower() == "kataloge":
            return rest, (".katalog.md", ".md")
        return rest, (".md", ".katalog.md", ".reihe.md")
    return roh, None


def finden(name: str, thema: str = "") -> list:
    """Pfade der Themen-Dateien zu einem Namen (leer: keine)."""
    roh, endungen = _bevorzugt(name)
    return ablage.finden(_DIR, roh, thema, endungen)


def _alt_finden(name: str) -> str:
    """Vor dem Umzug: die Datei im alten Aufbau, sonst ''."""
    roh, endungen = _bevorzugt(name)
    _, stamm, _ = ablage.name_zerlegen(roh)
    folge = ("kataloge",) + ALT_BEREICHE if endungen and endungen[0] == ".katalog.md" \
        else ALT_BEREICHE
    for bereich in folge:
        p = os.path.join(_DIR, bereich, stamm + ".md")
        if stamm and os.path.isfile(p):
            return p
    return ""


def _alt_uebernehmen(name: str, thema: str = "") -> list:
    """Vor dem Umzug: gibt es den Namen nur im alten Aufbau, wird die Datei
    zuerst in den neuen kopiert (die alte bleibt für den Umzug liegen), damit
    Ergänzen auf ihrem Inhalt aufsetzt statt daneben eine zweite anzulegen.
    → finden() danach."""
    alt = _alt_finden(name)
    if alt and not finden(name, thema):
        bereich = os.path.basename(os.path.dirname(alt))
        _anlegen(thema, os.path.basename(alt)[:-3], _ALT_ART.get(bereich, "notiz"),
                 "", _ohne_titel(_lesen(alt)) + "\n")
    return finden(name, thema)


def _ort(pfad: str) -> str:
    """themen/sport/spagat.md → 'sport/spagat' (so nennt die KI es)."""
    rel = os.path.relpath(pfad, _DIR).replace(os.sep, "/")
    if rel.startswith(ablage.THEMEN + "/"):
        rel = rel[len(ablage.THEMEN) + 1:]
    return rel[:-3] if rel.endswith(".md") else rel


def _mehrdeutig(treffer: list) -> str:
    return ("[Mehrdeutig: " + ", ".join(_ort(p) for p in treffer)
            + " — gib das Thema mit an (thema/name). Nichts geschrieben.]")


def dossier_lesen(name: str, thema: str = "") -> str:
    """Der Text (ohne Datei-Kopf) einer Datei, nach Name; '' wenn es sie
    nicht gibt. Kernakten und Tagebuch über ihre eigenen Wege."""
    akte = _kern_von(name)
    if akte:
        return kernakte_lesen(akte).strip()
    treffer = finden(name, thema)
    if treffer:
        return _rumpf(treffer[0]).strip()
    alt = _alt_finden(name)
    return _lesen(alt).strip() if alt else ""


lesen = dossier_lesen


def ort_von(name: str, thema: str = "") -> str:
    """Wo eine Datei liegt ('sport/spagat'), '' wenn es sie nicht gibt."""
    treffer = finden(name, thema)
    return _ort(treffer[0]) if treffer else ""


def namen() -> list:
    """Alle Dateien als 'thema/name' — für Fehlermeldungen."""
    return [_ort(e["pfad"]) for e in ablage.alle(_wurzel())]


# ── Anlegen und Fortschreiben ─────────────────────────────────────────

def _anlegen(thema: str, name: str, art: str, beschreibung: str, rumpf: str, **mehr) -> str:
    pfad = ablage.pfad(_wurzel(), thema or ablage.ALLGEMEIN, name, art)
    kopf = ablage.neuer_kopf(ablage.slug(name), beschreibung, art, **mehr)
    ablage.schreiben(pfad, ablage.text_bauen(kopf, rumpf))
    _geaendert(pfad, index=True)
    return pfad


def _fortschreiben(pfad: str, rumpf: str, art: str = "", beschreibung: str = "") -> None:
    """Rumpf ersetzen, Kopf behalten (aktualisiert = heute; Art und
    Beschreibung nur, wenn ausdrücklich neu gegeben)."""
    kopf = ablage.kopf_auffrischen(ablage.zerlegen(_lesen(pfad))[0]
                                   or ablage.neuer_kopf(os.path.basename(pfad)[:-3], "", "notiz"))
    index = False
    meta = kopf["metadata"]
    if art and meta.get("art") != art:
        meta["art"], index = art, True
    beschreibung = " ".join((beschreibung or "").split())
    if beschreibung and kopf.get("description") != beschreibung:
        kopf["description"], index = beschreibung, True
    ablage.schreiben(pfad, ablage.text_bauen(kopf, rumpf))
    _geaendert(pfad, index=index)


def notieren(name: str, text: str, thema: str = "", art: str = "",
             beschreibung: str = "") -> str:
    """Etwas festhalten. Gibt es die Datei (irgendwo, oder im genannten
    Thema), wird angehängt — ein Katalog bekommt den Eintrag ersetzt oder
    neu (upsert). Sonst wird sie angelegt: im Thema `thema` (sonst
    „allgemein"), Art `art` (sonst notiz), mit `beschreibung` als Haken im
    Index (sonst die erste Zeile).

    ANHÄNGEN, nicht überschreiben: eine KI, die ersetzt, löscht still, was
    sie beim Schreiben nicht im Kopf hatte. Neu schreiben: ersetzen()."""
    text = (text or "").strip()
    if not text:
        return "[Fehler: leerer Eintrag]"
    if len(text) > MAX_NOTIZ:
        text = text[:MAX_NOTIZ] + " …[gekürzt]"
    akte = _kern_von(name)
    if akte:
        _kern_anhaengen(akte, text + "\n")
        return f"Notiert in {_KERN_NAMEN[akte]}."
    art = ablage.slug(art)
    if art == "messreihe":
        return "[Messreihen legt create_series an, nicht write_note. Nichts geschrieben.]"
    roh, endungen = _bevorzugt(name)
    _, stamm, endung = ablage.name_zerlegen(roh)
    if not stamm:
        return "[Fehler: kein Name]"
    treffer = _alt_uebernehmen(name, thema)
    if len(treffer) > 1:
        return _mehrdeutig(treffer)
    eintrag = katalog.kopf_lesen(text)
    if not treffer:
        if not art:
            art = ("katalog" if endung == ".katalog.md" or (endungen or ("",))[0] == ".katalog.md"
                   else "dossier" if eintrag else _alt_art(name) or "notiz")
        if art == "katalog" and not eintrag:
            return _keine_katalog_form(stamm)
        if art == "notiz" and not eintrag:
            anderswo = _wo_steht_der_titel(stamm)
            if anderswo:
                return _doppelt_hinweis(stamm, anderswo)
        if art == "katalog":
            rumpf = text + "\n"
        else:
            rumpf = katalog.kopf_setzen("", text) if eintrag else \
                (text + "\n" if art in _OHNE_DATUM else f"## {date.today().isoformat()}\n{text}\n")
        # Der Haken kommt von der KI, nicht aus dem Text: sonst stünde der
        # Anfang jeder Notiz im gecachten Kopf — Inhalte gehören nicht hinein.
        # Ein Dossier-Titel ist kein Inhalt, der darf es sein.
        pfad = _anlegen(thema, stamm, art, beschreibung or (eintrag.get("titel") or ""), rumpf)
        hinweis = katalog_abgleichen(pfad) if eintrag and art != "katalog" else ""
        ohne = "" if beschreibung or eintrag else (
            " Ohne beschreibung steht sie im Index nur mit Namen — gib sie beim "
            "nächsten write_note auf diese Datei mit.")
        beweis = (f" Neu: '{eintrag['titel']}'. " + _katalog_beweis(pfad, eintrag["titel"])) \
            if art == "katalog" else ""
        return (f"Neu angelegt: {_ort(pfad)} ({art})." + beweis
                + (f" {hinweis}." if hinweis else "") + ohne)
    return _anhaengen(treffer[0], text, eintrag, art, beschreibung)


def _anhaengen(pfad: str, text: str, eintrag: dict, art: str, beschreibung: str) -> str:
    kopf, alt = ablage.zerlegen(_lesen(pfad))
    ist = ablage.art_von(kopf)
    ort = _ort(pfad)
    if ist == "katalog":
        # Ein Katalog hat eine FORM, und die wird verteidigt (20.08.2026: erst
        # ein Eintrag, dann Prosa in DIESELBE Datei — halb Liste, halb Text).
        if not eintrag:
            return _keine_katalog_form(ort)
        titel = eintrag["titel"]
        gab_es = katalog.hat_titel(alt, titel)
        _fortschreiben(pfad, katalog.upsert(alt, titel, text.strip()), beschreibung=beschreibung)
        return (f"{'Aktualisiert' if gab_es else 'Neu'} in {ort}: '{titel}'. "
                + _katalog_beweis(pfad, titel))
    if eintrag:
        # Ein Katalog-Kopf macht aus einer Notiz ein Vorhaben: Kopf setzen,
        # Prosa behalten, Art umstellen — die Datei bleibt, wo sie ist.
        neu_art = art or ("dossier" if ist == "notiz" else ist)
        _fortschreiben(pfad, katalog.kopf_setzen(alt, text), neu_art, beschreibung)
        hinweis = katalog_abgleichen(pfad)
        return f"Kopf von {ort}." + (f" {hinweis}." if hinweis else "")
    if text in alt:
        return f"Steht schon woertlich in {ort} — nichts geaendert."
    if ist == "notiz":
        anderswo = _wo_steht_der_titel(ablage.name_zerlegen(ort)[1])
        if anderswo:
            return _doppelt_hinweis(ablage.name_zerlegen(ort)[1], anderswo)
    if ist in _OHNE_DATUM:
        # Ohne Datums-Überschrift: eine Notiz ist eine Faktenliste, kein
        # Verlauf — wann etwas galt, steht im Tagebuch.
        rumpf = alt.rstrip("\n") + ("\n" if alt.strip() else "") + text + "\n"
    else:
        rumpf = alt.rstrip("\n") + f"\n\n## {date.today().isoformat()}\n{text}\n"
    _fortschreiben(pfad, rumpf, art, beschreibung)
    zu_lang = len(rumpf) > MAX_DOSSIER
    return (f"Notiert in {ort}."
            + (" ⚠ Die Datei ist sehr lang geworden — räum sie beim nächsten "
               "Mal auf (rewrite_note)." if zu_lang else ""))


dossier_notieren = notieren

# Arten, an die ohne Datums-Überschrift angehängt wird: Faktenlisten, kein
# Verlauf (Dossier, Projekt und alles Unbekannte bekommen „## JJJJ-MM-TT").
_OHNE_DATUM = ("notiz", "quelle", "steckbrief", "ziel", "regel", "katalog")


def _keine_katalog_form(ort: str) -> str:
    return ("[Das ist kein Katalog-Eintrag, sondern Prosa — ein Katalog nimmt "
            "nur Eintraege nach Schema (## Titel, darunter - thema:/- equipment:/"
            "- aufwand:/- status:). Lies read_note('vorlagen/katalog'). Fliesstext "
            f"gehoert in eine Notiz oder ein Dossier, nicht nach {ort}.]")


def _doppelt_hinweis(stamm: str, anderswo: str) -> str:
    # Dieselbe Sache an ZWEI Orten (20.08.2026): ob etwas Idee oder Fakt ist,
    # sieht der Code nicht — aber er merkt, dass es sie schon woanders gibt.
    return (f"Achtung: zu '{stamm}' gibt es schon einen Katalog-Eintrag in "
            f"{anderswo}. Trag es DORT nach (write_note '{anderswo}' mit dem "
            f"vollen Eintrag) statt eine zweite Ablage aufzumachen — sonst steht "
            f"dieselbe Sache an zwei Orten. Nichts geschrieben.")


def ersetzen(name: str, inhalt: str, thema: str = "") -> str:
    """Eine Datei komplett neu schreiben (gegatet). Der Datei-Kopf bleibt —
    außer der neue Inhalt bringt selbst einen mit; die alte Fassung liegt als
    .bak daneben. Gibt es sie nicht, wird sie als Notiz angelegt."""
    akte = _kern_von(name)
    if akte:
        kernakte_schreiben(akte, inhalt or "")
        return f"{_KERN_NAMEN[akte]} neu geschrieben (alte Fassung liegt als .bak daneben)."
    treffer = _alt_uebernehmen(name, thema)
    if len(treffer) > 1:
        return _mehrdeutig(treffer)
    neu_kopf, rumpf = ablage.zerlegen((inhalt or "").strip())
    if not treffer:
        _, stamm, _ = ablage.name_zerlegen(_bevorzugt(name)[0])
        if not stamm:
            return "[Fehler: kein Name]"
        pfad = _anlegen(thema, stamm, ablage.art_von(neu_kopf) if neu_kopf else "notiz",
                        str(neu_kopf.get("description") or ""), rumpf)
        return f"{_ort(pfad)} neu angelegt."
    pfad = treffer[0]
    alt = _lesen(pfad)
    dateien.atomar_schreiben(pfad + ".bak", alt)
    kopf = ablage.zerlegen(alt)[0]
    meta = neu_kopf.get("metadata") if isinstance(neu_kopf.get("metadata"), dict) else {}
    _fortschreiben(pfad, rumpf, meta.get("art", ""), str(neu_kopf.get("description") or ""))
    if not kopf:
        _geaendert(pfad, index=True)
    hinweis = katalog_abgleichen(pfad) if katalog.kopf_lesen(rumpf) and \
        ablage.art_von(ablage.zerlegen(_lesen(pfad))[0]) != "katalog" else ""
    return (f"{_ort(pfad)} neu geschrieben (alte Fassung liegt als .bak daneben)"
            + (f". {hinweis}." if hinweis else "."))


dossier_ersetzen = ersetzen


def archivieren(name: str, thema: str = "") -> str:
    """Eine Datei, die nicht mehr gilt, nach _archiv/ legen — nie löschen
    (der Abgleich ist additiv; Sasha will Falsches vielleicht nachlesen).
    Kernakten nie: die gehören Sasha."""
    if _kern_von(name):
        return "[Steckbrief, Ziele und Hausregeln archiviert die KI nicht — die gehören Sasha.]"
    treffer = finden(name, thema)
    if not treffer:
        return f"[Keine Datei {name!r}. Nichts archiviert.]"
    if len(treffer) > 1:
        return _mehrdeutig(treffer).replace("geschrieben", "archiviert")
    ort = _ort(treffer[0])
    ziel = ablage.archivieren(_wurzel(), treffer[0])
    _geaendert(ziel, index=True)
    datasync.notify_change(treffer[0])
    return f"{ort} archiviert (liegt jetzt unter {os.path.relpath(ziel, _DIR)})."


# ── Kataloge ──────────────────────────────────────────────────────────

def _kataloge() -> list:
    return [p for t in ablage.themen(_wurzel()) for p in ablage.dateien_im_thema(_DIR, t)
            if p.endswith(".katalog.md")]


def _wo_steht_der_titel(stamm: str) -> str:
    """In welchem Katalog steht schon ein Eintrag dieses Namens? → Ort oder ''.
    Über slug verglichen: „Fraktal-Rendering (3D)" und „fraktal-rendering"
    sind dieselbe Sache."""
    for p in _kataloge():
        if any(slug(t).startswith(stamm) for t in katalog.titel_liste(_rumpf(p))):
            return _ort(p)
    return ""


def _katalog_beweis(pfad: str, titel: str) -> str:
    """Nachlesen, was jetzt WIRKLICH dasteht → ein Satz. Das Werkzeug-Ergebnis
    geht ohnehin ans Modell zurück; steht dort der Beweis statt „OK", hat sie
    nachgesehen, ohne dass ein Aufruf mehr anfällt (Sasha, 20.08.2026)."""
    text = _rumpf(pfad)
    anzahl = len(katalog.titel_liste(text))
    if not katalog.hat_titel(text, titel):
        return "⚠ Steht anschliessend NICHT in der Datei — sag das."
    return ("Der Katalog hat jetzt %d %s."
            % (anzahl, "Eintrag" if anzahl == 1 else "Eintraege"))


def katalog_abgleichen(dossier_pfad: str) -> str:
    """Den Kopf eines Dossiers in seinen Katalog übertragen (vom Code, nicht
    vom Modell — so kann die Verknüpfung nicht vergessen werden). Der Katalog
    wird über alle Themen gesucht; fehlt er, entsteht er im Thema des
    Dossiers."""
    kopf = katalog.kopf_lesen(_rumpf(dossier_pfad))
    if not kopf:
        return ""
    name = slug(kopf.get("katalog") or "") or "ideen"
    stamm = os.path.basename(dossier_pfad)[:-3]
    kopf["katalog"], kopf["dossier"] = name, stamm
    treffer = ablage.finden(_DIR, name, "", (".katalog.md",))
    eintrag = katalog.eintrag_rendern(kopf)
    if treffer:
        pfad = treffer[0]
        _fortschreiben(pfad, katalog.upsert(_rumpf(pfad), kopf["titel"], eintrag))
        return f"{_ort(pfad)} aktualisiert ({kopf['titel']})"
    thema = os.path.basename(os.path.dirname(dossier_pfad))
    pfad = _anlegen(thema, name, "katalog", f"Katalog {name}", eintrag)
    return f"{_ort(pfad)} aktualisiert ({kopf['titel']}) — Katalog neu angelegt"


def konsistenz() -> list:
    """Was auseinandergelaufen ist (für Tests und auf Zuruf, nie im Prompt):
    Katalog-Einträge, deren `dossier:` ins Leere zeigt, und Dossiers ohne
    Kopf, die darum in keinem Katalog stehen."""
    aus, verlinkt = [], set()
    for p in _kataloge():
        for titel, ziel in katalog.verweise(_rumpf(p)):
            verlinkt.add(ziel)
            if not ablage.finden(_DIR, ziel, "", (".md",)):
                aus.append(f"{_ort(p)}: {titel!r} zeigt auf {ziel}, das es nicht gibt")
    for e in ablage.alle(_wurzel()):
        if e["art"] == "dossier" and e["name"] not in verlinkt \
                and not katalog.kopf_lesen(e["rumpf"]):
            aus.append(f"{_ort(e['pfad'])}: kein Katalog-Kopf — taucht in keinem "
                       f"Katalog auf. Absicht oder vergessen?")
    return aus


# ── Messreihen unter einem Thema ──────────────────────────────────────
# Die Werte führt core/graphs.py (Format unverändert, eine Liste je Tag);
# hier nur, WO sie liegen: themen/<thema>/<name>.reihe.json, daneben eine
# .reihe.md mit Kopf, damit die Reihe wie jede Datei im Index steht.

_TYP_WORT = {"number": "Zahl", "scale": "Skala 1–5", "time": "Uhrzeit",
             "period": "Zeitspanne"}


def reihe_anlegen(gid: str, thema: str, name: str, typ: str = "", einheit: str = "") -> str:
    """Eine (neue, leere) Messreihe unter ein Thema legen. → Ort der Kopf-Datei.
    Gibt es schon Werte in data/<gid>.json, bleiben sie dort, bis der Umzug
    sie holt — eine leere Datei unter dem Thema würde sie sonst verdecken."""
    stamm = ablage.reihe_stamm(gid)
    ordner = ablage.thema_ordner(_wurzel(), thema or ablage.ALLGEMEIN)
    werte = os.path.join(ordner, stamm + ablage.REIHE_JSON)
    if not os.path.exists(werte):
        ablage.schreiben(werte, "[]\n")
    einheit = f" in {einheit}" if einheit else ""
    kopf = ablage.neuer_kopf(stamm, f"Messreihe {name} ({_TYP_WORT.get(typ, typ)}{einheit})",
                             "messreihe", reihe=gid)
    md = os.path.join(ordner, stamm + ".reihe.md")
    ablage.schreiben(md, ablage.text_bauen(
        kopf, f"Die Werte liegen in {stamm}{ablage.REIHE_JSON} (Kurve „{name}“ im Graph-Werkzeug)."))
    _geaendert(md, index=True)
    return _ort(md)


def reihe_archivieren(gid: str) -> None:
    """Werte und Kopf einer Reihe nach _archiv/ (die Kurve wurde gelöscht)."""
    werte = ablage.reihe_finden(_DIR, gid)
    if not werte:
        return
    md = werte[:-len(ablage.REIHE_JSON)] + ".reihe.md"
    for p in (werte, md):
        if os.path.exists(p):
            ablage.archivieren(_DIR, p)
    _geaendert(werte, index=True)


# ── Vorlagen (ki/vorlagen/) ───────────────────────────────────────────

def vorlage(name: str) -> str:
    """Eine Vorlage lesen; beim ersten Zugriff aus dem Code angelegt, danach
    eine Datei, die Sasha umschreiben kann, ohne dass ein Update sie
    überbügelt."""
    schluessel = slug(name)
    if schluessel not in katalog.VORLAGEN:
        return f"[Keine Vorlage {name!r}. Es gibt: {', '.join(katalog.VORLAGEN)}]"
    pfad = os.path.join(_wurzel(), ablage.KI, "vorlagen", schluessel + ".md")
    if not os.path.exists(pfad):
        ablage.schreiben(pfad, katalog.VORLAGEN[schluessel])
    return _lesen(pfad).strip()


# ── Tagebuch: themen/tagebuch/<JJJJ-MM>.md, je Tag eine Überschrift ────

_MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember")


def tagebuch_pfad(tag) -> str:
    return os.path.join(_DIR, ablage.THEMEN, ablage.TAGEBUCH, f"{tag:%Y-%m}.md")


def tagebuch_notieren(text: str, tag=None) -> str:
    """Eine Zeile ins Tagebuch, mit Uhrzeit. SEINE Worte, nicht destilliert —
    daraus wird später „wie war eigentlich Spanien" beantwortet."""
    text = (text or "").strip()
    if not text:
        return "[Fehler: leerer Eintrag]"
    if len(text) > MAX_NOTIZ:
        text = text[:MAX_NOTIZ] + " …[gekürzt]"
    t = tag or date.today()
    pfad = tagebuch_pfad(t)
    zeile = f"- {datetime.now().strftime('%H:%M')} {text}\n"
    if not os.path.exists(pfad):
        kopf = ablage.neuer_kopf(f"{t:%Y-%m}", f"Tagebuch {_MONATE[t.month - 1]} {t.year}",
                                 "tagebuch")
        ablage.schreiben(pfad, ablage.text_bauen(kopf, f"## {t.isoformat()}\n{zeile}"))
        _geaendert(pfad, index=True)
        return "Ins Tagebuch geschrieben."
    kopf, rumpf = ablage.zerlegen(_lesen(pfad))
    tage = re.findall(r"^## (\d{4}-\d{2}-\d{2})\s*$", rumpf, re.M)
    if not tage or tage[-1] != t.isoformat():
        rumpf = rumpf.rstrip("\n") + f"\n\n## {t.isoformat()}\n"
    ablage.schreiben(pfad, ablage.text_bauen(ablage.kopf_auffrischen(kopf),
                                             rumpf.rstrip("\n") + "\n" + zeile))
    _geaendert(pfad)
    return "Ins Tagebuch geschrieben."


def tagebuch_lesen(tag=None) -> str:
    """Die Einträge eines Tages (Standard: heute); vor dem Umzug aus der
    alten Tagesdatei."""
    t = tag or date.today()
    rumpf = _rumpf(tagebuch_pfad(t))
    m = re.search(rf"^## {t.isoformat()}\s*\n(.*?)(?=^## |\Z)", rumpf, re.M | re.S)
    if m:
        return m.group(1).strip()
    return _lesen(os.path.join(_DIR, "tagebuch", t.isoformat() + ".md")).strip()


# ── Suche ─────────────────────────────────────────────────────────────

def _alt_dateien() -> list:
    """Vor dem Umzug: (ort, pfad) der Dateien im alten Aufbau."""
    raus = []
    for bereich in ("tagebuch",) + ALT_BEREICHE:
        ordner = os.path.join(_DIR, bereich)
        if os.path.isdir(ordner):
            raus += [(f"{bereich}/{f[:-3]}", os.path.join(ordner, f))
                     for f in sorted(os.listdir(ordner), reverse=True) if f.endswith(".md")]
    return raus


def suchen(begriff: str, max_treffer: int = MAX_TREFFER) -> str:
    """Volltextsuche über Hausregeln, Steckbrief, Ziele und alle Themen
    (samt Tagebuch, Katalogen, Quellen und dem Haken jeder Datei).

    Stumpfer Substring-Vergleich, absichtlich: kein Embedder, keine
    Datenbank, und er findet Eigennamen zuverlässiger als jede Ähnlichkeits-
    suche. Wird er zu grob, kommt ein Index DARÜBER — nicht darunter."""
    begriff = (begriff or "").strip()
    if len(begriff) < 2:
        return "[Fehler: Suchbegriff zu kurz]"
    nadel = begriff.casefold()
    treffer = []

    def durch(ort, zeilen):
        for zeile in zeilen:
            if len(treffer) >= max_treffer:
                return
            if nadel in zeile.casefold() and not zeile.startswith("# "):
                treffer.append(f"[{ort}] {zeile.strip()}")

    for akte in KERNAKTEN:
        durch(_KERN_NAMEN[akte], kernakte_lesen(akte).splitlines())
    for e in ablage.alle(_wurzel()):
        if os.path.dirname(e["pfad"]) == os.path.dirname(kern_pfad(STECKBRIEF)) \
                and e["name"] in (STECKBRIEF, ZIELE):
            continue
        ort = _ort(e["pfad"])
        durch(ort, [f"(Haken) {e['beschreibung']}"] if e["beschreibung"] else [])
        durch(ort, e["rumpf"].splitlines())
    for ort, pfad in _alt_dateien():
        durch(ort, _lesen(pfad).splitlines())
    if not treffer:
        return (f"Nichts zu {begriff!r} gefunden (Hausregeln, Steckbrief, Ziele "
                f"und alle Themen samt Tagebuch durchsucht).")
    return f"{len(treffer)} Treffer zu {begriff!r}:\n" + "\n".join(treffer)


# ── Für Sasha und die Routen: was in welchem Thema liegt ──────────────

def themen_uebersicht() -> list:
    """[{thema, dateien: [{name, art, beschreibung, ort}]}] — die TUI zeigt
    das Gedächtnis nach Themen (GET /api/gedaechtnis)."""
    raus = []
    for t in ablage.themen(_wurzel()):
        eintraege = [ablage.eintrag(_DIR, p) for p in ablage.dateien_im_thema(_DIR, t)]
        raus.append({"thema": t, "dateien": [
            {"name": e["name"], "art": e["art"], "beschreibung": e["beschreibung"],
             "ort": _ort(e["pfad"])} for e in eintraege]})
    alt = {}
    for ort, _ in _alt_dateien():
        bereich, name = ort.split("/", 1)
        alt.setdefault(bereich, []).append(name)
    for bereich, namen_ in sorted(alt.items()):
        raus.append({"thema": f"{bereich} (alter aufbau)", "dateien": [
            {"name": n, "art": "", "beschreibung": "", "ort": f"{bereich}/{n}"}
            for n in sorted(namen_)]})
    return raus


# ── Was in den gecachten Prompt-Kopf geht ─────────────────────────────

_REGELN = (
    "Das sind Namen und Haken, keine Inhalte: geht es um eine Sache, lies die "
    "Datei mit read_note (\"thema/name\") — rate nicht aus dem Titel.\n"
    "- Festhalten mit write_note. Erst nachsehen, ob es schon eine passende "
    "Datei gibt, und die ergänzen statt eine zweite anzulegen.\n"
    "- Neue Datei: thema (ein vorhandenes, ein neues nur wenn keins passt), "
    "art und beschreibung (eine Zeile — danach entscheidest du später, ob du "
    "sie liest). Arten: notiz (Fakten, kurze Listen), dossier (Prosa über eine "
    "Sache, die er verfolgt — Vorlage read_note(\"vorlagen/dossier\"); ihr "
    "Katalog-Eintrag entsteht von selbst), katalog (viele Einträge nach einem "
    "Schema, Vorlage \"vorlagen/katalog\"), quelle, ziel, projekt.\n"
    "- Nicht festhalten, was ohnehin nachlesbar ist (Kalender, Mails, "
    "Gespräche). Relative Zeitangaben („morgen\") als festes Datum. Sagt Sasha, "
    "wie du etwas machen sollst: das Warum und wann es gilt mitschreiben.\n"
    "- Was nicht mehr stimmt: archive_note — nichts wird gelöscht.")


def kopf_block() -> str:
    """Hausregeln + Steckbrief + der Index. Sonst nichts.

    Bewusst nur der Index (wie Claudes MEMORY.md): sie soll SEHEN, dass es
    ein Spagat-Dossier gibt, und es lesen, wenn es um den Spagat geht. Byte-
    stabil, solange keine Datei dazukommt oder ihren Haken ändert — gehört
    deshalb in den gecachten Teil (10 % des Preises). Die Ziele stehen seit
    2026-10-11 nur noch im Index (person/ziele), nicht mehr ganz im Kopf."""
    teile = []
    r = hausregeln()
    if r:
        teile.append("## Hausregeln\n"
                     "Das hat Sasha dir ausdrücklich gesagt. Im Zweifel geht "
                     "es jeder allgemeinen Anweisung vor.\n" + _ohne_titel(r))
    s = steckbrief()
    if s:
        teile.append("## Über Sasha\n" + _ohne_titel(s))
    index = ablage.index_text(_DIR) if os.path.isdir(_DIR) else ""
    alt = sorted({ort.split("/", 1)[0] for ort, _ in _alt_dateien()})
    if alt:
        index += ("\n\n" if index else "") + "## alter aufbau (noch nicht umgezogen)\n" + \
            "\n".join(f"- {b}/ — " + ", ".join(sorted(o.split("/", 1)[1] for o, _ in _alt_dateien()
                                                     if o.startswith(b + "/")))
                      for b in alt)
        z = ziele()
        if z and not os.path.exists(kern_pfad(ZIELE)):
            teile.append("## Seine Ziele\n" + _ohne_titel(z))
    if index:
        teile.append("## Was im Gedächtnis liegt\n" + index + "\n\n" + _REGELN)
    return "\n\n".join(teile)


# ── Import aus einer anderen KI (write_note mit herkunft) ─────────────
#
# 2026-10-08, Skill import-memory: Sasha holt seine Erinnerungen aus Claude
# (oder ChatGPT/Gemini) herüber. Ein Import ist NUR ERGÄNZEN — im Code
# verankert, nicht nur eine Bitte im Skill: zeilenweise (was schon dasteht,
# wird übersprungen), nie in Kataloge (dort ERSETZT ein gleichnamiger Eintrag),
# nie ins Tagebuch, keine Zeilen mit Link oder Bild, Herkunftsvermerk vom
# CODE, die Datei einmal atomar geschrieben. Kernakten über das Gate.

IMPORT_MAX_ZEILEN = 30     # je Aufruf — der Skill schreibt in Etappen
IMPORT_MAX_ZEILE = 500     # Zeichen je Zeile
_IMPORT_LINK = re.compile(r"https?://|www\.|!\[|\]\(", re.I)
_IMPORT_DATUM = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]\s*(?:[-–:]\s*)?")
_IMPORT_VERMERK = re.compile(r"\s*(\[import [^\]]*\]|_\(seit [^)]*\)_)\s*$", re.I)


def _import_kern(zeile: str) -> str:
    """Vergleichsform einer Zeile: ohne Aufzählung, Datum, Vermerk, Satzende."""
    z = (zeile or "").strip().lstrip("-*• ").strip()
    z = _IMPORT_DATUM.sub("", z)
    while True:
        kuerzer = _IMPORT_VERMERK.sub("", z)
        if kuerzer == z:
            break
        z = kuerzer
    return " ".join(z.split()).rstrip(".!;").casefold()


def _import_herkunft(herkunft: str) -> str:
    h = re.sub(r"[^a-z0-9-]+", "-", (herkunft or "").strip().lower()).strip("-")
    return h[:20]


def _import_auswahl(text: str, vorhanden: str, wer: str) -> tuple:
    """→ (neue fertige Zeilen, übersprungen als [(grund, zeile)])."""
    schon = {_import_kern(z) for z in vorhanden.splitlines() if _import_kern(z)}
    heute = date.today().isoformat()
    neu, weg = [], []
    for roh in (text or "").splitlines():
        zeile = roh.strip().lstrip("-*• ").strip()
        kern = _import_kern(zeile)
        if not zeile or not kern:
            continue
        if _IMPORT_LINK.search(zeile):
            weg.append(("enthält einen Link oder ein Bild", zeile))
        elif len(zeile) > IMPORT_MAX_ZEILE:
            weg.append((f"länger als {IMPORT_MAX_ZEILE} Zeichen", zeile))
        elif kern in schon:
            weg.append(("steht schon da", zeile))
        else:
            schon.add(kern)
            m = _IMPORT_DATUM.match(zeile)
            vom = f", Eintrag vom {m.group(1)}" if m else ""
            zeile = _IMPORT_DATUM.sub("", zeile).strip()
            neu.append(f"- {zeile}  [import {wer} {heute}{vom}]")
    return neu, weg


def import_ergaenzen(name: str, text: str, herkunft: str, thema: str = "") -> str:
    """Zeilen aus einem Import anhängen — nur, was noch nicht da ist.
    `text` = eine Tatsache je Zeile. Neue Dateien werden Notizen im Thema
    `thema` (sonst „allgemein")."""
    wer = _import_herkunft(herkunft)
    if not wer:
        return "[Fehler: herkunft fehlt — z.B. 'claude' oder 'chatgpt']"
    roh = (name or "").strip().lower()
    if roh in ("", "tagebuch", "diary") or roh.startswith("tagebuch/"):
        return ("[Ein Import gehört nicht ins Tagebuch — nimm eine Notiz, ein "
                "Dossier oder (nach Sashas Ja) Steckbrief/Ziele. Nichts geschrieben.]")
    zeilen = [z for z in (text or "").splitlines() if z.strip()]
    if not zeilen:
        return "[Fehler: keine Zeilen]"
    if len(zeilen) > IMPORT_MAX_ZEILEN:
        return (f"[{len(zeilen)} Zeilen sind zu viele für einen Schritt (höchstens "
                f"{IMPORT_MAX_ZEILEN}) — teil es auf. Nichts geschrieben.]")
    akte = _kern_von(name)
    if akte:
        alt = kernakte_lesen(akte)
        ort = _KERN_NAMEN[akte]
    else:
        treffer = _alt_uebernehmen(name, thema)
        if len(treffer) > 1:
            return _mehrdeutig(treffer)
        art = ablage.art_von(ablage.zerlegen(_lesen(treffer[0]))[0]) if treffer else "notiz"
        praefix = roh.split("/", 1)[0] if "/" in roh else ""
        if art in ("katalog", "quelle", "vorlage", "messreihe", "tagebuch") or \
                praefix in ("kataloge", "quellen", "vorlagen") or roh.endswith(".katalog"):
            return (f"[Ein Import schreibt nicht in {art if treffer else name} — dort "
                    f"würde Vorhandenes ersetzt oder es ist kein Ort für Fakten. Nimm "
                    f"eine Notiz. Nichts geschrieben.]")
        _, stamm, _ = ablage.name_zerlegen(_bevorzugt(name)[0])
        if not stamm:
            return "[Fehler: kein Name]"
        if not treffer:
            anderswo = _wo_steht_der_titel(stamm)
            if anderswo:
                return (f"[Zu '{stamm}' gibt es schon einen Katalog-Eintrag in "
                        f"{anderswo} — nimm einen anderen Namen oder frag Sasha. "
                        f"Nichts geschrieben.]")
        alt = _rumpf(treffer[0]) if treffer else ""
        ort = _ort(treffer[0]) if treffer else f"{slug(thema) or ablage.ALLGEMEIN}/{stamm}"
    neu, weg = _import_auswahl(text, alt, wer)
    if neu:
        _import_schreiben(akte, treffer[0] if not akte and treffer else None,
                          thema, name, alt, neu, wer)
    teile = [f"{'Ergänzt in' if alt else 'Neu angelegt:'} {ort}: {len(neu)} Zeile(n)"
             + f", je mit [import {wer} {date.today().isoformat()}]"
             if neu else f"Nichts geschrieben in {ort}"]
    for grund, zeile in weg:
        kurz = zeile if len(zeile) <= 80 else zeile[:79] + "…"
        teile.append(f"übersprungen ({grund}): {kurz!r}")
    if neu:
        jetzt = kernakte_lesen(akte) if akte else dossier_lesen(name, thema)
        teile.append(f"Die Datei hat jetzt {len(jetzt.splitlines())} Zeilen.")
    return " · ".join(teile)


def _import_schreiben(akte, pfad, thema, name, alt, neu, wer) -> None:
    text = alt.rstrip("\n") + "\n" if alt.strip() else (
        HAUSREGELN_KOPF if akte == HAUSREGELN else "")
    if pfad and ablage.art_von(ablage.zerlegen(_lesen(pfad))[0]) in ("dossier", "projekt"):
        # Wie beim Fortschreiben eines Dossiers unter einer Überschrift —
        # einmal je Tag und Herkunft, nicht über jeder Etappe neu.
        kopf = f"## {date.today().isoformat()} · import {wer}"
        if [z for z in text.splitlines() if z.startswith("## ")][-1:] != [kopf]:
            text += ("" if text.endswith("\n\n") else "\n") + kopf + "\n"
    rumpf = text + "\n".join(neu) + "\n"
    if akte:
        kernakte_schreiben(akte, rumpf)
    elif pfad:
        _fortschreiben(pfad, rumpf)
    else:
        _, stamm, _ = ablage.name_zerlegen(_bevorzugt(name)[0])
        _anlegen(thema, stamm, "notiz", f"Aus dem Import von {wer}", rumpf, herkunft=wer)


# ── Dokumente holen und lesbar machen ─────────────────────────────────

# Binaeres, das nicht in Text umzuwandeln ist, landet hier — MIT einem
# Markdown-Vermerk daneben. Sashas Bedingung: es soll nichts rumfliegen.
# Deshalb gilt: jede geholte Sache hat GENAU EINEN Ort und IMMER einen
# lesbaren Eintrag in quellen/, auch wenn die Datei selbst binaer ist.
DATEIEN = "dateien"   # Unterordner im Thema: themen/<thema>/dateien/

_ENDUNGEN = {
    "application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg",
    "image/gif": "gif", "image/svg+xml": "svg", "application/zip": "zip",
    "text/csv": "csv", "application/json": "json",
}


def pdf_text(daten: bytes) -> tuple:
    """PDF-Bytes → (text, fehler). Genau einer von beiden ist leer.

    Herausgelöst am 2026-10-07 aus dokument_holen, damit Anhänge denselben
    Weg gehen — zwei PDF-Wege liefen sonst irgendwann auseinander. Seit
    2026-10-08 über core/pdf_datei.py (pypdf, mit Seitenmarken) statt
    `pdftotext`: derselbe Leser wie read_pdf und die Anhänge, und er läuft
    auch auf Rechnern ohne poppler."""
    import pdf_datei
    return pdf_datei.text_alle(daten)


def herunterladen(url: str) -> tuple:
    """-> (bytes, Inhaltstyp) einer http(s)-Adresse, höchstens
    _MAX_DOKUMENT + 1 Bytes. Eigene Funktion (2026-10-10), damit der
    Prüfstand fetch_document wie fetch_url auf seinen Netz-Ersatz lenken
    kann — vorher ging es an ihm vorbei ins echte Netz."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as antwort:
        daten = antwort.read(_MAX_DOKUMENT + 1)
        typ = (antwort.headers.get("Content-Type") or "").split(";")[0].strip()
    return daten, typ


def dokument_holen(url: str, name: str, thema: str = "") -> str:
    """Etwas aus dem Netz holen, lesbar machen, an EINEN Ort legen.

    Die Werkzeugkette, die Sasha wollte: sie sucht das Modulhandbuch im
    Netz, zieht es, legt es richtig ab und kann es danach lesen — ohne
    dass er eine Datei anfassen muss.

    Drei Faelle, ein Ergebnis:
      * PDF   → per `pdftotext` (poppler) zu Text. Ein PDF ist binaer, die
                KI kann es NICHT direkt lesen — und das waere auch die
                falsche Loesung: ein Modulhandbuch hat hundert Seiten, die
                niemand pro Frage im Kontext haben will. Einmal
                extrahiert ist es durchsuchbar und billig.
      * Text/HTML → Tags raus, Text nach themen/<thema>/<name>.md (art quelle).
      * Binaeres  → Datei nach themen/<thema>/dateien/, PLUS ein Vermerk
                in <name>.md, was das ist und wo es herkommt.

    Der letzte Punkt ist die eigentliche Regel: es entsteht nie eine
    Datei ohne Eintrag. Sonst liegt in einem halben Jahr ein Ordner voller
    namenloser Downloads herum, und niemand weiss mehr, wozu.

    Unterschied zu `fetch_url`: das holt etwas, um es JETZT zu lesen, und
    vergisst es danach. Hier wird abgelegt, um es spaeter wiederzufinden.
    """
    import re as _re
    import html as _html

    schluessel = _slug(name)
    if not schluessel:
        return "[Fehler: kein Name fuer die Ablage]"

    quelle = (url or "").strip()
    aus_dem_netz = quelle.lower().startswith(("http://", "https://"))

    if aus_dem_netz:
        try:
            daten, typ = herunterladen(quelle)
        except Exception as e:
            return f"[Download fehlgeschlagen: {e}]"
    else:
        # LOKALE DATEI. Sasha legt Modulhandbuch und Stundenplan als PDF hin,
        # statt eine URL zu haben — ohne diesen Weg kaeme sie nicht daran.
        #
        # Ueber die Erlaubnis entscheidet context.erlaubt(), also dieselbe
        # Instanz wie bei read_file. Zwei Antworten auf "was darf sie sehen"
        # waeren die Sorte Sicherheitsluecke, die niemand bemerkt: eine
        # Ablage-Funktion, die mehr erreicht als die Lese-Funktion, ist ein
        # Umweg um die Sperre.
        import context
        pfad = context.pfad_aufloesen(quelle)
        grund = context.erlaubt(pfad)
        if grund:
            return f"[Zugriff verweigert: {grund}]"
        if not os.path.isfile(pfad):
            return f"[Datei nicht gefunden: {quelle}]"
        if os.path.getsize(pfad) > _MAX_DOKUMENT:
            return f"[Groesser als {_MAX_DOKUMENT // 1_000_000} MB — abgebrochen.]"
        with open(pfad, "rb") as f:
            daten = f.read()
        endung = os.path.splitext(pfad)[1].lower()
        typ = {".pdf": "application/pdf", ".md": "text/markdown",
               ".txt": "text/plain", ".json": "application/json",
               ".html": "text/html", ".csv": "text/csv"}.get(endung, "")
        if not typ and daten[:5] != b"%PDF-":
            # Ohne bekannte Endung: als Text versuchen, wenn es sich als
            # UTF-8 lesen laesst. Sonst faellt es unten in den Datei-Zweig.
            try:
                daten.decode("utf-8")
                typ = "text/plain"
            except UnicodeDecodeError:
                typ = ""
        quelle = pfad

    if len(daten) > _MAX_DOKUMENT:
        return f"[Groesser als {_MAX_DOKUMENT // 1_000_000} MB — abgebrochen.]"

    kopf = (f"> {'Geholt' if aus_dem_netz else 'Uebernommen'} "
            f"am {date.today().isoformat()} von {quelle}\n")
    thema = slug(thema) or ablage.ALLGEMEIN
    beschreibung = f"Dokument, {'geholt' if aus_dem_netz else 'übernommen'} von " + (
        quelle if len(quelle) <= 80 else quelle[:79] + "…")

    # ── PDF ──────────────────────────────────────────────────────────
    if daten[:5] == b"%PDF-":
        text, fehler = pdf_text(daten)
        if fehler:
            return f"[{fehler}]"
        kopf += "> Aus dem PDF extrahiert.\n\n"

    # ── Text und HTML ────────────────────────────────────────────────
    elif typ.startswith("text/") or typ in ("application/json",
                                            "application/xml"):
        text = daten.decode("utf-8", "replace")
        if "html" in typ:
            text = _re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
            text = _re.sub(r"(?i)<(br|/p|/div|/h[1-6]|/li)[^>]*>", "\n", text)
            text = _re.sub(r"<[^>]+>", " ", text)
            text = _html.unescape(text)
            text = _re.sub(r"[ \t]+", " ", text)
            text = _re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
            kopf += "> Aus HTML zu Text gemacht.\n\n"
        else:
            kopf += f"> Originaltyp: {typ or 'text'}\n\n"
        text = text.strip()
        if not text:
            return "[Leere Seite.]"

    # ── Alles andere: Datei ablegen, Vermerk schreiben ───────────────
    else:
        endung = _ENDUNGEN.get(typ) or (url.rsplit(".", 1)[-1][:5].lower()
                                        if "." in url.rsplit("/", 1)[-1]
                                        else "bin")
        ordner = os.path.join(ablage.thema_ordner(_wurzel(), thema), DATEIEN)
        os.makedirs(ordner, exist_ok=True)
        ziel = os.path.join(ordner, f"{schluessel}.{endung}")
        dateien.atomar_schreiben(ziel, daten)
        text = (f"Binaerdatei, nicht als Text lesbar.\n\n"
                f"- Typ:   {typ or 'unbekannt'}\n"
                f"- Groesse: {len(daten) // 1024} KB\n"
                f"- Liegt:  `themen/{thema}/{DATEIEN}/{schluessel}.{endung}`\n")
        kopf += "> Die Datei selbst liegt daneben, hier steht nur der Vermerk.\n\n"
        ort = _quelle_ablegen(thema, schluessel, beschreibung, kopf + text)
        return (f"Datei abgelegt als themen/{thema}/{DATEIEN}/{schluessel}.{endung}, "
                f"Vermerk in {ort}.")

    if len(text) > _MAX_DOKUMENT_TEXT:
        text = text[:_MAX_DOKUMENT_TEXT] + "\n\n…[hier abgeschnitten]"
    ort = _quelle_ablegen(thema, schluessel, beschreibung, kopf + text)
    return (f"{ort} abgelegt ({len(text)} Zeichen). "
            f"Such gezielt mit search_memory darin, statt es am Stueck zu "
            f"lesen — und kipp es nie ganz in eine Antwort.")


def _quelle_ablegen(thema: str, schluessel: str, beschreibung: str, rumpf: str) -> str:
    """Eine Quelle anlegen oder (gleicher Name im Thema) ersetzen. → Ort."""
    pfad = ablage.pfad(_wurzel(), thema, schluessel, "quelle")
    neu = not os.path.exists(pfad)
    kopf = ablage.neuer_kopf(schluessel, beschreibung, "quelle")
    ablage.schreiben(pfad, ablage.text_bauen(kopf, rumpf))
    _geaendert(pfad, index=neu)
    return _ort(pfad)
