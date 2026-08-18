"""
Das Datei-Gedächtnis, das den Konzept-Graphen ablöst.

Der Graph hat nicht an der Extraktion gescheitert, sondern am fehlenden
Schema: der Extraktor erfand pro Turn, welcher Typ und welches Verb
passt. Ergebnis nach Wochen Betrieb — 42 von 104 Kanten waren
`erwähnt-am` (Buchhaltung darüber, WANN geredet wurde), und unter den
Fakten stand `Sasha wohnt-in Universität des Saarlandes`.

Hier wird geprüft, dass der Ersatz die vier Eigenschaften hat, an denen
der Graph gescheitert ist:

  1. Er verliert nichts (anhängen, nie überschreiben).
  2. Er ist billig (Titel im Prompt, Inhalte auf Abruf, byte-stabil also
     cachebar).
  3. Er behält die Sprache (Sashas Sätze, nicht Tripel).
  4. Das Rohmaterial läuft weiter, auch ohne Extraktion.
"""
from datetime import date

import pytest

import ai
import consolidation
import gedaechtnis


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))


# ── Nichts geht verloren ──────────────────────────────────────────────

def test_notieren_haengt_an_statt_zu_ersetzen():
    """Eine KI, die eine Datei neu schreibt, löscht still alles, was sie
    beim Schreiben nicht im Kopf hatte."""
    gedaechtnis.dossier_notieren("Umzug", "Küche: Regale hängen.")
    gedaechtnis.dossier_notieren("Umzug", "Bad: nichts passiert.")
    inhalt = gedaechtnis.dossier_lesen("umzug")
    assert "Regale hängen" in inhalt
    assert "Bad: nichts passiert" in inhalt


def test_ersetzen_legt_eine_sicherung_an():
    """Aufräumen ist die Tätigkeit, bei der man am ehesten etwas verliert."""
    gedaechtnis.dossier_notieren("Umzug", "alter Stand")
    gedaechtnis.dossier_ersetzen("Umzug", "neuer, sauberer Stand")
    assert gedaechtnis.dossier_lesen("umzug") == "neuer, sauberer Stand"
    with open(gedaechtnis._pfad("dossiers", "umzug") + ".bak",
              encoding="utf-8") as f:
        assert "alter Stand" in f.read()


def test_dossier_name_kann_nicht_ausbrechen():
    """Ein Modell, das `../../data/ai_config` als Dossier-Titel schickt,
    darf damit nicht in fremde Dateien schreiben."""
    assert gedaechtnis._slug("../../data/ai_config") == "data-ai-config"
    assert "/" not in gedaechtnis._slug("a/b/c")
    assert gedaechtnis._slug("...") == ""


def test_zu_langer_eintrag_wird_gekappt():
    gedaechtnis.dossier_notieren("Umzug", "x" * (gedaechtnis.MAX_NOTIZ + 500))
    assert "…[gekürzt]" in gedaechtnis.dossier_lesen("umzug")


# ── Die Sprache bleibt ────────────────────────────────────────────────

def test_tagebuch_behaelt_den_wortlaut():
    """`Sasha zustand Fieber` ist das, was von "ich lag drei Tage flach
    und hab die Vorlesung verpasst" übrig blieb. Genau das nicht mehr."""
    satz = "ich lag drei Tage flach und hab die Vorlesung verpasst"
    gedaechtnis.tagebuch_notieren(satz)
    assert satz in gedaechtnis.tagebuch_lesen()


def test_tagebuch_traegt_die_uhrzeit():
    gedaechtnis.tagebuch_notieren("aufgewacht")
    zeile = [z for z in gedaechtnis.tagebuch_lesen().splitlines()
             if "aufgewacht" in z][0]
    assert zeile.startswith("- ") and ":" in zeile[:8]


def test_suche_findet_ueber_tagebuch_und_dossiers():
    gedaechtnis.tagebuch_notieren("Spanien war anstrengend aber schön")
    gedaechtnis.dossier_notieren("Umzug", "Spanien-Kisten stehen noch rum")
    treffer = gedaechtnis.suchen("Spanien")
    assert "tagebuch" in treffer
    assert "dossiers/umzug" in treffer


def test_suche_sagt_ehrlich_wenn_nichts_da_ist():
    """"Nichts gefunden" und "weiß ich nicht" müssen unterscheidbar sein."""
    assert "Nichts zu" in gedaechtnis.suchen("Einhorn")


# ── Billig: Titel in den Prompt, Inhalte auf Abruf ────────────────────

def test_kopf_block_nennt_titel_aber_keine_inhalte():
    """Alle Dossiers in den Prompt zu kippen wäre exakt der Fehler des
    Graph-Blocks: viel Kontext, wenig Bezug, bei jedem Turn bezahlt."""
    gedaechtnis.dossier_notieren("Umzug", "geheimer inhalt des dossiers")
    block = gedaechtnis.kopf_block()
    assert "umzug" in block
    assert "geheimer inhalt" not in block
    assert "read_note" in block          # und wie sie drankommt


def test_kopf_block_ist_byte_stabil():
    """Er sitzt im gecachten Teil. Änderte er sich pro Turn, wäre der
    Cache eine reine Kostensteigerung."""
    gedaechtnis.dossier_notieren("Umzug", "irgendwas")
    assert gedaechtnis.kopf_block() == gedaechtnis.kopf_block()


def test_leeres_gedaechtnis_erzeugt_keinen_block():
    """Kein Platzhalter-Gerüst im Prompt, solange nichts drinsteht."""
    assert gedaechtnis.kopf_block() == ""


def test_steckbrief_und_ziele_stehen_im_kopf():
    with open(gedaechtnis._pfad("", gedaechtnis.STECKBRIEF), "w",
              encoding="utf-8") as f:
        f.write("Fokus und Fertigstellen hat Vorrang.")
    with open(gedaechtnis._pfad("", gedaechtnis.ZIELE), "w",
              encoding="utf-8") as f:
        f.write("Spagat, L-Sit, Zugspitze.")
    block = gedaechtnis.kopf_block()
    assert "Fokus und Fertigstellen" in block
    assert "Zugspitze" in block


# ── Der Graph ist aus, das Rohmaterial läuft weiter ───────────────────

def test_graph_kontext_ist_aus():
    """Er ging bei JEDEM Turn ungecacht raus und lieferte Rauschen."""
    assert ai.GRAPH_KONTEXT is False


def test_tripel_extraktion_ist_aus():
    """Sie kostete einen eigenen LLM-Call pro Turn — rund 2,70 € im Monat
    dafür, das Gedächtnis schlechter zu machen."""
    assert consolidation.GRAPH_EXTRAKTION is False


def test_rohmaterial_wird_trotzdem_geschrieben(monkeypatch, tmp_path):
    """Die wichtigste Garantie des Umbaus: die Gespräche laufen weiter in
    das Transkript. Verloren geht nichts, es wird nur nicht mehr jeder
    Satz in Tripel zerhackt."""
    geschrieben = []
    monkeypatch.setattr(consolidation.transkript, "schreiben",
                        lambda turns, store=None: geschrieben.append(turns) or [])
    gerufen = []
    monkeypatch.setattr(consolidation, "_call_graph_extractor",
                        lambda *a: gerufen.append(1) or ([], []))
    consolidation.extract_turn_into_graph(
        "ich hatte gestern einen breakdown", "klingt hart", store=None)
    assert geschrieben, "das Rohmaterial fehlt"
    assert not gerufen, "der Extraktor lief trotzdem"


# ── Wer fragen muss und wer nicht ─────────────────────────────────────

def test_notieren_fragt_nicht_um_erlaubnis():
    """Eine KI, die vor jeder Notiz fragt, ist kein Sekretär, sondern eine
    Zumutung — sie soll mitschreiben wie jemand, der danebensitzt."""
    assert not ai.braucht_erlaubnis("write_note")
    assert not ai.braucht_erlaubnis("read_note")
    assert not ai.braucht_erlaubnis("search_memory")


def test_umschreiben_fragt_schon():
    """Das ist der destruktive Weg."""
    assert ai.braucht_erlaubnis("rewrite_note")
    frage = ai._permission_question("rewrite_note", {"name": "umzug"})
    assert "umzug" in frage and "neu schreiben" in frage


# ── Kein Dienstbotentum ───────────────────────────────────────────────

def test_beide_schienen_bieten_sich_nicht_an():
    """Sagt Sasha "ich muss noch so viele Mails schreiben", ist die
    richtige Antwort ein Kommentar — nicht "soll ich das übernehmen?".
    Das Anbieten macht aus einem Gegenüber ein Callcenter."""
    from profil import klein, gross
    for text in (klein.SYSTEM, gross.system()):
        assert "## Kein Dienstbotentum" in text
        assert "Du bietest dich nicht an" in text
