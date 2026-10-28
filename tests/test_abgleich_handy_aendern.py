"""Termine vom Handy ändern, Vorkommen aus/an, Ebene wechseln, löschen
(core/abgleich_vorschlaege.py, memory/betrieb/abgleich_fremde_knoten.md
„Termine vom Handy“) — und: eine wieder angewählte App, dann gilt die Mitte
(core/abgleich.py, memory/betrieb/abgleich.md „Grundsatz“).

Grundsatz (Sasha, 28.10.2026): die Cloud wird nie überschrieben. Ein
Widerspruch wird abgelehnt, beide Fassungen bleiben, ein Hinweis zeigt es.
Feste Daten, nie „heute“ (memory/betrieb/tests.md Regel 8)."""
import hashlib

import pytest
from icalendar import Calendar

import abgleich
import abgleich_apps
import abgleich_vorschlaege as vs
import adapter
import kalender_ics_abbildung as abb
from test_abgleich import LISTE, Welt  # noqa: F401
from test_abgleich_handy import Handy, _termin, kalender_welt  # noqa: F401

UID = "a" * 32 + "@zentrale"
REL = f"data/kalender/termine/{UID}.ics"
GOOGLE = "data/kalender/termine/abc.ics"


@pytest.fixture
def welt(tmp_path, monkeypatch):
    return Welt(tmp_path, monkeypatch)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _ersetzen(roh: bytes, alt: str, neu: str) -> bytes:
    assert alt.encode() in roh, alt
    return roh.replace(alt.encode(), neu.encode(), 1)


def _routine(uid, aus=()):
    kal = abb.routine_kalender({"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU",
                                "time": "17:00", "ende": "18:00", "seit": "2026-11-03",
                                "aus": list(aus)}, uid)
    return abb.zusammenfuehren(None, kal, uid)


def _daten(roh):
    return abb.datei_lesen(roh)[0]["daten"]


# ── Ändern ohne Widerspruch ────────────────────────────────────────────

def test_aendern_ohne_widerspruch_behaelt_was_das_handy_nicht_kennt(kalender_welt):
    welt = kalender_welt
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    # In der Mitte steht eine Notiz und eine fremde Erinnerung (Google).
    roh = laptop.pfad(f"kalender/termine/{UID}.ics").read_bytes()
    roh = _ersetzen(roh, "END:VEVENT", "DESCRIPTION:Noten mitbringen\r\nBEGIN:VALARM\r\n"
                    "ACTION:DISPLAY\r\nDESCRIPTION:gleich\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT")
    laptop.pfad(f"kalender/termine/{UID}.ics").write_bytes(roh)
    laptop.abgleichen()
    pc.abgleichen()
    h = Handy(welt)
    basis = h.lesen(REL)
    # Das Handy benennt um und verliert beim Lesen Notiz und Erinnerung.
    neu = _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Handy umbenannt")
    neu = _ersetzen(neu, "DESCRIPTION:Noten mitbringen\r\n", "")
    kal = Calendar.from_ical(neu)
    for ev in kal.walk("VEVENT"):
        ev.subcomponents.clear()
    h.schreiben(REL, kal.to_ical(), basis_sha=_sha(basis))
    b = laptop.abgleichen()
    assert not b.hinweise
    jetzt = laptop.lesen(f"kalender/termine/{UID}.ics")
    assert "SUMMARY:Am Handy umbenannt" in jetzt
    assert "Noten mitbringen" in jetzt and "BEGIN:VALARM" in jetzt     # nichts verloren
    q = h.quittung(REL)
    assert q["ergebnis"] == "angenommen" and q["umschlag"] == h.letzter_umschlag
    pc.abgleichen()
    assert "SUMMARY:Am Handy umbenannt" in pc.lesen(f"kalender/termine/{UID}.ics")
    # Der Umschlag liegt noch im Eingang: nicht noch einmal geprüft, nichts gesendet.
    assert laptop.abgleichen().gesendet == []
    h.wegraeumen(REL)
    laptop.abgleichen()
    assert h.quittung(REL) is None                       # Quittung verfällt mit dem Umschlag


def test_fremde_uid_von_google_laesst_sich_aendern(kalender_welt):
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    h = Handy(welt)
    basis = h.lesen(GOOGLE)
    h.schreiben(GOOGLE, _ersetzen(basis, "SUMMARY:Von Google", "SUMMARY:Google am Handy"),
                basis_sha=_sha(basis))
    b = laptop.abgleichen()
    assert not b.hinweise
    assert "SUMMARY:Google am Handy" in laptop.lesen("kalender/termine/abc.ics")
    assert "UID:abc@google.com" in laptop.lesen("kalender/termine/abc.ics")


# ── Widerspruch: abgelehnt, beide bleiben ──────────────────────────────

def test_widerspruch_wird_abgelehnt_und_nichts_ueberschrieben(kalender_welt):
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    h = Handy(welt)
    basis = h.lesen(REL)
    # Inzwischen ändert der Laptop denselben Termin …
    laptop.schreiben(f"kalender/termine/{UID}.ics",
                     _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Laptop").decode())
    laptop.abgleichen()
    # … und das Handy, auf der alten Fassung, mit späterem LAST-MODIFIED.
    neu = _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Handy")
    h.schreiben(REL, neu, basis_sha=_sha(basis), basis=basis)
    b = laptop.abgleichen()
    assert "SUMMARY:Am Laptop" in laptop.lesen(f"kalender/termine/{UID}.ics")
    assert any("abgelehnt" in x and "Widerspruch" in x for x in b.hinweise)
    q = h.quittung(REL)
    assert q["ergebnis"] == "abgelehnt" and "Widerspruch" in q["grund"]
    aufgehoben = list((laptop.zustand / "konflikte" / "eingang-handy").rglob("*.ics"))
    assert len(aufgehoben) == 1 and b"SUMMARY:Am Handy" in aufgehoben[0].read_bytes()
    assert not laptop.abgleichen().hinweise              # einmal gemeldet, nicht jedes Mal


def test_ohne_basis_inhalt_und_mitte_weitergelaufen_wird_abgelehnt(kalender_welt):
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    h = Handy(welt)
    basis = h.lesen(REL)
    laptop.schreiben(f"kalender/termine/{UID}.ics",
                     _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Laptop").decode())
    laptop.abgleichen()
    # Ein anderer Rechner (ohne die alte Fassung in seiner Basis) prüft.
    pc = welt.rechner("pc")
    pc.abgleichen()
    h.schreiben(REL, _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Handy"),
                basis_sha=_sha(basis))
    b = pc.abgleichen()
    assert "SUMMARY:Am Laptop" in pc.lesen(f"kalender/termine/{UID}.ics")
    assert any("kenne ich nicht" in x for x in b.hinweise)


def test_dreiweg_je_vevent_beide_seiten_an_verschiedenen_terminen():
    """Hauptteil am Handy, eine Abweichung (RECURRENCE-ID) in der Mitte
    geändert: beides kommt hinein."""
    uid = "s" * 32 + "@zentrale"
    kal = abb.routine_kalender({"label": "Probe", "rrule": "FREQ=WEEKLY;BYDAY=WE", "time": "19:00",
                                "seit": "2026-11-04",
                                "abweichungen": {"2026-11-11": {"tag": "2026-11-11",
                                                                "time": "20:00"}}}, uid)
    b = abb.zusammenfuehren(None, kal, uid)
    assert b.count(b"BEGIN:VEVENT") == 2
    p = _ersetzen(b, "SUMMARY:Probe", "SUMMARY:Probe (Handy)")
    m = _ersetzen(b, "T200000", "T203000")
    neu, widerspruch = vs.dreiweg(b, p, m)
    assert not widerspruch
    assert b"SUMMARY:Probe (Handy)" in neu and b"T203000" in neu
    # Dieselbe Abweichung auf beiden Seiten verschieden: Widerspruch, nichts.
    p2 = _ersetzen(b, "T200000", "T210000")
    assert vs.dreiweg(b, p2, m)[0] is None


# ── Einzelnes Vorkommen aus / wieder an ────────────────────────────────

def test_vorkommen_aus_und_wieder_an(kalender_welt):
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    uid = "9" * 32 + "@zentrale"
    rel = f"data/kalender/termine/{uid}.ics"
    laptop.schreiben(f"kalender/termine/{uid}.ics", _routine(uid).decode())
    laptop.abgleichen()
    h = Handy(welt)
    basis = h.lesen(rel)
    # Aus: EXDATE + X-ZENTRALE-AUS (genaue Liste, b64-JSON wie in ZENTRALE).
    kal = Calendar.from_ical(basis)
    ev = kal.walk("VEVENT")[0]
    ev.add("EXDATE", abb._ts(abb._datum("2026-11-17"), abb._hhmm("17:00")))
    ev.pop(abb.X_AUS, None)
    ev.add(abb.X_AUS, abb._xkodieren(["2026-11-17"]))
    h.schreiben(rel, kal.to_ical(), basis_sha=_sha(basis))
    assert not laptop.abgleichen().hinweise
    assert _daten(laptop.pfad(f"kalender/termine/{uid}.ics").read_bytes())["aus"] == ["2026-11-17"]
    # Wieder an: das Handy nimmt nur das EXDATE weg (X-ZENTRALE-AUS vergessen)
    # — der Rechner gleicht die Liste an, sonst bliebe es in ZENTRALE aus.
    h.holen()
    basis = h.lesen(rel)
    kal = Calendar.from_ical(basis)
    kal.walk("VEVENT")[0].pop("EXDATE")
    h.schreiben(rel, kal.to_ical(), basis_sha=_sha(basis))
    assert not laptop.abgleichen().hinweise
    roh = laptop.pfad(f"kalender/termine/{uid}.ics").read_bytes()
    assert b"EXDATE" not in roh
    assert not _daten(roh).get("aus")


# ── Löschen nur mit Grabstein ──────────────────────────────────────────

def test_loeschen_nur_ausdruecklich_und_nur_auf_der_gesehenen_fassung(kalender_welt):
    welt = kalender_welt
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    pc.abgleichen()
    h = Handy(welt)
    basis = h.lesen(REL)
    # Ohne Hauptteil (nur eine leere Hülle) ist es kein Löschen.
    h.schreiben(REL, b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n", basis_sha=_sha(basis))
    laptop.abgleichen()
    assert laptop.da(f"kalender/termine/{UID}.ics")
    # Löschen auf einer alten Fassung: abgelehnt.
    h.schreiben(REL, None, loeschen=True, basis_sha="0" * 64)
    b = laptop.abgleichen()
    assert laptop.da(f"kalender/termine/{UID}.ics")
    assert any("nicht gelöscht" in x for x in b.hinweise)
    assert h.quittung(REL)["ergebnis"] == "abgelehnt"
    # Richtig: loeschen + basis_sha → Grabstein, auf allen Rechnern beiseite.
    h.schreiben(REL, None, loeschen=True, basis_sha=_sha(basis))
    laptop.abgleichen()
    assert not laptop.da(f"kalender/termine/{UID}.ics")
    inhalt = welt.inhalt()
    assert REL in inhalt["geloescht"] and REL not in inhalt["dateien"]
    assert h.quittung(REL)["ergebnis"] == "angenommen"
    pc.abgleichen()
    assert not pc.da(f"kalender/termine/{UID}.ics")
    assert list((pc.zustand / "beiseite").rglob(f"{UID}.ics"))    # nie weggeworfen


# ── Ebene wechseln ─────────────────────────────────────────────────────

def test_ebene_wechseln_ist_kein_loeschen_und_neu_und_keine_doppelten(kalender_welt):
    welt = kalender_welt
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    laptop.schreiben("kalender/uncommitted/" + "u" * 32 + "@zentrale.ics",
                     _termin("u" * 32 + "@zentrale", "Vielleicht").decode())
    laptop.abgleichen()
    pc.abgleichen()
    h = Handy(welt)
    basis = h.lesen(REL)
    ziel = f"data/kalender/uncommitted/{UID}.ics"
    h.schreiben(ziel, basis, basis_sha=_sha(basis))
    assert not laptop.abgleichen().hinweise
    inhalt = welt.inhalt()
    assert ziel in inhalt["dateien"] and REL not in inhalt["dateien"]
    for r in (laptop, pc):
        r.abgleichen()
        treffer = [p for p in (r.wurzel / "data" / "kalender").rglob("*.ics")
                   if UID.encode() in p.read_bytes()]
        assert [p.parent.name for p in treffer] == ["uncommitted"]
    assert h.quittung(ziel)["ergebnis"] == "angenommen"


def test_ebene_wechseln_auf_alter_fassung_wird_abgelehnt(kalender_welt):
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    laptop.schreiben("kalender/uncommitted/x.ics", _termin("x@google.com").decode())
    laptop.abgleichen()
    h = Handy(welt)
    basis = h.lesen(REL)
    laptop.schreiben(f"kalender/termine/{UID}.ics",
                     _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Laptop").decode())
    laptop.abgleichen()
    h.schreiben(f"data/kalender/uncommitted/{UID}.ics",
                _ersetzen(basis, "SUMMARY:Schon da", "SUMMARY:Am Handy"),
                basis_sha=_sha(basis), basis=basis)
    b = laptop.abgleichen()
    assert any("Widerspruch" in x for x in b.hinweise)
    assert laptop.da(f"kalender/termine/{UID}.ics")
    assert not laptop.da(f"kalender/uncommitted/{UID}.ics")


# ── Wieder angewählte App: die Mitte gilt ─────────────────────────────

def test_wieder_angewaehlte_app_die_mitte_gilt_eigenes_wird_aufgehoben(welt):
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    laptop.schreiben("gedaechtnis/sasha.md", "mag Tee\n")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    pc.abgleichen()
    # Die Einstellungen sind in diesem Test für alle gespielten Rechner
    # dieselben: die Wahl vor jedem Lauf setzen, wie sie auf dem Gerät stünde.
    pc._als_ich()
    abgleich_apps.setzen({n: True for n in abgleich_apps.tabelle()} | {"assistent": False})
    pc.abgleichen()
    abgleich_apps.setzen({"assistent": True})                      # der Laptop hat sie an
    laptop.schreiben("gedaechtnis/sasha.md", "mag Kaffee\n")           # die Mitte läuft weiter
    laptop.abgleichen()
    abgleich_apps.setzen({"assistent": False})
    pc.schreiben("gedaechtnis/sasha.md", "mag Tee\nund Kekse\n")       # hier, während abgewählt
    pc.abgleichen()
    abgleich_apps.setzen({"assistent": True})
    b = pc.abgleichen()
    assert pc.lesen("gedaechtnis/sasha.md") == "mag Kaffee\n"
    assert "⟪" not in pc.lesen("gedaechtnis/sasha.md")
    assert any("App neu dabei" in x for x in b.hinweise)
    aufgehoben = list((pc.zustand / "konflikte").rglob("sasha.md"))
    assert len(aufgehoben) == 1 and aufgehoben[0].read_text() == "mag Tee\nund Kekse\n"
    laptop.abgleichen()
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Kaffee\n"
    # Danach wieder normal: Änderungen von hier gehen hoch.
    pc.schreiben("gedaechtnis/sasha.md", "mag Kaffee\nund Kekse\n")
    assert not pc.abgleichen().hinweise
    laptop.abgleichen()
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Kaffee\nund Kekse\n"


def test_kalender_wieder_dabei_spaeteres_last_modified_ersetzt_die_mitte_nicht(kalender_welt, monkeypatch):
    welt = kalender_welt
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    pc.abgleichen()
    an = {"pc": True}
    monkeypatch.setattr(adapter, "kalender_ueber_cloud",
                        lambda wurzel=None: an["pc"] or abgleich.dateien.knoten() != "pc")
    an["pc"] = False
    pc.abgleichen()                                  # Kalender auf dem PC aus
    roh = laptop.pfad(f"kalender/termine/{UID}.ics").read_bytes()
    laptop.pfad(f"kalender/termine/{UID}.ics").write_bytes(
        _ersetzen(roh, "SUMMARY:Schon da", "SUMMARY:In der Mitte"))
    laptop.abgleichen()
    hier = _ersetzen(roh, "SUMMARY:Schon da", "SUMMARY:Alt am PC")
    lm = [z for z in hier.decode().splitlines() if z.startswith("LAST-MODIFIED")][0]
    hier = _ersetzen(hier, lm, "LAST-MODIFIED:20991231T000000Z")
    pc.pfad(f"kalender/termine/{UID}.ics").write_bytes(hier)
    an["pc"] = True
    b = pc.abgleichen()                              # wieder dabei
    assert "SUMMARY:In der Mitte" in pc.lesen(f"kalender/termine/{UID}.ics")
    assert any("App neu dabei" in x for x in b.hinweise)
    assert list((pc.zustand / "konflikte").rglob(f"{UID}.ics"))
    laptop.abgleichen()
    assert "SUMMARY:In der Mitte" in laptop.lesen(f"kalender/termine/{UID}.ics")
