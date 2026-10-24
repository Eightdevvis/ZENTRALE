"""Die Befehle von `zentrale`. Jeder nimmt ein Terminal und gibt einen
Rückgabewert (0 = gut). Gerechnet wird im Kern; hier wird nur gefragt und
gezeigt."""

import os

from zentrale_cli import WURZEL
from zentrale_cli.aktualisieren import kanal
from zentrale_cli.ausgabe import banner
from zentrale_cli.texte import t

import abgleich            # noqa: E402  (Kern, über zentrale_cli/__init__ im Pfad)
import abgleich_apps       # noqa: E402
import abgleich_mitte      # noqa: E402
import abgleich_schluessel  # noqa: E402
import adapter             # noqa: E402
import adapter_ablauf      # noqa: E402
import adapter_bruecke     # noqa: E402
import adapter_geheim      # noqa: E402
import ai_config           # noqa: E402
import cloud_api           # noqa: E402
import cloud_nutzung       # noqa: E402
import dateien             # noqa: E402
import knoten              # noqa: E402
import konto               # noqa: E402

EINRICHTUNG = "einrichtung"   # Einstellung: wann dieses Gerät eingerichtet wurde


def eingerichtet() -> bool:
    return bool(ai_config.setting(EINRICHTUNG))


def einrichtung_merken():
    import datetime
    ai_config.set_override(EINRICHTUNG, datetime.date.today().isoformat(), persist=True)


# ── Begrüßung, Fassung ─────────────────────────────────────────────────

def welcome(term):
    banner(term)
    term.sag()
    term.sag(t("welcome_title"), "fett")
    term.sag(t("welcome_body"))
    term.sag()
    term.sag(t("welcome_next"), "fett")
    breite = max(len(b) for b, _w in t("welcome_steps")) + 2
    for befehl, was in t("welcome_steps"):
        term.sag("  " + term.f(befehl.ljust(breite), "akzent") + was)
    return 0


def version(term):
    term.sag(t("version_line", fassung=knoten.fassung(WURZEL), kanal=t("kanal")[kanal(WURZEL)]))
    return 0


# ── Konto ──────────────────────────────────────────────────────────────

def _neues_passwort(term, frage_key="ask_password_new"):
    while True:
        p1 = term.geheim(t(frage_key, n=konto.MIN_PASSWORT))
        try:
            konto.passwort_pruefen(p1)
        except konto.KontoFehler as e:
            term.sag(str(e), "warn")
            continue
        if term.geheim(t("ask_password_again")) == p1:
            return p1
        term.sag(t("passwords_differ"), "warn")


def _name(term, pruefen):
    """Fragt „username:", bis der Name die Regeln erfüllt (Fehlersatz dazwischen)."""
    while True:
        try:
            return pruefen(term.frage(t("ask_name")))
        except konto.KontoFehler as e:
            term.sag(str(e), "warn")


def login(term):
    d = konto.lesen() if konto.angemeldet() else None
    if d:
        term.sag(t("login_already", name=d["name"]))
        return 0
    name = _name(term, konto.name_lesen)
    pw = term.geheim(t("ask_password"))
    term.sag(t("working_key"), "blass")
    d = konto.anmelden(name, pw)
    term.sag(t("login_ok", name=d["name"], device=d["knoten"]), "gut")
    return 0


def logout(term):
    # Vor dem Abmelden die Zugangsdaten auf den Geräteschlüssel — mit dem
    # Kontoschlüssel verschwände sonst auch ihr Schlüssel (core/adapter_geheim.py).
    adapter_geheim.vor_abmelden()
    term.sag(t("logout_ok") if konto.abmelden() else t("logout_none"))
    return 0


def account_create(term):
    if konto.angemeldet():
        term.sag(t("login_already", name=konto.lesen()["name"]))
        return 1
    term.sag(t("create_intro"))
    term.sag()
    code = term.frage(t("ask_code")).strip()
    name = _name(term, konto.neuer_name)
    pw = _neues_passwort(term)
    term.sag(t("working_key"), "blass")
    entwurf = konto.Entwurf(pw)
    term.sag()
    term.sag("  " + t("emergency_title"), "warn", "fett")
    term.sag()
    term.sag("      " + entwurf.notfall_text, "fett")
    term.sag()
    for zeile in t("emergency_warning").splitlines():
        term.sag("  " + zeile, "warn")
    term.sag()
    if not term.ja(t("emergency_confirm")):
        term.sag(t("emergency_not_saved"))
        return 1
    term.sag(t("working_key"), "blass")
    while True:
        try:
            d = konto.anlegen(entwurf, name, code, pw)
            break
        except konto.NameVergeben as e:        # Code und Entwurf gelten weiter
            term.sag(str(e), "warn")
            name = _name(term, konto.neuer_name)
    term.sag(t("create_ok", name=d["name"]), "gut")
    return 0


def account_recover(term):
    term.sag(t("recover_intro"))
    name = _name(term, konto.name_lesen)
    notfall = term.geheim(t("ask_emergency"))
    pw = _neues_passwort(term)
    term.sag(t("working_key"), "blass")
    d = konto.wiederherstellen(name, notfall, pw)
    term.sag(t("recover_ok", name=d["name"]), "gut")
    return 0


def account_password(term):
    if not konto.angemeldet():
        term.sag(t("not_logged_in"))
        return 1
    alt = term.geheim(t("ask_password_old"))
    neu = _neues_passwort(term)
    term.sag(t("working_key"), "blass")
    konto.passwort_aendern(alt, neu)
    term.sag(t("password_ok"), "gut")
    return 0


# ── Abgleich ───────────────────────────────────────────────────────────

def app_name(n, tabelle=None):
    """(Name, Beschreibung) einer App für Menschen."""
    if n in t("app"):
        return t("app")[n]
    return ((tabelle or abgleich_apps.tabelle()).get(n, {}).get("titel") or n, "")


def neue_apps_fragen(term, cloud=True):
    """Apps mit Daten, über die dieses Gerät noch nicht entschieden hat
    (core/abgleich_apps.py): am Terminal einmal fragen, die Antwort gilt je
    Gerät. Ohne Terminal nie blockieren — eine Zeile, und die App wird bis
    dahin weder geholt noch gesendet. `cloud` = auch in der Cloud nachsehen
    (nur das Inhaltsverzeichnis, und nur, wenn es Unentschiedene gibt)."""
    holen = abgleich.cloud_pfade if cloud and abgleich.cloud_an() else None
    neu = abgleich_apps.offen(WURZEL, holen)
    if not neu:
        return
    if not term.interaktiv:
        term.sag(t("new_apps_hint", liste=", ".join(app_name(n)[0] for n in neu)), "warn")
        return
    for n in neu:
        abgleich_apps.setzen({n: term.ja(t("ask_new_app", name=app_name(n)[0]))})


def neue_apps_beim_start(term):
    """Beim Start von `zentrale`: nur mit eingeschalteter Cloud, und nur auf
    diesem Gerät nachsehen (schnell, auch offline). Was erst in der Cloud
    liegt, fragt der nächste `zentrale sync`."""
    if abgleich.cloud_an():
        neue_apps_fragen(term, cloud=False)


def sync(term):
    if abgleich.mitte_art() == "http" and not konto.angemeldet():
        term.sag(t("not_logged_in"))
        return 1
    _ki_uebernehmen(term, still=True)
    neue_apps_fragen(term)
    try:
        b = abgleich.abgleichen(WURZEL)
    except abgleich.Besetzt:
        term.sag(t("sync_busy"))
        return 1
    if b.art == "erstbefuellung":
        term.sag(t("sync_first_fill"))
    elif b.art == "erstabgleich":
        term.sag(t("sync_first_join"))
    term.sag(t("sync_result", geholt=len(b.geholt), gesendet=len(b.gesendet),
               beiseite=len(b.beiseite)), "gut")
    for h in b.hinweise:
        term.sag(t("sync_note", text=h), "warn")
    return 0


def _apps_text(entscheidungen, tabelle):
    if entscheidungen is None:
        return t("st_areas_all")
    an = [app_name(n, tabelle)[0] for n in tabelle if entscheidungen.get(n)]
    return ", ".join(an) if an else t("st_areas_none")


def _apps_zeilen(z, tabelle):
    """Die Apps des Abgleichs, zuerst die Cloud selbst (core/eingebaute_apps.py)."""
    zeilen = [(app_name("cloud")[0], t("st_app_cloud_on") if z["cloud"] else t("st_app_cloud_off"))]
    e = z["apps"]
    for n in tabelle:
        if tabelle[n].get("pflicht"):
            zeilen.append((app_name(n, tabelle)[0], t("st_app_adapter", n=len(adapter.alle()))))
            continue
        stand = ("st_app_on" if e is None or e.get(n) else
                 "st_app_off" if n in e else "st_app_open")
        zeilen.append((app_name(n, tabelle)[0], t(stand)))
    return zeilen


def status(term):
    d = None
    try:
        d = konto.lesen()
    except konto.KontoFehler as e:
        term.sag(str(e), "warn")
    z = abgleich.zustand()
    tabelle = abgleich_apps.tabelle()
    zeilen = [
        (t("st_account"), d["name"] if d else t("st_account_none")),
        (t("st_server"), (d or {}).get("server") or cloud_api.adresse()),
        (t("st_device"), dateien.knoten()),
        (t("st_version"), f"{knoten.fassung(WURZEL)} ({t('kanal')[kanal(WURZEL)]})"),
        (t("st_way"), f"{z['weg']} / {z['mitte_art']}"),
        (t("st_areas"), _apps_text(z["apps"], tabelle)),
        (t("st_sync"), (z["letzter_erfolg"] or t("st_sync_never")).replace("T", " ")),
    ]
    if z["fehler"]:
        zeilen.append((t("st_sync_error"), z["fehler"]))
    breite = max(len(k) for k, _v in zeilen) + 2
    for k, v in zeilen:
        term.sag("  " + term.f(k.ljust(breite), "blass") + str(v))
    term.sag()
    term.sag(t("st_apps"), "fett")
    apps_zeilen = _apps_zeilen(z, tabelle)
    breite = max(len(k) for k, _v in apps_zeilen) + 2
    for k, v in apps_zeilen:
        term.sag("  " + term.f(k.ljust(breite), "blass") + v)
    if z["hinweise"]:
        term.sag()
        term.sag(t("st_notes"), "fett")
        for h in z["hinweise"][-10:]:
            term.sag(f"  {h['am'][:16].replace('T', ' ')}  {h['text']}")
        term.sag(t("sync_conflicts_dir", ordner=z["konflikte_ordner"]), "blass")
    nutzung_warnung(term)
    return 0


# ── Adapter (core/adapter.py, memory/hub/adapter.md) ───────────────────

def _uhr_kurz(iso):
    import datetime
    try:
        return datetime.datetime.fromisoformat(iso).astimezone().strftime("%d.%m. %H:%M")
    except (TypeError, ValueError):
        return str(iso)


def _bruecke_text(a):
    if not adapter.braucht_bruecke(a):
        return t("ad_bridge_none")
    if adapter_ablauf.nur_lokal():
        return t("ad_bridge_local")
    m = adapter_bruecke.lesen(a["id"])
    if not m:
        return t("ad_bridge_free")
    bis = _uhr_kurz(m.get("ablauf"))
    if adapter_bruecke.abgelaufen(m):
        return t("ad_bridge_expired", wer=m.get("inhaber"), bis=bis)
    return t("ad_bridge_holds", wer=m.get("inhaber"), bis=bis)


def _anschluss_status(a):
    if a.get("art") == "ki-anbieter":
        namen = adapter_geheim.ki_namen()
        lesbar = [n for n in namen if adapter_geheim.lesen(adapter_geheim.KI + n)]
        if len(lesbar) == len(namen):
            return t("ad_keys", n=len(lesbar))
        return t("ad_keys_unreadable", n=len(lesbar), m=len(namen) - len(lesbar))
    if a.get("speist") == "kalender":
        import kalender_sync_zustand
        b = kalender_sync_zustand.bewerten()
        return b.get("hinweis") or b.get("kurz") or t("ad_cal_unknown")
    return ""


def adapter_liste(term):
    """`zentrale adapter`: die Anschlüsse, wer die Brücke fährt (nur lesen —
    die Brücke wechselt von selbst)."""
    alle = adapter.alle()
    term.sag(t("ad_title"), "fett")
    if not alle:
        term.sag(t("ad_none"))
        return 0
    kopf = t("ad_head")
    zeilen = [(a["id"], a["art"], a["speist"], _bruecke_text(a), _anschluss_status(a))
              for a in alle.values()]
    breiten = [max(len(str(z[i])) for z in zeilen + [kopf]) + 2 for i in range(4)]
    term.sag("  " + term.f("".join(k.ljust(b) for k, b in zip(kopf, breiten)) + kopf[4], "blass"))
    for z in zeilen:
        term.sag("  " + "".join(str(v).ljust(b) for v, b in zip(z, breiten)) + str(z[4]))
    return 0


def _ki_uebernehmen(term, still=False):
    r = adapter_ablauf.einrichten(kalender=False)["ki"]
    if r["uebernommen"]:
        term.sag(t("ad_setup_ki", liste=", ".join(r["uebernommen"])), "gut")
    elif not still:
        term.sag(t("ad_setup_ki_none"))
    if r["behalten"]:
        term.sag(t("ad_setup_ki_kept", liste=", ".join(r["behalten"])), "warn")


def adapter_setup(term):
    """`zentrale adapter setup`: was dieses Gerät schon angekabelt hat in den
    Adapter holen. Der Kalender-Umstieg passiert genau hier, bewusst."""
    import adapter_vdirsyncer
    _ki_uebernehmen(term)
    r = adapter_ablauf.einrichten(vdir=os.path.join(WURZEL, "data", "kalender"))
    k = r["kalender"]
    if k == "angelegt":
        term.sag(t("ad_setup_cal_created"), "gut")
    elif k == "vorhanden":
        term.sag(t("ad_setup_cal_exists"))
    elif k == "kein_paar":
        term.sag(t("ad_setup_cal_nopair"), "warn")
    else:
        term.sag(t("ad_setup_cal_none", pfad=adapter_vdirsyncer.vorgabe_config()))
    term.sag(t("ad_setup_next"), "blass")
    return 0


# ── Geräte ─────────────────────────────────────────────────────────────

def geraet_melden(sorte="vollknoten") -> dict:
    """Die eigene Beschreibung in die Cloud (PUT /v1/knoten/<name>)."""
    b = knoten.beschreibung(sorte, wurzel=WURZEL)
    # Der Server nimmt nur den Namen, mit dem diese Sitzung angemeldet ist.
    b["name"] = (konto.lesen() or {}).get("knoten") or b["name"]
    try:
        konto.client().put("/v1/knoten/" + b["name"], b)
    except cloud_api.CloudFehler as e:
        raise konto.KontoFehler(str(e)) from None
    return b


def devices(term):
    if not konto.angemeldet():
        term.sag(t("not_logged_in"))
        return 1
    ich = geraet_melden()
    try:
        antwort = konto.client().get("/v1/knoten")
    except cloud_api.CloudFehler as e:
        raise konto.KontoFehler(str(e)) from None
    liste = antwort.get("knoten", []) if isinstance(antwort, dict) else antwort
    term.sag(t("dev_title", name=konto.lesen()["name"]), "fett")
    if not liste:
        term.sag("  " + t("dev_none"))
    for k in sorted(liste or [], key=lambda k: str(k.get("name"))):
        hw = k.get("hardware") or {}
        hat = ", ".join(t("hw")[n] for n in ("gpu", "bildschirm", "mikro", "lautsprecher")
                        if hw.get(n)) or "—"
        selbst = " " + term.f(t("dev_this"), "gut") if k.get("name") == ich["name"] else ""
        term.sag(f"  {term.f(str(k.get('name')), 'akzent')}{selbst}")
        term.sag(f"     {k.get('sorte', '?')} · {hat} · {k.get('programm', '?')} · "
                 + t("dev_seen", zeit=str(k.get("zuletzt_gesehen", "?"))[:16].replace("T", " ")),
                 "blass")
    return 0


# ── Cloud-Nutzung ──────────────────────────────────────────────────

_STUFE_FARBE = {"ok": ("gut",), "50": ("warn",), "80": ("warn", "fett"),
                "95": ("fehler",), "voll": ("fehler", "fett")}
BALKEN = 24


def _menge(n, einheit):
    n = float(n or 0)
    if einheit == "bytes":
        for grenze, name in ((1e9, "GB"), (1e6, "MB"), (1e3, "kB")):
            if n >= grenze:
                return f"{n / grenze:.2f} {name}"
        return f"{int(n)} B"
    return f"{int(n):,}"


def _uhr(iso):
    return str(iso or "")[11:16]


def nutzung_warnung(term):
    """EINE Zeile, wenn ein Gratis-Limit ≥ 50 % steht (nur Betreiber). Nie ein Fehler."""
    w = cloud_nutzung.warnung()
    if not w:
        return
    weitere = t("use_more", n=w["weitere"]) if w["weitere"] else ""
    term.sag(t("use_warning", text=w["text"].rstrip("."), weitere=weitere + "."),
             *_STUFE_FARBE.get(w["level"], ("warn",)))


def cloud_usage(term):
    if not konto.angemeldet():
        term.sag(t("not_logged_in"))
        return 1
    try:
        d = cloud_nutzung.holen()
    except cloud_nutzung.NurBetreiber:
        term.sag(t("use_only_operator"))
        return 1
    term.sag(t("use_title") + "  " + term.f(t("use_asof", zeit=str(d.get("zeit", ""))[:16].replace("T", " ")),
                                            "blass"), "fett")
    grenzen = [g for g in d.get("grenzen", []) if isinstance(g, dict)]
    breite = max([len(str(g.get("name", ""))) for g in grenzen] + [0]) + 2
    for g in grenzen:
        prozent = float(g.get("percent") or 0)
        farbe = _STUFE_FARBE.get(str(g.get("level")), ("warn",))
        voll = min(BALKEN, round(prozent / 100 * BALKEN))
        balken = term.f("█" * voll, *farbe) + term.f("░" * (BALKEN - voll), "blass")
        term.sag(f"  {str(g.get('name', '')).ljust(breite)}{balken} " + term.f(f"{prozent:5.1f} %", *farbe))
        einheit = g.get("unit")
        menge = f"{_menge(g.get('used'), einheit)} / {_menge(g.get('limit'), einheit)}"
        if einheit != "bytes":
            menge += f" {einheit}"
        if g.get("cloudflare") is not None:
            quelle = t("use_both", selbst=_menge(g.get("self"), einheit), cf=_menge(g.get("cloudflare"), einheit),
                       um=_uhr(g.get("cloudflare_at")))
        else:
            quelle = t("use_self")
        zeitraum = t("use_period").get(str(g.get("period")), str(g.get("period")))
        term.sag("  " + " " * breite + term.f(f"{menge} · {zeitraum} · {quelle}", "blass"))
    term.sag()
    warnungen = d.get("warnungen") or []
    if not warnungen:
        term.sag(t("use_all_ok"), "gut")
    for w in warnungen:
        term.sag("  " + str(w.get("text", "")), *_STUFE_FARBE.get(str(w.get("level")), ("warn",)))
    term.sag(t("use_money"), "blass")
    term.sag(t("use_checked", datum=d.get("grenzen_geprueft", "?")), "blass")
    return 0


# ── TUI ────────────────────────────────────────────────────────────────

def tui(term):
    skript = os.path.join(WURZEL, "scripts", "start_tui.sh")
    try:
        os.execv("/bin/bash", ["bash", skript])
    except OSError as e:
        term.sag(t("tui_missing", grund=e), "fehler")
        return 1


FEHLER = (konto.KontoFehler, cloud_api.CloudFehler, abgleich_mitte.MitteFehler,
          abgleich_schluessel.SchluesselFehler, adapter.AdapterFehler,
          adapter_geheim.GeheimFehler, ValueError)
