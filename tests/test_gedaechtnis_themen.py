"""Das Gedächtnis nach Themen (2026-10-11).

Sasha: „wir sortieren momentan nach datenformat, FALSCH. wir sollten nach
thema sortieren … guck dir einfach dich selbst an, was du darfst und kannst
in deiner memory und modellier genau danach." Geprüft wird, was Claudes
Datei-Gedächtnis ausmacht und was der Umzug garantieren muss:

  - eine Datei je Sache mit Kopf (name, description, metadata) — lesbar und
    schreibbar in beide Richtungen (Claude-Dateien gehen unverändert durch);
  - ein Index, der im gecachten Kopf steht und sich NUR bei echter Änderung
    der Struktur ändert;
  - vorhandene Datei ergänzen statt eine zweite anlegen, archivieren statt
    löschen, Kataloge und Messreihen unter ihrem Thema;
  - der Umzug: Vorschlag ohne Änderung, Sashas Tabelle wird übernommen,
    nichts geht verloren, ein zweiter Lauf tut nichts.
"""
import importlib.util
import json
import os

import pytest

import gedaechtnis
import gedaechtnis_ablage as ablage
import graphs
import ki_werkzeuge

HIER = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    daten = tmp_path / "daten"
    daten.mkdir()
    monkeypatch.setattr(graphs, "_DATA_DIR", str(daten))
    monkeypatch.setattr(graphs, "_REGISTRY", str(daten / "graphs.json"))


def _lesen(pfad):
    with open(pfad, encoding="utf-8") as f:
        return f.read()


# ── Der Kopf: Claudes Format, in beide Richtungen ──────────────────────

CLAUDE_DATEI = """---
name: mac-tastatur
description: "Super statt Alt nutzen: Alt-Remap unzuverlässig"
type: feedback
metadata:
  quelle: claude
---

Cmd+Pfeil wechselt den Fokus.
"""


def test_claude_datei_wird_gelesen_und_unveraendert_wieder_geschrieben():
    kopf, rumpf = ablage.zerlegen(CLAUDE_DATEI)
    assert kopf["name"] == "mac-tastatur"
    assert kopf["description"] == "Super statt Alt nutzen: Alt-Remap unzuverlässig"
    assert kopf["type"] == "feedback" and kopf["metadata"] == {"quelle": "claude"}
    assert ablage.art_von(kopf) == "feedback"           # type gilt, wenn art fehlt
    assert rumpf == "Cmd+Pfeil wechselt den Fokus.\n"
    neu = ablage.text_bauen(kopf, rumpf)
    assert ablage.zerlegen(neu) == (kopf, rumpf)


def test_ohne_kopf_bleibt_der_text_ganz():
    assert ablage.zerlegen("# Titel\n\nText") == ({}, "# Titel\n\nText")
    assert ablage.zerlegen("---\nkaputt ohne ende") == ({}, "---\nkaputt ohne ende")


def test_beschreibung_mit_doppelpunkt_bricht_den_kopf_nicht():
    kopf = ablage.neuer_kopf("x", "Wegzeiten: Uni 20 min # Rad", "notiz")
    assert ablage.zerlegen(ablage.text_bauen(kopf, "a"))[0]["description"] == \
        "Wegzeiten: Uni 20 min # Rad"


# ── Anlegen, ergänzen, nicht doppeln ───────────────────────────────────

def test_neue_datei_liegt_unter_ihrem_thema_mit_kopf():
    antwort = gedaechtnis.notieren("wegzeiten", "Uni: 20 min Rad.", thema="Alltag",
                                   beschreibung="Wie lange er wohin braucht")
    assert "alltag/wegzeiten (notiz)" in antwort
    text = _lesen(os.path.join(gedaechtnis._DIR, "themen", "alltag", "wegzeiten.md"))
    kopf, rumpf = ablage.zerlegen(text)
    assert kopf["name"] == "wegzeiten"
    assert kopf["description"] == "Wie lange er wohin braucht"
    assert kopf["metadata"]["art"] == "notiz" and kopf["metadata"]["aktualisiert"]
    assert rumpf.strip() == "Uni: 20 min Rad."


def test_vorhandene_datei_wird_ergaenzt_auch_ohne_thema():
    """Claudes erste Regel: erst nachsehen, ob es schon eine passende Datei
    gibt, und die ergänzen — nicht daneben eine zweite anlegen."""
    gedaechtnis.notieren("wegzeiten", "Uni: 20 min.", thema="alltag")
    gedaechtnis.notieren("wegzeiten", "Bahnhof: 5 min.")
    gedaechtnis.notieren("wegzeiten", "Geige: 7 min.", thema="alltag")
    assert len(gedaechtnis.finden("wegzeiten")) == 1
    assert ablage.themen(gedaechtnis._DIR) == ["alltag"]
    text = gedaechtnis.dossier_lesen("wegzeiten")
    assert "Uni" in text and "Bahnhof" in text and "Geige" in text


def test_gleicher_name_in_zwei_themen_wird_nicht_geraten():
    gedaechtnis.notieren("plan", "a", thema="sport")
    gedaechtnis.notieren("plan", "b", thema="studium")
    antwort = gedaechtnis.notieren("plan", "c")
    assert antwort.startswith("[Mehrdeutig") and "sport/plan" in antwort
    assert "c" not in gedaechtnis.dossier_lesen("sport/plan").split()
    assert "Mehrdeutig" in ki_werkzeuge.ausfuehren("read_note", {"name": "plan"})
    assert "b" in ki_werkzeuge.ausfuehren("read_note", {"name": "plan", "thema": "studium"})


def test_haken_kommt_von_der_ki_nicht_aus_dem_inhalt():
    """Der Index steht im gecachten Kopf — Inhalte gehören da nicht hinein."""
    antwort = gedaechtnis.notieren("geheim", "persönlicher Inhalt", thema="person")
    assert "Ohne beschreibung" in antwort
    assert "persönlicher Inhalt" not in gedaechtnis.kopf_block()
    gedaechtnis.notieren("geheim", "noch was", beschreibung="Etwas Privates")
    assert "[geheim](themen/person/geheim.md) — Etwas Privates" in gedaechtnis.kopf_block()


def test_katalog_unter_thema_upsert_und_dossier_kopf():
    gedaechtnis.notieren("training", "## L-Sit\n- thema: core\n- status: idee",
                         thema="sport", art="katalog", beschreibung="Übungen")
    gedaechtnis.notieren("training.katalog", "## L-Sit\n- thema: core\n- status: queued")
    kat = gedaechtnis.dossier_lesen("sport/training.katalog")
    assert kat.count("## L-Sit") == 1 and "queued" in kat
    # Ein Dossier mit Kopf trägt sich in den Katalog seines Namens ein, egal
    # in welchem Thema der liegt.
    gedaechtnis.notieren("spagat", "## Spagat\n- katalog: training\n- status: priorisiert",
                         thema="sport")
    kat = gedaechtnis.dossier_lesen("training.katalog")
    assert "## Spagat" in kat and "dossier:   spagat" in kat
    # Ein Dossier gleichen Namens daneben stört den Katalog nicht.
    gedaechtnis.notieren("training", "Stand: gedrosselt.", thema="sport", art="dossier")
    assert len(gedaechtnis.finden("sport/training")) == 1
    assert "gedrosselt" in gedaechtnis.dossier_lesen("sport/training")
    assert "gedrosselt" not in gedaechtnis.dossier_lesen("training.katalog")


def test_tagebuch_je_monat_mit_tagesueberschrift():
    from datetime import date
    gedaechtnis.tagebuch_notieren("eins")
    gedaechtnis.tagebuch_notieren("zwei")
    pfad = gedaechtnis.tagebuch_pfad(date.today())
    assert pfad.endswith(f"themen/tagebuch/{date.today():%Y-%m}.md")
    rumpf = ablage.zerlegen(_lesen(pfad))[1]
    assert rumpf.count(f"## {date.today().isoformat()}") == 1
    assert "eins" in gedaechtnis.tagebuch_lesen() and "zwei" in gedaechtnis.tagebuch_lesen()
    assert "tagebuch" in gedaechtnis.kopf_block()


# ── Archivieren statt löschen ──────────────────────────────────────────

def test_archivieren_legt_weg_und_der_index_vergisst_sie():
    gedaechtnis.notieren("alt", "stimmt nicht mehr", thema="alltag", beschreibung="Veraltet")
    assert "Veraltet" in gedaechtnis.kopf_block()
    befund = ki_werkzeuge._verteilen("archive_note", {"name": "alltag/alt"})
    assert befund.status == "ok" and befund.beleg
    assert not gedaechtnis.finden("alt")
    assert "Veraltet" not in gedaechtnis.kopf_block()
    archiv = os.path.join(gedaechtnis._DIR, "_archiv", "themen", "alltag", "alt.md")
    assert "stimmt nicht mehr" in _lesen(archiv)
    # Zweimal archivieren überschreibt das Archiv nicht.
    gedaechtnis.notieren("alt", "zweite Fassung", thema="alltag")
    gedaechtnis.archivieren("alt")
    assert len(os.listdir(os.path.dirname(archiv))) == 2


def test_kernakten_archiviert_die_ki_nicht():
    gedaechtnis.kernakte_schreiben("steckbrief", "Studiert.")
    for name in ("steckbrief", "sasha", "person/ziele", "hausregeln"):
        assert gedaechtnis.archivieren(name).startswith("[")
    assert gedaechtnis.steckbrief() == "Studiert."


def test_archivieren_abbruch_legt_zurueck(monkeypatch):
    """Steht es nachgelesen noch da, ist der alte Stand wiederhergestellt
    (dieselbe Transaktion wie bei allen schreibenden Werkzeugen)."""
    gedaechtnis.notieren("wege", "Bahnhof 5 min.", thema="alltag")
    monkeypatch.setattr(gedaechtnis, "ort_von", lambda *a, **k: "alltag/wege")
    befund = ki_werkzeuge._verteilen("archive_note", {"name": "wege"})
    assert befund.status == "fehlgeschlagen" and befund.code == "W-NICHT-GESPEICHERT"
    assert "Bahnhof" in gedaechtnis.dossier_lesen("alltag/wege")
    assert not os.path.exists(os.path.join(gedaechtnis._DIR, "_archiv", "themen",
                                           "alltag", "wege.md"))


# ── Der Index im Kopf ──────────────────────────────────────────────────

def test_index_aendert_sich_nur_bei_neuer_struktur():
    """Er steht im gecachten Prompt-Kopf: anhängen darf ihn nicht ändern
    (sonst bräche jede Notiz den Cache), eine neue Datei schon."""
    gedaechtnis.notieren("spagat", "Stand 22 cm.", thema="sport", art="dossier",
                         beschreibung="Voller Spagat")
    vorher = gedaechtnis.kopf_block()
    gedaechtnis.notieren("spagat", "Stand 20 cm.")
    gedaechtnis.tagebuch_notieren("geübt")
    zwischen = gedaechtnis.kopf_block()
    gedaechtnis.tagebuch_notieren("nochmal")
    assert gedaechtnis.kopf_block() == zwischen
    assert "Stand 2" not in zwischen
    gedaechtnis.notieren("parkour", "mi 18 Uhr", thema="sport", beschreibung="Parkour")
    assert gedaechtnis.kopf_block() != zwischen
    assert vorher.split("## sport")[1].startswith("\n- [spagat](themen/sport/spagat.md) (dossier)")


def test_index_datei_wird_mitgeschrieben():
    gedaechtnis.notieren("wegzeiten", "x", thema="alltag", beschreibung="Wege")
    index = _lesen(os.path.join(gedaechtnis._DIR, "INDEX.md"))
    assert index.startswith("# Gedächtnis — Index")
    assert "- [wegzeiten](themen/alltag/wegzeiten.md) — Wege" in index
    assert ki_werkzeuge.ausfuehren("read_note", {"name": "index"}).startswith("## alltag")


def test_kopf_hat_regeln_wie_claude():
    gedaechtnis.notieren("x", "y", thema="alltag")
    block = gedaechtnis.kopf_block()
    for teil in ("ergänzen statt eine zweite", "beschreibung", "archive_note",
                 "festes Datum", "Warum"):
        assert teil in block, teil


# ── Messreihen unter ihrem Thema ───────────────────────────────────────

def test_messreihe_mit_thema_liegt_im_gedaechtnis_und_wird_beschrieben():
    befund = ki_werkzeuge._verteilen("create_series", {"name": "Schlaf", "typ": "period",
                                                       "thema": "gesundheit"})
    assert befund.status == "ok" and "gesundheit/schlaf.reihe" in befund.beleg
    werte = os.path.join(gedaechtnis._DIR, "themen", "gesundheit", "schlaf.reihe.json")
    assert graphs._values_path("g_schlaf") == werte
    ki_werkzeuge._verteilen("log_series", {"series": "gesundheit/schlaf", "value": 420,
                                           "day": "2026-10-10"})
    assert json.loads(_lesen(werte))[0]["value"] == 420
    assert "(messreihe) — Messreihe Schlaf (Zeitspanne)" in gedaechtnis.kopf_block()


def test_messreihe_ohne_thema_bleibt_wo_sie_war():
    """Rückfall, bis umgezogen: data/g_*.json wie bisher."""
    g = graphs.create_graph("Gym", gtype="time")
    graphs.log_value(g["id"], "2026-10-10", 600)
    assert graphs._values_path(g["id"]) == os.path.join(graphs._DATA_DIR, g["id"] + ".json")
    assert graphs.read_values(g["id"])[0]["value"] == 600


def test_geloeschte_reihe_unter_thema_wird_archiviert():
    g = graphs.create_graph("Puls", gtype="number")
    gedaechtnis.reihe_anlegen(g["id"], "gesundheit", "Puls", "number")
    graphs.delete_graph(g["id"])
    assert not gedaechtnis.finden("puls.reihe")
    assert os.path.exists(os.path.join(gedaechtnis._DIR, "_archiv", "themen", "gesundheit",
                                       "puls.reihe.json"))


def test_werte_ausserhalb_der_themen_werden_nie_gefunden():
    """Die id kommt über /api/log von außen: kein Weg aus dem Ordner."""
    for gid in ("../ai_config", "g_../../x", ".versteckt", "", None, 5):
        assert ablage.reihe_finden(gedaechtnis._DIR, gid) is None


# ── Der alte Aufbau bis zum Umzug ──────────────────────────────────────

def _alt_bestand(wurzel):
    """Ein kleiner alter Bestand (wie Sashas vom 11.10.2026, erfunden)."""
    dateien = {
        "sasha.md": "# Sasha\n\nStudiert Biophysik.\n",
        "ziele.md": "# Ziele\n\n- Spagat\n",
        "hausregeln.md": "# Hausregeln\n\n- Kurz antworten.\n",
        "dossiers/spagat.md": "# spagat\n\nVoller Spagat. Blockiert an den Adduktoren.\n",
        "dossiers/umzug.md": "## Umzug fertig kriegen\n- katalog: vorhaben\n- status: "
                             "in_schedule\n\nKüche fehlt.\n",
        "kataloge/vorhaben.md": "# vorhaben\n\n## Umzug fertig kriegen\n- katalog: vorhaben\n"
                                "- status: in_schedule\n- dossier: umzug\n",
        "notizen/fraktal-rendering.md": "# fraktal-rendering\n\nMandelbulber ausprobieren.\n",
        "quellen/modulhandbuch.md": "# modulhandbuch\n\n> Geholt am 2026-08-18 von "
                                    "https://uni.de/mh.pdf\n\nExperimentalphysik I\n",
        "quellen/dateien/plan.png": "PNG",
        "tagebuch/2026-08-18.md": "# 2026-08-18\n\n- 14:25 Praktikum verpasst.\n",
        "tagebuch/2026-08-20.md": "# 2026-08-20\n\n- 09:00 Geige.\n",
        "vorlagen/katalog.md": "# katalog\n\nmeine Vorlage\n",
        "skills/kurz/SKILL.md": "---\nname: kurz\ndescription: x\n---\n\nKurz.\n",
        "projekte/geige/projekt.json": "{}",
    }
    for rel, text in dateien.items():
        pfad = os.path.join(wurzel, rel)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(text)
    return dateien


def test_vor_dem_umzug_liest_sie_den_alten_bestand():
    _alt_bestand(gedaechtnis._DIR)
    block = gedaechtnis.kopf_block()
    assert "Studiert Biophysik" in block and "Kurz antworten" in block
    assert "Spagat" in block                      # Ziele, solange alt
    assert "dossiers/ — spagat, umzug" in block
    assert "Adduktoren" in ki_werkzeuge.ausfuehren("read_note", {"name": "spagat"})
    assert "notizen/fraktal-rendering" in gedaechtnis.suchen("Mandelbulber")
    assert gedaechtnis.skills_ordner().endswith(os.path.join("gedaechtnis", "skills"))


def test_ergaenzen_vor_dem_umzug_setzt_auf_dem_alten_inhalt_auf():
    _alt_bestand(gedaechtnis._DIR)
    gedaechtnis.notieren("spagat", "Heute 2 cm weiter.")
    text = gedaechtnis.dossier_lesen("spagat")
    assert "Adduktoren" in text and "2 cm weiter" in text
    gedaechtnis.regel_notieren("Nicht duzen.")
    assert "Kurz antworten" in gedaechtnis.hausregeln()
    assert "Nicht duzen" in gedaechtnis.hausregeln()


# ── Der Umzug ──────────────────────────────────────────────────────────

def _umzug():
    spec = importlib.util.spec_from_file_location(
        "gedaechtnis_umzug", os.path.join(HIER, "..", "scripts", "gedaechtnis_umzug.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _alles(wurzel):
    """{relativer Pfad: Inhalt} aller Dateien unter wurzel."""
    raus = {}
    for ort, _, namen in os.walk(wurzel):
        for n in namen:
            p = os.path.join(ort, n)
            with open(p, "rb") as f:
                raus[os.path.relpath(p, wurzel)] = f.read()
    return raus


def _reihen(daten):
    with open(os.path.join(daten, "graphs.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "g_sleep", "name": "sleep", "type": "period", "unit": ""}], f)
    with open(os.path.join(daten, "g_sleep.json"), "w", encoding="utf-8") as f:
        json.dump([{"date": "2026-10-10", "value": 60, "end": 480}], f)


def test_trocken_zeigt_die_tabelle_und_aendert_nichts(tmp_path, capsys):
    u = _umzug()
    wurzel = gedaechtnis._DIR
    _alt_bestand(wurzel)
    _reihen(graphs._DATA_DIR)
    vorher = _alles(wurzel)
    tabelle = tmp_path / "vorschlag.md"
    assert u.main(["--wurzel", wurzel, "--daten", graphs._DATA_DIR,
                   "--tabelle", str(tabelle)]) == 0
    aus = capsys.readouterr().out
    assert _alles(wurzel) == vorher
    assert "Trocken" in aus
    t = tabelle.read_text(encoding="utf-8")
    assert "| dossiers/spagat.md | sport | spagat | dossier |" in t
    assert "| sasha.md | person | steckbrief | steckbrief |" in t and "(fest)" in t
    assert "| data/g_sleep.json | gesundheit | sleep | messreihe |" in t
    assert "| kataloge/vorhaben.md | allgemein | vorhaben | katalog |" in t


def test_wirklich_nichts_verloren_und_idempotent(tmp_path):
    u = _umzug()
    wurzel, daten = gedaechtnis._DIR, graphs._DATA_DIR
    alt = _alt_bestand(wurzel)
    _reihen(daten)
    # Sasha korrigiert: Fraktale gehören zu „kunst", nicht zu „basteln".
    tabelle = tmp_path / "plan.md"
    u.main(["--wurzel", wurzel, "--daten", daten, "--tabelle", str(tabelle)])
    text = tabelle.read_text(encoding="utf-8").replace(
        "| notizen/fraktal-rendering.md | basteln | fraktal-rendering | notiz |",
        "| notizen/fraktal-rendering.md | kunst | fraktale | notiz |")
    tabelle.write_text(text, encoding="utf-8")
    assert u.main(["--wurzel", wurzel, "--daten", daten, "--plan", str(tabelle),
                   "--wirklich"]) == 0

    # Nichts verloren: jede alte Datei liegt Wort für Wort im _alt-Ordner …
    alt_ordner = [d for d in os.listdir(wurzel) if d.startswith("_alt_vor_themen_")]
    assert len(alt_ordner) == 1
    gesichert = _alles(os.path.join(wurzel, alt_ordner[0]))
    for rel, inhalt in alt.items():
        if rel.startswith(("skills/", "projekte/")):
            continue
        assert gesichert[rel] == inhalt.encode(), rel
    assert gesichert[os.path.join("data", "g_sleep.json")]
    # … und inhaltlich in der neuen Struktur.
    neu = _alles(os.path.join(wurzel, "themen"))
    assert "Adduktoren" in neu["sport/spagat.md"].decode()
    assert "Mandelbulber" in neu["kunst/fraktale.md"].decode()
    assert "Experimentalphysik" in neu["studium/modulhandbuch.md"].decode()
    assert neu["allgemein/dateien/plan.png"] == b"PNG"     # kein Vermerk namens plan
    monat = neu["tagebuch/2026-08.md"].decode()
    assert monat.index("## 2026-08-18") < monat.index("## 2026-08-20") and "Geige" in monat
    assert json.loads(neu["gesundheit/sleep.reihe.json"])[0]["end"] == 480
    assert "reihe: g_sleep" in neu["gesundheit/sleep.reihe.md"].decode()
    assert "Studiert Biophysik" in gedaechtnis.steckbrief()
    assert "Kurz antworten" in gedaechtnis.hausregeln()
    assert "meine Vorlage" in gedaechtnis.vorlage("katalog")
    assert os.path.isfile(os.path.join(wurzel, "ki", "skills", "kurz", "SKILL.md"))
    assert os.path.isfile(os.path.join(wurzel, "projekte", "geige", "projekt.json"))
    assert not os.path.exists(os.path.join(daten, "g_sleep.json"))
    assert graphs.read_values("g_sleep")[0]["value"] == 60
    # Köpfe und Index
    kopf = ablage.zerlegen(neu["wohnen/umzug.md"].decode())[0]
    assert kopf["metadata"]["art"] == "dossier"
    assert kopf["description"] == "Umzug fertig kriegen (in_schedule)"
    index = _lesen(os.path.join(wurzel, "INDEX.md"))
    assert "[fraktale](themen/kunst/fraktale.md)" in index
    # Nichts mehr vom alten Aufbau im Kopf, kein Zwischenordner.
    assert "alter aufbau" not in gedaechtnis.kopf_block()
    assert not os.path.exists(os.path.join(wurzel, u.ZWISCHEN))

    # Ein zweiter Lauf findet nichts und ändert nichts.
    vorher = _alles(wurzel)
    assert u.main(["--wurzel", wurzel, "--daten", daten, "--wirklich"]) == 0
    assert _alles(wurzel) == vorher


def test_was_die_ki_vor_dem_umzug_schrieb_bleibt(tmp_path):
    """Nach dem Update, vor dem Umzug, hat die KI schon in den neuen Aufbau
    geschrieben: der Umzug führt zusammen, statt zu überschreiben."""
    u = _umzug()
    wurzel = gedaechtnis._DIR
    _alt_bestand(wurzel)
    gedaechtnis.notieren("spagat", "Heute 2 cm weiter.", thema="sport")
    gedaechtnis.tagebuch_notieren("nach dem update")
    u.main(["--wurzel", wurzel, "--daten", graphs._DATA_DIR, "--wirklich"])
    spagat = gedaechtnis.dossier_lesen("sport/spagat")
    assert spagat.count("Adduktoren") == 1 and "2 cm weiter" in spagat
    assert "nach dem update" in gedaechtnis.tagebuch_lesen()


def test_abgebrochener_umzug_wird_beim_naechsten_lauf_fertig(tmp_path, monkeypatch):
    u = _umzug()
    wurzel = gedaechtnis._DIR
    _alt_bestand(wurzel)
    zeilen = u.plan_bauen(wurzel, graphs._DATA_DIR)
    echt = u._einsetzen
    monkeypatch.setattr(u, "_einsetzen", lambda *a: (_ for _ in ()).throw(OSError("Strom weg")))
    with pytest.raises(OSError):
        u.ausfuehren(wurzel, zeilen, graphs._DATA_DIR)
    assert os.path.isdir(os.path.join(wurzel, u.ZWISCHEN))     # nichts verloren
    monkeypatch.setattr(u, "_einsetzen", echt)
    u.ausfuehren(wurzel, u.plan_bauen(wurzel, graphs._DATA_DIR), graphs._DATA_DIR)
    assert "Adduktoren" in gedaechtnis.dossier_lesen("sport/spagat")
    assert not os.path.exists(os.path.join(wurzel, u.ZWISCHEN))
