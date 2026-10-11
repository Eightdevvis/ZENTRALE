"""Claude-Skills übernehmen — aus einer Zip in der Ablage (2026-10-09;
seit 2026-10-11 aus der Ablage statt aus Input/).

Anlass: Gespräch 20261009-155510. Sasha legte „Chefkoch ai-v1.zip" (Claude-
Plugin: .claude-plugin/plugin.json + skills/chefkoch-ai/SKILL.md +
references/*.md) ab; übernehmen ging nicht. Seit 2026-10-11 ist die Ablage
der eine Ort für Dateien (Sasha: „ja einfach nur die ablage dann") — er legt
die Zip in ~/Zentrale/Ablage oder hängt sie an, import_skill nimmt die id.

Geprüft wird Verhalten: was danach in der Skill-Liste steht, was NICHT
geschrieben wird (Zip-Slip, Symlink, zu groß, Name schon da, keine Zip).
"""
import io
import json
import os
import stat
import zipfile

import pytest

import ablage
import gedaechtnis
import ki_werkzeuge
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
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_DIR", str(leer / "anthropic"))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "anthropic" / "zentrale.json"))


def _md(name, beschreibung="Wenn Sasha kochen will oder fragt, was im Kühlschrank ist."):
    return SKILL_MD.format(name=name, beschreibung=beschreibung)


def _zip_bytes(eintraege: dict, symlinks=()) -> bytes:
    roh = io.BytesIO()
    with zipfile.ZipFile(roh, "w") as z:
        for name, text in eintraege.items():
            z.writestr(name, text)
        for name in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return roh.getvalue()


def _zip(titel, eintraege: dict, symlinks=()) -> str:
    """Eine Zip in Sashas Ablage (wie angehängt/eingeworfen) → id."""
    return ablage.anlegen(titel, _zip_bytes(eintraege, symlinks), "zip",
                          herkunft="einwurf")["id"]


def _chefkoch_zip():
    return _zip("Chefkoch ai-v1.zip", {
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


def _import(doc_id):
    return ki_werkzeuge._verteilen("import_skill", {"id": doc_id})


# ── Übernehmen ─────────────────────────────────────────────────────────

def test_plugin_zip_wie_chefkoch():
    doc_id = _chefkoch_zip()
    r = _import(doc_id)
    assert r.status == werkzeug_befund.OK, r
    assert r.startswith("Skill „chefkoch-ai“ ÜBERNOMMEN (aktiv): SKILL.md + 2 Referenzen.")
    assert "Sandbox" not in r                       # keine Skripte dabei
    s = {x["name"]: x for x in skills.alle()}["chefkoch-ai"]
    assert s["status"] == "aktiv" and s["herkunft"] == "sasha"
    with open(os.path.join(skills.ordner(), "chefkoch-ai", "_zentrale.json"), encoding="utf-8") as f:
        z = json.load(f)
    assert z["quelle"] == "Chefkoch ai-v1.zip (Plugin chefkoch-ai 1.0.0, Autor Sasha, Lizenz MIT)"
    assert "x@y.z" not in json.dumps(z)
    assert "- chefkoch-ai — Wenn Sasha kochen will" in skills.prompt_block()
    assert "Eisen" in skills.laden("chefkoch-ai", "references/naehrstoffe.md")
    assert not [n for n in os.listdir(skills.ordner()) if n.startswith(".")]
    assert ablage.gibt_es(doc_id) and not ablage.im_papierkorb(ablage.kopf(doc_id))


def test_mehrere_skills_im_plugin_und_skripte():
    r = _import(_zip("paket.zip", {
        ".claude-plugin/plugin.json": "{}",
        "skills/eins/SKILL.md": _md("eins"),
        "skills/zwei/SKILL.md": _md("zwei"),
        "skills/zwei/scripts/rechne.py": "print(1)",
    }))
    assert r.status == "ok", r
    assert "„eins“: SKILL.md;" in r and "„zwei“: SKILL.md + 1 Skript" in r
    assert "Sandbox: run_code mit skill=„zwei“" in r
    assert {"eins", "zwei"} <= {s["name"] for s in skills.aktive()}


def test_ganz_oder_gar_nicht_wenn_einer_kaputt_ist():
    vorher = _stand()
    r = _import(_zip("paket.zip", {
        ".claude-plugin/plugin.json": "{}",
        "skills/gut/SKILL.md": _md("gut"),
        "skills/kaputt/SKILL.md": "# ohne Kopf\n\nText.",
    }))
    assert r.status == "fehlgeschlagen" and r.code == "S-SKILL-UNGUELTIG", r
    assert _stand() == vorher


def test_zip_mit_skill_md_in_der_wurzel_und_mit_huellordner():
    assert _import(_zip("a.zip", {"SKILL.md": _md("wurzel-skill")})).status == "ok"
    assert _import(_zip("b.zip", {"Hülle v2/.claude-plugin/plugin.json": "{}",
                                  "Hülle v2/skills/in-huelle/SKILL.md": _md("in-huelle")})
                   ).status == "ok"
    assert {"wurzel-skill", "in-huelle"} <= {s["name"] for s in skills.aktive()}


def test_ausgelassen_wird_verstecktes_und_schluessel():
    r = _import(_zip("w.zip", {"wochenplan/SKILL.md": _md("wochenplan", "Wenn Sasha plant."),
                               "wochenplan/references/a.md": "A",
                               "wochenplan/.DS_Store": "x", "wochenplan/api_key.txt": "geheim"}))
    assert r.startswith("Skill „wochenplan“ ÜBERNOMMEN (aktiv): SKILL.md + 1 Referenz."), r
    assert "2 Dateien ausgelassen" in r
    assert not os.path.exists(os.path.join(skills.ordner(), "wochenplan", "api_key.txt"))


# ── Abbrüche: nichts geschrieben ───────────────────────────────────────

@pytest.mark.parametrize("eintraege, symlinks", [
    ({"../x/SKILL.md": _md("x")}, ()),
    ({"skills/a/../../../boese.md": "x", "SKILL.md": _md("a")}, ()),
    ({"/etc/boese.md": "x", "SKILL.md": _md("a")}, ()),
    ({"SKILL.md": _md("a")}, ("references/link.md",)),
])
def test_unsichere_zip_wird_nicht_ausgepackt(eintraege, symlinks):
    vorher = _stand()
    r = _import(_zip("boese.zip", eintraege, symlinks))
    assert r.status == "fehlgeschlagen" and r.code == "S-UNSICHER", r
    assert "nichts übernommen" in r
    assert _stand() == vorher


def test_zu_gross_und_zu_viele(monkeypatch):
    vorher = _stand()
    monkeypatch.setattr(skill_import, "MAX_BYTES", 1000)
    assert _import(_zip("gross.zip", {"SKILL.md": _md("gross"), "assets/x.bin": "0" * 5000})
                   ).code == "S-ZU-GROSS"
    monkeypatch.setattr(skill_import, "MAX_BYTES", 10 ** 7)
    monkeypatch.setattr(skill_import, "MAX_DATEIEN", 3)
    assert _import(_zip("viele.zip", {"SKILL.md": _md("viele")}
                        | {f"references/{i}.md": "x" for i in range(5)})).code == "S-ZU-GROSS"
    assert _stand() == vorher


def test_name_gibt_es_schon():
    assert _import(_chefkoch_zip()).status == "ok"
    vorher = _stand()
    r = _import(_zip("Chefkoch v2.zip", {"SKILL.md": _md("chefkoch-ai", "Andere Fassung.")}))
    assert r.status == "fehlgeschlagen" and r.code == "S-SKILL-GIBT-ES", r
    assert _stand() == vorher


@pytest.mark.parametrize("eintraege, code", [
    ({"liesmich.txt": "nichts"}, "S-KEIN-SKILL"),
    ({"SKILL.md": "---\nname: Großer Name\ndescription: x\n---\n\nText."}, "S-SKILL-UNGUELTIG"),
    ({"SKILL.md": "---\nname: ohne-beschreibung\n---\n\nText."}, "S-SKILL-UNGUELTIG"),
    ({"SKILL.md": "---\nname: leer\ndescription: Wenn x.\n---\n"}, "S-SKILL-UNGUELTIG"),
])
def test_kein_oder_ungueltiger_skill(eintraege, code):
    vorher = _stand()
    assert _import(_zip("x.zip", eintraege)).code == code
    assert _stand() == vorher


def test_keine_zip_oder_fehlt():
    text = ablage.anlegen("notiz.md", "keine zip", "markdown", herkunft="einwurf")["id"]
    assert _import(text).code == "S-KEINE-ZIP"
    assert _import("gibts-nicht-0000").code == "S-QUELLE-FEHLT"
    assert _import("").code == "S-QUELLE-FEHLT"


def test_jeder_code_ist_erklaert():
    import fehlercodes
    for code in ("S-QUELLE-FEHLT", "S-KEINE-ZIP", "S-ZIP-KAPUTT", "S-UNSICHER", "S-ZU-GROSS",
                 "S-KEIN-SKILL", "S-SKILL-UNGUELTIG", "S-SKILL-GIBT-ES"):
        assert fehlercodes.bekannt(code), code


# ── Gate und Frage ─────────────────────────────────────────────────────

def test_gate_fragt_mit_name_und_datei():
    w = werkzeug_register.eintrag("import_skill")
    assert w.klein is None and w.schreibt and w.erlaubnis is True and not w.immer_erlaubbar
    doc_id = _chefkoch_zip()
    frage = werkzeug_register.frage("import_skill", {"id": doc_id})
    assert frage.startswith("Skill „chefkoch-ai“ aus „Chefkoch ai-v1.zip“ übernehmen?"), frage
    assert "chefkoch-ai" not in os.listdir(skills.ordner())     # die Frage übernimmt nichts
    assert "nix" in werkzeug_register.frage("import_skill", {"id": "nix"})
