"""
Die zwei Schienen: welcher Prompt und welches Tool-Set gehen an welches Modell.

Ein 9B-Modell und ein Frontier-Modell teilten sich bis hierher EINEN Prompt.
Jede Anpassung für das eine war Ballast oder Gift für das andere. Jetzt hat
jedes seine eigene Schiene — und diese Tests halten drei Dinge fest:

  1. Der Umzug nach profil/klein.py war WÖRTLICH. Der lokale Pfad ist gerade
     nicht live testbar (unterwegs läuft kein Ollama); ein stiller Zeichen-
     verlust dort fiele erst daheim auf, Wochen später.
  2. Beide Schienen bieten dasselbe an, damit der Kern nicht wissen muss, auf
     welcher er fährt.
  3. Ein umbenanntes Tool rutscht nicht am Erlaubnis-Gate vorbei. Das wäre der
     stillste denkbare Fehler: die KI schreibt in den Kalender, ohne zu fragen.
"""
import re

import pytest

import ai
import profil
from profil import gross, klein


# ── Die Schnittstelle ──────────────────────────────────────────────────

@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_jede_schiene_bietet_dasselbe_an(p):
    """Sonst müsste der Kern für jede Schiene einen Sonderfall kennen — und
    genau das soll die Aufteilung ja verhindern."""
    assert isinstance(p.NAME, str) and p.NAME
    assert isinstance(p.SYSTEM, str) and p.SYSTEM
    assert isinstance(p.TOOLS, list) and p.TOOLS
    assert isinstance(p.TERMINAL, set)
    assert isinstance(p.MERKMALE, dict)
    kopf = p.system()
    assert isinstance(kopf, str) and p.SYSTEM in kopf


@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_system_nimmt_eine_fremde_persona_an(p):
    """Der Tutor bringt seinen eigenen Prompt mit."""
    kopf = p.system("ICH BIN WER ANDERS")
    assert "ICH BIN WER ANDERS" in kopf
    assert p.SYSTEM not in kopf


def test_dashview_laesst_sich_abschalten():
    """ZENTRALE_DASHVIEW=0 ist der A/B-Vergleich für das Dashboard-Sicht-
    Experiment — der muss weiter gehen."""
    assert klein._DASHBOARD_VIEW in klein.system(dashview=True)
    assert klein._DASHBOARD_VIEW not in klein.system(dashview=False)


# ── Der Umzug war wörtlich ─────────────────────────────────────────────

def test_ai_zeigt_auf_die_kleine_schiene():
    """Der lokale Pfad, die vier scripts/bench_*.py und die bestehenden Tests
    greifen weiter über ai.* zu. Die Namen dürfen nicht ins Leere zeigen."""
    assert ai._SYSTEM_PROMPT is klein._SYSTEM_PROMPT
    assert ai._CAPABILITIES_PROMPT is klein._CAPABILITIES_PROMPT
    assert ai.ANTWORT_SUFFIX is klein.ANTWORT_SUFFIX
    assert ai._ASCII_MARKER_PROMPT is klein._ASCII_MARKER_PROMPT
    assert ai._DASHBOARD_VIEW is klein._DASHBOARD_VIEW
    assert ai._MIC_INPUT_HINT is klein._MIC_INPUT_HINT
    assert ai.TOOLS is klein.TOOLS


def test_der_kopf_hat_alle_teile_in_der_alten_reihenfolge():
    """Die Reihenfolge ist nicht Geschmack: der statische Kopf muss über alle
    Turns byte-identisch sein, und was das Modell zuletzt liest, wiegt am
    schwersten."""
    kopf = klein.system(dashview=True)
    stellen = [kopf.index(t) for t in (
        klein._SYSTEM_PROMPT,
        klein._CAPABILITIES_PROMPT,
        klein.ANTWORT_SUFFIX,
        klein._ASCII_MARKER_PROMPT,
        klein._DASHBOARD_VIEW,
    )]
    assert stellen == sorted(stellen)


def test_klein_behaelt_seine_kruecken():
    """Sie sind der Grund, warum es zwei Schienen gibt. Verschwinden sie hier
    aus Versehen mit, war die ganze Trennung umsonst."""
    namen = {t["function"]["name"] for t in klein.TOOLS}
    assert "antwort" in namen
    assert klein.MERKMALE["antwort_tool"] is True
    assert klein.ANTWORT_SUFFIX in klein.system()
    assert klein._ASCII_MARKER_PROMPT in klein.system()


# ── Was gross NICHT mehr mitschleppt ───────────────────────────────────

def test_gross_hat_die_kruecken_abgeworfen():
    namen = {t["function"]["name"] for t in gross.TOOLS}
    assert "antwort" not in namen
    assert klein.ANTWORT_SUFFIX not in gross.system()
    assert klein._ASCII_MARKER_PROMPT not in gross.system()
    assert klein._DASHBOARD_VIEW not in gross.system()
    # Dashboard-Markup, das die TUI gar nicht rendert — das Modell wuerde
    # Marker tippen, die als roher Text erscheinen.
    assert "## Text-Effekte" not in gross.system()
    # Few-Shot: eine Technik fuer kleine Modelle.
    assert "## So endet ein Turn" not in gross.system()


def test_kein_wort_ueber_den_graphen_im_prompt():
    """Hier stand frueher `test_gross_behaelt_die_subjekt_grenze`.

    Die Subjekt-Grenze ("Sashas Gefuehle sind nicht deine") war noetig,
    solange das Gedaechtnis aus Tripeln bestand: aus `Sasha zustand einsam`
    konnte ein Modell "ich bin einsam seit dem 19. Mai" machen. In Prosa
    steht "Sasha war im August krank" — da ist nichts zu verwechseln.

    Was jetzt bewacht wird, ist das eigentliche Risiko: Anweisungen, die
    auf eine Welt zeigen, die es nicht mehr gibt. Vier der sechs
    Meta-Regeln beschrieben den Konzept-Graphen und seinen Extraktor.
    Falsche Anweisungen sind schlimmer als gar keine — das Modell versucht,
    sie zu befolgen.
    """
    text = gross.system() + " ".join(
        t["function"]["description"] for t in gross.TOOLS)
    for wort in ("Aktiviertes Wissen", "Wissens-Block", "Konzept-Graph",
                 "Extraktor", "Das kannst DU"):
        assert wort not in text, wort

def test_der_schnitt_haelt():
    """Die Zahl, um die es geht. Faellt sie zurueck, hat jemand wieder etwas
    in den Praefix gelegt, das jeden Turn mitbezahlt wird."""
    # Frueher: "gross < klein/2". Das passte, solange gross nur "klein minus
    # Kruecken" war. Seit dem 18.08.2026 hat es EIGENE Inhalte, die klein
    # nicht hat (Antwortverhalten aus Anthropics Prompt, die Hausregel-
    # Mechanik) — ein Verhaeltnis misst dann das Falsche. Was zaehlt, ist
    # die absolute Groesse: der Kopf geht bei jedem Cache-Write mit raus.
    assert len(gross.system()) < 5000, "der gecachte Kopf laeuft voll"
    # Beschreibungen der GEERBTEN Werkzeuge — das war der Schnitt von
    # damals (6.342 → ~2.200). Die eigenen Gedaechtnis-Werkzeuge kamen
    # spaeter dazu und werden getrennt gedeckelt: sie sind kein Ballast,
    # den jemand vergessen hat, sondern der Ersatz fuer den Graph-Block,
    # der frueher UNGECACHT bei jedem Turn mitreiste. Ein Schema im
    # gecachten Praefix kostet ein Zehntel davon.
    eigen = {t["function"]["name"] for t in gross._GEDAECHTNIS}
    besch = sum(len(t["function"]["description"]) for t in gross.TOOLS
                if t["function"]["name"] not in eigen)
    assert besch < 3000
    besch_eigen = sum(len(t["function"]["description"]) for t in gross.TOOLS
                      if t["function"]["name"] in eigen)
    # 18.08.2026 von 2.500 auf 2.800: write_note verweist jetzt auf die
    # Vorlagen. Das sind ~110 Zeichen im gecachten Praefix und der Grund,
    # warum Dossier und Katalog-Eintrag zusammen entstehen — die Kopplung
    # war vorher eine Bitte, die uebergangen wurde. Die Grenze soll Wildwuchs
    # BEWUSST machen, nicht verbieten; wer sie anhebt, schreibt dazu warum.
    assert besch_eigen < 2800


def test_praefix_bleibt_ueber_der_cache_mindestgroesse():
    """Anthropic cacht erst ab 1.024 Token (Sonnet 5) bzw. 512 (Opus 5). Wer
    weiter eindampft, spart Zeichen und verliert dafuer den Cache — das waere
    unterm Strich TEURER. Grobe Schaetzung: 4 Zeichen je Token.

    Gemessen wird der GESAMTE gecachte Praefix, nicht der Text der Schiene:
    Anthropic rendert tools → system → messages und cacht alles davor. Der
    Schienentext allein ist seit dem Entruempeln (18.08.2026) unter 512
    Token — zusammen mit dem Tool-Schema liegt der Praefix aber weit
    darueber, und nur das entscheidet, ob der Cache greift."""
    import json
    praefix = len(json.dumps(gross.TOOLS, ensure_ascii=False)) + len(gross.system())
    assert praefix // 4 > 1024


def test_parameter_schemata_laufen_nicht_auseinander():
    """Die Parameter sind der Vertrag mit Python (kalender.RANGE_BUCKETS & Co).
    Beschreibungen darf jede Schiene selbst formulieren — Parameter nicht.
    Zwei Schienen mit verschiedenen Parametern waeren ein Bug, kein Feintuning."""
    aus_klein = {t["function"]["name"]: t["function"]["parameters"]
                 for t in klein.TOOLS}
    # Werkzeuge, die NUR diese Schiene hat, koennen naturgemaess nicht mit
    # klein abgeglichen werden — sie haben dort kein Gegenstueck. Der
    # Vertrag gilt fuer das GETEILTE Set.
    eigen = {t["function"]["name"] for t in gross._GEDAECHTNIS}
    for t in gross.TOOLS:
        fn = t["function"]
        if fn["name"] in eigen:
            continue
        # gross benennt um; ueber den kanonischen Namen wieder zusammenfuehren.
        passend = [k for k, v in aus_klein.items()
                   if profil.kanonisch(k) == profil.kanonisch(fn["name"])]
        assert len(passend) == 1, fn["name"]
        assert fn["parameters"] == aus_klein[passend[0]], fn["name"]


def test_gross_teilt_die_persona_mit_klein():
    """Zwei Kopien waeren zwei Persoenlichkeiten, je nachdem welches Backend
    laeuft — und sie wuerden auseinanderlaufen, ohne dass es jemand merkt.

    Geteilt wird, was eine WAHL ist: der Grundton, die Haltung, die Absage
    ans Dienstbotentum. Ein unangewiesenes Modell ist nicht trocken und
    bietet sehr wohl seine Hilfe an."""
    for teil in ("## Stimme", "## Substanz statt Pflichtprogramm",
                 "## Kein Dienstbotentum"):
        assert teil in klein.SYSTEM
        assert teil in gross.SYSTEM


def test_gross_schneidet_die_kalibrierung_weg():
    """Laenge und Floskel-Stopliste bringt ein Frontier-Modell mit.

    Sasha im Anthropic-Chat: "ich sprech claude einfach direkt an, keine
    regeln". Fuer das 9B bleiben sie noetig — genau dafuer gibt es zwei
    Schienen."""
    for teil in ("## Länge", "## Floskel-Stopliste", "## Text-Effekte",
                 "## So endet ein Turn"):
        assert teil in klein.SYSTEM, teil
        assert teil not in gross.SYSTEM, teil


def test_jede_beschreibung_ist_gesetzt():
    """Ein Tool ohne Beschreibung faellt beim Bauen auf, nicht erst, wenn das
    Modell raet, wofuer es gut ist."""
    for t in gross.TOOLS:
        assert t["function"]["description"].strip()


# ── Kanonische Namen ───────────────────────────────────────────────────

def test_deutsche_namen_werden_uebersetzt():
    assert profil.kanonisch("lies_news") == "read_news"
    assert profil.kanonisch("web_suche") == "web_search"
    assert profil.kanonisch("frage_knopf") == "ask_choice"


def test_kanonisch_ist_idempotent_und_tolerant():
    """Zweimal übersetzen darf nichts kaputtmachen, und ein unbekannter Name
    muss durchrutschen — der fällt weiter unten als 'unbekanntes Tool' auf,
    nicht hier als KeyError mitten im Gespräch."""
    for name in ("read_news", "read_calendar", "voellig_ausgedacht"):
        assert profil.kanonisch(name) == name
    assert profil.kanonisch(profil.kanonisch("hole_url")) == "fetch_url"


# ── Auswahl ────────────────────────────────────────────────────────────

def test_cloud_faehrt_gross_lokal_faehrt_klein(monkeypatch):
    monkeypatch.delenv("ZENTRALE_PROMPT_PROFIL", raising=False)
    monkeypatch.setattr(profil, "_aus_config", lambda: None)
    assert profil.fuer_backend("cloud") is gross
    assert profil.fuer_backend("local") is klein


def test_env_taucht_die_schiene_zurueck(monkeypatch):
    """»Die andere kann man schnell wieder reintauschen« — eine Zeile."""
    monkeypatch.setenv("ZENTRALE_PROMPT_PROFIL", "klein")
    assert profil.fuer_backend("cloud") is klein


def test_unbekannte_schiene_faellt_auf_klein_zurueck(monkeypatch):
    """Klein ist die vorsichtigere: sie hat die Krücken drin. Ein Tippfehler
    in der Config macht die KI dann höchstens geschwätzig, nicht kaputt."""
    monkeypatch.setenv("ZENTRALE_PROMPT_PROFIL", "kruemelmonster")
    assert profil.fuer_backend("cloud") is klein


# ── Kein Tool rutscht am Kern (oder am Gate) vorbei ────────────────────

def _dispatchbare_namen() -> set:
    """Die Namen, die _dispatch_tool tatsächlich kennt — aus dem Quelltext
    gelesen, damit der Test nicht die Tools ausführt."""
    import inspect
    quelle = inspect.getsource(ai._dispatch_tool)
    return set(re.findall(r'name == "([a-z_]+)"', quelle))


@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_jedes_angebotene_tool_kann_der_kern_auch_ausfuehren(p):
    """Der teuerste Fehler beim Umbenennen: das Modell ruft ein Tool, das es
    im Schema sieht, und der Kern antwortet '[Unbekanntes Tool]'. Kostet eine
    volle Runde und macht die KI vor Sasha zum Lügner."""
    kennt = _dispatchbare_namen()
    # Terminale Tools laufen nicht über _dispatch_tool, sondern werden im Loop
    # abgefangen (siehe cloud.run_tool).
    terminal = {profil.kanonisch(t) for t in p.TERMINAL}
    for t in p.TOOLS:
        name = profil.kanonisch(t["function"]["name"])
        if name in terminal or name == "ask_choice":
            continue
        assert name in kennt, f"{p.NAME}: {name} wird angeboten, aber nicht ausgeführt"


@pytest.mark.parametrize("alias,kanon", sorted(profil.ALIASE.items()))
def test_das_gate_kennt_beide_schreibweisen(alias, kanon):
    """Ein Schreib-Tool, das unter seinem Alias am Gate vorbeikommt, würde
    ungefragt in Sashas Kalender schreiben. Der Fehler wäre völlig lautlos."""
    assert ai.braucht_erlaubnis(alias) == ai.braucht_erlaubnis(kanon)


def test_gate_greift_bei_den_schreibenden_tools():
    for name in ("add_calendar_entry", "delete_calendar_entry",
                 "web_suche", "web_search", "hole_url", "fetch_url"):
        assert ai.braucht_erlaubnis(name), name
    for name in ("read_calendar", "read_file", "list_files", "lies_news"):
        assert not ai.braucht_erlaubnis(name), name


# ── Was von Anthropics eigenem Prompt uebernommen wurde ───────────────

def test_uebernommene_kalibrierung_ist_da():
    """Aus dem veroeffentlichten claude.ai-Prompt uebernommen, weil es
    Verhalten kalibriert statt ein Produkt zu konfigurieren.

    Zwei davon loesen gemessene Probleme: die Ein-Frage-Regel ist die
    Antwort auf "wann ist wieder Zeit fuers Training?" -> "sag mir den
    Begriff, dann such ich gezielter", und die Floskel-Regel kommt MIT
    Begruendung, was bei Modellen zuverlaessiger sitzt als ein Verbot.
    """
    t = gross.system()
    assert "## Antwortverhalten" in t
    assert "höchstens EINE Frage" in t
    assert "unaufrichtig" in t
    assert "mündiger Erwachsener" in t
    assert "ohne Selbstgeißelung" in t
    assert "sieh selbst nach" in t


def test_anthropics_ton_wurde_nicht_uebernommen():
    """Der Ton-Absatz ("warm tone, kindness") zieht gegen Sashas
    gewaehlten Grundton. Sasha, 18.08.2026: "der sarkasmus stachel
    bleibt." Stuenden beide da, gewaenne der ausfuehrlichere."""
    t = gross.system()
    assert "Sarkasmus" in t
    assert "warm tone" not in t
    assert "ohne negative Annahmen" not in t


def test_kein_chat_app_ballast():
    """Neun Zehntel des veroeffentlichten Prompts konfigurieren eine
    Chat-App. Nichts davon darf hier hereinrutschen — das waere genau der
    Fehler, den wir am selben Tag ausgeraeumt haben."""
    t = gross.system().lower()
    for wort in ("daumen", "thumbs", "artifact", "minderjährig",
                 "evenhandedness", "safeguard"):
        assert wort not in t, wort
