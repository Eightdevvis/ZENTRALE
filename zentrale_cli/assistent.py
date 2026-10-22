"""`zentrale setup` — der Einrichtungs-Assistent (Bauplan v1): Login ja/nein →
alles / auswählen / clean slate → holen. Die Wahl gilt je Gerät
(core/abgleich_bereiche.py); ein nicht gewählter Bereich wird hier weder
geholt noch gesendet."""

from zentrale_cli import befehle
from zentrale_cli.texte import t

import abgleich_bereiche as bereiche  # noqa: E402
import ai_config                      # noqa: E402
import konto                          # noqa: E402


def bereiche_waehlen(term):
    """→ Liste der ids oder None (abgebrochen)."""
    art = term.eins_von(t("setup_choose_q"), t("setup_choose_opts"))
    if art == "all":
        return list(bereiche.IDS)
    if art == "none":
        return []
    vorher = bereiche.gewaehlt()
    an = set(bereiche.IDS if vorher is None else vorher)
    eintraege = [(i, *t("area")[i]) for i in bereiche.IDS]
    gewaehlt = term.ankreuzen(t("setup_pick_title"), eintraege, an)
    return None if gewaehlt is None else [i for i in bereiche.IDS if i in gewaehlt]


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
    ids = bereiche_waehlen(term)
    if ids is None:
        term.sag(t("cancelled"))
        return 1
    bereiche.setzen(ids)
    term.sag(t("setup_choice_saved", liste=", ".join(t("area")[i][0] for i in ids))
             if ids else t("setup_choice_none"))
    cloud_einschalten()
    befehle.einrichtung_merken()
    try:
        befehle.geraet_melden()
    except konto.KontoFehler as e:
        term.sag(str(e), "warn")       # Gerät melden ist Beiwerk — Abgleich geht vor
    if ids:
        term.sag(t("setup_sync_now"), "blass")
        befehle.sync(term)
    term.sag(t("setup_done"), "gut")
    return 0
