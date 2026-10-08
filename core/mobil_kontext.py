# core/mobil_kontext.py
#
# Das Kontextpaket fürs Handy: data/mobil/kontext.json. Das Handy ist ein
# eigener Knoten an der Mitte (memory/betrieb/abgleich.md, Abschnitt „Format
# für fremde Knoten"); es ruft das Sprachmodell selbst auf und braucht dafür
# denselben festen System-Prompt wie die Cloud-Schiene hier — Persona,
# Gedächtnis-Kopf, Hausregeln, Skill-Liste. Statt das in Dart nachzubauen,
# legt jeder Rechner beim Abgleich den fertigen Text ab (2026-10-08).
#
# Nie hinein: Schlüssel, Werkzeug-Schemas (das Handy hat keine Werkzeuge
# und hängt selbst einen Absatz an, was es nicht sehen kann).
#
# Schicht 3: liest den festen Teil von cloud._static_system — gebaut wird er
# dort, hier nur abgelegt. profil/ und werkzeug_* werden nicht angefasst.

import datetime
import json
import os

import ai_backends
import cloud
import dateien

PFAD = os.path.join("data", "mobil", "kontext.json")
VERSION = 1


def bauen() -> dict:
    """Das Paket: {version, stand, anbieter, modell, effort, system}."""
    anbieter = ai_backends.chat_provider()
    if anbieter == "auto":
        anbieter = ai_backends.cloud_provider() or "claude"
    return {
        "version": VERSION,
        "stand": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "anbieter": anbieter,
        "modell": ai_backends.chat_model(anbieter),
        "effort": ai_backends.chat_effort(),
        "system": cloud._static_system(None, False),
    }


def schreiben(wurzel) -> bool:
    """Paket unter <wurzel>/data/mobil/kontext.json ablegen — nur, wenn sich
    außer dem Zeitstempel etwas geändert hat (sonst wäre jeder Abgleich eine
    neue Fassung in der Mitte). → True, wenn geschrieben."""
    neu = bauen()
    pfad = os.path.join(wurzel, PFAD)
    try:
        with open(pfad, encoding="utf-8") as f:
            alt = json.load(f)
    except (OSError, ValueError):
        alt = {}
    if {k: v for k, v in alt.items() if k != "stand"} == {k: v for k, v in neu.items() if k != "stand"}:
        return False
    dateien.json_schreiben(pfad, neu)
    return True
