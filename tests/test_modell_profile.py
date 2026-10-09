"""Modell-Profile (core/profil/modelle/, 2026-10-09).

Ein Profil legt sich über die Schiene und darf für EIN Modell (qwen) Prompt,
Werkzeuge und Aufruf-Werte ändern. Was hier vor allem gilt: wer kein Profil
hat (Claude), fährt byte-gleich wie vorher — dasselbe Schienen-Objekt,
derselbe Kopf, dieselben Werkzeuge, derselbe Aufruf.
"""

import copy
import json
import sys
import types

import pytest

import cloud
import cloud_openai
import nutzer_angaben
import profil
from profil import gross, modelle


@pytest.fixture
def mit_qwen_profil(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", json.dumps({"qwen-*": "qwen"}))


# ── Zuordnung ──────────────────────────────────────────────────────────

def test_claude_bekommt_kein_profil(mit_qwen_profil):
    for m in ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"):
        assert profil.fuer_backend("cloud", modell=m) is gross


def test_standard_ohne_einstellung_laesst_claude_unberuehrt(monkeypatch):
    monkeypatch.delenv("ZENTRALE_MODELL_PROFILE", raising=False)
    assert profil.fuer_backend("cloud", modell="claude-sonnet-5") is gross
    assert not any(n.startswith("claude") for n in modelle.STANDARD)


def test_ohne_modell_wie_bisher(mit_qwen_profil):
    assert profil.fuer_backend("cloud") is gross
    assert cloud._profil() is gross


def test_qwen_bekommt_profil_ueber_gross(mit_qwen_profil):
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    assert s is not gross
    assert s.PROFIL == "qwen"
    # Die Schiene bleibt gross: Ausführer und Prüfer sind genauso streng.
    assert s.NAME == "gross"
    assert s.MERKMALE == gross.MERKMALE


def test_genauer_name_vor_muster(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE",
                       json.dumps({"qwen-*": "qwen", "qwen-max": "gibtsnicht"}))
    # Genauer Name gewinnt — und ein unbekanntes Profil heißt: keins.
    assert modelle.name_fuer("qwen-max") is None
    assert modelle.name_fuer("qwen-plus") == "qwen"


def test_leere_zuordnung_schaltet_ab(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", "{}")
    assert profil.fuer_backend("cloud", modell="qwen-plus") is gross


def test_kaputte_einstellung_faellt_auf_standard(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", "{kein json")
    assert modelle.zuordnung() == modelle.STANDARD


# ── Claude byte-gleich ────────────────────────────────────────────────

def test_kopf_fuer_claude_byte_gleich(mit_qwen_profil):
    ohne = cloud._static_system(None, tutor_mode=False)
    mit = cloud._static_system(None, tutor_mode=False,
                               schiene=cloud._profil("claude-sonnet-5"))
    assert mit == ohne


def test_profil_veraendert_gross_nicht(mit_qwen_profil):
    vorher_tools = copy.deepcopy(gross.TOOLS)
    vorher_system = gross.system()
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    s.system()
    _ = s.TOOLS
    assert gross.TOOLS == vorher_tools
    assert gross.system() == vorher_system
    assert cloud.cloud_tools() is gross.TOOLS


# ── Der Aufruf ─────────────────────────────────────────────────────────

class _Strom:
    """Gefälschter OpenAI-Client: merkt sich die Aufruf-Argumente, antwortet
    mit einem Text ohne Werkzeug."""

    def __init__(self):
        self.aufrufe = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.aufrufe.append(kw)
        delta = types.SimpleNamespace(content="ok", tool_calls=None,
                                      reasoning_content=None)
        return iter([types.SimpleNamespace(
            usage=None, choices=[types.SimpleNamespace(delta=delta)])])


def _eine_runde(adapter):
    gen = adapter.runde()
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def test_adapter_ohne_profil_wie_bisher():
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "claude-x", [{"role": "user", "content": "hi"}],
                                    [{"type": "function", "function": {"name": "t"}}])
    _eine_runde(a)
    kw = client.aufrufe[0]
    assert "tool_choice" not in kw and "extra_body" not in kw
    assert kw["temperature"] == cloud_openai._TEMP
    assert kw["max_tokens"] == cloud_openai._MAX_TOKENS


def test_adapter_nimmt_werte_des_profils(monkeypatch):
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.TEMPERATUR = 0.1
    attrappe.MAX_TOKENS = 1234
    attrappe.tool_choice = lambda **lage: "required" if lage["nr"] == 0 else None
    s = modelle.ModellSchiene(gross, attrappe)
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "m", [{"role": "user", "content": "hi"}],
                                    [{"type": "function", "function": {"name": "t"}}],
                                    profil=s)
    _eine_runde(a)
    _eine_runde(a)
    erst, dann = client.aufrufe
    assert erst["temperature"] == 0.1 and erst["max_tokens"] == 1234
    assert erst["tool_choice"] == "required"
    assert "tool_choice" not in dann


def test_aufrufer_wert_geht_vor_profil():
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.TEMPERATUR = 0.1
    s = modelle.ModellSchiene(gross, attrappe)
    a = cloud_openai._OpenAIAdapter(_Strom(), "m", [], [], temperatur=0.9, profil=s)
    assert a.temperatur == 0.9


def test_profil_ohne_werkzeuge_bietet_kein_tool_choice():
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.tool_choice = lambda **lage: "required"
    s = modelle.ModellSchiene(gross, attrappe)
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "m", [{"role": "user", "content": "hi"}],
                                    [], profil=s)
    _eine_runde(a)
    assert "tool_choice" not in client.aufrufe[0]


# ── Was das qwen-Profil tut ────────────────────────────────────────────

def test_qwen_kopf_beginnt_mit_arbeitsweise(mit_qwen_profil):
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    kopf = s.system()
    assert kopf.startswith("## Arbeitsweise")
    assert kopf.endswith(gross.system())


def test_erinnerung_steht_im_umschlag_am_ende(mit_qwen_profil):
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    v = cloud._volatile_text("", False, False)
    mit = s.erinnerung(v)
    assert mit.endswith("</kontext_automatisch>")
    assert modelle.qwen.erinnerung() in mit
    assert mit.index(modelle.qwen.erinnerung()) > mit.index("## Jetzt")


def test_qwen_uhrzeiten_vorgerechnet():
    q = modelle.qwen
    assert "= 6:30 oder 18:30" in q.uhrzeiten("parkour ist ab jetzt um halb sieben")
    assert "= 7:15 oder 19:15" in q.uhrzeiten("viertel nach sieben")
    assert "= 12:30 oder 0:30" in q.uhrzeiten("halb eins")
    assert q.uhrzeiten("um 18 uhr") == ""
    mit = q.erinnerung([{"role": "user", "content": "training ab jetzt um halb acht"}])
    assert mit.startswith(q.erinnerung()) and "19:30" in mit


def test_qwen_texte_mit_nutzername(mit_qwen_profil, monkeypatch):
    monkeypatch.setenv("ZENTRALE_NUTZER_NAME", "Kim")
    monkeypatch.setenv("ZENTRALE_NUTZER_PRONOMEN", "sie")
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    kopf = s.system()
    arbeitsweise = kopf.split("\n\n## ", 1)[0]
    assert "Kim" in arbeitsweise and "Sasha" not in arbeitsweise
    assert "{" not in arbeitsweise
    assert "Kim" in modelle.qwen.erinnerung()



def test_qwen_werkzeuge_vereinfacht_ohne_gross_zu_aendern(mit_qwen_profil):
    vorher = copy.deepcopy(gross.TOOLS)
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    nach_name = {t["function"]["name"]: t["function"] for t in s.TOOLS}
    assert "layers" not in nach_name["read_calendar"]["parameters"]["properties"]
    assert "Dauer bleibt" in nach_name["edit_calendar_routine"]["description"]
    assert len(s.TOOLS) == len(gross.TOOLS)
    assert gross.TOOLS == vorher


# ── Zusatz-Prüfer „soll ich?" statt tun ────────────────────────────────

from profil.modelle import zusatzpruefer as zp  # noqa: E402


class _BasisPruefer:
    modus = "an"

    def __init__(self, korrektur=None):
        self.protokoll = []
        self.korrekturen = 0
        self.befunde = []
        self._k = korrektur

    def nach_antwort(self, text, *, letzte_runde):
        return self._k

    def abschluss(self, text):
        return {"basis": True}


class _Schritt:
    def __init__(self, schreibt, status):
        self.schreibt, self.status = schreibt, status


def test_fragt_statt_tut_erkennt_erlaubnisfrage():
    assert zp.fragt_statt_tut(
        "der zahnarzt am dienstag ist jetzt erst um 16:30",
        "Ich ändere den Termin auf 16:30. Soll ich das jetzt durchführen?")
    assert zp.fragt_statt_tut(
        "parkour am mittwoch ist ab jetzt um halb sieben",
        "Sag kurz Bescheid — dann mach ich's.")


def test_echte_rueckfrage_und_plaudern_bleiben():
    # Angabe fehlt: die Frage nach dem Tag ist keine Erlaubnis-Frage.
    assert not zp.fragt_statt_tut(
        "trag mir noch ne extra fahrstunde nächste woche ein",
        "An welchem Tag und um wie viel Uhr?")
    # Sasha will nichts ändern.
    assert not zp.fragt_statt_tut(
        "wie war dein tag", "Soll ich dir was erzählen?")


def test_nachfrage_pruefer_eine_runde_dann_ruhe():
    b = _BasisPruefer()
    p = zp.ZusatzPruefer(b, "verschieb den zahnarzt auf 16:30")
    erst = p.nach_antwort("Soll ich das so ändern?", letzte_runde=False)
    assert erst == nutzer_angaben.einsetzen(zp.ERLAUBNIS) and b.korrekturen == 1
    assert p.nach_antwort("Soll ich das so ändern?", letzte_runde=False) is None
    assert p.abschluss("x") == {"basis": True}


def test_nachfrage_pruefer_schweigt_nach_schreiben_und_laesst_basis_vor():
    b = _BasisPruefer()
    b.protokoll.append(_Schritt(True, "ok"))
    p = zp.ZusatzPruefer(b, "verschieb den zahnarzt")
    assert p.nach_antwort("Soll ich noch was ändern?", letzte_runde=False) is None
    p2 = zp.ZusatzPruefer(_BasisPruefer(korrektur="BASIS"), "verschieb den zahnarzt")
    assert p2.nach_antwort("Soll ich?", letzte_runde=False) == "BASIS"
    p3 = zp.ZusatzPruefer(_BasisPruefer(), "verschieb den zahnarzt")
    assert p3.nach_antwort("Soll ich?", letzte_runde=True) is None


def test_qwen_profil_legt_nachfrage_pruefer_um_den_basis_pruefer(mit_qwen_profil):
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    b = _BasisPruefer()
    p = s.pruefer(b, messages=[{"role": "user", "content": "lösch den friseur"}])
    assert isinstance(p, zp.ZusatzPruefer)
    assert s.pruefer(None, messages=[]) is None
    # Ohne Profil (Claude) bleibt der Prüfer der Schiene, wie er ist.
    assert gross is profil.fuer_backend("cloud", modell="claude-sonnet-5")


class _KSchritt:
    def __init__(self, name, args, status, text):
        self.name, self.args, self.status, self.text = name, args, status, text
        self.schreibt = False


def test_zusatzpruefer_aufruf_als_text():
    b = _BasisPruefer()
    p = zp.ZusatzPruefer(b, "steht der noch drin?", {"read_calendar"})
    assert p.nach_antwort("read_calendar(zeitraum=naechste_woche)",
                          letzte_runde=False) == nutzer_angaben.einsetzen(zp.ALS_TEXT)
    # Ein Satz, der ein Werkzeug nur erwähnt, ist kein Aufruf als Text.
    p2 = zp.ZusatzPruefer(_BasisPruefer(), "x", {"read_calendar"})
    assert p2.nach_antwort("Ich habe read_calendar (nächste Woche) gelesen: frei.",
                           letzte_runde=False) is None


def test_zusatzpruefer_leere_stichwortsuche():
    b = _BasisPruefer()
    b.protokoll.append(_KSchritt("read_calendar", {"suche": "uni"}, "ok",
                                 "Keine Einträge mit 'uni' in diesem Zeitraum."))
    p = zp.ZusatzPruefer(b, "die uni-sachen sollen nur im semester stehen")
    assert p.nach_antwort("Keine Uni-Sachen im Kalender gefunden.",
                          letzte_runde=False) == nutzer_angaben.einsetzen(zp.STICHWORT)
    # Hat sie auch ohne Stichwort gelesen, darf sie „nichts da“ sagen.
    b2 = _BasisPruefer()
    b2.protokoll += [_KSchritt("read_calendar", {"suche": "uni"}, "ok", "Keine Einträge"),
                     _KSchritt("read_calendar", {"zeitraum": "naechste_30_tage"}, "ok",
                               "Kalender …: Montag …")]
    p2 = zp.ZusatzPruefer(b2, "die uni-sachen")
    assert p2.nach_antwort("Keine Uni-Sachen im Kalender gefunden.",
                           letzte_runde=False) is None


def test_zusatzpruefer_tat_ohne_werkzeug():
    # Runde 7, m03: „ist gelöscht.“ ohne delete_calendar_entry.
    p = zp.ZusatzPruefer(_BasisPruefer(), "der friseur fällt aus, lösch den bitte")
    assert p.nach_antwort("Der Friseurtermin am Freitag ist gelöscht.",
                          letzte_runde=False) == nutzer_angaben.einsetzen(zp.TAT)
    # Gespräch 20261009-150713: „Alles korrigiert“ nach „ok“.
    p2 = zp.ZusatzPruefer(_BasisPruefer(), "ok")
    assert p2.nach_antwort("Alles korrigiert: alle Vorlesungen laufen ab 12.10.",
                           letzte_runde=False) == nutzer_angaben.einsetzen(zp.TAT)


def test_zusatzpruefer_tat_schweigt_bei_beleg_frage_und_ohne_wunsch():
    b = _BasisPruefer()
    b.protokoll.append(_Schritt(True, "ok"))
    p = zp.ZusatzPruefer(b, "lösch den friseur")
    assert p.nach_antwort("Friseur ist gelöscht.", letzte_runde=False) is None
    p2 = zp.ZusatzPruefer(_BasisPruefer(), "lösch den friseur")
    assert p2.nach_antwort("Er ist noch nicht gelöscht — welcher Friseur, Fr oder Sa?",
                           letzte_runde=False) is None
    p3 = zp.ZusatzPruefer(_BasisPruefer(), "steht der noch drin?")
    assert p3.nach_antwort("Nein, der ist weg.", letzte_runde=False) is None


def test_zusatzpruefer_zeit_nach_aenderung_nur_aus_dem_ergebnis():
    # Abschlusslauf m04: gespeichert 19:30–20:00, gesagt „19:30 bis 20:30“.
    b = _BasisPruefer()
    s = _KSchritt("edit_calendar_routine", {}, "ok",
                  "Routine „Training“ wöchentlich do 19:30–20:00 GEÄNDERT")
    s.schreibt = True
    b.protokoll.append(s)
    p = zp.ZusatzPruefer(b, "training ist ab jetzt um halb acht")
    k = p.nach_antwort("Training ist ab jetzt 19:30 bis 20:30.", letzte_runde=False)
    assert k and "19:30–20:30" in k
    p2 = zp.ZusatzPruefer(b, "training ist ab jetzt um halb acht")
    assert p2.nach_antwort("Training ist jetzt 19:30–20:00.", letzte_runde=False) is None
    # Ohne Änderung in diesem Zug prüft er Zeiten nicht (Plaudern, Vorschläge).
    p3 = zp.ZusatzPruefer(_BasisPruefer(), "wann ist training?")
    assert p3.nach_antwort("Vielleicht 18:00–19:00?", letzte_runde=False) is None

def test_qwen_erste_runde_erst_lesen_nur_bei_aenderungswunsch():
    q = modelle.qwen
    tools = [{"function": {"name": "read_calendar"}}, {"function": {"name": "x"}}]
    lesen = {"type": "function", "function": {"name": "read_calendar"}}
    aendern = [{"role": "user", "content": "parkour am mittwoch ist ab jetzt um halb sieben"}]
    assert q.tool_choice(nr=0, verlauf=aendern, tools=tools) == lesen
    assert q.tool_choice(nr=1, verlauf=aendern, tools=tools) is None
    # Ohne read_calendar im Angebot wird nichts erzwungen.
    assert q.tool_choice(nr=0, verlauf=aendern, tools=tools[1:]) is None
    plaudern = [{"role": "user", "content": "wie geht's dir heute?"}]
    assert q.tool_choice(nr=0, verlauf=plaudern, tools=tools) is None
    zustimmung = [{"role": "user", "content": "lösch die alten"},
                  {"role": "assistant", "content": "Soll ich alle drei löschen?"},
                  {"role": "user", "content": "ok"}]
    assert q.tool_choice(nr=0, verlauf=zustimmung, tools=tools) == lesen
    ok_ohne_frage = [{"role": "assistant", "content": "Schön."},
                     {"role": "user", "content": "ok"}]
    assert q.tool_choice(nr=0, verlauf=ok_ohne_frage, tools=tools) is None
    # Runde 9, f08: „nur nachschauen, noch nix eintragen“ ist kein Änderungswunsch.
    nachschauen = [{"role": "user", "content": "wann ist analysis I? schau im lsf nach "
                                               "— nur nachschauen, noch nix eintragen"}]
    assert q.tool_choice(nr=0, verlauf=nachschauen, tools=tools) is None
