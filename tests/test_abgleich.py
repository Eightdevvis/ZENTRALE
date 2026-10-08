"""Abgleich über die Mitte (core/abgleich.py, memory/betrieb/abgleich.md).

Zwei (manchmal drei) gespielte Rechner gleichen gegen eine Wegwerf-Mitte ab:
ein leeres git-Repo im tmp. Nie gegen GitHub, nie gegen Sashas data/.

Geprüft wird, was Sasha am rsync-Weg „cursed" fand, und was nie passieren
darf: gleichzeitige Änderungen verschlucken sich, Gelöschtes kommt zurück,
Klartext oder der Schlüssel landen in der Mitte, ein Absturz verliert etwas.
"""
import json
import os
import subprocess

import pytest

import abgleich
import abgleich_mitte
import abgleich_schluessel as schluessel
import ai_config
import dateien


# ── Die Welt: eine Mitte, mehrere Rechner ──────────────────────────────

class Rechner:
    def __init__(self, welt, name):
        self.welt, self.name = welt, name
        self.wurzel = welt.tmp / name / "zentrale"
        self.zustand = welt.tmp / name / "abgleich"
        (self.wurzel / "data").mkdir(parents=True, exist_ok=True)

    def _als_ich(self):
        mp = self.welt.mp
        mp.setenv("ZENTRALE_ABGLEICH_DIR", str(self.zustand))
        mp.setattr(dateien, "knoten", lambda: self.name)

    def abgleichen(self, **kw):
        self._als_ich()
        return abgleich.abgleichen(str(self.wurzel), **kw)

    def zustand_lesen(self):
        self._als_ich()
        return abgleich.zustand()

    def pfad(self, rel):
        return self.wurzel / "data" / rel

    def schreiben(self, rel, inhalt):
        p = self.pfad(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(inhalt, (list, dict)):
            inhalt = json.dumps(inhalt, indent=2, ensure_ascii=False)
        p.write_text(inhalt, encoding="utf-8")

    def lesen(self, rel):
        return self.pfad(rel).read_text(encoding="utf-8")

    def json(self, rel):
        return json.loads(self.lesen(rel))

    def da(self, rel):
        return self.pfad(rel).exists()


class Welt:
    def __init__(self, tmp, mp):
        self.tmp, self.mp = tmp, mp
        self.mitte = tmp / "mitte.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.mitte)], check=True)
        mp.setenv("ZENTRALE_ABGLEICH_MITTE", str(self.mitte))
        mp.setenv("ZENTRALE_ABGLEICH_SCHLUESSEL", str(tmp / "schluessel"))
        mp.setattr(ai_config, "_overrides", {})
        mp.setattr(ai_config, "_config", {})
        self.schluessel_pfad = schluessel.anlegen()

    def rechner(self, name):
        return Rechner(self, name)

    def blobs(self):
        """Inhalt JEDER Datei in JEDEM Stand der Mitte, dazu die Commit-Texte."""
        def git(*a):
            return subprocess.run(["git", "-C", str(self.mitte), *a], capture_output=True,
                                  check=True).stdout
        raus = []
        objekte = git("rev-list", "--all", "--objects").decode().split("\n")
        for z in objekte:
            if not z.strip():
                continue
            sha = z.split()[0]
            typ = git("cat-file", "-t", sha).strip()
            if typ in (b"blob", b"commit"):
                raus.append((z.split(" ", 1)[1] if " " in z else "", git("cat-file", "-p", sha)))
        return raus

    def inhalt(self):
        """Das entschlüsselte Inhaltsverzeichnis der Mitte."""
        r = self.rechner("_leser")
        r._als_ich()
        m = abgleich.mitte_oeffnen()
        stand, lesen, _ = m.holen()
        return json.loads(schluessel.Tresor(schluessel.laden()).auf(lesen(abgleich.INHALT)))


@pytest.fixture
def welt(tmp_path, monkeypatch):
    return Welt(tmp_path, monkeypatch)


LISTE = [{"id": "einkauf", "name": "Einkauf", "created": "2026-10-01", "next_item": 3,
          "items": [{"id": 1, "text": "Milch", "done": False},
                    {"id": 2, "text": "Brot", "done": False}]}]


def _zwei(welt, **dateien_):
    """Laptop füllt die Mitte, PC holt — beide auf demselben Stand."""
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    for rel, inhalt in dateien_.items():
        laptop.schreiben(rel.replace("__", "/"), inhalt)
    assert laptop.abgleichen().art == "erstbefuellung"
    assert pc.abgleichen().art == "erstabgleich"
    return laptop, pc


# ── Grundweg ───────────────────────────────────────────────────────────

def test_erstbefuellung_und_der_zweite_rechner_bekommt_alles(welt):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE, "gedaechtnis__sasha.md": "# Sasha\nmag Tee\n"})
    assert pc.json("lists.json") == LISTE
    assert pc.lesen("gedaechtnis/sasha.md") == "# Sasha\nmag Tee\n"
    assert pc.zustand_lesen()["letzter_erfolg"]


def test_trocken_aendert_weder_mitte_noch_rechner(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("lists.json", LISTE)
    b = laptop.abgleichen(trocken=True)
    assert b.gesendet == ["data/lists.json"]
    r = subprocess.run(["git", "-C", str(welt.mitte), "branch", "--list"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == ""
    assert not (laptop.zustand / "basis.json").exists()


def test_verschiedene_eintraege_derselben_liste_bleiben_beide(welt):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    l = laptop.json("lists.json")
    l[0]["items"][0]["done"] = True                       # Laptop hakt Milch ab
    laptop.schreiben("lists.json", l)
    p = pc.json("lists.json")
    p[0]["items"][1]["text"] = "Vollkornbrot"            # PC benennt Brot um
    p[0]["items"].append({"id": 3, "text": "Eier", "done": False})
    p[0]["next_item"] = 4
    pc.schreiben("lists.json", p)
    laptop.abgleichen()
    pc.abgleichen()
    laptop.abgleichen()
    for r in (laptop, pc):
        items = {i["id"]: i for i in r.json("lists.json")[0]["items"]}
        assert items[1]["done"] is True
        assert items[2]["text"] == "Vollkornbrot"
        assert items[3]["text"] == "Eier"
    assert not pc.zustand_lesen()["hinweise"]


def test_gleiche_neue_nummer_auf_beiden_rechnern_beide_bleiben(welt):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    for r, text in ((laptop, "Eier"), (pc, "Käse")):
        x = r.json("lists.json")
        x[0]["items"].append({"id": 3, "text": text, "done": False})
        x[0]["next_item"] = 4
        r.schreiben("lists.json", x)
    laptop.abgleichen()
    pc.abgleichen()
    laptop.abgleichen()
    for r in (laptop, pc):
        x = r.json("lists.json")[0]
        texte = sorted(i["text"] for i in x["items"])
        assert texte == ["Brot", "Eier", "Käse", "Milch"]
        ids = [i["id"] for i in x["items"]]
        assert len(set(ids)) == 4
        assert x["next_item"] > max(ids)        # die App vergibt keine Nummer doppelt
    assert laptop.json("lists.json") == pc.json("lists.json")


def test_derselbe_eintrag_regel_greift_mit_hinweis_und_nichts_verloren(welt):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    for r, text in ((laptop, "Hafermilch"), (pc, "Sojamilch")):
        x = r.json("lists.json")
        x[0]["items"][0]["text"] = text
        r.schreiben("lists.json", x)
    laptop.abgleichen()                         # Laptop war zuerst in der Mitte
    b = pc.abgleichen()
    assert pc.json("lists.json")[0]["items"][0]["text"] == "Hafermilch"
    assert any("lists.json" in h for h in b.hinweise)
    assert pc.zustand_lesen()["hinweise"]
    # Die Fassung des PCs ist aufgehoben, nicht weg.
    aufgehoben = list((pc.zustand / "konflikte").rglob("lists.json"))
    assert aufgehoben and "Sojamilch" in aufgehoben[0].read_text(encoding="utf-8")


def test_markdown_verschiedene_stellen_zusammen_gleiche_stelle_beide_fassungen(welt):
    text = "# Sasha\n\nmag Tee\n\nwohnt in Köln\n\nspielt Geige\n"
    laptop, pc = _zwei(welt, **{"gedaechtnis__sasha.md": text})
    laptop.schreiben("gedaechtnis/sasha.md", text.replace("mag Tee", "mag Kaffee"))
    pc.schreiben("gedaechtnis/sasha.md", text.replace("spielt Geige", "spielt Cello"))
    laptop.abgleichen()
    pc.abgleichen()
    t = pc.lesen("gedaechtnis/sasha.md")
    assert "mag Kaffee" in t and "spielt Cello" in t and "⟪" not in t
    # Jetzt dieselbe Zeile auf beiden Seiten.
    laptop.abgleichen()
    laptop.schreiben("gedaechtnis/sasha.md", t.replace("wohnt in Köln", "wohnt in Berlin"))
    pc.schreiben("gedaechtnis/sasha.md", t.replace("wohnt in Köln", "wohnt in Hamburg"))
    laptop.abgleichen()
    b = pc.abgleichen()
    t = pc.lesen("gedaechtnis/sasha.md")
    assert "wohnt in Berlin" in t and "wohnt in Hamburg" in t
    assert "zwei Fassungen" in t
    assert any("sasha.md" in h for h in b.hinweise)


def test_zaehler_beide_kosten_bleiben(welt):
    usage = {"tage": {"2026-10-08": {"euro": 1.0, "calls": 2}}}
    laptop, pc = _zwei(welt, **{"ai_usage.json": usage})
    for r, (e, c) in ((laptop, (1.5, 3)), (pc, (1.25, 4))):
        r.schreiben("ai_usage.json", {"tage": {"2026-10-08": {"euro": e, "calls": c}}})
    laptop.abgleichen()
    pc.abgleichen()
    assert pc.json("ai_usage.json")["tage"]["2026-10-08"] == {"euro": 1.75, "calls": 5}


def test_gespraeche_je_rechner_konfliktfrei(welt):
    laptop, pc = _zwei(welt, **{"gespraeche__g1__kopf.json": {"titel": "Hallo"}})
    laptop.schreiben("gespraeche/g1/laptop.jsonl", '{"id": "a", "text": "vom Laptop"}\n')
    pc.schreiben("gespraeche/g1/pc.jsonl", '{"id": "b", "text": "vom PC"}\n')
    laptop.abgleichen()
    pc.abgleichen()
    laptop.abgleichen()
    for r in (laptop, pc):
        assert "vom Laptop" in r.lesen("gespraeche/g1/laptop.jsonl")
        assert "vom PC" in r.lesen("gespraeche/g1/pc.jsonl")
    assert not laptop.zustand_lesen()["hinweise"]


def test_transkript_beide_haengen_an_nichts_doppelt(welt):
    laptop, pc = _zwei(welt, **{"ai_transcripts__2026-10.jsonl": '{"t": 1}\n'})
    laptop.schreiben("ai_transcripts/2026-10.jsonl", '{"t": 1}\n{"t": "laptop"}\n')
    pc.schreiben("ai_transcripts/2026-10.jsonl", '{"t": 1}\n{"t": "pc"}\n')
    laptop.abgleichen()
    pc.abgleichen()
    laptop.abgleichen()
    zeilen = pc.lesen("ai_transcripts/2026-10.jsonl").splitlines()
    assert sorted(zeilen) == sorted(['{"t": 1}', '{"t": "laptop"}', '{"t": "pc"}'])
    assert laptop.lesen("ai_transcripts/2026-10.jsonl") == pc.lesen("ai_transcripts/2026-10.jsonl")


# ── Löschen ────────────────────────────────────────────────────────────

def test_geloescht_bleibt_geloescht(welt):
    laptop, pc = _zwei(welt, **{"gedaechtnis__notizen__alt.md": "weg damit\n",
                                "lists.json": LISTE})
    laptop.pfad("gedaechtnis/notizen/alt.md").unlink()
    x = laptop.json("lists.json")
    x[0]["items"] = [i for i in x[0]["items"] if i["id"] != 2]   # Brot raus
    laptop.schreiben("lists.json", x)
    laptop.abgleichen()
    b = pc.abgleichen()
    assert not pc.da("gedaechtnis/notizen/alt.md")
    assert [i["text"] for i in pc.json("lists.json")[0]["items"]] == ["Milch"]
    # Nicht weggeworfen, sondern beiseitegelegt.
    assert b.beiseite == ["data/gedaechtnis/notizen/alt.md"]
    assert list((pc.zustand / "beiseite").rglob("alt.md"))
    # Und es kommt nicht zurück, egal wie oft abgeglichen wird.
    pc.abgleichen()
    laptop.abgleichen()
    assert not laptop.da("gedaechtnis/notizen/alt.md")
    assert "data/gedaechtnis/notizen/alt.md" not in welt.inhalt()["dateien"]
    assert "data/gedaechtnis/notizen/alt.md" in welt.inhalt()["geloescht"]


def test_ein_alter_rechner_bringt_geloeschtes_nicht_zurueck(welt):
    """Der PC kommt mit seinem alten rsync-Stand zum ersten Mal dazu — genau
    der Fall, in dem Gelöschtes bisher immer zurückkam."""
    laptop = welt.rechner("laptop")
    laptop.schreiben("gedaechtnis/notizen/alt.md", "weg damit\n")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    laptop.pfad("gedaechtnis/notizen/alt.md").unlink()
    laptop.abgleichen()
    pc = welt.rechner("pc")                     # alter Stand, nie abgeglichen
    pc.schreiben("gedaechtnis/notizen/alt.md", "weg damit\n")
    pc.schreiben("lists.json", LISTE[:0] + [dict(LISTE[0], name="Alter Name")])
    pc.schreiben("gedaechtnis/nur_pc.md", "nur hier\n")
    b = pc.abgleichen()
    assert b.art == "erstabgleich"
    assert not pc.da("gedaechtnis/notizen/alt.md")
    assert pc.json("lists.json") == LISTE                      # die Mitte gilt
    assert pc.lesen("gedaechtnis/nur_pc.md") == "nur hier\n"  # Neues kommt dazu
    assert list((pc.zustand / "konflikte").rglob("lists.json"))
    laptop.abgleichen()
    assert not laptop.da("gedaechtnis/notizen/alt.md")
    assert laptop.lesen("gedaechtnis/nur_pc.md") == "nur hier\n"


def test_loeschen_gegen_aendern_die_aenderung_gewinnt(welt):
    laptop, pc = _zwei(welt, **{"notes.json": [{"id": "n1", "title": "A", "blocks": []}]})
    laptop.pfad("notes.json").unlink()
    pc.schreiben("notes.json", [{"id": "n1", "title": "B", "blocks": []}])
    pc.abgleichen()
    b = laptop.abgleichen()
    assert laptop.json("notes.json")[0]["title"] == "B"
    assert b.hinweise


# ── Verschlüsselung und Schlüssel ──────────────────────────────────────

def test_kein_klartext_und_kein_schluessel_in_der_mitte(welt):
    laptop, pc = _zwei(welt, **{
        "lists.json": [{"id": "geheimliste", "name": "Zahnarzt Termin Dienstag",
                        "next_item": 1, "items": []}],
        "gedaechtnis__dossiers__oma_hilde.md": "Oma Hilde wohnt in der Lindenstraße 7\n",
        "gespraeche__g1__laptop.jsonl": '{"text": "Mein Lieblingsessen ist Linsensuppe"}\n',
    })
    pc.schreiben("notes.json", [{"id": "n", "title": "Passwortlose Notiz Kirschbaum"}])
    pc.abgleichen()
    key = (welt.tmp / "schluessel").read_text().strip()
    verraeterisch = ["Zahnarzt", "Lindenstra", "Linsensuppe", "Kirschbaum", "Hilde",
                     "geheimliste", "lists.json", "gedaechtnis", "dossiers", "gespraeche",
                     "notes.json", key, key[:20]]
    blobs = welt.blobs()
    assert blobs
    for pfad, inhalt in blobs:
        for wort in verraeterisch:
            assert wort.encode() not in inhalt, (pfad, wort)
            assert wort not in pfad, (pfad, wort)


def test_schluessel_liegt_nie_im_datenordner(welt):
    assert not os.path.realpath(welt.schluessel_pfad).startswith(str(welt.tmp / "laptop"))
    assert oct(os.stat(welt.schluessel_pfad).st_mode & 0o777) == "0o600"


def test_keys_und_kalender_gehen_nicht_in_die_mitte(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("ai_config.json", {"ANTHROPIC_API_KEY": "sk-ant-xyz"})
    laptop.schreiben("mail_secrets.enc", "x")
    laptop.schreiben("kalender/termine/a.ics", "BEGIN:VCALENDAR\n")
    laptop.schreiben("news_digest.json", {})
    laptop.schreiben("kalender_neben.json", {"puffer_min": 10})
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    drin = set(welt.inhalt()["dateien"])
    assert drin == {"data/kalender_neben.json", "data/lists.json"}


def test_ohne_schluessel_klarer_fehler_und_nichts_in_der_mitte(welt):
    os.remove(welt.schluessel_pfad)
    laptop = welt.rechner("laptop")
    laptop.schreiben("lists.json", LISTE)
    with pytest.raises(schluessel.SchluesselFehler, match="kein Abgleich-Schlüssel"):
        laptop.abgleichen()
    r = subprocess.run(["git", "-C", str(welt.mitte), "branch", "--list"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == ""
    assert "Schlüssel" in laptop.zustand_lesen()["fehler"]


def test_falscher_schluessel_klarer_fehler(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    os.remove(welt.schluessel_pfad)
    schluessel.anlegen()                       # ein anderer
    pc = welt.rechner("pc")
    with pytest.raises(schluessel.SchluesselFehler, match="passt nicht"):
        pc.abgleichen()
    assert not pc.da("lists.json")


def test_schluessel_anlegen_ueberschreibt_nie(welt):
    alt = open(welt.schluessel_pfad).read()
    with pytest.raises(schluessel.SchluesselFehler):
        schluessel.anlegen()
    assert open(welt.schluessel_pfad).read() == alt


def test_kaputte_schluessel_zeile_wird_abgelehnt(welt):
    with pytest.raises(schluessel.SchluesselFehler):
        schluessel.ablegen("das ist kein schlüssel")


# ── Absturz, gleichzeitige Rechner, App schreibt dazwischen ────────────

def test_absturz_vor_dem_senden_nichts_verloren(welt, monkeypatch):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    x = laptop.json("lists.json")
    x[0]["items"][0]["done"] = True
    laptop.schreiben("lists.json", x)

    echt = abgleich_mitte.GitMitte.senden

    def absturz(self, kennung):
        raise RuntimeError("Strom weg")
    monkeypatch.setattr(abgleich_mitte.GitMitte, "senden", absturz)
    with pytest.raises(RuntimeError):
        laptop.abgleichen()
    monkeypatch.setattr(abgleich_mitte.GitMitte, "senden", echt)
    assert laptop.json("lists.json")[0]["items"][0]["done"] is True
    laptop.abgleichen()
    pc.abgleichen()
    assert pc.json("lists.json")[0]["items"][0]["done"] is True


def test_absturz_nach_dem_senden_wird_zu_ende_gebracht(welt, monkeypatch):
    usage = {"tage": {"t": {"euro": 1.0}}}
    laptop, pc = _zwei(welt, **{"ai_usage.json": usage,
                                "ai_transcripts__2026-10.jsonl": "a\n"})
    pc.schreiben("ai_usage.json", {"tage": {"t": {"euro": 2.0}}})
    pc.schreiben("ai_transcripts/2026-10.jsonl", "a\npc\n")
    pc.abgleichen()
    laptop.schreiben("ai_usage.json", {"tage": {"t": {"euro": 1.5}}})
    laptop.schreiben("ai_transcripts/2026-10.jsonl", "a\nlaptop\n")
    echt = abgleich._vorhaben_abschliessen

    def absturz(wurzel, bericht=None):
        raise RuntimeError("Strom weg")
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", absturz)
    with pytest.raises(RuntimeError):
        laptop.abgleichen()
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", echt)
    laptop.abgleichen()                         # findet das Vorhaben, bringt es zu Ende
    # Nichts doppelt gezählt, nichts doppelt angehängt.
    assert laptop.json("ai_usage.json")["tage"]["t"]["euro"] == 2.5
    assert sorted(laptop.lesen("ai_transcripts/2026-10.jsonl").split()) == ["a", "laptop", "pc"]
    pc.abgleichen()
    assert pc.json("ai_usage.json")["tage"]["t"]["euro"] == 2.5


def test_jemand_war_schneller_neu_holen_und_beide_bleiben(welt, monkeypatch):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    x = pc.json("lists.json")
    x[0]["items"][0]["done"] = True
    pc.schreiben("lists.json", x)
    y = laptop.json("lists.json")
    y[0]["items"][1]["done"] = True
    laptop.schreiben("lists.json", y)
    echt = abgleich_mitte.GitMitte.holen
    einmal = {"n": 0}

    def holen_und_dazwischen(self):
        r = echt(self)
        if einmal["n"] == 0:
            einmal["n"] = 1
            pc.abgleichen()                     # der PC sendet genau jetzt
            laptop._als_ich()
        return r
    monkeypatch.setattr(abgleich_mitte.GitMitte, "holen", holen_und_dazwischen)
    laptop.abgleichen()
    monkeypatch.setattr(abgleich_mitte.GitMitte, "holen", echt)
    pc.abgleichen()
    for r in (laptop, pc):
        assert [i["done"] for i in r.json("lists.json")[0]["items"]] == [True, True]


def test_app_schreibt_waehrend_des_abgleichs_nichts_verloren(welt, monkeypatch):
    laptop, pc = _zwei(welt, **{"lists.json": LISTE})
    x = pc.json("lists.json")
    x[0]["items"][0]["done"] = True             # kommt gleich von der Mitte
    pc.schreiben("lists.json", x)
    pc.abgleichen()
    echt = abgleich._vorhaben_abschliessen

    def app_schreibt_dazwischen(wurzel, bericht=None):
        y = laptop.json("lists.json")
        y[0]["items"].append({"id": 3, "text": "Eier", "done": False})
        laptop.schreiben("lists.json", y)
        return echt(wurzel, bericht)
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", app_schreibt_dazwischen)
    laptop.abgleichen()
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", echt)
    # Die Datei der App wurde nicht überschrieben ...
    assert [i["text"] for i in laptop.json("lists.json")[0]["items"]][-1] == "Eier"
    # ... und der nächste Lauf führt beides zusammen.
    laptop.abgleichen()
    pc.abgleichen()
    for r in (laptop, pc):
        items = r.json("lists.json")[0]["items"]
        assert items[0]["done"] is True and items[-1]["text"] == "Eier"


# ── Weg umstellen, Zustand ─────────────────────────────────────────────

def test_umstellen_nur_nach_einem_abgleich(welt):
    laptop = welt.rechner("laptop")
    laptop._als_ich()
    with pytest.raises(abgleich_mitte.MitteFehler):
        abgleich.umstellen("mitte")
    assert abgleich.weg() == "rsync"
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    abgleich.umstellen("mitte")
    assert abgleich.weg() == "mitte"
    with pytest.raises(ValueError):
        abgleich.umstellen("ftp")
    abgleich.umstellen("rsync")
    assert abgleich.weg() == "rsync"


def test_unbekannte_mitte_art_klarer_fehler(welt, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    with pytest.raises(abgleich_mitte.MitteFehler, match="gibt es noch nicht"):
        welt.rechner("laptop").abgleichen()


def test_mitte_nicht_erreichbar_klarer_fehler(welt, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE", str(welt.tmp / "gibt-es-nicht.git"))
    with pytest.raises(abgleich_mitte.MitteFehler, match="nicht erreichbar"):
        welt.rechner("laptop").abgleichen()
