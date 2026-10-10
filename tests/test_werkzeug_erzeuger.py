"""Der Werkzeug-Erzeuger, unabhängig vom Kalender (core/werkzeug_erzeuger/).

2026-10-10, Sasha: „ki harness wird aus den feldern GEBAUT". Geprüft an
einer erfundenen Quelle (eine Einkaufsliste im Speicher), was JEDE Quelle
bekommt: Pflichtfelder und Auswahl aus dem Schema (Abbruch mit Code, bevor
etwas geschrieben wird), die Ja/Nein-Frage aus den Feldern, Nachlesen nach
dem Schreiben, Zurücknehmen bei Abweichung (ganz oder gar nicht), die feste
Satzform mit Kennung, nur Lesen für eine Quelle ohne Nachlesen, Zuschnitt
für schwache Modelle.
"""
import copy

import pytest

import werkzeug_erzeuger as wz
from werkzeug_erzeuger import Ablehnung, Ergebnis


def _aktion(name, art, felder, pflicht=(), **x):
    return {"name": name, "description": f"{name} tut etwas.",
            "inputSchema": {"type": "object", "properties": felder, "required": list(pflicht)},
            "x-zentrale": {"art": art, **x}}


AKTIONEN = [
    _aktion("add_item", "anlegen", {
        "titel": {"type": "string", "description": "Was.",
                  "x-zentrale": {"wort": "Titel", "fehlt": "TITEL-LEER"}},
        "menge": {"type": "integer", "description": "Wie viel.", "x-zentrale": {"wort": "Menge"}},
        "laden": {"type": "string", "enum": ["rewe", "edeka"], "description": "Wo.",
                  "x-zentrale": {"wort": "Laden", "schwach": False}},
    }, pflicht=("titel",), frage="auf die Liste setzen", worte=["gekauft", "kaufen"],
        einfach="Setzt etwas auf die Liste."),
    _aktion("edit_item", "aendern", {
        "kennung": {"type": "string", "description": "Kennung.", "x-zentrale": {"ziel": True}},
        "menge": {"type": "integer", "description": "Neue Menge.", "x-zentrale": {"wort": "Menge"}},
    }, pflicht=("kennung", "menge"), frage="ändern"),
    _aktion("del_item", "loeschen", {
        "kennung": {"type": "string", "description": "Kennung.", "x-zentrale": {"ziel": True}},
    }, pflicht=("kennung",), frage="löschen"),
    _aktion("list_items", "lesen", {}),
]


class Liste:
    """Die erfundene Quelle: ein Dict im Speicher, Kennungen i1, i2 …"""

    def __init__(self, nachlesen=True):
        self.daten, self.n = {}, 0
        self.verfaelschen = None
        if not nachlesen:
            self.nachlesen = None

    def ausfuehren(self, name, args):
        if name == "list_items":
            return Ergebnis(text=", ".join(e["titel"] for e in self.daten.values()) or "leer")
        if name == "add_item":
            if args["titel"] == "verboten":
                raise Ablehnung("VERBOTEN", "das darf nicht auf die Liste")
            self.n += 1
            k = f"i{self.n}"
            self.daten[k] = {"titel": args["titel"], "menge": args.get("menge", 1)}
            return Ergebnis(kennung=k, verlangt={"titel": args["titel"]},
                            nachsatz=lambda e: f", Menge {e['menge']}")
        if name == "edit_item":
            k = args["kennung"]
            if k not in self.daten:
                raise Ablehnung("KENNUNG-UNBEKANNT", f"{k} gibt es nicht")
            vorher = dict(self.daten[k])
            self.daten[k]["menge"] = args["menge"]
            return Ergebnis(kennung=k, verlangt={"menge": args["menge"]}, vorher=vorher)
        if name == "del_item":
            vorher = self.daten.pop(args["kennung"])
            return Ergebnis(kennung=args["kennung"], vorher=vorher)
        raise AssertionError(name)

    def nachlesen(self, k):
        e = self.daten.get(k)
        if e is None:
            return None
        e = dict(e)
        if self.verfaelschen:
            e.update(self.verfaelschen)
        return e

    def loeschen(self, k):
        self.daten.pop(k, None)

    def wiederherstellen(self, k, vorher):
        self.daten[k] = dict(vorher)

    def beschreiben(self, e):
        return f"Eintrag „{e.get('titel')}“"

    def ziel(self, k):
        e = self.daten.get(k.lstrip("#"))
        return f"„{e['titel']}“" if e else f"#{k} (gibt es nicht)"


@pytest.fixture
def quelle():
    return wz.Quelle(name="liste", praefix="X", bereich="liste", aktionen=AKTIONEN,
                     adapter=Liste())


def _w(quelle, name):
    return {w.name: w for w in wz.werkzeuge(quelle)}[name]


def test_eintraege_sind_nur_gross_und_schreibendes_wird_gefragt(quelle):
    ws = wz.werkzeuge(quelle)
    assert [w.name for w in ws] == ["add_item", "edit_item", "del_item", "list_items"]
    for w in ws:
        assert w.klein is None and w.gross and w.erzeugt == "liste" and w.bereich == "liste"
        assert "x-zentrale" not in str(w.parameter)          # das Modell sieht reines JSON Schema
    add, lesen = ws[0], ws[3]
    assert add.erlaubnis is True and add.schreibt and add.immer_erlaubbar
    assert ws[1].immer_erlaubbar is False and ws[2].immer_erlaubbar is False
    assert lesen.erlaubnis is False and not lesen.schreibt
    assert add.worte == ("gekauft", "kaufen")
    # Prompt-Cache: dieselben Bytes bei jedem Bau
    assert [w.parameter for w in wz.werkzeuge(quelle)] == [w.parameter for w in ws]


def test_feste_satzform_mit_kennung_aus_dem_nachgelesenen(quelle):
    r = _w(quelle, "add_item").ausfuehrer({"titel": "Milch", "menge": 2})
    assert r == "Eintrag „Milch“ EINGETRAGEN (#i1), Menge 2." and r.status == "ok"
    assert r.beleg == r
    r = _w(quelle, "edit_item").ausfuehrer({"kennung": "i1", "menge": 3})
    assert r.startswith("Eintrag „Milch“ GEÄNDERT (#i1)")
    r = _w(quelle, "del_item").ausfuehrer({"kennung": "i1"})
    assert r == "Eintrag „Milch“ GELÖSCHT." and quelle.adapter.daten == {}


@pytest.mark.parametrize("args, code", [
    ({}, "X-TITEL-LEER"),
    ({"titel": "   "}, "X-TITEL-LEER"),
    ({"titel": "Milch", "laden": "aldi"}, "X-WERT-UNGUELTIG"),
    ({"titel": "Milch", "menge": "zwei"}, "X-WERT-UNGUELTIG"),
    ({"titel": "Milch", "farbe": "weiß"}, "X-UNBEKANNTES-FELD"),
    ({"titel": "verboten"}, "X-VERBOTEN"),
])
def test_abbruch_mit_code_vor_dem_schreiben(quelle, args, code):
    r = _w(quelle, "add_item").ausfuehrer(args)
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert "ABGEBROCHEN – nichts eingetragen. Fehler " + code in r
    assert quelle.adapter.daten == {}


def test_auswahl_ohne_gross_klein(quelle):
    r = _w(quelle, "add_item").ausfuehrer({"titel": "Milch", "laden": " REWE "})
    assert r.status == "ok"


def test_anders_nachgelesen_wird_zurueckgenommen(quelle):
    a = quelle.adapter
    a.verfaelschen = {"titel": "Hafermilch"}
    r = _w(quelle, "add_item").ausfuehrer({"titel": "Milch"})
    assert r.code == "W-NICHT-GESPEICHERT" and "wieder gelöscht" in r and "titel" in r
    assert a.daten == {}
    a.verfaelschen = None
    _w(quelle, "add_item").ausfuehrer({"titel": "Brot", "menge": 1})
    vorher = copy.deepcopy(a.daten)
    a.verfaelschen = {"menge": 99}
    r = _w(quelle, "edit_item").ausfuehrer({"kennung": "i2", "menge": 5})
    assert r.code == "W-NICHT-GESPEICHERT" and "wiederhergestellt" in r
    assert a.daten == vorher


def test_zuruecknehmen_das_scheitert_sagt_nicht_belegt(quelle, monkeypatch):
    a = quelle.adapter
    a.verfaelschen = {"titel": "falsch"}
    monkeypatch.setattr(a, "loeschen", lambda k: (_ for _ in ()).throw(OSError("Platte voll")))
    r = _w(quelle, "add_item").ausfuehrer({"titel": "Milch"})
    assert r.status == "fehlgeschlagen" and "NICHT belegt" in r and "Platte voll" in r


def test_loeschen_das_nachgelesen_noch_dasteht_ist_kein_erfolg(quelle, monkeypatch):
    _w(quelle, "add_item").ausfuehrer({"titel": "Milch"})
    monkeypatch.setattr(quelle.adapter, "ausfuehren",
                        lambda name, args: Ergebnis(kennung="i1", vorher={"titel": "Milch"}))
    r = _w(quelle, "del_item").ausfuehrer({"kennung": "i1"})
    assert r.code == "W-NICHT-GESPEICHERT" and "noch da" in r


def test_frage_aus_den_feldern(quelle):
    _w(quelle, "add_item").ausfuehrer({"titel": "Milch"})
    f = _w(quelle, "add_item").frage({"titel": "Brot", "menge": 2, "laden": ""})
    assert f == "Soll ich auf die Liste setzen: Titel Brot, Menge 2?"
    f = _w(quelle, "edit_item").frage({"kennung": "i1", "menge": 4})
    assert f == "Soll ich ändern „Milch“: Menge 4?"
    assert "gibt es nicht" in _w(quelle, "del_item").frage({"kennung": "i9"})


def test_eigene_frage_des_adapters_geht_vor(quelle):
    quelle.adapter.frage = lambda name, args: "Wirklich?" if name == "del_item" else None
    assert _w(quelle, "del_item").frage({"kennung": "i1"}) == "Wirklich?"
    assert _w(quelle, "edit_item").frage({"kennung": "i1", "menge": 1}).startswith("Soll ich")


def test_lesen_gibt_den_text_ohne_gate(quelle):
    w = _w(quelle, "list_items")
    assert w.ausfuehrer({}) == "leer"


def test_quelle_ohne_nachlesen_bekommt_nur_lesen():
    q = wz.Quelle(name="fremd", praefix="X", bereich="liste", aktionen=AKTIONEN,
                  adapter=Liste(nachlesen=False))
    assert [w.name for w in wz.werkzeuge(q)] == ["list_items"]


def test_kaputtes_schema_faellt_beim_erzeugen_auf():
    kaputt = _aktion("x", "anlegen", {"a": {"type": "string", "x-zentrale": {"schwach": False}}},
                     pflicht=("a",))
    with pytest.raises(wz.SchemaFehler):
        wz.werkzeuge(wz.Quelle("q", "X", "liste", [kaputt], Liste()))
    with pytest.raises(wz.SchemaFehler):
        wz.werkzeuge(wz.Quelle("q", "X", "liste", [_aktion("y", "basteln", {})], Liste()))


def test_mcp_hinweise_ohne_x_zentrale():
    from werkzeug_erzeuger import schema
    assert schema.art({"annotations": {"readOnlyHint": True}}) == "lesen"
    assert schema.art({"annotations": {"destructiveHint": True}}) == "loeschen"


def test_zuschnitt_fuer_schwache_modelle(quelle):
    ws = wz.werkzeuge(quelle)
    nach = {w.name: w for w in ws}
    tools = [{"type": "function", "function": {"name": w.name, "description": w.gross,
                                               "parameters": copy.deepcopy(w.parameter)}}
             for w in ws]
    neu = wz.zuschneiden(tools, "schwach", nach.get)
    add = neu[0]["function"]
    assert "laden" not in add["parameters"]["properties"]
    assert add["description"] == "Setzt etwas auf die Liste."
    assert "laden" in tools[0]["function"]["parameters"]["properties"]   # Kopie
    assert neu[1] == tools[1]
