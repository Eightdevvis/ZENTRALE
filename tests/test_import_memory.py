"""Skill import-memory (2026-10-08): Erinnerungen aus einer anderen KI holen.

Geprüft wird die WERKZEUG-Seite — was der Code garantiert, egal wie gut das
Modell den Skill befolgt: write_note mit `herkunft` ergänzt nur (zeilenweise,
ohne Doppeltes, ohne Links, nie in Kataloge/Tagebuch, alles oder nichts),
die Kernakten bleiben hinter dem Ja/Nein-Knopf, und der Skill wird als
Vorlage ausgeliefert. Der Probelauf nutzt einen ERFUNDENEN Export
(tests/fixtures/import_memory_beispiel.txt) und ein gefälschtes Modell.
Wie gut die SKILL.md das Modell führt, prüft kein Test — das steht im
Bericht des Bau-Agenten (claude_web_plan.md §7).
"""
import json
import os
import re
from datetime import date

import pytest

import erlaubnis
import gedaechtnis
import ki_antwort
import ki_werkzeuge
import skill_format
import skills
import state
import werkzeug_schleife
from werkzeug_schleife import Runde

HEUTE = date.today().isoformat()
VERMERK = f"[import claude {HEUTE}"
HIER = os.path.dirname(os.path.abspath(__file__))
BEISPIEL = os.path.join(HIER, "fixtures", "import_memory_beispiel.txt")


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


def _datei(rel):
    with open(os.path.join(gedaechtnis._DIR, rel + ".md"), encoding="utf-8") as f:
        return f.read()


def _schreiben(rel, text):
    pfad = os.path.join(gedaechtnis._DIR, rel + ".md")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)


def _import(name, text, herkunft="claude"):
    return ki_werkzeuge.ausfuehren("write_note",
                                   {"name": name, "text": text, "herkunft": herkunft})


# ── Nur ergänzen ──────────────────────────────────────────────────────

def test_neue_notiz_bekommt_zeilen_mit_herkunftsvermerk():
    aus = _import("vorlieben", "Mag schwarzen Tee.\n- Hört Techno beim Löten.")
    text = _datei("notizen/vorlieben")
    assert text.startswith("# vorlieben\n\n")
    assert f"- Mag schwarzen Tee.  {VERMERK}]" in text
    assert f"- Hört Techno beim Löten.  {VERMERK}]" in text
    assert "Neu angelegt: notizen/vorlieben: 2 Zeile(n)" in aus


def test_vorhandenes_bleibt_wort_fuer_wort_und_steht_vorne():
    alt = "# vorlieben\n\nMag schwarzen Tee ohne Zucker.\nSchläft schlecht bei Vollmond.\n"
    _schreiben("notizen/vorlieben", alt)
    _import("vorlieben", "Hört Techno beim Löten.")
    assert _datei("notizen/vorlieben").startswith(alt)


def test_doppeltes_wird_uebersprungen_auch_in_anderer_schreibweise():
    _schreiben("notizen/vorlieben", "# vorlieben\n\nMag schwarzen Tee ohne Zucker.\n")
    aus = _import("vorlieben", "[2026-03-15] - mag schwarzen Tee ohne Zucker\n"
                               "Hört Techno.\n- hört techno.")
    text = _datei("notizen/vorlieben")
    assert text.count("Tee") == 1 and text.lower().count("techno") == 1
    assert aus.count("steht schon da") == 2


def test_zweiter_gleicher_import_schreibt_nichts():
    _import("vorlieben", "Mag Tee.\nHört Techno.")
    vorher = _datei("notizen/vorlieben")
    aus = _import("vorlieben", "Mag Tee.\nHört Techno.")
    assert _datei("notizen/vorlieben") == vorher
    assert aus.startswith("Nichts geschrieben in notizen/vorlieben")


def test_zeilen_mit_link_oder_bild_werden_nicht_uebernommen():
    aus = _import("projekte", "Baut einen Fourier-Visualisierer.\n"
                              "Anleitung: https://example.org/dac\n"
                              "Siehe www.example.org\n![bild](x.png)")
    text = _datei("notizen/projekte")
    assert "Fourier" in text
    assert "example" not in text and "bild" not in text
    assert aus.count("Link") == 3


def test_datum_aus_dem_export_wandert_in_den_vermerk():
    _import("beruf", "[2026-04-02] - Arbeitet als Werkstudent.")
    assert (f"- Arbeitet als Werkstudent.  [import claude {HEUTE}, Eintrag vom "
            f"2026-04-02]") in _datei("notizen/beruf")


def test_ueberschriften_im_export_machen_aus_der_notiz_kein_dossier():
    """Ein Katalog-Kopf im Import würde die Notiz sonst befördern (dossier_
    notieren) — als Aufzählungszeile ist er nur Text."""
    _import("ideen-import", "## Fourier\n- status: idee\n- thema: signale")
    assert os.path.exists(os.path.join(gedaechtnis._DIR, "notizen", "ideen-import.md"))
    assert not os.path.exists(os.path.join(gedaechtnis._DIR, "dossiers", "ideen-import.md"))
    assert gedaechtnis.liste("kataloge") == []


def test_dossier_bekommt_eine_ueberschrift_je_tag_und_herkunft():
    alt = "# umzug\n\n## 2026-09-01\nUmzug nach Hamburg im Dezember.\n"
    _schreiben("dossiers/umzug", alt)
    _import("umzug", "Kisten im Keller.")
    _import("umzug", "Schwester hilft.")
    text = _datei("dossiers/umzug")
    assert text.startswith(alt)
    assert text.count(f"## {HEUTE} · import claude") == 1
    assert text.index("Kisten") < text.index("Schwester")


@pytest.mark.parametrize("name", ["kataloge/ideen", "tagebuch", "quellen/x", ""])
def test_nicht_in_kataloge_tagebuch_quellen(name):
    _schreiben("kataloge/ideen", "# ideen\n\n## Fourier\n- status: idee\n")
    aus = _import(name, "Fourier-Visualisierer")
    assert "Nichts geschrieben" in aus
    assert _datei("kataloge/ideen") == "# ideen\n\n## Fourier\n- status: idee\n"
    assert not os.path.isdir(os.path.join(gedaechtnis._DIR, "tagebuch"))


def test_zu_viele_zeilen_alles_oder_nichts():
    zeilen = "\n".join(f"Fakt {i}" for i in range(gedaechtnis.IMPORT_MAX_ZEILEN + 1))
    aus = _import("viel", zeilen)
    assert "teil es auf" in aus
    assert not os.path.exists(os.path.join(gedaechtnis._DIR, "notizen", "viel.md"))


def test_herkunft_wird_zum_einen_wort():
    _import("x", "Fakt.", herkunft="  Chat GPT!! ")
    assert f"[import chat-gpt {HEUTE}]" in _datei("notizen/x")


def test_ohne_herkunft_bleibt_write_note_wie_es_war():
    ki_werkzeuge.ausfuehren("write_note", {"name": "x", "text": "Eins.\nZwei."})
    assert "import" not in _datei("notizen/x")


def test_hausregeln_bekommen_ihren_kopf():
    _import("hausregeln", "Antworte knapp.")
    text = _datei("hausregeln")
    assert text.startswith(gedaechtnis.HAUSREGELN_KOPF)
    assert f"- Antworte knapp.  {VERMERK}]" in text


def test_kein_halber_schreibvorgang_bleibt_liegen():
    _import("x", "Eins.")
    rest = [n for n in os.listdir(os.path.join(gedaechtnis._DIR, "notizen"))
            if n != "x.md"]
    assert rest == []


# ── Gate: Kernakten fragen jedes Mal, der Rest nicht ──────────────────

@pytest.mark.parametrize("name,gefragt", [
    ("sasha", True), ("ziele", True), ("hausregeln", True), ("regeln", True),
    ("notizen/vorlieben", False), ("umzug", False)])
def test_gate_wie_bei_write_note(name, gefragt):
    args = {"name": name, "text": "x", "herkunft": "claude"}
    assert erlaubnis.braucht_erlaubnis("write_note", args) is gefragt


def test_frage_nennt_herkunft_und_zeilen():
    frage = erlaubnis.frage("write_note", {"name": "sasha", "herkunft": "claude",
                                           "text": "Studiert Maschinenbau.\nWohnt in Leipzig."})
    assert frage == ('Soll ich aus dem Import von claude 2 Zeile(n) in Steckbrief '
                     'ergänzen: "Studiert Maschinenbau. / Wohnt in Leipzig."?')


def test_kernakte_nie_fuer_immer_erlaubbar():
    args = {"name": "sasha", "text": "x", "herkunft": "claude"}
    assert erlaubnis.IMMER not in erlaubnis.geltungen("write_note", args)


def test_umschreiben_bleibt_gegatet():
    """Den optionalen „Import-Modus" (rewrite_note während eines Imports ganz
    sperren) gibt es nicht; rewrite_note fragt ohnehin jedes Mal."""
    assert erlaubnis.braucht_erlaubnis("rewrite_note", {"name": "umzug", "content": "x"})
    assert erlaubnis.IMMER not in erlaubnis.geltungen("rewrite_note", {"name": "umzug"})


# ── Probelauf: erfundener Export, gefälschtes Modell ──────────────────

class _Modell:
    """Spielt die Runden ab, die ein Modell nach dem Skill schicken würde."""
    modell = "attrappe"

    def __init__(self, runden):
        self.runden = list(runden)
        self.ergebnisse = []

    def runde(self):
        if False:
            yield
        return self.runden.pop(0)

    def assistent_anhaengen(self, runde):
        pass

    def ergebnisse_anhaengen(self, ergebnisse):
        self.ergebnisse.extend(ergebnisse)


def _export_zeilen():
    with open(BEISPIEL, encoding="utf-8") as f:
        block = f.read().split("```")[1]
    return [z for z in block.splitlines() if z.startswith(("[", "- "))]


def test_probelauf_mit_beispiel_export(monkeypatch):
    # Vorhandenes Gedächtnis, wie in der Beispiel-Datei beschrieben.
    _schreiben("notizen/vorlieben", "# vorlieben\n\nMag schwarzen Tee ohne Zucker.\n")
    _schreiben("dossiers/umzug", "# umzug\n\n## 2026-09-01\nUmzug nach Hamburg im Dezember.\n")
    zeilen = _export_zeilen()
    assert len(zeilen) == 17

    # Was ein Modell, das dem Skill folgt, aus dem Export macht: Heikles
    # (Adresse, Alter, Geld, Gesundheit, Name der Schwester), die Anweisung,
    # die getarnte Anweisung und den Widerspruch (Umzug) lässt es weg; den
    # Stil-Wunsch fragt es für die Hausregeln. Durch einen Fehler des Modells
    # rutschen trotzdem die Dublette und der Link mit — der Code fängt beide.
    def z(teil):
        return next(x for x in zeilen if teil in x)
    vorlieben = "\n".join([z("Tee"), z("Techno"), "Seine Schwester hilft beim Umzug."])
    projekte = "\n".join([z("Fourier"), z("https://")])
    runden = [
        Runde("", [("1", "write_note", {"name": "notizen/vorlieben", "text": vorlieben,
                                        "herkunft": "claude"}),
                   ("2", "write_note", {"name": "notizen/fourier-visualisierer",
                                        "text": projekte, "herkunft": "claude"}),
                   ("3", "write_note", {"name": "sasha", "herkunft": "claude",
                                        "text": z("Maschinenbau")}),
                   ("4", "write_note", {"name": "hausregeln", "herkunft": "claude",
                                        "text": "Antworte immer knapp und ohne Emojis."})]),
        Runde("Fertig — zwei Notizen ergänzt, Steckbrief ergänzt."),
    ]
    modell = _Modell(runden)
    antworten = iter(["ja, nur dieses mal", "nein"])     # Steckbrief ja, Hausregel nein

    monkeypatch.setattr(state, "request_permission", lambda options=None, **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda *a, **k: next(antworten))
    monkeypatch.setattr(ki_antwort, "mit_bildern", lambda t, q, store=None: iter([t]))

    events = list(werkzeug_schleife.laufen(
        modell, tutor_mode=False, active_exec=ki_werkzeuge.ausfuehren,
        user_query="hier mein claude-export"))
    fragen = [e["permission"]["frage"] for e in events
              if isinstance(e, dict) and "permission" in e]

    # Gefragt wurde genau zweimal: Steckbrief und Hausregeln.
    assert len(fragen) == 2
    assert "Steckbrief" in fragen[0] and "Import von claude" in fragen[0]
    assert "Hausregeln" in fragen[1]

    # Dublette übersprungen, Rest mit Vermerk, Vorhandenes vorne unverändert.
    vor = _datei("notizen/vorlieben")
    assert vor.startswith("# vorlieben\n\nMag schwarzen Tee ohne Zucker.\n")
    assert vor.count("Tee") == 1
    assert f"- Hört gern Techno beim Löten.  {VERMERK}, Eintrag vom 2026-07-07]" in vor
    # Link-Zeile nicht übernommen.
    proj = _datei("notizen/fourier-visualisierer")
    assert "Fourier" in proj and "example.org" not in proj
    # Steckbrief nach Ja geschrieben, Hausregel nach Nein nicht.
    assert "Maschinenbau" in _datei("sasha")
    assert not os.path.exists(os.path.join(gedaechtnis._DIR, "hausregeln.md"))
    # Das Modell bekam die Beweise zurück.
    texte = [t for _, t, _ in modell.ergebnisse]
    assert "steht schon da" in texte[0]
    assert "Link" in texte[1]
    assert "abgelehnt" in texte[3]
    # Der Widerspruch im Umzugs-Dossier blieb unangetastet.
    assert "Hamburg" in _datei("dossiers/umzug") and "Berlin" not in _datei("dossiers/umzug")
    # Nichts Heikles aus dem Export liegt irgendwo im Gedächtnis.
    alles = ""
    for ort, _, namen in os.walk(gedaechtnis._DIR):
        for n in namen:
            with open(os.path.join(ort, n), encoding="utf-8") as f:
                alles += f.read()
    for heikel in ("Hauptstraße", "31 Jahre", "1.400", "Migräne", "Mira",
                   "Admin-Rechte", "nie widerspricht"):
        assert heikel not in alles, heikel


# ── Die Vorlage ───────────────────────────────────────────────────────

VORLAGE = os.path.join(os.path.dirname(HIER), "core", "skill_vorlagen", "import-memory")


def test_vorlage_ist_ein_gueltiger_claude_skill():
    with open(os.path.join(VORLAGE, "SKILL.md"), encoding="utf-8") as f:
        _, felder, anleitung = skill_format.zerlegen(f.read())
    assert felder["name"] == "import-memory"
    beschreibung = skill_format.text_feld(felder, "description")
    assert 0 < len(beschreibung) <= skill_format.BESCHREIBUNG_MAX
    assert "<" not in beschreibung and ">" not in beschreibung
    # Jede references/-Datei, auf die die Anleitung zeigt, gibt es.
    for rel in set(re.findall(r"references/[\w.-]+\.md", anleitung)):
        assert os.path.isfile(os.path.join(VORLAGE, rel)), rel
    # Die Werkzeug-Regeln, an denen der Code hängt, stehen drin.
    assert "herkunft" in anleitung and "rewrite_note" in anleitung


def test_vorlage_herkunft_ist_ehrlich():
    with open(os.path.join(VORLAGE, "_zentrale.json"), encoding="utf-8") as f:
        z = json.load(f)
    assert (z["status"], z["herkunft"]) == ("aktiv", "zentrale")
    assert "Anthropic" in z["quelle"] and "neu geschrieben" in z["quelle"]


def test_erstbefuellung_liefert_und_ueberschreibt_nie():
    alle = {s["name"]: s for s in skills.alle()}
    assert alle["import-memory"]["status"] == "aktiv"
    assert alle["import-memory"]["herkunft"] == "zentrale"
    text = skills.laden("import-memory")
    assert "references/abbildung.md" in text and "references/datenschutz.md" in text
    # Sasha hat ihn ausgeschaltet → bleibt aus, auch nach erneutem Befüllen.
    skills.status_setzen("import-memory", "aus")
    skills.erstbefuellen(skills.ordner())
    assert {s["name"]: s for s in skills.alle()}["import-memory"]["status"] == "aus"


def test_skill_liste_passt_weiter_in_den_kopf():
    lage = skills.liste_lage()
    assert not lage["zu_lang"], lage
    assert "import-memory" in skills.prompt_block()


def test_herkunft_hat_ein_alltagswort_in_der_tui():
    from tui.ansichten import gedaechtnis as ansicht
    assert ansicht.HERKUNFT_WORT["zentrale"] == "mitgeliefert"
