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

BEREICHE = ("dossiers", "kataloge", "quellen")

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
    allen Bereichen gesucht; existiert nichts, landet Neues in `dossiers`
    (die Prosa-Ablage ist der ungefaehrliche Default — ein versehentlich
    dort gelandeter Eintrag stoert niemanden, ein versehentlich in einem
    Katalog gelandeter Absatz zerschiesst dessen Form).
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
    return "dossiers", schluessel


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
    war_da = os.path.exists(pfad)
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
    return (f"{bereich}/{schluessel} neu geschrieben"
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
    if not (url or "").lower().startswith(("http://", "https://")):
        return "[Fehler: nur http(s)-Adressen]"

    try:
        with urllib.request.urlopen(url, timeout=60) as antwort:
            daten = antwort.read(_MAX_DOKUMENT + 1)
            typ = (antwort.headers.get("Content-Type") or "").split(";")[0].strip()
    except Exception as e:
        return f"[Download fehlgeschlagen: {e}]"
    if len(daten) > _MAX_DOKUMENT:
        return f"[Groesser als {_MAX_DOKUMENT // 1_000_000} MB — abgebrochen.]"

    kopf = (f"# {schluessel}\n\n> Geholt am {date.today().isoformat()} "
            f"von {url}\n")

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
            "- **dossiers/** sind Prosa über eine Sache, die er ernsthaft "
            "verfolgt. Dort stehen auch die Messreihen, die dazugehören.\n"
            "- **kataloge/** sind viele kurze Einträge nach gleichem Schema: "
            "`thema`, `equipment`, `aufwand`, `status`, `dossier`. Status ist "
            f"eines von: {', '.join(STATUS)}. Über die `thema`-Stichworte "
            "findest du, was zusammengehört — eine Idee passt zu einem Modul "
            "oder zu etwas, das ihn heute interessiert hat.\n"
            "- **quellen/** sind abgelegte Dokumente, meist lang. Such darin "
            "gezielt mit search_memory, statt sie ganz zu lesen.")
    if not teile:
        return ""
    return "\n\n".join(teile)
