"""Die Sandbox für run_code (core/sandbox.py, Phase 7, 2026-10-07).

Geprüft wird das Versprechen an Sasha: kein Netz, kein Blick auf seine
Dateien, Grenzen für Zeit, Speicher, Prozesse und Ausgabe — und nie ohne
Sandbox. Tests, die bwrap wirklich brauchen, überspringen sich, wo es fehlt
oder nicht startet (Pi).
"""
import os

import pytest

import sandbox
import werkzeug_register

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

braucht_bwrap = pytest.mark.skipif(not sandbox.verfuegbar(),
                                   reason="bubblewrap fehlt oder startet nicht")


# ── Abschottung ─────────────────────────────────────────────────────────

@braucht_bwrap
def test_python_laeuft_und_gibt_aus():
    erg = sandbox.ausfuehren("print(6 * 7)")
    assert erg["rc"] == 0 and erg["ausgabe"].strip() == "42"
    assert not erg["abgebrochen"]


@braucht_bwrap
def test_kein_netz():
    erg = sandbox.ausfuehren(
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), 2)\n"
        "    print('OFFEN')\n"
        "except OSError:\n"
        "    print('ZU')\n")
    assert erg["ausgabe"].strip() == "ZU"


@braucht_bwrap
@pytest.mark.parametrize("pfad", [
    os.path.join(ROOT, "data", "ai_config.json"),
    os.path.join(ROOT, "core", "sandbox.py"),
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~"),
    "/etc/passwd",
])
def test_sashas_dateien_sind_unsichtbar(pfad):
    erg = sandbox.ausfuehren(
        "import os\n"
        "print('DA' if os.path.exists(%r) else 'WEG')" % pfad)
    assert erg["rc"] == 0, erg
    assert erg["ausgabe"].strip() == "WEG"


@braucht_bwrap
def test_shell_sieht_auch_nichts_und_hat_leere_umgebung(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "geheim-123")
    erg = sandbox.ausfuehren(
        f"cat {ROOT}/data/ai_config.json; ls ~/.ssh; env; exit 3",
        sprache="shell")
    assert erg["rc"] == 3
    assert "geheim-123" not in erg["ausgabe"]
    assert "HOME=/arbeit" in erg["ausgabe"]
    assert "No such file" in erg["fehler"]


@braucht_bwrap
def test_system_ist_nur_lesend():
    for ziel in ("/usr/x", "/x", "/etc/x"):
        erg = sandbox.ausfuehren(f"echo x > {ziel}", sprache="shell")
        assert erg["rc"] != 0, ziel
    assert not os.path.exists("/usr/x")
    # /tmp ist beschreibbar (im Speicher, nach dem Lauf weg)
    assert sandbox.ausfuehren("echo x > /tmp/x", sprache="shell")["rc"] == 0


# ── Arbeitsordner ───────────────────────────────────────────────────────

@braucht_bwrap
def test_neue_datei_steht_in_dateien_neu():
    erg = sandbox.ausfuehren(
        "import os\nos.mkdir('unter')\nopen('unter/a.txt','w').write('hallo')")
    assert erg["dateien_neu"] == [{"name": "unter/a.txt", "bytes": 5}]
    assert os.path.isfile(os.path.join(erg["ordner"], "unter", "a.txt"))
    assert os.path.realpath(erg["ordner"]).startswith(
        os.path.realpath(sandbox.basis_ordner()))


@braucht_bwrap
def test_mitgegebene_dateien_sind_lesbar_aber_nicht_neu():
    erg = sandbox.ausfuehren("print(open('ein.csv').read())",
                             dateien={"ein.csv": "a,b"})
    assert erg["ausgabe"].strip() == "a,b"
    assert erg["dateien_neu"] == []


def test_dateiname_darf_nicht_aus_dem_ordner():
    erg = sandbox.ausfuehren("print(1)", dateien={"../raus.txt": "x"})
    assert erg["rc"] is None and "Ungültiger Dateiname" in erg["fehler"]


@braucht_bwrap
def test_symlink_nach_draussen_wird_nicht_verfolgt():
    """Ein Programm legt einen Verweis auf ~/.ssh an. Die Auflistung danach
    (außerhalb der Sandbox!) darf ihm nicht folgen."""
    ziel = os.path.expanduser("~")
    erg = sandbox.ausfuehren(f"import os; os.symlink({ziel!r}, 'heim')")
    assert erg["dateien_neu"] == [{"name": "heim", "bytes": len(ziel)}]


def test_aufraeumen_loescht_nur_alte(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_SANDBOX_DIR", str(tmp_path))
    alt, neu = tmp_path / "alt", tmp_path / "neu"
    alt.mkdir()
    neu.mkdir()
    (alt / "x").write_text("1")
    os.utime(alt, (0, 0))
    assert sandbox.aufraeumen(tage=7) == 1
    assert not alt.exists() and neu.exists()


# ── Grenzen ─────────────────────────────────────────────────────────────

@braucht_bwrap
def test_zeitlimit_beendet_endlosschleife():
    erg = sandbox.ausfuehren("while True: pass", zeitlimit_s=1)
    assert erg["abgebrochen"] is True
    assert erg["dauer_s"] < 5
    assert "Zeitlimit" in erg["fehler"]


@braucht_bwrap
def test_zeitlimit_nimmt_auch_kindprozesse_mit():
    erg = sandbox.ausfuehren("sleep 307 & sleep 307 & wait",
                             sprache="shell", zeitlimit_s=1)
    assert erg["abgebrochen"] is True
    # Nichts aus der Sandbox läuft weiter. (Nicht per pgrep -f: das fände
    # auch die Shell, die diesen Test gestartet hat.)
    reste = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if f.read() == b"sleep\x00307\x00":
                    reste.append(pid)
        except OSError:
            pass
    assert reste == []


@braucht_bwrap
def test_speichergrenze():
    erg = sandbox.ausfuehren("x = bytearray(900 * 1024 * 1024)\nprint('voll')")
    assert erg["rc"] != 0
    assert "MemoryError" in erg["fehler"]


@braucht_bwrap
def test_prozessgrenze_stoppt_forkbombe():
    erg = sandbox.ausfuehren(
        "import os, time\n"
        "n = 0\n"
        "try:\n"
        "    while True:\n"
        "        if os.fork() == 0:\n"
        "            time.sleep(2); os._exit(0)\n"
        "        n += 1\n"
        "except OSError:\n"
        "    print(n)\n", zeitlimit_s=10)
    assert erg["rc"] == 0, erg
    assert int(erg["ausgabe"]) < sandbox.PROZESSE_MAX


@braucht_bwrap
def test_ausgabe_wird_gekappt_kopf_und_schwanz():
    erg = sandbox.ausfuehren("for i in range(200000): print(i)")
    aus = erg["ausgabe"]
    assert len(aus) < sandbox.AUSGABE_MAX_ZEICHEN + 200
    assert aus.startswith("0\n1\n")
    assert aus.rstrip().endswith("199999")
    assert "gekürzt" in aus


@braucht_bwrap
def test_tmp_ist_begrenzt():
    if "--size" not in sandbox._tmp_argumente(sandbox._bwrap_pfad()):
        pytest.skip("bwrap zu alt für --size")
    erg = sandbox.ausfuehren(
        "for i in 1 2; do head -c 40000000 /dev/zero > /tmp/f$i || exit 9; done",
        sprache="shell")
    assert erg["rc"] == 9


def test_zeitlimit_wird_gedeckelt(monkeypatch):
    gesehen = {}

    def laufen(bwrap, arbeit, programm, sprache, zeit, vorher):
        gesehen["zeit"] = zeit
        return sandbox._ergebnis(rc=0)
    monkeypatch.setattr(sandbox, "_bwrap_pfad", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(sandbox, "_laufen", laufen)
    sandbox.ausfuehren("print(1)", zeitlimit_s=9999)
    assert gesehen["zeit"] == sandbox.ZEITLIMIT_MAX_S


# ── Nie ohne Sandbox ────────────────────────────────────────────────────

def test_ohne_bwrap_wird_nichts_ausgefuehrt(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "_bwrap_pfad", lambda: None)
    spur = tmp_path / "gelaufen"
    erg = sandbox.ausfuehren(f"open({str(spur)!r}, 'w').write('x')")
    assert erg["rc"] is None
    assert "nicht installiert" in erg["fehler"]
    assert not spur.exists()


def test_scheiterndes_bwrap_wird_fehler_kein_rueckfall(monkeypatch, tmp_path):
    """bwrap ist da, startet aber nicht (z. B. Namensräume gesperrt): das
    Programm darf dann auch nicht „einfach so" laufen."""
    falsch = tmp_path / "bwrap"
    falsch.write_text("#!/bin/sh\necho 'bwrap: kaputt' >&2\nexit 1\n")
    falsch.chmod(0o755)
    monkeypatch.setattr(sandbox, "_bwrap_pfad", lambda: str(falsch))
    spur = tmp_path / "gelaufen"
    erg = sandbox.ausfuehren(f"open({str(spur)!r}, 'w').write('x')")
    assert erg["rc"] is None
    assert "ließ sich nicht starten" in erg["fehler"]
    assert "kaputt" in erg["fehler"]
    assert not spur.exists()


def test_unbekannte_sprache():
    erg = sandbox.ausfuehren("x", sprache="ruby")
    assert erg["rc"] is None and "Unbekannte Sprache" in erg["fehler"]


# ── Das Werkzeug ────────────────────────────────────────────────────────

def test_run_code_ist_immer_gegatet():
    assert werkzeug_register.braucht_erlaubnis("run_code")
    assert werkzeug_register.braucht_erlaubnis("run_code", {"code": "print(1)"})
    assert "run_code" in werkzeug_register.immer_bestaetigen()


def test_frage_zeigt_sprache_und_anfang():
    code = "\n".join(f"zeile_{i} = {i}" for i in range(10))
    f = werkzeug_register.frage("run_code", {"code": code, "sprache": "shell"})
    assert "Shell-Programm" in f
    assert "zeile_0 = 0 ⏎ zeile_1 = 1" in f
    assert "zeile_5" not in f
    assert "(+6 Zeilen)" in f
    lang = werkzeug_register.frage("run_code", {"code": "x" * 5000})
    assert len(lang) < 500


def test_run_code_nur_auf_der_gross_schiene():
    klein = [w.name for w in werkzeug_register.auf_schiene("klein")]
    gross = [w.name for w in werkzeug_register.auf_schiene("gross")]
    assert "run_code" not in klein
    # Hinten an (Prompt-Cache): direkt hinter dem, was vor ihm da war. Seit
    # 07.10.2026 (Phase 4) kommen die Skill-Werkzeuge dahinter.
    assert gross[gross.index("log_series") + 1] == "run_code"


def test_werkzeug_ergebnis_fuers_modell(monkeypatch):
    import ki_werkzeuge
    gesehen = {}

    def falsch(code, sprache, zeitlimit_s):
        gesehen.update(code=code, sprache=sprache, zeit=zeitlimit_s)
        return sandbox._ergebnis(ausgabe="42\n", rc=0, dauer_s=0.1,
                                 dateien_neu=[{"name": "a.txt", "bytes": 3}],
                                 ordner="/home/sasha/.cache/geheim")
    monkeypatch.setattr(sandbox, "ausfuehren", falsch)
    text = ki_werkzeuge._verteilen(
        "run_code", {"code": "print(42)", "sprache": "shell", "zeitlimit": 500})
    assert gesehen == {"code": "print(42)", "sprache": "shell",
                       "zeit": sandbox.ZEITLIMIT_MAX_S}
    assert "Rückgabewert 0" in text and "42" in text
    assert "a.txt (3 Bytes)" in text
    assert "/home/sasha" not in text


def test_werkzeug_ohne_code():
    import ki_werkzeuge
    assert "kein Code" in ki_werkzeuge._verteilen("run_code", {"code": "  "})


def test_nicht_ausgefuehrt_ist_klar_erkennbar():
    text = sandbox.als_text(sandbox._ergebnis(fehler="bwrap fehlt"))
    assert text.startswith("[Nicht ausgeführt:")
