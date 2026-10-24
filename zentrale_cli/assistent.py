"""`zentrale setup` — der Einrichtungs-Assistent (Bauplan v1, seit 2026-10-23
je App: memory/hub/cloud_app.md): Login ja/nein → welche Apps mit Daten
abgleichen (alle / auswählen / keine) → holen → Timer an. Angeboten werden nur Apps, die
hier oder in der Cloud schon Daten haben; ein frisches Konto sieht keine.
Die Wahl gilt je Gerät (core/abgleich_apps.py)."""

from zentrale_cli import befehle
from zentrale_cli.texte import t

import abgleich                       # noqa: E402
import abgleich_apps                  # noqa: E402
import ai_config                      # noqa: E402
import konto                          # noqa: E402


def apps_waehlen(term, angebot, tabelle):
    """angebot = Namen der Apps mit Daten → {name: ja/nein} oder None (abgebrochen)."""
    term.sag(t("setup_apps_found", liste=", ".join(befehle.app_name(n, tabelle)[0] for n in angebot)))
    art = term.eins_von(t("setup_choose_q"), t("setup_choose_opts"))
    if art == "all":
        return {n: True for n in angebot}
    if art == "none":
        return {n: False for n in angebot}
    vorher = abgleich_apps.entscheidungen()
    an = {n for n in angebot if vorher is None or vorher.get(n, True)}
    eintraege = [(n, *befehle.app_name(n, tabelle)) for n in angebot]
    gewaehlt = term.ankreuzen(t("setup_pick_title"), eintraege, an)
    return None if gewaehlt is None else {n: n in gewaehlt for n in angebot}


def cloud_einschalten():
    """Dieses Gerät gleicht ab jetzt über die Cloud ab (Einstellungen dieses
    Geräts, data/ai_config.json)."""
    ai_config.set_override("abgleich_mitte_art", "http", persist=True)
    ai_config.set_override("abgleich_weg", "mitte", persist=True)


def setup(term, erster_start=False):
    term.sag(t("setup_title"), "fett")
    if erster_start:
        term.sag(t("setup_first_run"))
    term.sag()
    if not konto.angemeldet():
        weg = term.eins_von(t("setup_account_q"), t("setup_account_opts"))
        if weg == "local":
            befehle.einrichtung_merken()
            term.sag(t("setup_local_ok"), "gut")
            return 0
        rc = befehle.account_create(term) if weg == "create" else befehle.login(term)
        if rc != 0:
            return rc
    term.sag()
    tabelle = abgleich_apps.tabelle()
    angebot = abgleich_apps.mit_daten(befehle.WURZEL, abgleich.cloud_pfade())
    if angebot:
        wahl = apps_waehlen(term, angebot, tabelle)
        if wahl is None:
            term.sag(t("cancelled"))
            return 1
        an = [befehle.app_name(n, tabelle)[0] for n in angebot if wahl[n]]
        term.sag(t("setup_choice_saved", liste=", ".join(an)) if an else t("setup_choice_none"))
    else:
        wahl = {}
        term.sag(t("setup_nothing_yet"))
    abgleich_apps.setzen(wahl)          # {} heißt: neue Apps fragen selbst
    cloud_einschalten()
    befehle.einrichtung_merken()
    try:
        befehle.geraet_melden()
    except konto.KontoFehler as e:
        term.sag(str(e), "warn")       # Gerät melden ist Beiwerk — Abgleich geht vor
    if any((abgleich_apps.entscheidungen() or {}).values()):
        term.sag(t("setup_sync_now"), "blass")
        befehle.sync(term)
    # Die Timer (zentrale_cli/timer.py): ohne sie gleicht ein frisches Gerät
    # nur von Hand ab und nimmt nie die Kalender-Brücke. Ohne systemd --user
    # ein Satz — die Einrichtung geht trotzdem zu Ende.
    term.sag()
    befehle.timers_installieren(term, leise=True)
    befehle.vdirsyncer_hinweis(term)
    term.sag(t("setup_done"), "gut")
    return 0
