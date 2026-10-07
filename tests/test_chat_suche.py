"""Suche quer durch die Gespräche: search_chats und read_chat (Phase 3 des
Claude-Web-Plans, 2026-10-07, core/chat_suche.py).

Sasha: „mein kopf kann sich thematisch viel besser orientieren als datiert.
solang der assistant eh einfach crossgespräche suchen kann wie claude web."

Geprüft wird Verhalten:
  - findet über Gespräche (auch archivierte) und das alte Transkript,
  - liefert kein Denken und keine versteckten Erinnerungs-Aufträge,
  - Umlaut-/ß-Varianten, Groß/klein, Teilwörter; alle Wörter müssen vorkommen,
  - Rang nach Dichte und Aktualität, höchstens MAX_TREFFER,
  - das laufende Fenster des offenen Gesprächs kommt nicht doppelt,
  - leere Anfrage / nichts gefunden / unbekannte id,
  - read_chat: die letzten N, oder um die Fundstelle,
  - die Werkzeuge: nur gross, ungegatet, klein unverändert.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import chat_suche
import gespraeche
import ki_werkzeuge
import transkript
import werkzeug_register
from profil import gross, klein


@pytest.fixture(autouse=True)
def eigenes_transkript(tmp_path, monkeypatch):
    monkeypatch.setattr(transkript, "_DIR", str(tmp_path / "ai_transcripts"))


def _gespraech(titel, *paare, archiviert=False):
    gid = gespraeche.neu(titel)
    for rolle, text in paare:
        gespraeche.anhaengen(gid, rolle, text)
    if archiviert:
        gespraeche.archivieren(gid)
    return gid


def _alt(gid, rolle, text, tage):
    """Eine Nachricht mit altem Zeitstempel direkt in die Rechner-Datei."""
    ts = (datetime.now(timezone.utc) - timedelta(days=tage)).isoformat(timespec="microseconds")
    pfad = os.path.join(gespraeche._DIR, gid, "alt.jsonl")
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": os.urandom(6).hex(), "ts": ts, "knoten": "alt",
                            "art": "nachricht", "rolle": rolle, "text": text},
                           ensure_ascii=False) + "\n")
    gespraeche._cache.clear()


def _transkript(*zeilen, datei="2026-08.jsonl"):
    os.makedirs(transkript._DIR, exist_ok=True)
    with open(os.path.join(transkript._DIR, datei), "a", encoding="utf-8") as f:
        for i, (zeit, user, ai) in enumerate(zeilen, 1):
            f.write(json.dumps({"id": f"x:{i}", "zeit": zeit, "user": user, "ai": ai},
                               ensure_ascii=False) + "\n")


# ── Finden ─────────────────────────────────────────────────────────────

def test_findet_in_gespraechen_mit_titel_id_und_ausschnitt():
    gid = _gespraech("Fahrrad", ("user", "Der Schlauch am Hinterrad ist platt."),
                     ("assistant", "Flickzeug und Reifenheber reichen."))
    _gespraech("Kochen", ("user", "Was koche ich heute?"))
    treffer = chat_suche.suchen("schlauch")
    assert [t["id"] for t in treffer] == [gid]
    assert treffer[0]["titel"] == "Fahrrad"
    assert "Schlauch am Hinterrad" in treffer[0]["ausschnitt"]
    assert treffer[0]["rolle"] == "user"
    text = chat_suche.suchen_text("schlauch")
    assert gid in text and "Fahrrad" in text and "Sasha:" in text


def test_findet_auch_archivierte_gespraeche():
    gid = _gespraech("Alter Umzug", ("user", "Kartons für den Umzug"), archiviert=True)
    treffer = chat_suche.suchen("kartons")
    assert treffer and treffer[0]["id"] == gid and treffer[0]["archiviert"]
    assert "archiviert" in chat_suche.suchen_text("kartons")


def test_findet_im_alten_transkript_nach_tag():
    _transkript(("2026-08-17T10:00:00", "Wann ist Geige?", "Geigenstunde um 17:45."),
                ("2026-08-17T11:00:00", "danke", "Gern."),
                ("2026-08-20T09:00:00", "Wetter?", "Sonnig."))
    treffer = chat_suche.suchen("geige")
    assert [t["id"] for t in treffer] == ["transkript:2026-08-17"]
    assert "17.08.2026" in treffer[0]["titel"]
    # Lokal- und Cloud-Datei desselben Tages sind EIN Treffer.
    _transkript(("2026-08-17T12:00:00", "Geige morgen?", "Ja."), datei="cloud-2026-08.jsonl")
    assert [t["id"] for t in chat_suche.suchen("geige")] == ["transkript:2026-08-17"]


def test_alle_woerter_muessen_vorkommen_auch_ueber_zwei_nachrichten():
    a = _gespraech("A", ("user", "Die Geige muss zur Reparatur."),
                   ("assistant", "In den Herbstferien hat die Werkstatt zu."))
    _gespraech("B", ("user", "Geige üben."))
    assert [t["id"] for t in chat_suche.suchen("geige ferien")] == [a]


def test_umlaute_ss_und_gross_klein_sind_egal():
    gid = _gespraech("Weg", ("user", "Die Straße zur Übungshalle ist gesperrt."))
    for anfrage in ("strasse", "STRASSE", "Straße", "uebungshalle", "übung", "UEBUNG"):
        assert [t["id"] for t in chat_suche.suchen(anfrage)] == [gid], anfrage
    gid2 = _gespraech("Café", ("user", "Im Café am Eck."))
    assert [t["id"] for t in chat_suche.suchen("cafe")] == [gid2]


def test_fuellwoerter_stoeren_nicht():
    gid = _gespraech("Umzug", ("user", "Der Umzug ist im November."))
    assert [t["id"] for t in chat_suche.suchen("das mit dem umzug")] == [gid]


# ── Was NICHT geliefert wird ───────────────────────────────────────────

def test_denken_wird_nicht_durchsucht():
    gid = gespraeche.neu("Denken")
    gespraeche.anhaengen(gid, "user", "Hallo")
    gespraeche.anhaengen(gid, "assistant", "Hi.", denken="Geheimwort Zebrastreifen")
    assert chat_suche.suchen("zebrastreifen") == []
    assert "Zebrastreifen" not in chat_suche.lesen_text(gid)


def test_versteckte_auftraege_werden_nicht_geliefert():
    gid = gespraeche.erinnerungen()
    gespraeche.anhaengen(gid, "user", "Erinnere Sasha kurz an die Fahrschule", versteckt=True)
    gespraeche.anhaengen(gid, "assistant", "Fahrschule um 19:00.")
    treffer = chat_suche.suchen("fahrschule")
    assert treffer and treffer[0]["id"] == gid and treffer[0]["rolle"] == "assistant"
    assert chat_suche.suchen("erinnere") == []
    assert "Erinnere Sasha" not in chat_suche.lesen_text(gid)
    # Im alten Transkript fehlt das Flag — dort am Wortlaut erkannt.
    _transkript(("2026-09-01T18:00:00", "Erinnere Sasha kurz daran, dass Geige "
                 "um 17:45 anfaengt", "Geige gleich."))
    assert chat_suche.suchen("anfaengt") == []
    assert chat_suche.suchen("geige")[0]["rolle"] == "assistant"


def test_was_es_als_gespraech_gibt_kommt_aus_dem_transkript_nicht_doppelt():
    gid = _gespraech("Rad", ("user", "Kette quietscht"), ("assistant", "Kette ölen hilft."))
    _transkript(("2026-10-07T10:00:00", "Kette quietscht", "Kette ölen hilft."))
    assert [t["id"] for t in chat_suche.suchen("kette")] == [gid]


def test_das_laufende_fenster_kommt_nicht_doppelt(monkeypatch):
    monkeypatch.setattr(gespraeche, "FENSTER", 2)
    gid = _gespraech("Lang", ("user", "Alte Frage zum Zaun"), ("assistant", "Alte Antwort"),
                     ("user", "Neue Frage zum Tor"), ("assistant", "Neue Antwort"))
    # Offen: das Fenster (Tor) hat die KI schon, das Ältere (Zaun) nicht.
    assert chat_suche.suchen("tor", aktiv=gid) == []
    assert [t["id"] for t in chat_suche.suchen("zaun", aktiv=gid)] == [gid]
    # Ein anderes Gespräch ist offen: alles zählt.
    assert [t["id"] for t in chat_suche.suchen("tor", aktiv="anderes")] == [gid]


def test_das_werkzeug_nimmt_das_aktive_gespraech(monkeypatch):
    gid = _gespraech("Offen", ("user", "Bananenbrot backen"))
    gespraeche.aktiv_setzen(gid)
    ergebnis = ki_werkzeuge.ausfuehren("search_chats", {"query": "bananenbrot"})
    assert ergebnis.startswith("Nichts gefunden")
    gespraeche.aktiv_setzen(None)
    assert gid in ki_werkzeuge.ausfuehren("search_chats", {"query": "bananenbrot"})


# ── Rang und Grenzen ───────────────────────────────────────────────────

def test_rang_neu_vor_alt_bei_gleicher_dichte():
    alt = gespraeche.neu("Alt")
    _alt(alt, "user", "Zelt kaufen", tage=200)
    neu = _gespraech("Neu", ("user", "Zelt kaufen"))
    assert [t["id"] for t in chat_suche.suchen("zelt")] == [neu, alt]


def test_rang_dichte_schlaegt_wenig_alter():
    selten = _gespraech("Selten", ("user", "Zelt " + "und anderes Zeug " * 40))
    dicht = gespraeche.neu("Dicht")
    _alt(dicht, "user", "Zelt Zelt Zelt: welches Zelt?", tage=3)
    assert [t["id"] for t in chat_suche.suchen("zelt")] == [dicht, selten]


def test_hoechstens_max_treffer():
    for i in range(chat_suche.MAX_TREFFER + 4):
        _gespraech(f"G{i}", ("user", f"Kaktus Nummer {i}"))
    treffer = chat_suche.suchen("kaktus")
    assert len(treffer) == chat_suche.MAX_TREFFER
    text = chat_suche.suchen_text("kaktus")
    assert text.count("\n") <= 2 * chat_suche.MAX_TREFFER + 1


def test_ausschnitt_ist_kurz_und_um_die_fundstelle():
    lang = "Vorrede " * 80 + "hier steht das Fundwort Quokka mitten drin " + "Nachrede " * 80
    _gespraech("Lang", ("user", lang))
    a = chat_suche.suchen("quokka")[0]["ausschnitt"]
    assert "Quokka" in a and len(a) <= chat_suche.AUSSCHNITT + 2
    assert a.startswith("…") and a.endswith("…")


def test_leere_anfrage_und_nichts_gefunden():
    _gespraech("X", ("user", "irgendwas"))
    assert chat_suche.suchen("") == []
    assert chat_suche.suchen_text("   ").startswith("[Fehler")
    assert chat_suche.suchen_text("gibtsnicht").startswith("Nichts gefunden")


def test_ohne_gespraeche_und_transkript_geht_es_auch():
    assert chat_suche.suchen("egal") == []


def test_kaputte_transkript_zeilen_werden_uebersprungen():
    os.makedirs(transkript._DIR, exist_ok=True)
    with open(os.path.join(transkript._DIR, "2026-09.jsonl"), "w", encoding="utf-8") as f:
        f.write("{halb\n")
        f.write(json.dumps({"id": "2026-09:2", "zeit": "kaputt", "user": "Mango", "ai": ""}) + "\n")
        f.write(json.dumps({"id": "2026-09:3", "zeit": "2026-09-02T10:00:00",
                            "user": "Mango kaufen", "ai": "Ok."}) + "\n")
    assert [t["id"] for t in chat_suche.suchen("mango")] == ["transkript:2026-09-02"]


# ── read_chat ──────────────────────────────────────────────────────────

def test_read_chat_letzte_n_und_um_die_fundstelle():
    gid = gespraeche.neu("Viele")
    for i in range(50):
        gespraeche.anhaengen(gid, "user" if i % 2 == 0 else "assistant",
                             "Satz %d" % i + (" mit Pinguin" if i == 4 else ""))
    letzte = chat_suche.lesen_text(gid, anzahl=3)
    assert "Satz 49" in letzte and "Satz 46" not in letzte and "48–50 von 50" in letzte
    um = chat_suche.lesen_text(gid, anfrage="pinguin", anzahl=5)
    assert "Pinguin" in um and "Satz 49" not in um
    assert chat_suche.lesen_text(gid, anzahl=999).count("\n") == chat_suche.LESEN_MAX


def test_read_chat_kuerzt_lange_nachrichten_und_liest_transkript_tage():
    gid = _gespraech("Lang", ("assistant", "x" * 5000))
    assert len(chat_suche.lesen_text(gid)) < chat_suche.LESEN_NACHRICHT + 200
    _transkript(("2026-08-17T10:00:00", "Hallo", "Servus"))
    text = chat_suche.lesen_text("transkript:2026-08-17")
    assert "Sasha: Hallo" in text and "KI: Servus" in text


def test_read_chat_unbekannte_id():
    for eid in ("gibtsnicht", "", "../etc", "transkript:1999-01-01"):
        assert chat_suche.lesen_text(eid).startswith("[Kein Gespräch"), eid


# ── Die Werkzeuge im Register ──────────────────────────────────────────

def test_werkzeuge_nur_gross_und_frei():
    for name in ("search_chats", "read_chat"):
        w = werkzeug_register.eintrag(name)
        assert w.klein is None and w.gross
        assert not werkzeug_register.braucht_erlaubnis(name, {"query": "x", "id": "y"})
        assert name in {t["function"]["name"] for t in gross.TOOLS}
        assert name not in {t["function"]["name"] for t in klein.TOOLS}


def test_werkzeuge_laufen_ueber_den_ausfuehrer():
    gid = _gespraech("Rad", ("user", "Speichen nachziehen"))
    assert gid in ki_werkzeuge.ausfuehren("search_chats", {"query": "speichen"})
    assert "Speichen" in ki_werkzeuge.ausfuehren("read_chat", {"id": gid})
    assert "Speichen" in ki_werkzeuge.ausfuehren("read_chat",
                                                 {"id": gid, "query": "speichen", "anzahl": "x"})


def test_meta_regel_nennt_search_chats():
    assert "search_chats" in gross.system()
    assert "search_chats" not in klein.CAPABILITIES
