"""`zentrale setup` — der Einrichtungs-Assistent. Seit 2026-10-30 (Bauplan
memory/hub/building_kit_plan.md 5.1) ein geführter Dialog in Schritten:
zentrale_cli/wizard.py. Hier bleiben nur der Einstieg und zwei Bausteine,
die der Assistent nutzt. Die Wahl der Apps gilt je Gerät (core/abgleich_apps.py)."""

from zentrale_cli import befehle
from zentrale_cli.texte import t

import abgleich_apps                  # noqa: E402
import ai_config                      # noqa: E402


def apps_ankreuzen(term, offer, table):
    """Pick apps one by one → {name: yes/no}, or None (cancelled)."""
    before = abgleich_apps.entscheidungen()
    on = {n for n in offer if before is None or before.get(n, True)}
    entries = [(n, *befehle.app_name(n, table)) for n in offer]
    chosen = term.ankreuzen(t("setup_pick_title"), entries, on)
    return None if chosen is None else {n: n in chosen for n in offer}


def cloud_einschalten():
    """Dieses Gerät gleicht ab jetzt über die Cloud ab (Einstellungen dieses
    Geräts, data/ai_config.json)."""
    ai_config.set_override("abgleich_mitte_art", "http", persist=True)
    ai_config.set_override("abgleich_weg", "mitte", persist=True)


def setup(term, erster_start=False):
    from zentrale_cli import wizard
    term.sag(t("setup_title"), "fett")
    if erster_start:
        term.sag(t("setup_first_run"))
    return wizard.run(term, start=wizard.start_index(erster_start))
