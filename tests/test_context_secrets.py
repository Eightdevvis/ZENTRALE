# tests/test_context_secrets.py
#
# Regression für die Secret-Sperre in core/context.py.
#
# Vorgeschichte (2026-07-17): die Whitelist der lokalen KI ist bewusst breit
# (`data/*.json` deckt alle Logs ab) — und genau dadurch fiel der API-Key-Store
# data/ai_config.json mit hinein. Die KI konnte per read_file den DASHSCOPE-Key
# im Klartext lesen. Fix: eine Denylist, die VOR der Whitelist greift und nach
# Basename matcht. Dieser Test friert das ein: der Key-Store bleibt für die KI
# tabu, egal wie die Whitelist wächst.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import context


def _denied(out: str) -> bool:
    return isinstance(out, str) and out.startswith("[Zugriff verweigert")


def test_key_store_is_blocked():
    # data/ai_config.json MATCHT die Whitelist (`data/*.json`) — trotzdem tabu.
    out = context.read_file("data/ai_config.json")
    assert _denied(out), out
    assert "DASHSCOPE" not in out and "cloud_enabled" not in out


def test_legacy_config_blocked():
    out = context.read_file("data/tutor_config.json")
    assert _denied(out), out


def test_traversal_to_secret_blocked():
    # Umweg über .. darf die Sperre nicht aushebeln.
    out = context.read_file("data/../data/ai_config.json")
    assert _denied(out), out


def test_secret_suffixes_blocked():
    for name in ("data/mail.enc", "data/foo.key", "data/cert.pem"):
        out = context.read_file(name)
        assert _denied(out), (name, out)


def test_secret_never_listed():
    # list_files darf die Existenz des Key-Stores nicht mal verraten.
    files = context.list_available_files()
    assert not any(os.path.basename(f) in ("ai_config.json", "tutor_config.json")
                   for f in files), files


def test_normal_data_still_readable():
    # Die Sperre darf legitime Logs nicht mitreißen: eine harmlose data/*.json
    # bleibt lesbar (oder sauber 'nicht gefunden', wenn sie fehlt) — jedenfalls
    # NICHT als Secret abgelehnt.
    out = context.read_file("data/sleep_quality.json")
    assert not out.startswith("[Zugriff verweigert: Secret"), out


def test_source_code_still_readable():
    # Die KI darf ihren eigenen Code weiter lesen (core/*.py), auch ai_config.py
    # (Quellcode, kein Secret — der Key steht in der .json, nicht im .py).
    out = context.read_file("core/context.py")
    assert not out.startswith("[Zugriff verweigert"), out
