"""Nutzerordner (Input/, Output/), Suchen darin und Claude-Skills übernehmen
(2026-10-09).

Anlass: Gespräch 20261009-155510. Sasha legte „Chefkoch ai-v1.zip" (Claude-
Plugin: .claude-plugin/plugin.json + skills/chefkoch-ai/SKILL.md +
references/*.md) ab. list_files war bei 300 von 5.000 Dateien gekappt, die
KI sagte „ich seh keine chefkoch-Datei", übernehmen konnte sie ihn nicht.
Seitdem arbeitet der Assistent in einem Nutzerordner: Input/ (Sasha → KI),
Output/ (KI → Sasha); suchen wie find/grep, mit Angabe, wie vollständig.

Geprüft wird Verhalten: was danach in der Skill-Liste steht, was NICHT
geschrieben wird (Zip-Slip, Symlink, zu groß, Name schon da, außerhalb von
Input/), was die Suchen finden und wie ehrlich sie über sich selbst sind.
"""
import json
import os
import stat
import zipfile

import pytest

import context
import gedaechtnis
import ki_werkzeuge
import nutzer_ordner
import skill_import
import skills
import state
import werkzeug_befund
import werkzeug_register

SKILL_MD = ("---\nname: {name}\ndescription: {beschreibung}\n---\n\n"
            "# {name}\n\n1. Vorrat lesen.\n2. Gericht vorschlagen.\n")


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "Zentrale"))
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_DIR", str(leer / "anthropic"))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "anthropic" / "zentrale.json"))


@pytest.fixture
def ein():
    """Sashas Input/ (legt Input/ und Output/ an)."""
    from pathlib import Path
    return Path(nutzer_ordner.unterordner(nutzer_ordner.INPUT))


@pytest.fixture
def aus():
    from pathlib import Path
    return Path(nutzer_ordner.unterordner(nutzer_ordner.OUTPUT))


def _md(name, beschreibung="Wenn Sasha kochen will oder fragt, was im Kühlschrank ist."):
    return SKILL_MD.format(name=name, beschreibung=beschreibung)


def _zip(pfad, eintraege: dict, symlinks=()):
    """eintraege: {name im zip: text}; symlinks: Namen, die als Verweis
    (Unix-Modus) hineinkommen."""
    with zipfile.ZipFile(pfad, "w") as z:
        for name, text in eintraege.items():
            z.writestr(name, text)
        for name in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return str(pfad)


def _chefkoch_zip(wo):
    return _zip(wo / "Chefkoch ai-v1.zip", {
        ".claude-plugin/plugin.json": json.dumps({
            "name": "chefkoch-ai", "version": "1.0.0", "description": "Küche",
            "author": {"name": "Sasha", "email": "x@y.z"}, "license": "MIT"}),
        "skills/chefkoch-ai/SKILL.md": _md("chefkoch-ai"),
        "skills/chefkoch-ai/references/naehrstoffe.md": "Eisen, Zink.",
        "skills/chefkoch-ai/references/tricks.md": "Reis vorkochen.",
    })


def _stand():
    """Alles im Skill-Ordner, auch Verstecktes (Arbeitsordner müssen weg sein)."""
    wurzel = skills.ordner()
    raus = {}
    for ort, _, namen in os.walk(wurzel):
        for n in namen:
            p = os.path.join(ort, n)
            with open(p, "rb") as f:
                raus[os.path.relpath(p, wurzel)] = f.read()
        raus[os.path.relpath(ort, wurzel) + "/"] = b""
    return raus


def _import(pfad):
    return ki_werkzeuge._verteilen("import_skill", {"pfad": pfad})


# ── Der Nutzerordner ───────────────────────────────────────────────────

def test_nutzerordner_legt_input_und_output_an(tmp_path):
    w = nutzer_ordner.wurzel()
    assert w == os.path.realpath(tmp_path / "Zentrale")
    assert os.path.isdir(os.path.join(w, "Input")) and os.path.isdir(os.path.join(w, "Output"))


def test_aufloesen_fuehrt_nie_hinaus(ein, tmp_path):
    assert nutzer_ordner.aufloesen("x.zip") == str(ein / "x.zip")
    assert nutzer_ordner.aufloesen("Input/x.zip") == str(ein / "x.zip")
    assert nutzer_ordner.aufloesen("../geheim") is None
    assert nutzer_ordner.aufloesen("Input/../../geheim") is None
    assert nutzer_ordner.aufloesen("/etc/passwd") is None
    os.symlink(tmp_path, ein / "link")
    assert nutzer_ordner.aufloesen("Input/link/x") is None


def test_read_file_liest_aus_input(ein):
    (ein / "notiz.md").write_text("Eisen und Zink", encoding="utf-8")
    assert context.read_file("Input/notiz.md") == "Eisen und Zink"
    assert context.read_file(str(ein / "notiz.md")) == "Eisen und Zink"
    (ein / "api_token.txt").write_text("geheim", encoding="utf-8")
    assert context.read_file("Input/api_token.txt").startswith("[Zugriff verweigert")


# ── Übernehmen ─────────────────────────────────────────────────────────

def test_plugin_zip_wie_chefkoch(ein):
    _chefkoch_zip(ein)
    r = _import("Chefkoch ai-v1.zip")
    assert r.status == werkzeug_befund.OK, r
    assert r.startswith("Skill „chefkoch-ai“ ÜBERNOMMEN (aktiv): SKILL.md + 2 Referenzen.")
    assert "Sandbox" not in r                       # keine Skripte dabei
    s = {x["name"]: x for x in skills.alle()}["chefkoch-ai"]
    assert s["status"] == "aktiv" and s["herkunft"] == "sasha"
    with open(os.path.join(skills.ordner(), "chefkoch-ai", "_zentrale.json"), encoding="utf-8") as f:
        z = json.load(f)
    assert z["quelle"] == "Chefkoch ai-v1.zip (Plugin chefkoch-ai 1.0.0, Autor Sasha, Lizenz MIT)"
    assert "x@y.z" not in json.dumps(z)
    # Steht in der Liste, die in den Prompt geht, und ist ladbar.
    assert "- chefkoch-ai — Wenn Sasha kochen will" in skills.prompt_block()
    assert "Eisen" in skills.laden("chefkoch-ai", "references/naehrstoffe.md")
    assert not [n for n in os.listdir(skills.ordner()) if n.startswith(".")]
    assert os.path.isfile(ein / "Chefkoch ai-v1.zip")     # die Quelle bleibt liegen


def test_pfad_mit_input_davor_und_absolut(ein):
    _zip(ein / "a.zip", {"SKILL.md": _md("eins-a")})
    _zip(ein / "b.zip", {"SKILL.md": _md("eins-b")})
    assert _import("Input/a.zip").status == "ok"
    assert _import(str(ein / "b.zip")).status == "ok"


def test_ausserhalb_von_input_wird_abgelehnt(ein, aus, tmp_path):
    vorher = _stand()
    draussen = _chefkoch_zip(tmp_path)
    assert _import(draussen).code == "S-QUELLE-AUSSERHALB"
    assert _import("../Chefkoch ai-v1.zip").code == "S-QUELLE-AUSSERHALB"
    _zip(aus / "c.zip", {"SKILL.md": _md("aus-output")})
    assert _import("Output/c.zip").code == "S-QUELLE-AUSSERHALB"      # nur Input/
    os.symlink(draussen, ein / "verweis.zip")
    assert _import("verweis.zip").code == "S-QUELLE-AUSSERHALB"
    assert _stand() == vorher


def test_mehrere_skills_im_plugin_und_skripte(ein):
    _zip(ein / "paket.zip", {
        ".claude-plugin/plugin.json": "{}",
        "skills/eins/SKILL.md": _md("eins"),
        "skills/zwei/SKILL.md": _md("zwei"),
        "skills/zwei/scripts/rechne.py": "print(1)",
    })
    r = _import("paket.zip")
    assert r.status == "ok", r
    assert "„eins“: SKILL.md;" in r and "„zwei“: SKILL.md + 1 Skript" in r
    assert "Sandbox: run_code mit skill=„zwei“" in r
    assert {"eins", "zwei"} <= {s["name"] for s in skills.aktive()}


def test_ganz_oder_gar_nicht_wenn_einer_kaputt_ist(ein):
    vorher = _stand()
    _zip(ein / "paket.zip", {
        ".claude-plugin/plugin.json": "{}",
        "skills/gut/SKILL.md": _md("gut"),
        "skills/kaputt/SKILL.md": "# ohne Kopf\n\nText.",
    })
    r = _import("paket.zip")
    assert r.status == "fehlgeschlagen" and r.code == "S-SKILL-UNGUELTIG", r
    assert _stand() == vorher


def test_nackter_ordner(ein):
    o = ein / "wochenplan"
    (o / "references").mkdir(parents=True)
    (o / "SKILL.md").write_text(_md("wochenplan", "Wenn Sasha die Woche plant."), encoding="utf-8")
    (o / "references" / "a.md").write_text("A", encoding="utf-8")
    (o / ".DS_Store").write_text("x", encoding="utf-8")
    (o / "api_key.txt").write_text("geheim", encoding="utf-8")
    r = _import("wochenplan")
    assert r.startswith("Skill „wochenplan“ ÜBERNOMMEN (aktiv): SKILL.md + 1 Referenz."), r
    assert "2 Dateien ausgelassen" in r
    ziel = os.path.join(skills.ordner(), "wochenplan")
    assert not os.path.exists(os.path.join(ziel, "api_key.txt"))
    assert os.path.isfile(o / "SKILL.md")


def test_zip_mit_skill_md_in_der_wurzel_und_mit_huellordner(ein):
    _zip(ein / "a.zip", {"SKILL.md": _md("wurzel-skill")})
    _zip(ein / "b.zip", {"Hülle v2/.claude-plugin/plugin.json": "{}",
                         "Hülle v2/skills/in-huelle/SKILL.md": _md("in-huelle")})
    assert _import("a.zip").status == "ok"
    assert _import("b.zip").status == "ok"
    assert {"wurzel-skill", "in-huelle"} <= {s["name"] for s in skills.aktive()}


def test_die_skill_md_selbst_genannt(ein):
    (ein / "selbst").mkdir()
    (ein / "selbst" / "SKILL.md").write_text(_md("selbst"), encoding="utf-8")
    assert _import("selbst/SKILL.md").status == "ok"


# ── Abbrüche: nichts geschrieben ───────────────────────────────────────

@pytest.mark.parametrize("eintraege, symlinks", [
    ({"../x/SKILL.md": _md("x")}, ()),
    ({"skills/a/../../../boese.md": "x", "SKILL.md": _md("a")}, ()),
    ({"/etc/boese.md": "x", "SKILL.md": _md("a")}, ()),
    ({"SKILL.md": _md("a")}, ("references/link.md",)),
])
def test_unsichere_zip_wird_nicht_ausgepackt(ein, eintraege, symlinks):
    vorher = _stand()
    _zip(ein / "boese.zip", eintraege, symlinks)
    r = _import("boese.zip")
    assert r.status == "fehlgeschlagen" and r.code == "S-UNSICHER", r
    assert "nichts übernommen" in r
    assert _stand() == vorher
    assert not (ein / "x").exists() and not (ein.parent / "boese.md").exists()


def test_symlink_im_ordner(ein):
    o = ein / "mit-link"
    o.mkdir()
    (o / "SKILL.md").write_text(_md("mit-link"), encoding="utf-8")
    os.symlink("/etc/hostname", o / "verweis.md")
    vorher = _stand()
    assert _import("mit-link").code == "S-UNSICHER"
    assert _stand() == vorher


def test_zu_gross_und_zu_viele(ein, monkeypatch):
    vorher = _stand()
    monkeypatch.setattr(skill_import, "MAX_BYTES", 1000)
    _zip(ein / "gross.zip", {"SKILL.md": _md("gross"), "assets/x.bin": "0" * 5000})
    assert _import("gross.zip").code == "S-ZU-GROSS"
    monkeypatch.setattr(skill_import, "MAX_BYTES", 10 ** 7)
    monkeypatch.setattr(skill_import, "MAX_DATEIEN", 3)
    _zip(ein / "viele.zip", {"SKILL.md": _md("viele")} | {f"references/{i}.md": "x" for i in range(5)})
    assert _import("viele.zip").code == "S-ZU-GROSS"
    assert _stand() == vorher


def test_zip_bombe_wird_beim_auspacken_gestoppt(ein, monkeypatch):
    """Die Größe im Zip-Verzeichnis kann lügen — gezählt wird beim Auspacken."""
    _zip(ein / "bombe.zip", {"SKILL.md": _md("bombe"), "x.bin": "0" * 1500})
    echt = zipfile.ZipFile.infolist

    def luegen(self):
        infos = echt(self)
        for i in infos:
            i.file_size = 1
        return infos
    monkeypatch.setattr(zipfile.ZipFile, "infolist", luegen)
    monkeypatch.setattr(skill_import, "MAX_BYTES", 1000)
    vorher = _stand()
    assert _import("bombe.zip").code in ("S-ZU-GROSS", "S-ZIP-KAPUTT")
    assert _stand() == vorher


def test_name_gibt_es_schon(ein):
    _chefkoch_zip(ein)
    assert _import("Chefkoch ai-v1.zip").status == "ok"
    vorher = _stand()
    _zip(ein / "Chefkoch v2.zip", {"SKILL.md": _md("chefkoch-ai", "Andere Fassung.")})
    r = _import("Chefkoch v2.zip")
    assert r.status == "fehlgeschlagen" and r.code == "S-SKILL-GIBT-ES", r
    assert "chefkoch-ai" in r
    assert _stand() == vorher


@pytest.mark.parametrize("eintraege, code", [
    ({"liesmich.txt": "nichts"}, "S-KEIN-SKILL"),
    ({"SKILL.md": "---\nname: Großer Name\ndescription: x\n---\n\nText."}, "S-SKILL-UNGUELTIG"),
    ({"SKILL.md": "---\nname: ohne-beschreibung\n---\n\nText."}, "S-SKILL-UNGUELTIG"),
    ({"SKILL.md": "---\nname: leer\ndescription: Wenn x.\n---\n"}, "S-SKILL-UNGUELTIG"),
])
def test_kein_oder_ungueltiger_skill(ein, eintraege, code):
    vorher = _stand()
    _zip(ein / "x.zip", eintraege)
    assert _import("x.zip").code == code
    assert _stand() == vorher


def test_keine_zip_fehlt_oder_versteckt(ein):
    (ein / "text.zip").write_text("keine zip", encoding="utf-8")
    assert _import("text.zip").code == "S-ZIP-KAPUTT"
    assert _import("gibtsnicht.zip").code == "S-QUELLE-FEHLT"
    assert _import("").code == "S-QUELLE-FEHLT"
    _zip(ein / ".versteckt.zip", {"SKILL.md": _md("versteckt")})
    assert _import(".versteckt.zip").code == "S-QUELLE-GESPERRT"


def test_jeder_neue_code_ist_erklaert():
    import fehlercodes
    for code in ("S-QUELLE-FEHLT", "S-QUELLE-AUSSERHALB", "S-QUELLE-GESPERRT", "S-ZIP-KAPUTT",
                 "S-UNSICHER", "S-ZU-GROSS", "S-KEIN-SKILL", "S-SKILL-UNGUELTIG",
                 "S-SKILL-GIBT-ES"):
        assert fehlercodes.bekannt(code), code


# ── Gate und Frage ─────────────────────────────────────────────────────

def test_gate_fragt_mit_name_und_datei(ein):
    w = werkzeug_register.eintrag("import_skill")
    assert w.klein is None and w.schreibt and w.erlaubnis is True and not w.immer_erlaubbar
    assert werkzeug_register.braucht_erlaubnis("import_skill", {"pfad": "x"})
    _chefkoch_zip(ein)
    frage = werkzeug_register.frage("import_skill", {"pfad": "Chefkoch ai-v1.zip"})
    assert frage.startswith("Skill „chefkoch-ai“ aus „Chefkoch ai-v1.zip“ übernehmen?"), frage
    assert "chefkoch-ai" not in os.listdir(skills.ordner())     # die Frage übernimmt nichts
    assert "nix.zip" in werkzeug_register.frage("import_skill", {"pfad": "nix.zip"})


@pytest.mark.parametrize("name", ["find_files", "search_files"])
def test_suchen_sind_frei_und_nur_gross(name):
    w = werkzeug_register.eintrag(name)
    assert w.klein is None and w.gross and w.erlaubnis is False and not w.schreibt


# ── find_files ─────────────────────────────────────────────────────────

def _finden(**args):
    return ki_werkzeuge._verteilen("find_files", args)


def test_find_files_findet_die_chefkoch_zip(ein, aus):
    _chefkoch_zip(ein)
    (aus / "rezepte").mkdir()
    (aus / "rezepte" / "chefkoch-notiz.md").write_text("x", encoding="utf-8")
    r = _finden(muster="*chefkoch*")
    assert r.vollstaendig is True
    zeilen = r.splitlines()
    assert zeilen[0] == "Suche vollständig: 2 Treffer — durchsucht: Input/, Output/ (2 Dateien)."
    assert zeilen[1].startswith("  Input/Chefkoch ai-v1.zip  (")      # flach zuerst
    assert zeilen[2] == "  Output/rezepte/chefkoch-notiz.md  (1 KB)"
    # Namensteil ohne Platzhalter: Groß/Klein und Trenner egal.
    assert "Input/Chefkoch ai-v1.zip" in _finden(muster="chefkoch-ai")
    assert "Input/Chefkoch ai-v1.zip" in _finden(muster="*.ZIP")
    assert "Output/rezepte/  (Ordner)" in _finden(muster="rezepte")
    assert "chefkoch-notiz" not in _finden(muster="*.zip")


def test_find_files_ohne_treffer_ist_vollstaendig_mit_null(ein):
    r = _finden(muster="*.pdf")
    assert r.splitlines()[0].startswith("Suche vollständig: 0 Treffer — durchsucht: Input/, Output/")
    assert r.vollstaendig is True


def test_find_files_nur_im_nutzerordner_ohne_verstecktes_und_secrets(ein, tmp_path, monkeypatch):
    """Kein Weg in den Projektbaum oder den Lernordner (Sasha, 09.10.)."""
    lern = tmp_path / "codicus" / "learning"
    lern.mkdir(parents=True)
    (lern / "chefkoch.c").write_text("x", encoding="utf-8")
    monkeypatch.setattr(context, "_CODICUS", str(tmp_path / "codicus"))
    (ein / ".git").mkdir()
    (ein / ".git" / "chefkoch.txt").write_text("x", encoding="utf-8")
    (ein / "chefkoch_token.txt").write_text("x", encoding="utf-8")
    r = _finden(muster="*chefkoch*")
    assert "Suche vollständig: 0 Treffer" in r
    assert "learning" not in r and ".git" not in r and "token" not in r
    for weg in ("../codicus", "/etc", str(tmp_path)):
        assert "nicht in Input/ oder Output/" in _finden(muster="*", ordner=weg)


def test_find_files_zaehlt_alle_zeigt_50(ein):
    for i in range(60):
        (ein / f"bild_{i:02}.png").write_text("x", encoding="utf-8")
    r = _finden(muster="bild*", ordner="Input")
    zeilen = r.splitlines()
    assert zeilen[0] == "Suche vollständig: 60 Treffer — durchsucht: Input/ (60 Dateien)."
    assert len(zeilen) == 52 and zeilen[-1].startswith("  … 10 weitere Treffer nicht gezeigt")


def test_find_files_bricht_ehrlich_ab(ein, monkeypatch):
    import nutzer_suche
    monkeypatch.setattr(nutzer_suche, "MAX_GANG", 3)
    for i in range(5):
        (ein / f"d{i}.txt").write_text("x", encoding="utf-8")
    r = _finden(muster="*.txt")
    assert r.startswith("Suche NICHT vollständig: abgebrochen nach 3 Dateien")
    assert r.vollstaendig is False


def test_find_files_ohne_muster():
    assert _finden(muster=" ").startswith("[Fehler")


# ── search_files ───────────────────────────────────────────────────────

def _grep(**args):
    return ki_werkzeuge._verteilen("search_files", args)


def test_search_files_wie_grep(ein, aus):
    (ein / "rezepte.md").write_text("Linsen\nReis mit EISEN\nnichts\n", encoding="utf-8")
    (aus / "plan.txt").write_text("eisen am montag", encoding="utf-8")
    (ein / "bild.png").write_bytes(b"\x89PNG\x00eisen")
    r = _grep(text="Eisen")
    zeilen = r.splitlines()
    assert zeilen[0] == ("Suche vollständig: 2 Treffer — durchsucht: Input/, Output/ "
                         "(3 Dateien). Übersprungen: 1 Binärdateien.")
    assert "  Input/rezepte.md:2: Reis mit EISEN" in zeilen
    assert "  Output/plan.txt:1: eisen am montag" in zeilen
    assert r.vollstaendig is True
    nur_md = _grep(text="eisen", muster="*.md")
    assert "plan.txt" not in nur_md and "rezepte.md:2" in nur_md
    assert _grep(text="gibt es nicht").splitlines()[0].startswith("Suche vollständig: 0 Treffer")


def test_search_files_grenzen(ein, monkeypatch):
    import nutzer_suche
    (ein / "viel.txt").write_text("treffer\n" * 150, encoding="utf-8")
    r = _grep(text="treffer")
    assert r.startswith("Suche NICHT vollständig: abgebrochen nach 100 Treffern")
    assert len(r.splitlines()) == 101 and r.vollstaendig is False
    monkeypatch.setattr(nutzer_suche, "MAX_DATEI_BYTES", 10)
    r = _grep(text="treffer")
    assert r.startswith("Suche NICHT vollständig: 1 Dateien über") and r.vollstaendig is False


def test_search_files_liest_keine_secrets(ein):
    (ein / "passwort.txt").write_text("eisen", encoding="utf-8")
    assert "Suche vollständig: 0 Treffer" in _grep(text="eisen")


# ── list_files ─────────────────────────────────────────────────────────

def _auf_gross(name, args):
    marke = werkzeug_befund.schiene_setzen("gross")
    try:
        return ki_werkzeuge._verteilen(name, args)
    finally:
        werkzeug_befund.schiene_zuruecksetzen(marke)


def test_list_files_gross_zeigt_einen_ordner_wie_ls(ein, aus):
    _chefkoch_zip(ein)
    (ein / "fotos").mkdir()
    (ein / "fotos" / "a.jpg").write_text("x", encoding="utf-8")
    r = _auf_gross("list_files", {})
    assert r.splitlines() == ["Input/ — 2 Einträge, vollständig.", "  fotos/",
                              "  Chefkoch ai-v1.zip  (1 KB)"]
    assert _auf_gross("list_files", {"ordner": "Output"}) == "Output/ — leer."
    assert "fotos/ — 1 Einträge" in _auf_gross("list_files", {"ordner": "Input/fotos"})
    assert _auf_gross("list_files", {"ordner": "/etc"}).startswith("[Fehler")


def test_list_files_klein_wie_bisher(ein):
    """klein (lokales qwen) ist auf die alte Gesamtliste gemessen."""
    r = ki_werkzeuge._verteilen("list_files", {})
    assert r.startswith("Verfügbare Dateien:\n") and "Input/" not in r.splitlines()[0]
