"""Spielstände: mehrere Lernstände nebeneinander, einer ist aktiv.

Bis dahin hatte der Tutor genau EINEN Lernstand (tutor/data/<lang>/). Wer neu
anfangen wollte, musste Dateien löschen und war den alten Fortschritt los.
Geprüft wird hier gegen echte Verzeichnisse in tmp_path — die Fragen sind
Datei-Fragen, dafür braucht es keine Attrappen.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tutor import staende            # noqa: E402


def _alt_anlegen(root, lang="es", woerter=2, muenzen=22):
    """Den Zustand VOR den Spielständen nachstellen: Sprachordner flach."""
    d = os.path.join(root, lang)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "vocab.json"), "w", encoding="utf-8") as f:
        json.dump([{"word": "w%d" % i} for i in range(woerter)], f)
    with open(os.path.join(d, "game.json"), "w", encoding="utf-8") as f:
        json.dump({"coins": muenzen}, f)
    return d


# ── Anlegen und Wählen ───────────────────────────────────────────────────

def test_erster_zugriff_legt_einen_stand_an(tmp_path):
    """aktiv() darf nie None liefern — sonst müsste jede Schreibstelle im
    Tutor den Sonderfall »noch kein Stand« kennen."""
    sid = staende.aktiv(str(tmp_path))
    assert sid
    assert os.path.isdir(os.path.join(str(tmp_path), "staende", sid))


def test_pfad_liegt_unter_dem_aktiven_stand(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, a)
    assert staende.pfad(root, "es").endswith(os.path.join("staende", a, "es"))
    staende.waehlen(root, b)
    assert staende.pfad(root, "es").endswith(os.path.join("staende", b, "es"))


def test_gleiche_namen_kollidieren_nicht(tmp_path):
    root = str(tmp_path)
    ids = {staende.anlegen(root, "Neuer Anlauf", lang="es") for _ in range(3)}
    assert len(ids) == 3, "jeder Stand braucht einen eigenen Ordner"


def test_name_darf_alles_sein_der_ordner_nicht(tmp_path):
    """Der Name steht in stand.json und darf Umlaute und Emoji haben; der
    Ordner muss auf jedem Dateisystem heil bleiben."""
    root = str(tmp_path)
    sid = staende.anlegen(root, "Lucía & ich 💃", lang="es")
    assert all(c.isalnum() or c == "-" for c in sid)
    assert [s for s in staende.liste(root) if s["id"] == sid][0]["name"] == "Lucía & ich 💃"


def test_unbekannten_stand_waehlen_aendert_nichts(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    staende.waehlen(root, a)
    assert staende.waehlen(root, "gibtsnicht") is False
    assert staende.aktiv(root) == a


def test_liste_zeigt_woran_man_einen_stand_erkennt(tmp_path):
    """Namen allein reichen nicht — man will sehen, wie weit man war."""
    root = str(tmp_path)
    sid = staende.anlegen(root, "Mit Fortschritt", lang="es")
    staende.waehlen(root, sid)
    _alt_anlegen(os.path.join(root, "staende", sid), "es", woerter=30, muenzen=22)
    eintrag = [s for s in staende.liste(root) if s["id"] == sid][0]
    assert eintrag["sprachen"]["es"] == {"woerter": 30, "muenzen": 22}


def test_zuletzt_gespielter_steht_oben(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, a)
    staende.waehlen(root, b)
    assert staende.liste(root)[0]["id"] == b


# ── Umzug vom alten Einzel-Stand ─────────────────────────────────────────

def test_alter_lernstand_zieht_um_statt_verloren_zu_gehen(tmp_path):
    """Der alte Stand lag flach unter tutor/data/. Er wandert in einen
    Spielstand — niemand soll seinen Fortschritt verlieren, nur weil es die
    Funktion jetzt gibt."""
    root = str(tmp_path)
    _alt_anlegen(root, "es", woerter=30, muenzen=22)
    _alt_anlegen(root, "zh", woerter=5, muenzen=0)

    sid = staende.aktiv(root)                       # löst den Umzug aus

    assert not os.path.exists(os.path.join(root, "es")), "alt muss weg sein"
    # Ein Stand je Sprache: es und zh landen in ZWEI Ständen.
    alle = staende.liste(root)
    es = [s for s in alle if s["lang"] == "es"]
    zh = [s for s in alle if s["lang"] == "zh"]
    assert len(es) == 1 and len(zh) == 1 and es[0]["id"] != zh[0]["id"]
    assert es[0]["woerter"] == 30 and zh[0]["woerter"] == 5
    assert sid in (es[0]["id"], zh[0]["id"])


def test_umzug_laesst_gemeinsame_ordner_liegen(tmp_path):
    """Bilder und Musik gehören keinem Stand — die bleiben, wo sie sind."""
    root = str(tmp_path)
    _alt_anlegen(root, "es")
    for gemeinsam in ("vocab_images", "persona_music"):
        os.makedirs(os.path.join(root, gemeinsam))
    staende.aktiv(root)
    for gemeinsam in ("vocab_images", "persona_music"):
        assert os.path.isdir(os.path.join(root, gemeinsam))


def test_umzug_passiert_nur_einmal(tmp_path):
    root = str(tmp_path)
    _alt_anlegen(root, "es")
    sid = staende.aktiv(root)
    _alt_anlegen(root, "es", woerter=99)            # danach wieder etwas Flaches
    assert staende.migrieren(root) is None, "zweiter Umzug darf nicht laufen"
    assert staende.aktiv(root) == sid


def test_ohne_alte_daten_kein_umzug(tmp_path):
    assert staende.migrieren(str(tmp_path)) is None


# ── Die drei Datenmodule hängen wirklich am Stand ────────────────────────

def test_memory_srs_tools_folgen_dem_stand(tmp_path, monkeypatch):
    """Der Sinn der Übung: alle drei Speicherorte müssen mitwandern, nicht nur
    einer. Läge einer daneben, mischten sich zwei Spielstände."""
    from tutor import memory, srs, tools
    root = str(tmp_path)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)

    a = staende.anlegen(root, "A", lang="es")
    staende.waehlen(root, a)
    assert ("staende/%s/es" % a) in memory.mem_path("es").replace(os.sep, "/")
    assert ("staende/%s/es" % a) in srs._file("es").replace(os.sep, "/")
    assert ("staende/%s/es" % a) in tools._dir("es").replace(os.sep, "/")

    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, b)
    for pfad in (memory.mem_path("es"), srs._file("es"), tools._dir("es")):
        assert ("staende/%s/es" % b) in pfad.replace(os.sep, "/")


# ── Löschen ──────────────────────────────────────────────────────────────

def test_loeschen_entfernt_den_stand_samt_inhalt(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    _alt_anlegen(os.path.join(root, "staende", a), "es")
    assert staende.loeschen(root, a) is True
    assert not os.path.exists(os.path.join(root, "staende", a))
    assert [s["id"] for s in staende.liste(root)] == [b]


def test_unbekannten_stand_loeschen_ist_folgenlos(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    assert staende.loeschen(root, "gibtsnicht") is False
    assert [s["id"] for s in staende.liste(root)] == [a]


def test_aktiven_stand_loeschen_faellt_auf_einen_anderen_zurueck(tmp_path):
    """Man räumt meistens den auf, in dem man gerade steht — danach muss der
    Tutor weiterlaufen, nicht auf einen toten Zeiger zeigen."""
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, b)
    staende.waehlen(root, a)                     # a ist aktiv
    assert staende.loeschen(root, a) is True
    assert staende.aktiv(root) == b


def test_letzten_stand_loeschen_legt_einen_neuen_an(tmp_path):
    """Auch wer ALLES löscht, darf nicht in einem unbedienbaren Zustand
    landen — aktiv() liefert nie None."""
    root = str(tmp_path)
    a = staende.anlegen(root, "Einziger", lang="es")
    staende.waehlen(root, a)
    assert staende.loeschen(root, a) is True
    neu = staende.aktiv(root)
    assert neu and neu != a
    assert os.path.isdir(os.path.join(root, "staende", neu))


# ── Ein Stand = eine Sprache (seit 2026-09-17) ───────────────────────────

def test_stand_braucht_sprache_und_level(tmp_path):
    root = str(tmp_path)
    with pytest.raises(ValueError):
        staende.anlegen(root, "ohne")
    with pytest.raises(ValueError):
        staende.anlegen(root, "falsch", lang="es", level=7)
    sid = staende.anlegen(root, "de", lang="de", level=1)
    info = [s for s in staende.liste(root) if s["id"] == sid][0]
    assert info["lang"] == "de" and info["level"] == 1


def test_aktive_sprache_kommt_aus_dem_stand(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="de")
    staende.waehlen(root, a)
    assert staende.aktive_sprache(root) == "es"
    staende.waehlen(root, b)
    assert staende.aktive_sprache(root) == "de"
    assert staende.aktiv_info(root)["id"] == b


def test_pfad_weigert_fremde_sprache(tmp_path):
    """Physisch unmöglich: ein es-Write in einen de-Stand gibt keinen Pfad."""
    root = str(tmp_path)
    d = staende.anlegen(root, "Deutsch", lang="de")
    staende.waehlen(root, d)
    assert staende.pfad(root).endswith(os.path.join(d, "de"))
    assert staende.pfad(root, "de").endswith(os.path.join(d, "de"))
    with pytest.raises(staende.StandSprache):
        staende.pfad(root, "es")
    assert not os.path.exists(os.path.join(root, "staende", d, "es"))


def test_token_erkennt_wechsel(tmp_path):
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, a)
    tok = staende.token(root)
    assert staende.pruefen(root, tok)
    staende.waehlen(root, b)
    with pytest.raises(staende.StandGewechselt):
        staende.pruefen(root, tok)


def test_alte_staende_ohne_sprache_werden_aufgeteilt(tmp_path):
    """Modell vor 2026-09-17: ein Stand mit es/ und zh/ → zwei Stände, leere
    Sprachordner verschwinden, Ids bleiben stabil."""
    root = str(tmp_path)
    alt = os.path.join(root, "staende", "erster-anlauf")
    os.makedirs(alt)
    with open(os.path.join(alt, "stand.json"), "w") as f:
        json.dump({"name": "Erster Anlauf", "erstellt": "x", "zuletzt": "y"}, f)
    _alt_anlegen(alt, "es", woerter=30)
    _alt_anlegen(alt, "zh", woerter=4)
    os.makedirs(os.path.join(alt, "fr"))               # leer, nur angelegt
    with open(os.path.join(root, "aktiver_stand"), "w") as f:
        f.write("erster-anlauf\n")

    assert staende.aktiv(root) == "erster-anlauf"
    info = staende.aktiv_info(root)
    assert info["lang"] == "es" and info["level"] == 0
    assert not os.path.exists(os.path.join(alt, "fr"))
    assert not os.path.exists(os.path.join(alt, "zh"))
    zh = [s for s in staende.liste(root) if s["lang"] == "zh"]
    assert len(zh) == 1 and zh[0]["woerter"] == 4
    # idempotent
    assert staende.migrieren_sprachen(root) == []


def test_wechsel_wartet_auf_laufende_schreibfolge(tmp_path):
    """Die Sperre ist dieselbe: wer einen Stand wechselt, wartet, bis eine
    laufende Lese-Änder-Schreib-Folge fertig ist."""
    import threading, time
    root = str(tmp_path)
    a = staende.anlegen(root, "A", lang="es")
    b = staende.anlegen(root, "B", lang="es")
    staende.waehlen(root, a)
    reihenfolge = []

    def schreiber():
        with staende.stand_lock:
            reihenfolge.append("schreibe-start")
            time.sleep(0.3)
            assert staende.aktiv(root) == a          # niemand hat gewechselt
            reihenfolge.append("schreibe-ende")

    t = threading.Thread(target=schreiber); t.start()
    time.sleep(0.05)
    staende.waehlen(root, b)
    reihenfolge.append("gewechselt")
    t.join()
    assert reihenfolge == ["schreibe-start", "schreibe-ende", "gewechselt"]


# ── Level + Glosse (tools) ───────────────────────────────────────────────

def _tools_auf(tmp_path, monkeypatch):
    from tutor import memory, srs, tools
    root = str(tmp_path)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)
    return tools, root


def test_level_grundlagen_markiert_wichtige_kernwoerter(tmp_path, monkeypatch):
    tools, root = _tools_auf(tmp_path, monkeypatch)
    sid = staende.anlegen(root, "L1", lang="es", level=1)
    staende.waehlen(root, sid)
    tools.level_anwenden("es", 1)
    kern = tools._core_list("es")
    wichtig = {c["word"] for c in kern if c.get("priority") in ("critical", "high")}
    drilled = tools._drilled_words("es")
    assert wichtig and wichtig <= drilled
    assert not ({c["word"] for c in kern if c.get("priority") == "medium"} & drilled)
    assert not tools.core_graduated("es")


def test_level_verstaendigen_graduiert(tmp_path, monkeypatch):
    tools, root = _tools_auf(tmp_path, monkeypatch)
    sid = staende.anlegen(root, "L2", lang="es", level=2)
    staende.waehlen(root, sid)
    tools.level_anwenden("es", 2)
    assert tools.core_graduated("es")
    got, total = tools.core_coverage("es")
    assert got == total > 0


def test_glosse_folgt_der_muttersprache(monkeypatch):
    from tutor import tools, config
    e = {"word": "agua", "gloss": {"en": "water", "de": "Wasser"}}
    monkeypatch.setattr(config, "_overrides", {"native": "de"})
    assert tools.glosse(e) == "Wasser"
    monkeypatch.setattr(config, "_overrides", {"native": "en"})
    assert tools.glosse(e) == "water"
    monkeypatch.setattr(config, "_overrides", {"native": "zh"})   # fehlt → en
    assert tools.glosse(e) == "water"
    assert tools.glosse({"word": "x", "de": "alt"}) == "alt"        # altes Schema


def test_tools_schreiben_nie_in_fremde_sprache(tmp_path, monkeypatch):
    """Ein de-Stand ist aktiv: ein es-Zugriff über tools wirft, statt
    stillschweigend einen es-Ordner im de-Stand anzulegen."""
    tools, root = _tools_auf(tmp_path, monkeypatch)
    sid = staende.anlegen(root, "DE", lang="de")
    staende.waehlen(root, sid)
    with pytest.raises(staende.StandSprache):
        tools._dir("es")
    assert not os.path.exists(os.path.join(root, "staende", sid, "es"))
