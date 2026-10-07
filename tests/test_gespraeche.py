"""Gespräche auf der Platte (core/gespraeche.py, Claude-Web-Plan Phase 2).

Was hier bewiesen wird, ist das Versprechen an den Sync (rsync, additiv,
neueste Datei gewinnt): zwei Rechner schreiben nie in dieselbe Datei, beim
Lesen wird zusammengelegt, und nichts geht verloren — auch nicht beim
Wiederholen über Rechnergrenzen.
"""
import json
import os
import threading

import pytest

import gespraeche
import gespraech_titel


def _texte(gid):
    return [n["text"] for n in gespraeche.nachrichten(gid)]


def test_ein_gespraech_ist_ein_ordner_mit_kopf_und_datei_pro_rechner():
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "hallo", knoten="pc")
    gespraeche.anhaengen(gid, "assistant", "hi", knoten="laptop")
    ordner = os.path.join(gespraeche._DIR, gid)
    assert sorted(os.listdir(ordner)) == ["kopf.json", "laptop.jsonl", "pc.jsonl"]
    kopf = json.load(open(os.path.join(ordner, "kopf.json")))
    assert kopf["archiviert"] is False and kopf["projekt"] is None
    zeile = json.loads(open(os.path.join(ordner, "pc.jsonl")).readline())
    assert zeile["art"] == "nachricht" and zeile["knoten"] == "pc"
    assert zeile["ts"].endswith("+00:00") and "." in zeile["ts"]   # UTC, Mikrosekunden


def test_zwei_rechner_dateien_werden_nach_zeit_zusammengelegt():
    """PC und Laptop schreiben abwechselnd; jede Datei hat nur ihre Hälfte,
    gelesen wird die richtige Reihenfolge."""
    gid = gespraeche.neu()
    for i in range(6):
        gespraeche.anhaengen(gid, "user", f"n{i}", knoten="pc" if i % 2 else "laptop")
    assert _texte(gid) == [f"n{i}" for i in range(6)]
    pc = open(os.path.join(gespraeche._DIR, gid, "pc.jsonl")).read()
    assert "n1" in pc and "n0" not in pc


def test_zusammenlegen_haengt_nicht_an_der_dateireihenfolge():
    """Eine vom Sync spät angekommene Datei mit ÄLTEREN Einträgen sortiert
    sich trotzdem richtig ein."""
    gid = gespraeche.neu()
    ordner = os.path.join(gespraeche._DIR, gid)
    def zeile(ts, text, kn):
        return json.dumps({"id": text, "ts": ts, "knoten": kn, "art": "nachricht",
                           "rolle": "user", "text": text}) + "\n"
    with open(os.path.join(ordner, "aaa.jsonl"), "w") as f:
        f.write(zeile("2026-10-07T10:00:02.000000+00:00", "zwei", "aaa"))
    with open(os.path.join(ordner, "zzz.jsonl"), "w") as f:
        f.write(zeile("2026-10-07T10:00:01.000000+00:00", "eins", "zzz"))
        f.write(zeile("2026-10-07T10:00:03.000000+00:00", "drei", "zzz"))
    assert _texte(gid) == ["eins", "zwei", "drei"]


def test_gleichzeitiges_schreiben_zweier_rechner_verliert_nichts():
    gid = gespraeche.neu()
    n = 200

    def schreiber(kn):
        for i in range(n):
            gespraeche.anhaengen(gid, "user", f"{kn}-{i}", knoten=kn)

    t = [threading.Thread(target=schreiber, args=(kn,)) for kn in ("pc", "laptop")]
    for x in t:
        x.start()
    for x in t:
        x.join()
    texte = _texte(gid)
    assert len(texte) == 2 * n
    for kn in ("pc", "laptop"):
        eigene = [x for x in texte if x.startswith(kn + "-")]
        assert eigene == [f"{kn}-{i}" for i in range(n)]       # Reihenfolge je Rechner


def test_halbe_zeile_nach_absturz_wird_uebersprungen():
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "ganz", knoten="pc")
    with open(os.path.join(gespraeche._DIR, gid, "pc.jsonl"), "a") as f:
        f.write('{"id": "x", "ts": "2026')
    assert _texte(gid) == ["ganz"]


def test_verwerfen_ab_ueber_rechnergrenzen():
    """Der Laptop verwirft ab einer Nachricht, die der PC geschrieben hat —
    auch die späteren PC-Nachrichten zählen dann nicht mehr; was NACH dem
    Verwerfen kommt, zählt wieder."""
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "frage 1", knoten="pc")
    gespraeche.anhaengen(gid, "assistant", "antwort 1", knoten="pc")
    f2 = gespraeche.anhaengen(gid, "user", "frage 2", knoten="pc")
    gespraeche.anhaengen(gid, "assistant", "schlechte antwort", knoten="pc")
    gespraeche.verwerfen_ab(gid, f2["id"], knoten="laptop")
    gespraeche.anhaengen(gid, "user", "frage 2 besser", knoten="laptop")
    assert _texte(gid) == ["frage 1", "antwort 1", "frage 2 besser"]
    # Nichts ist gelöscht: alle Zeilen stehen noch in den Dateien.
    pc = open(os.path.join(gespraeche._DIR, gid, "pc.jsonl")).read()
    assert "schlechte antwort" in pc


def test_verwerfen_einer_unbekannten_nachricht_ist_ein_fehler():
    gid = gespraeche.neu()
    with pytest.raises(gespraeche.Unbekannt):
        gespraeche.verwerfen_ab(gid, "gibts-nicht")


def test_archivieren_statt_loeschen():
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "bleib")
    gespraeche.archivieren(gid)
    assert gid not in [g["id"] for g in gespraeche.liste()]
    assert gid in [g["id"] for g in gespraeche.liste(archivierte=True)]
    assert _texte(gid) == ["bleib"]                 # Inhalt unverändert da
    gespraeche.archivieren(gid, an=False)
    assert gid in [g["id"] for g in gespraeche.liste()]
    assert not hasattr(gespraeche, "loeschen")


def test_liste_neueste_zuerst_erinnerungen_immer_oben():
    a = gespraeche.neu("alt")
    gespraeche.anhaengen(a, "user", "x")
    gespraeche.erinnerungen()
    gespraeche.anhaengen(gespraeche.ERINNERUNGEN, "assistant", "termin!")
    b = gespraeche.neu("neu")
    gespraeche.anhaengen(b, "user", "y")
    gespraeche.anhaengen(a, "user", "jetzt wieder aktiv")
    ids = [g["id"] for g in gespraeche.liste()]
    assert ids == [gespraeche.ERINNERUNGEN, a, b]


def test_leere_gespraeche_fehlen_in_der_liste():
    gespraeche.neu("leer")
    assert gespraeche.liste() == []


def test_ungelesen_bis_gelesen():
    gid = gespraeche.neu("x")
    gespraeche.anhaengen(gid, "user", "frage")
    assert gespraeche.liste()[0]["ungelesen"] is False      # eigene Frage
    gespraeche.anhaengen(gid, "assistant", "antwort")
    assert gespraeche.liste()[0]["ungelesen"] is True
    gespraeche.gelesen_setzen(gid)
    assert gespraeche.liste()[0]["ungelesen"] is False


def test_aktiv_ist_pro_rechner(monkeypatch):
    a, b = gespraeche.neu("a"), gespraeche.neu("b")
    monkeypatch.setattr(gespraeche, "knoten", lambda: "pc")
    gespraeche.aktiv_setzen(a)
    monkeypatch.setattr(gespraeche, "knoten", lambda: "laptop")
    assert gespraeche.aktiv() is None
    gespraeche.aktiv_setzen(b)
    monkeypatch.setattr(gespraeche, "knoten", lambda: "pc")
    assert gespraeche.aktiv() == a
    gespraeche.aktiv_setzen(None)
    assert gespraeche.aktiv() is None


def test_aktiv_setzen_auf_unbekanntes_gespraech():
    with pytest.raises(gespraeche.Unbekannt):
        gespraeche.aktiv_setzen("gibts-nicht")


def test_ungueltige_ids_kommen_nicht_aus_dem_ordner():
    for gid in ("../x", "_knoten", "", ".", "a/b"):
        assert not gespraeche.gibt_es(gid)
        with pytest.raises(gespraeche.Unbekannt):
            gespraeche.nachrichten(gid)


def test_verlauf_fuer_ki_fenster_vermerk_und_auftrag():
    gid = gespraeche.neu()
    for i in range(60):
        gespraeche.anhaengen(gid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    v = gespraeche.verlauf_fuer_ki(gid)
    assert len(v) == gespraeche.FENSTER == 50
    assert v[-1] == {"role": "assistant", "content": "m59"}
    g2 = gespraeche.neu()
    gespraeche.anhaengen(g2, "user", "tu was", versteckt=True)
    gespraeche.anhaengen(g2, "assistant", "halb", abgebrochen=True)
    assert gespraeche.verlauf_fuer_ki(g2) == [
        {"role": "user", "content": gespraeche.AUFTRAG_VORSATZ + "tu was"},
        {"role": "assistant", "content": "halb\n\n(abgebrochen)"}]
    assert [n["text"] for n in gespraeche.nachrichten(g2)] == ["halb"]


def test_denken_wird_gekappt_und_das_ende_bleibt():
    gid = gespraeche.neu()
    lang = "a" * 30000 + "SCHLUSS"
    n = gespraeche.anhaengen(gid, "assistant", "x", denken=lang)
    assert len(n["denken"]) == gespraeche.DENKEN_GRENZE
    assert n["denken"].endswith("SCHLUSS")


def test_automatischer_titel_ueberschreibt_keinen_von_hand():
    gid = gespraeche.neu()
    assert gespraeche.umbenennen(gid, "Mein Titel")
    assert gespraeche.umbenennen(gid, "Automatisch", von="modell") is False
    assert gespraeche.kopf(gid)["titel"] == "Mein Titel"


# ── Titel ───────────────────────────────────────────────────────────────

def test_titel_ohne_cloud_sind_die_ersten_woerter():
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "wie flicke ich am besten einen fahrradschlauch unterwegs")
    t = gespraech_titel.im_hintergrund(gid, "wie flicke ich am besten einen "
                                       "fahrradschlauch unterwegs", "so", cloud=False)
    t.join(5)
    assert gespraeche.kopf(gid)["titel"] == "wie flicke ich am besten einen …"


def test_titel_bei_fehler_der_cloud_faellt_auf_woerter_zurueck(monkeypatch):
    import billig

    def kaputt(*a, **k):
        raise RuntimeError("kein netz")
    monkeypatch.setattr(billig, "einmal", kaputt)
    gid = gespraeche.neu()
    t = gespraech_titel.im_hintergrund(gid, "kurze frage", "antwort", cloud=True)
    t.join(5)
    assert gespraeche.kopf(gid)["titel"] == "kurze frage"


def test_titel_vom_billigen_modell(monkeypatch):
    import billig
    gefragt = {}

    def einmal(system, nachricht, **k):
        gefragt.update(k, nachricht=nachricht)
        return '"Fahrradschlauch flicken unterwegs."\nweiterer text', "billig-1"
    monkeypatch.setattr(billig, "einmal", einmal)
    gid = gespraeche.neu()
    gespraech_titel.erster_titel(gid, "wie flicke ich den schlauch")
    assert gespraech_titel.braucht_modell(gid)
    gespraech_titel.im_hintergrund(gid, "wie flicke ich den schlauch", "so", cloud=True).join(5)
    assert gespraeche.kopf(gid)["titel"] == "Fahrradschlauch flicken unterwegs"
    assert "wie flicke ich den schlauch" in gefragt["nachricht"]
    assert not gespraech_titel.braucht_modell(gid)


def test_billig_bucht_die_kosten(monkeypatch):
    """Der Einmal-Aufruf läuft durch usage.buchen — auch der Titel kostet
    Geld, und was man nicht sieht, kann man nicht deckeln."""
    import sys
    import ai_backends
    import billig
    import usage

    class Antwort:
        content = [type("B", (), {"type": "text", "text": "Kurzer Titel"})()]
        usage = type("U", (), {"input_tokens": 50, "output_tokens": 5})()

    class Fake:
        def __init__(self, *a, **k):
            self.messages = type("M", (), {"create": lambda _s, **kw: Antwort()})()

    modul = type(sys)("anthropic")
    modul.Anthropic = Fake
    monkeypatch.setitem(sys.modules, "anthropic", modul)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "claude")
    gebucht = {}
    monkeypatch.setattr(usage, "buchen",
                        lambda m, **k: gebucht.update(k, modell=m) or 0.0001)
    text, mdl = billig.einmal("sys", "hallo")
    assert text == "Kurzer Titel"
    assert gebucht["modell"] == mdl and gebucht["input_tokens"] == 50
