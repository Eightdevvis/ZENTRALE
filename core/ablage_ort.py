# core/ablage_ort.py
#
# WO die Ablage liegt — eine Stelle für die Ablage selbst (core/ablage.py)
# und für Abgleich und Datensicherung (core/abgleich_auswahl.py), die im
# Fundament stehen und die Ablage nicht importieren dürfen.
#
# 2026-10-11: die Ablage zog aus data/ablage/ (im Code-Ordner) nach
# ~/Zentrale/Ablage/ — Sasha: „der user soll nich im code fischen gehen
# müssen". Einstellung ablage_dir (Env ZENTRALE_ABLAGE_DIR; Tests) nennt den
# sichtbaren Ordner; Köpfe und Fassungen liegen versteckt darunter.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import os

import ai_config

STANDARD = "~/Zentrale/Ablage"
VERSTECKT = ".ablage"


def wurzel() -> str:
    """Der Ordner, den Sasha sieht."""
    eigen = str(ai_config.setting("ablage_dir") or "").strip() or STANDARD
    return os.path.abspath(os.path.expanduser(eigen))


def dokumente() -> str:
    """Köpfe und Fassungen (versteckt): <wurzel>/.ablage/dokumente/<id>/."""
    return os.path.join(wurzel(), VERSTECKT, "dokumente")
