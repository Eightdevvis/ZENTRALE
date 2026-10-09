"""
Prüfstand sparen (2026-10-09, Sasha: Kosten senken) — mit gefälschtem
Modell, ohne einen bezahlten Aufruf:
  - früh abbrechen, sobald ein Fall sicher verloren ist (frueh.py);
  - aufzeichnen und kostenlos abspielen (aufnahme.py), inkl. „ab Zug n
    nicht mehr gültig";
  - Richter über die Message Batches API (richter_batch.py), mit Zeitgrenze.
"""
import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import frueh, kind, richter_batch  # noqa: E402
from test_cloud_loop import FakeBlock, FakeClient  # noqa: E402
from test_pruefstand import FALL, RUNDEN, _richter_attrappe  # noqa: E402

import ai_backends  # noqa: E402
import cloud  # noqa: E402
import usage  # noqa: E402


@pytest.fixture
def modell(monkeypatch):
    """Wie im Trockentest: Cloud-Weg mit gefälschtem Client."""
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "chat_cloud_kind", lambda: "anthropic")
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "claude")
    monkeypatch.setattr(cloud, "_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(cloud.graph, "einmal_seeden", lambda *a, **k: None)

    def einhaengen(runden):
        c = FakeClient([dict(r) for r in runden])
        monkeypatch.setattr(cloud, "_get_client", lambda: c)
        return c
    return einhaengen


# ── Früh abbrechen ─────────────────────────────────────────────────────

ZWEI_ZUEGE = dict(FALL, id="frueh", netz={}, endzustand=[
    {"was": "Drive bleibt", "am": "2026-10-09", "label": "drive", "findet_statt": True},
    {"was": "Zug 1 nennt die Uhrzeit", "antwort": {"zug": 1, "muster": ["18:30"]}}],
    zuege=[{"sagt": "was steht an?"}, {"sagt": "und morgen?"}])
ERFUNDEN = [{"stop_reason": "end_turn", "text": ["Drive ist morgen."],
             "content": [FakeBlock("text", text="Drive ist morgen.")]},
            {"stop_reason": "end_turn", "text": ["Morgen nichts."],
             "content": [FakeBlock("text", text="Morgen nichts.")]}]


def test_frueh_abbrechen_wenn_ein_gefahrener_zug_durchfiel(modell, tmp_path):
    c = modell(ERFUNDEN)
    erg = kind.ausfuehren(ZWEI_ZUEGE, code_wurzel=ROOT, tmp=str(tmp_path / "p"),
                          ohne_richter=True, frueh=True)
    assert erg["frueh_abgebrochen"]["nach_zug"] == 1
    assert "Zug 1 nennt die Uhrzeit" in erg["frueh_abgebrochen"]["grund"]
    assert len(erg["zuege"]) == 1 and len(c.calls) == 1        # Zug 2 nicht bezahlt
    assert erg["endzustand"][0]["ok"]                           # Endzustand trotzdem geprüft


def test_ohne_schalter_laeuft_der_fall_zu_ende(modell, tmp_path):
    c = modell(ERFUNDEN)
    erg = kind.ausfuehren(ZWEI_ZUEGE, code_wurzel=ROOT, tmp=str(tmp_path / "p"),
                          ohne_richter=True)
    assert "frueh_abgebrochen" not in erg and len(c.calls) == 2


def test_endgueltig_verfehlte_pruefungen():
    fall = {"endzustand": [{"was": "eine Frage", "fragen": {"art": "erlaubnis", "anzahl": 1}},
                           {"was": "Zug 1 sagt Zeit", "antwort": {"zug": 1, "muster": ["10:00"]}},
                           {"was": "Kalender", "am": "2026-10-12", "label": "x", "anzahl": 0}]}
    erg = {"zuege": [{"antwort": "Mo 10:00", "kontext": "", "werkzeuge": [],
                      "fragen": [{"art": "erlaubnis"}]}]}
    assert frueh.verloren(fall, erg) is None                  # Kalender zählt nie
    erg["zuege"][0]["fragen"].append({"art": "erlaubnis"})
    assert "schon 2 statt 1" in frueh.verloren(fall, erg)
    erg["zuege"][0]["fragen"].pop()
    erg["zuege"][0]["antwort"] = "Mo um zehn"
    assert "Zug 1 sagt Zeit" in frueh.verloren(fall, erg)


def test_harte_marke_erfundene_kennung():
    erg = {"zuege": [{"antwort": "Steht als #tbeef.", "kontext": "#t1234 Drive",
                      "fragen": [], "werkzeuge": []}]}
    assert "#tbeef" in frueh.harte_marke(erg)
    erg["zuege"][0]["kontext"] = "#tbeef Drive"
    assert frueh.harte_marke(erg) is None


def test_harte_marke_schreiben_trotz_nein():
    erg = {"zuege": [{"antwort": "", "kontext": "", "fragen": [], "werkzeuge": [
        {"name": "add_calendar_entry", "args": {}, "ergebnis": "[ergebnis: ok] steht",
         "frage": {"art": "erlaubnis", "antwort": "nein"}}]}]}
    assert "trotz „nein“" in frueh.harte_marke(erg)
    erg["zuege"][0]["werkzeuge"][0]["ergebnis"] = "[ergebnis: abgelehnt]"
    assert frueh.harte_marke(erg) is None


# ── Aufzeichnen und abspielen ──────────────────────────────────────────

def test_aufzeichnen_und_kostenlos_abspielen(modell, tmp_path):
    aufn = tmp_path / "f.json"
    modell(RUNDEN)
    erst = kind.ausfuehren(FALL, code_wurzel=ROOT, tmp=str(tmp_path / "a"),
                           richter_fragen=_richter_attrappe([]), aufnahme=str(aufn))
    daten = json.loads(aufn.read_text())
    assert len(daten["runden"]) == 4 and daten["runden"][0]["zug"] == 1
    assert daten["runden"][0]["final"]["content"][0]["name"] == "web_search"

    def kein_modell():
        raise AssertionError("beim Abspielen darf kein Modell gefragt werden")
    cloud._get_client = kein_modell        # Abspielen hängt sich selbst ein
    vorher = usage.monat_euro(usage.PRUEFSTAND)
    zweit = kind.ausfuehren(FALL, code_wurzel=ROOT, tmp=str(tmp_path / "b"),
                            abspielen=str(aufn))
    assert zweit["abspielen"]["gueltig"], zweit["abspielen"]
    assert [w["name"] for w in zweit["zuege"][0]["werkzeuge"]] == \
        [w["name"] for w in erst["zuege"][0]["werkzeuge"]]
    assert zweit["zuege"][0]["antwort"] == erst["zuege"][0]["antwort"]
    assert [e["ok"] for e in zweit["endzustand"]] == [e["ok"] for e in erst["endzustand"]]
    assert zweit["richter"]["fehler"] == "Richter nicht gefragt"
    assert usage.monat_euro(usage.PRUEFSTAND) == pytest.approx(vorher)   # 0 €


def test_abspielen_merkt_wenn_die_aufnahme_nicht_mehr_passt(modell, tmp_path):
    aufn = tmp_path / "f.json"
    modell(RUNDEN)
    kind.ausfuehren(FALL, code_wurzel=ROOT, tmp=str(tmp_path / "a"), ohne_richter=True,
                    aufnahme=str(aufn))
    daten = json.loads(aufn.read_text())
    kaputt = copy.deepcopy(daten)
    # So, als wäre das Werkzeug damals gescheitert: der Ausgang passt nicht mehr.
    kaputt["runden"][1]["ergebnisse"][1][1] = not kaputt["runden"][1]["ergebnisse"][1][1]
    aufn.write_text(json.dumps(kaputt))
    erg = kind.ausfuehren(FALL, code_wurzel=ROOT, tmp=str(tmp_path / "b"), abspielen=str(aufn))
    ab = erg["abspielen"]
    assert not ab["gueltig"] and ab["ungueltig_ab_zug"] == 1
    assert "anders ausgegangen" in ab["grund"]
    from pruefstand_teile import bericht
    assert "ab Zug 1 nicht mehr gültig" in bericht.uebersicht_zeile(erg)


# ── Richter im Batch ───────────────────────────────────────────────────

class _Batches:
    def __init__(self, fertig_nach=1, antwort="B ¦ 1 ¦ belegt ¦ U1 ¦ was steht an ¦ x ¦ x ¦ ok"):
        self.fertig_nach, self.antwort = fertig_nach, antwort
        self.abfragen, self.storniert, self.anfragen = 0, False, None

    def create(self, requests):
        self.anfragen = requests
        return SimpleNamespace(id="b1", processing_status="in_progress")

    def retrieve(self, bid):
        self.abfragen += 1
        return SimpleNamespace(id=bid, processing_status=(
            "ended" if self.abfragen >= self.fertig_nach else "in_progress"))

    def cancel(self, bid):
        self.storniert = True

    def results(self, bid):
        for r in reversed(self.anfragen):                 # Reihenfolge beliebig
            msg = SimpleNamespace(content=[SimpleNamespace(type="text", text=self.antwort)],
                                  usage=SimpleNamespace(input_tokens=1000, output_tokens=100))
            yield SimpleNamespace(custom_id=r["custom_id"],
                                  result=SimpleNamespace(type="succeeded", message=msg))


def _ergebnisse():
    zug = {"sagt": "was steht an", "antwort": "Nichts.", "kontext": "", "werkzeuge": [],
           "kalender_danach": ""}
    return [{"id": "a", "modelle": ["claude-sonnet-5"], "zuege": [zug, dict(zug)]},
            {"id": "b", "modelle": ["claude-sonnet-5"], "zuege": [dict(zug, antwort="")]}]


def test_batch_richtet_alle_faelle_zum_halben_preis(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "_FILE", str(tmp_path / "u.json"))
    b = _Batches(fertig_nach=3)
    client = SimpleNamespace(messages=SimpleNamespace(batches=b))
    ergs = richter_batch.richten(_ergebnisse(), client=client, schlafen=lambda s: None)
    assert [r["custom_id"] for r in b.anfragen] == ["f0-z1", "f0-z2"]   # leere Antwort: keine Anfrage
    assert b.anfragen[0]["params"]["model"] == "claude-sonnet-5"
    a = ergs[0]
    assert a["richter"]["modell"] == "claude-sonnet-5 (Batch)"
    assert [x["zug"] for x in a["richter"]["behauptungen"]] == [1, 2]
    import prices
    halb = prices.euro("claude-sonnet-5", input_tokens=1000, output_tokens=100) / 2
    assert a["richter_kosten_eur"] == pytest.approx(2 * halb, rel=1e-3)
    assert usage.monat_euro(usage.PRUEFSTAND) == pytest.approx(2 * halb, rel=1e-3)
    assert usage.monat_euro() == 0.0                                 # nicht Sashas Chat
    assert ergs[1]["richter"]["behauptungen"] == []


def test_batch_zeitgrenze_storniert_und_wirft():
    b = _Batches(fertig_nach=99)
    uhr = iter(range(0, 10_000, 100))
    with pytest.raises(richter_batch.KeinBatch, match="nicht fertig"):
        richter_batch.richten(_ergebnisse(), client=SimpleNamespace(
            messages=SimpleNamespace(batches=b)), warten_s=250,
            schlafen=lambda s: None, uhr=lambda: next(uhr))
    assert b.storniert


def test_batch_nur_fuer_claude():
    ergs = _ergebnisse()
    ergs[0]["modelle"] = ["qwen-plus"]
    with pytest.raises(richter_batch.KeinBatch, match="Claude"):
        richter_batch.richten(ergs, client=object())
