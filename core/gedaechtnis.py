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
# ── Die Speicher ──────────────────────────────────────────────────────
#
#   steckbrief   sasha.md       Wer er ist, was gilt. SASHA pflegt das.
#   ziele        ziele.md       Ziele mit Horizont. Sasha pflegt, KI schlägt vor.
#   dossiers     dossiers/*.md  PROSA über EINE Sache, die er ernsthaft verfolgt.
#   kataloge     kataloge/*.md  VIELE gleichförmige Einträge mit Attributen.
#   quellen      quellen/*.md   Abgelegte Dokumente (aus PDF extrahiert).
#   tagebuch     tagebuch/*.md  Was gesagt und getan wurde, chronologisch.
#
# ── Dossier oder Katalog? Die Regel ───────────────────────────────────
# Was man LESEN will, wird Prosa. Was man DURCHSEHEN will, wird Katalog.
#
# Der Ideenpool ist der Fall, an dem das kippt: Sasha hat tausende Maker-
# und Hacker-Ideen. Pro Idee ein Dossier wäre unlesbar, und Prosa lässt
# sich nicht überfliegen. Ein Katalog-Eintrag ist dagegen in zwanzig
# Sekunden getippt und in einem Rutsch zu scannen:
#
#   ## Fourier-Visualisierer aufm Oszi
#   - thema:     fourier, frequenzen, signale
#   - equipment: arduino, dac, loetkolben
#   - aufwand:   klein
#   - status:    idee
#   - dossier:   -
#
# Wird eine Sache ernst, bekommt sie ein DOSSIER, und der Katalog-Eintrag
# zeigt darauf (`dossier:`). Das gilt nicht nur für Elektronik: auch den
# Spagat lernt man strategisch — wo genau die Beweglichkeit blockiert,
# welche Muskelgruppen Unterstützung brauchen. Das ist mehr, als in einen
# Katalog-Eintrag passt, und weniger als ein Elektronikprojekt.
#
# ── Wo die Messreihen verlinkt werden: im DOSSIER ─────────────────────
# Bewusst NICHT im Katalog-Eintrag. Was nur als Idee notiert und morgen
# vergessen ist, wird nicht vermessen — weder der aktuelle Stand noch ein
# Trend. Gemessen wird, was man wirklich verfolgt, und genau das ist die
# Schwelle, ab der ein Dossier existiert.
#
# ── Wie das Schemen daraus Verbindungen zieht ─────────────────────────
# Über GETEILTE STICHWORTE, nicht über Kanten. Die Idee sagt
# `thema: fourier`, das Modul im Katalog sagt `thema: signalverarbeitung,
# fourier`, die Interessens-Spur von heute Morgen sagt `fourier`. »Welche
# Idee passt jetzt« ist damit eine Schnittmenge, die die Volltextsuche
# beantwortet — ohne dass irgendwo ein Extraktor Beziehungen erfindet.
# Genau daran ist der Graph gescheitert: er dachte sich die Vokabeln
# selbst aus. Hier kommen sie aus Sashas Katalogen, sichtbar und
# korrigierbar.
#
# ── Fertigkeiten werden ABGELEITET, nicht gepflegt ────────────────────
# Es gibt bewusst keine handgepflegte Fertigkeitsliste. Was Sasha kann,
# steht in den Dossiers abgeschlossener Projekte (`gelernt:`-Zeilen) —
# wer drei Dinge mit I2C gebaut hat, kann I2C. Eine Liste, die man von
# Hand nachführt, ist am Tag nach dem Anlegen veraltet.
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
HAUSREGELN = "hausregeln"

# Die drei Dateien, die GANZ OBEN liegen (nicht in einem Bereich) und
# vollstaendig in den Prompt gehen. Alles andere holt sie per Werkzeug.
_OBEN = (HAUSREGELN, STECKBRIEF, ZIELE)

# Obergrenzen. Ein Dossier, das ein Modell vollschreibt, bis es den halben
# Kontext frisst, ist wieder dasselbe Problem in Grün.
MAX_DOSSIER = 20_000     # Zeichen; darüber wird beim Anhängen gewarnt
MAX_NOTIZ   = 4_000      # Zeichen pro einzelnem Eintrag
MAX_TREFFER = 12         # Suchtreffer
_MAX_DOKUMENT = 25_000_000   # Bytes Download; ein Modulhandbuch liegt weit darunter
_MAX_DOKUMENT_TEXT = 400_000 # Zeichen je abgelegtem Text


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


def _ohne_titel(text: str) -> str:
    """Fuehrende "# Titel"-Zeile abschneiden.

    Im Prompt steht ueber jedem Block schon eine Ueberschrift; die des
    Dateikopfs dazu waere doppelt. Zwei Zeilen Rauschen mal drei Dateien,
    bei jedem Cache-Write bezahlt.
    """
    zeilen = text.lstrip().splitlines()
    if zeilen and zeilen[0].startswith("# "):
        zeilen = zeilen[1:]
    return "\n".join(zeilen).strip()


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


def hausregeln() -> str:
    """Verhaltensregeln, die SASHA im Gespraech gesetzt hat.

    Der Kern-Prompt ist Code: versioniert, getestet, reviewbar. Er bleibt
    es. Aber Sasha sagt Dinge wie "lass das", "frag nicht so viel", "das
    brauch ich nicht" — und ohne einen Ort dafuer ist die Korrektur nach
    einem Turn wieder weg.

    Warum die KI NICHT ihren eigenen Prompt umschreiben darf: sie wuerde
    frueher oder spaeter genau die Regeln entfernen, die sie am Erfinden
    und am Vorschnell-Notieren hindern — und niemand merkt es, weil der
    Prompt nur im Devtools sichtbar ist. Eine getrennte Datei kostet
    dieselbe Wirkung und ist in zehn Sekunden zu ueberpruefen.

    Sie steht deshalb im Prompt VOR allem anderen: was Sasha ausdruecklich
    gesagt hat, schlaegt im Zweifel die allgemeine Anweisung.
    """
    return _lesen(_pfad("", HAUSREGELN)).strip()


def regel_notieren(text: str) -> str:
    """Eine Hausregel anhaengen, mit Datum.

    Bewusst anhaengen und nicht ersetzen — auch hier gilt, dass ein Modell
    beim Neuschreiben verliert, was es gerade nicht im Kopf hat. Zum
    Aufraeumen gibt es rewrite_note.
    """
    text = (text or "").strip().lstrip("-").strip()
    if not text:
        return "[Fehler: leere Regel]"
    if len(text) > 400:
        return "[Zu lang fuer eine Regel — sag es in einem Satz.]"
    pfad = _pfad("", HAUSREGELN)
    if not os.path.exists(pfad):
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("# Hausregeln\n\n> Von Sasha im Gespräch gesetzt. Er darf "
                    "hier jederzeit streichen und ändern.\n\n")
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(f"- {text}  _(seit {date.today().strftime('%d.%m.%Y')})_\n")
    return f"Als Hausregel festgehalten: {text}"


# ── Bereiche ──────────────────────────────────────────────────────────

BEREICHE = ("dossiers", "notizen", "kataloge", "quellen", "vorlagen")

# Zustaende eines Katalog-Eintrags. Sashas Schnitt, 18.08.2026 — er
# unterscheidet, was bloss Einfall ist, was ihm wirklich wichtig waere,
# was fuer bald angestellt ist und was tatsaechlich schon im Plan steht.
STATUS = ("idee", "priorisiert", "queued", "in_schedule",
          "abgeschlossen", "pausiert")


def liste(bereich: str) -> list:
    ordner = os.path.join(_wurzel(), bereich)
    if not os.path.isdir(ordner):
        return []
    return sorted(f[:-3] for f in os.listdir(ordner) if f.endswith(".md"))


def _finden(name: str) -> tuple:
    """(bereich, schluessel) zu einem Namen — mit oder ohne Praefix.

    Akzeptiert "kataloge/ideen" genauso wie "ideen". Ohne Praefix wird in
    allen Bereichen gesucht; existiert nichts, landet Neues in `notizen`.

    Der Default war bis 18.08.2026 `dossiers`, und das war eine Falle.
    Seit ein Dossier einen Katalog-Kopf hat (thema/equipment/aufwand/
    status), ist es ein VORHABEN — kein Ort fuer einen schlichten Fakt.
    Als Sasha fragte, ob sie sich Wegzeiten merken kann, ueberlegte sie
    genau richtig ("am einfachsten eine kurze Notiz 'wegzeiten'"), konnte
    das aber nicht ausfuehren: jeder neue Name wurde ein Dossier. Also
    schrieb sie die Fahrzeit zur Geigenschule in `dossiers/umzug` — die am
    wenigsten falsche vorhandene Datei.

    `notizen` ist der ungefaehrliche Default: formlos, ohne Kopf, ohne
    Katalog-Eintrag. Ein Vorhaben entsteht nicht mehr aus Versehen durch
    einen neuen Namen, sondern absichtlich dadurch, dass sie die Vorlage
    ausfuellt (siehe `dossier_notieren`).
    """
    roh = (name or "").strip().strip("/")
    if "/" in roh:
        kopf, rest = roh.split("/", 1)
        kopf = kopf.strip().lower()
        if kopf in BEREICHE:
            return kopf, _slug(rest)
    schluessel = _slug(roh)
    if schluessel in _OBEN:
        return "", schluessel
    for bereich in BEREICHE:
        if os.path.exists(_pfad(bereich, schluessel)):
            return bereich, schluessel
    return "notizen", schluessel


# ── Dossiers (und die anderen Bereiche, gleicher Mechanismus) ─────────

def dossier_liste() -> list:
    return liste("dossiers")


def dossier_lesen(name: str) -> str:
    bereich, schluessel = _finden(name)
    return _lesen(_pfad(bereich, schluessel)).strip()


def dossier_notieren(name: str, text: str) -> str:
    """Einen datierten Absatz an ein Dossier hängen. Legt es an, wenn nötig.

    ANHÄNGEN, nicht überschreiben: eine KI, die eine Datei ersetzt, löscht
    stillschweigend alles, was sie beim Schreiben nicht im Kopf hatte. Für
    echtes Umschreiben gibt es `dossier_ersetzen`, und das hängt am
    Erlaubnis-Gate.
    """
    bereich, schluessel = _finden(name)
    if not schluessel:
        return "[Fehler: kein Name]"
    text = (text or "").strip()
    if not text:
        return "[Fehler: leerer Eintrag]"
    if len(text) > MAX_NOTIZ:
        text = text[:MAX_NOTIZ] + " …[gekürzt]"

    pfad = _pfad(bereich, schluessel)

    # Beginnt der Text mit einem Katalog-Kopf, ist er der KOPF des Dossiers
    # und keine Tagesnotiz. Ihn unter eine Datums-Ueberschrift zu haengen
    # waere genau der Fehler, den die Vorlage vermeiden soll — dann stuende
    # der Eintrag mitten im Text und der Abgleich faende ihn nie.
    kopf = kopf_lesen(text) if bereich in ("dossiers", "notizen") else {}

    # DIE VORLAGE ENTSCHEIDET DIE ART. Ein Kopf macht aus einer formlosen
    # Notiz ein Vorhaben — und die Datei zieht mit um, statt eine zweite
    # neben der alten anzulegen. Getrenntes Gedaechtnis unter demselben
    # Namen ist genau die stille Divergenz, gegen die das ganze
    # Kopf-im-Dossier-Modell gebaut ist.
    if kopf and bereich == "notizen":
        ziel = _pfad("dossiers", schluessel)
        if os.path.exists(pfad):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            os.rename(pfad, ziel)
        bereich, pfad = "dossiers", ziel

    war_da = os.path.exists(pfad)
    if kopf:
        _kopf_setzen(pfad, text)
        hinweis = katalog_abgleichen(schluessel)
        return (f"{'Kopf von' if war_da else 'Neu angelegt:'} "
                f"{bereich}/{schluessel}."
                + (f" {hinweis}." if hinweis else ""))

    # ── Ein Katalog hat eine FORM, und die wird verteidigt ────────────
    # Am 20.08.2026 hat sie zu einer Idee erst einen sauberen Eintrag
    # geschrieben und in der naechsten Runde einen Prosa-Absatz in DIESELBE
    # Katalogdatei. Danach war der Katalog halb Liste, halb Fliesstext —
    # und Sasha las zwei widerspruechliche "steht drin".
    #
    # Ein Katalog nimmt nur Eintraege. Prosa gehoert in eine Notiz oder ein
    # Dossier, und die Absage sagt genau das: eine Fehlermeldung, die den
    # richtigen Ort nennt, korrigiert an der Stelle, an der es passiert —
    # eine Prompt-Zeile wird uebergangen.
    if bereich == "kataloge" and not kopf_lesen(text):
        return ("[Das ist kein Katalog-Eintrag, sondern Prosa — ein Katalog "
                "nimmt nur Eintraege nach Schema (## Titel, darunter "
                "- thema:/- equipment:/- aufwand:/- status:). Lies "
                "read_note('vorlagen/katalog'). Fliesstext gehoert in eine "
                f"Notiz ('{schluessel}') oder ein Dossier.]")

    if bereich in ("notizen", "kataloge"):
        # Ohne Datums-Ueberschrift: eine Notiz ist eine Faktenliste, kein
        # Verlauf. "## 2026-08-18" ueber jeder einzelnen Zeile — zweimal
        # dasselbe Datum, wenn zwei Wegzeiten am selben Tag dazukommen —
        # ist Rauschen, das die Liste unlesbar macht. Wann etwas galt,
        # steht im Tagebuch; hier steht, WAS gilt.
        #
        # Fuer Kataloge gilt dasselbe aus einem zweiten Grund: dort stand
        # das Datum als "## 2026-08-20" DIREKT UEBER dem "## Titel" des
        # Eintrags — zwei Ueberschriften uebereinander, von denen die obere
        # nichts bedeutet.
        _anhaengen(pfad, f"{text}\n")
    else:
        _anhaengen(pfad, f"\n## {date.today().isoformat()}\n{text}\n")

    zu_lang = len(_lesen(pfad)) > MAX_DOSSIER
    return (f"{'Notiert in' if war_da else 'Neu angelegt:'} "
            f"{bereich}/{schluessel}."
            + (" ⚠ Das Dossier ist sehr lang geworden — räum es beim nächsten "
               "Mal auf (dossier_ersetzen)." if zu_lang else ""))


def dossier_ersetzen(name: str, inhalt: str) -> str:
    """Ein Dossier komplett neu schreiben. Die alte Fassung bleibt als .bak.

    Das ist der Aufräum-Weg: aus zwanzig angehängten Absätzen wird ein
    sauberer Stand. Destruktiv, deshalb gegatet — und selbst dann mit
    Sicherungskopie, denn Aufräumen ist genau die Tätigkeit, bei der man
    am ehesten versehentlich etwas verliert.
    """
    bereich, schluessel = _finden(name)
    if not schluessel:
        return "[Fehler: kein Name]"
    pfad = _pfad(bereich, schluessel)
    alt = _lesen(pfad)
    if alt:
        with open(pfad + ".bak", "w", encoding="utf-8") as f:
            f.write(alt)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write((inhalt or "").strip() + "\n")
    hinweis = katalog_abgleichen(schluessel) if bereich == "dossiers" else ""
    return (f"{bereich}/{schluessel} neu geschrieben"
            + (" (alte Fassung liegt als .bak daneben)" if alt else "")
            + (f". {hinweis}." if hinweis else "."))


# ── Vorlagen, Katalog-Kopf und Abgleich ───────────────────────────────
#
# Das Problem, das Sasha gemeldet hat: schreibt sie ein Dossier, taucht
# nicht verlaesslich ein Katalog-Eintrag dazu auf. Das war eine ANWEISUNG
# im Prompt, und Anweisungen werden uebergangen.
#
# Die Loesung ist, das zweite Artefakt abzuschaffen. Der KOPF DES DOSSIERS
# IST DER KATALOG-EINTRAG; der Code zieht ihn heraus und traegt ihn ein.
# Zwei Dinge synchron zu halten geht auf Dauer immer schief — eines kann
# nicht von sich selbst abweichen.
#
# Die KI fuellt dafuer nur eine Vorlage aus. Die Vorlagen sind gewoehnliche
# Dateien (`vorlagen/*.md`), damit Sasha sie aendern kann wie alles andere,
# und sie sind ueber read_note erreichbar — kein neues Werkzeug, kein
# zusaetzliches Schema im Prompt.

VORLAGEN = "vorlagen"

_VORLAGE_KATALOG = """# katalog

> Vorlage fuer einen Katalog-Eintrag. Kopieren, ausfuellen, mit write_note
> in den gewuenschten Katalog schreiben (z.B. name="kataloge/ideen").
> Fuer eine Sache, die du ernsthaft verfolgst, nimm stattdessen die
> Dossier-Vorlage — deren Kopf ist genau dieser Block.

## <Titel>
- katalog:   ideen
- thema:     <stichworte, kommagetrennt>
- equipment: <was es braucht, oder ->
- aufwand:   klein | mittel | gross
- status:    idee | priorisiert | queued | in_schedule | abgeschlossen | pausiert
"""

_VORLAGE_DOSSIER = """# dossier

> Vorlage fuer ein Dossier. Der KOPF ist zugleich der Katalog-Eintrag: der
> Code zieht ihn heraus, ergaenzt `dossier:` selbst und traegt ihn in den
> unter `katalog:` genannten Katalog ein. Du musst dich um die Verknuepfung
> nicht kuemmern — und sie kann nicht verlorengehen.
>
> Alles unter dem Kopf ist Prosa: schreib in Saetzen, nicht in Stichworten.

## <Titel>
- katalog:   ideen
- thema:     <stichworte, kommagetrennt>
- equipment: <was es braucht, oder ->
- aufwand:   klein | mittel | gross
- status:    priorisiert

## Ziel
<was am Ende dastehen soll>

## Stand
<wo es gerade steht, mit Datum>

## Naechster Schritt
<das eine, was als naechstes drankommt>

## Messreihe
<Name der Kurve, oder - wenn es nichts zu messen gibt>
"""

_VORLAGEN = {"katalog": _VORLAGE_KATALOG, "dossier": _VORLAGE_DOSSIER}

# Felder eines Katalog-Eintrags, in dieser Reihenfolge gerendert. `dossier`
# steht hinten, weil es der Code setzt und nicht der Mensch.
KATALOG_FELDER = ("katalog", "thema", "equipment", "aufwand", "status",
                  "dossier")

_KOPF_TITEL = re.compile(r"^##\s+(.+?)\s*$")
_KOPF_FELD = re.compile(r"^-\s*([a-zA-Zaeoeue]+)\s*:\s*(.*?)\s*$")


def vorlage(name: str) -> str:
    """Eine Vorlage lesen; legt sie beim ersten Zugriff an.

    Ausgeliefert wird sie aus dem Code, gespeichert wird sie als Datei —
    so hat ein frischer Rechner sofort eine, und Sasha kann sie trotzdem
    umschreiben, ohne dass ein Update sie ueberbuegelt.
    """
    schluessel = _slug(name)
    if schluessel not in _VORLAGEN:
        return f"[Keine Vorlage {name!r}. Es gibt: {', '.join(_VORLAGEN)}]"
    pfad = _pfad(VORLAGEN, schluessel)
    if not os.path.exists(pfad):
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(_VORLAGEN[schluessel])
    return _lesen(pfad).strip()


def kopf_lesen(text: str) -> dict:
    """Den fuehrenden Katalog-Block eines Dossiers parsen.

    Erwartet als erste inhaltliche Zeile `## Titel`, darunter
    `- feld: wert`-Zeilen. Kein Kopf -> leeres Dict, dann passiert nichts:
    ein Dossier ohne Kopf ist erlaubt, es taucht dann nur in keinem
    Katalog auf.
    """
    if not isinstance(text, str):
        return {}
    zeilen = [z for z in text.strip().splitlines()]
    # eine fuehrende "# name"-Zeile (Dateititel) ueberspringen
    while zeilen and (not zeilen[0].strip() or zeilen[0].startswith("# ")):
        zeilen.pop(0)
    if not zeilen:
        return {}
    titel = _KOPF_TITEL.match(zeilen[0])
    if not titel:
        return {}
    kopf = {"titel": titel.group(1)}
    for z in zeilen[1:]:
        if not z.strip():
            break
        feld = _KOPF_FELD.match(z)
        if not feld:
            break
        kopf[feld.group(1).lower()] = feld.group(2)
    return kopf if len(kopf) > 1 else {}


def _eintrag_rendern(kopf: dict) -> str:
    zeilen = [f"## {kopf.get('titel', '?')}"]
    breite = max(len(f) for f in KATALOG_FELDER) + 1
    for feld in KATALOG_FELDER:
        wert = (kopf.get(feld) or "").strip() or "-"
        zeilen.append(f"- {(feld + ':'):<{breite}} {wert}")
    return "\n".join(zeilen) + "\n"


def _upsert(katalogtext: str, titel: str, eintrag: str) -> str:
    """Einen `## Titel`-Abschnitt ersetzen oder anhaengen.

    Ersetzen statt anhaengen ist der Punkt: aendert sie im Dossier den
    Status, soll der Katalog nachziehen — nicht eine zweite Zeile daneben
    bekommen. Sonst haetten wir die Doppelpflege durch die Hintertuer.
    """
    zeilen = (katalogtext or "").splitlines()
    start = None
    for i, z in enumerate(zeilen):
        m = _KOPF_TITEL.match(z)
        if m and m.group(1).strip().casefold() == titel.strip().casefold():
            start = i
            break
    if start is None:
        rumpf = katalogtext.rstrip()
        return (rumpf + "\n\n" + eintrag) if rumpf else eintrag
    ende = len(zeilen)
    for j in range(start + 1, len(zeilen)):
        if _KOPF_TITEL.match(zeilen[j]):
            ende = j
            break
    neu = zeilen[:start] + eintrag.rstrip().splitlines() + [""] + zeilen[ende:]
    return "\n".join(neu).rstrip() + "\n"


def _kopf_setzen(pfad: str, neuer_kopf: str):
    """Den fuehrenden Katalog-Block einer Datei setzen, Prosa behalten.

    Schreibt sie den Kopf ein zweites Mal (etwa mit geaendertem Status),
    wird der alte ersetzt statt ein zweiter danebengelegt. Was darunter
    steht — Ziel, Stand, Tagesnotizen — bleibt unangetastet.
    """
    alt = _lesen(pfad)
    rest = ""
    if alt:
        zeilen = alt.splitlines()
        # ueber Dateititel und alten Kopf hinweg bis zur naechsten
        # Ueberschrift, die KEIN Feldblock ist
        i = 0
        while i < len(zeilen) and (not zeilen[i].strip()
                                   or zeilen[i].startswith("# ")):
            i += 1
        if i < len(zeilen) and _KOPF_TITEL.match(zeilen[i]):
            i += 1
            while i < len(zeilen) and (_KOPF_FELD.match(zeilen[i])
                                       or not zeilen[i].strip()):
                i += 1
        rest = "\n".join(zeilen[i:]).strip()
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(neuer_kopf.strip() + ("\n\n" + rest + "\n" if rest else "\n"))


def katalog_abgleichen(dossier_name: str) -> str:
    """Den Kopf eines Dossiers in seinen Katalog uebertragen.

    Wird vom Code gerufen, nicht vom Modell — genau deshalb kann die
    Verknuepfung nicht mehr vergessen werden. `dossier:` setzt ebenfalls
    der Code; was im Text stand, wird ueberschrieben.
    """
    schluessel = _slug(dossier_name)
    kopf = kopf_lesen(_lesen(_pfad("dossiers", schluessel)))
    if not kopf:
        return ""
    katalog = _slug(kopf.get("katalog") or "") or "ideen"
    kopf["katalog"] = katalog
    kopf["dossier"] = schluessel

    pfad = _pfad("kataloge", katalog)
    neu_angelegt = not os.path.exists(pfad)
    text = _lesen(pfad)
    if not text.strip():
        text = f"# {katalog}\n"
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(_upsert(text, kopf["titel"], _eintrag_rendern(kopf)))
    return (f"kataloge/{katalog} aktualisiert ({kopf['titel']})"
            + (" — Katalog neu angelegt" if neu_angelegt else ""))


def konsistenz() -> list:
    """Was auseinandergelaufen ist. Fuer Tests und auf Zuruf, nie im Prompt.

    Zwei Arten von Waisen: ein Katalog-Eintrag, dessen `dossier:` ins Leere
    zeigt (Dossier geloescht oder umbenannt), und ein Dossier ohne Kopf,
    das darum in keinem Katalog auftaucht.
    """
    aus = []
    verlinkt = set()
    for katalog in liste("kataloge"):
        text = _lesen(_pfad("kataloge", katalog))
        titel = None
        for z in text.splitlines():
            m = _KOPF_TITEL.match(z)
            if m:
                titel = m.group(1)
                continue
            feld = _KOPF_FELD.match(z)
            if feld and feld.group(1).lower() == "dossier":
                ziel = feld.group(2).strip()
                if ziel and ziel != "-":
                    verlinkt.add(ziel)
                    if not os.path.exists(_pfad("dossiers", ziel)):
                        aus.append(f"kataloge/{katalog}: {titel!r} zeigt auf "
                                   f"dossiers/{ziel}, das es nicht gibt")
    for dossier in liste("dossiers"):
        if dossier in verlinkt:
            continue
        if not kopf_lesen(_lesen(_pfad("dossiers", dossier))):
            aus.append(f"dossiers/{dossier}: kein Katalog-Kopf — taucht in "
                       f"keinem Katalog auf. Absicht (Uebersichts-Dossier "
                       f"ueber einen ganzen Bereich) oder vergessen?")
    return aus


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
    for bereich in ("tagebuch",) + BEREICHE:
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
        return (f"Nichts zu {begriff!r} gefunden (Tagebuch, Dossiers, "
            f"Kataloge und Quellen durchsucht).")
    return f"{len(treffer)} Treffer zu {begriff!r}:\n" + "\n".join(treffer)


# ── Dokumente holen und lesbar machen ─────────────────────────────────

# Binaeres, das nicht in Text umzuwandeln ist, landet hier — MIT einem
# Markdown-Vermerk daneben. Sashas Bedingung: es soll nichts rumfliegen.
# Deshalb gilt: jede geholte Sache hat GENAU EINEN Ort und IMMER einen
# lesbaren Eintrag in quellen/, auch wenn die Datei selbst binaer ist.
DATEIEN = "quellen/dateien"

_ENDUNGEN = {
    "application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg",
    "image/gif": "gif", "image/svg+xml": "svg", "application/zip": "zip",
    "text/csv": "csv", "application/json": "json",
}


def dokument_holen(url: str, name: str) -> str:
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
      * Text/HTML → Tags raus, Text nach quellen/<name>.md.
      * Binaeres  → Datei nach quellen/dateien/, PLUS ein Vermerk in
                quellen/<name>.md, was das ist und wo es herkommt.

    Der letzte Punkt ist die eigentliche Regel: es entsteht nie eine
    Datei ohne Eintrag. Sonst liegt in einem halben Jahr ein Ordner voller
    namenloser Downloads herum, und niemand weiss mehr, wozu.

    Unterschied zu `fetch_url`: das holt etwas, um es JETZT zu lesen, und
    vergisst es danach. Hier wird abgelegt, um es spaeter wiederzufinden.
    """
    import re as _re
    import html as _html
    import shutil
    import subprocess
    import tempfile
    import urllib.request

    schluessel = _slug(name)
    if not schluessel:
        return "[Fehler: kein Name fuer die Ablage]"

    quelle = (url or "").strip()
    aus_dem_netz = quelle.lower().startswith(("http://", "https://"))

    if aus_dem_netz:
        try:
            with urllib.request.urlopen(quelle, timeout=60) as antwort:
                daten = antwort.read(_MAX_DOKUMENT + 1)
                typ = (antwort.headers.get("Content-Type") or "").split(";")[0].strip()
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
        pfad = os.path.expanduser(quelle)
        if not os.path.isabs(pfad):
            for wurzel in context._WURZELN:
                if os.path.exists(os.path.join(wurzel, pfad)):
                    pfad = os.path.join(wurzel, pfad)
                    break
        pfad = os.path.abspath(pfad)
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

    kopf = (f"# {schluessel}\n\n> {'Geholt' if aus_dem_netz else 'Uebernommen'} "
            f"am {date.today().isoformat()} von {quelle}\n")

    # ── PDF ──────────────────────────────────────────────────────────
    if daten[:5] == b"%PDF-":
        if not shutil.which("pdftotext"):
            return "[pdftotext fehlt — ohne poppler-utils kein PDF]"
        with tempfile.TemporaryDirectory() as tmp:
            roh = os.path.join(tmp, "doc.pdf")
            with open(roh, "wb") as f:
                f.write(daten)
            try:
                fertig = subprocess.run(["pdftotext", "-layout", roh, "-"],
                                        capture_output=True, timeout=120)
                text = fertig.stdout.decode("utf-8", "replace").strip()
            except Exception as e:
                return f"[PDF-Umwandlung fehlgeschlagen: {e}]"
        if not text:
            return ("[Nichts Lesbares drin — vermutlich ein gescanntes PDF "
                    "ohne Textebene.]")
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
        ordner = os.path.join(_wurzel(), DATEIEN)
        os.makedirs(ordner, exist_ok=True)
        ziel = os.path.join(ordner, f"{schluessel}.{endung}")
        with open(ziel, "wb") as f:
            f.write(daten)
        text = (f"Binaerdatei, nicht als Text lesbar.\n\n"
                f"- Typ:   {typ or 'unbekannt'}\n"
                f"- Groesse: {len(daten) // 1024} KB\n"
                f"- Liegt:  `{DATEIEN}/{schluessel}.{endung}`\n")
        kopf += "> Die Datei selbst liegt daneben, hier steht nur der Vermerk.\n\n"
        with open(_pfad("quellen", schluessel), "w", encoding="utf-8") as f:
            f.write(kopf + text)
        return (f"Datei abgelegt als {DATEIEN}/{schluessel}.{endung}, "
                f"Vermerk in quellen/{schluessel}.")

    if len(text) > _MAX_DOKUMENT_TEXT:
        text = text[:_MAX_DOKUMENT_TEXT] + "\n\n…[hier abgeschnitten]"
    with open(_pfad("quellen", schluessel), "w", encoding="utf-8") as f:
        f.write(kopf + text)
    return (f"quellen/{schluessel} abgelegt ({len(text)} Zeichen). "
            f"Such gezielt mit search_memory darin, statt es am Stueck zu "
            f"lesen — und kipp es nie ganz in eine Antwort.")


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
    r = hausregeln()
    if r:
        teile.append("## Hausregeln\n"
                     "Das hat Sasha dir ausdrücklich gesagt. Im Zweifel geht "
                     "es jeder allgemeinen Anweisung vor.\n" + _ohne_titel(r))
    s, z = steckbrief(), ziele()
    if s:
        teile.append("## Über Sasha\n" + _ohne_titel(s))
    if z:
        teile.append("## Seine Ziele\n" + _ohne_titel(z))

    zeilen = []
    for bereich in BEREICHE:
        namen = liste(bereich)
        if namen:
            zeilen.append(f"- **{bereich}/** — {', '.join(namen)}")
    if zeilen:
        teile.append(
            "## Was im Gedächtnis liegt\n" + "\n".join(zeilen) + "\n\n"
            "Das sind TITEL, keine Inhalte. Geht es um eines davon, lies es "
            "mit read_note (\"umzug\" oder \"kataloge/ideen\") — rate nicht aus "
            "dem Titel. Was du Neues erfährst, hältst du mit write_note fest.\n"
            "- **notizen/** sind formlos: einzelne Fakten, kurze Listen, "
            "alles, was kein Vorhaben ist (Wegzeiten, Gewohnheiten, "
            "Vorlieben). Ein Name, den es noch nicht gibt, landet hier — "
            "das ist der richtige Ort für „merk dir das\", und du brauchst "
            "dafür keine Vorlage.\n"
            "- **dossiers/** sind Prosa über eine Sache, die er ernsthaft "
            "verfolgt. Dort stehen auch die Messreihen, die dazugehören. "
            "Ein Dossier entsteht, indem du die Vorlage ausfüllst — schreibst "
            "du einen Katalog-Kopf in eine bestehende Notiz, wird sie zum "
            "Dossier befördert und zieht mit um.\n"
            "- **kataloge/** sind viele kurze Einträge nach gleichem Schema: "
            "`thema`, `equipment`, `aufwand`, `status`, `dossier`. Status ist "
            f"eines von: {', '.join(STATUS)}. Über die `thema`-Stichworte "
            "findest du, was zusammengehört — eine Idee passt zu einem Modul "
            "oder zu etwas, das ihn heute interessiert hat.\n"
            "- **quellen/** sind abgelegte Dokumente, meist lang. Such darin "
            "gezielt mit search_memory, statt sie ganz zu lesen.\n"
            "- **vorlagen/** sind Muster zum Ausfüllen. Bevor du ein Dossier "
            "oder einen Katalog-Eintrag anlegst, lies die passende: "
            "read_note(\"vorlagen/dossier\") bzw. \"vorlagen/katalog\". Ein "
            "Dossier BEGINNT mit dem Katalog-Kopf — den Eintrag im Katalog "
            "erzeugt der Code daraus von selbst, samt Verknüpfung.")
    if not teile:
        return ""
    return "\n\n".join(teile)
