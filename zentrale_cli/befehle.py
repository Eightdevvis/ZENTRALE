"""Die Befehle von `zentrale`. Jeder nimmt ein Terminal und gibt einen
Rückgabewert (0 = gut). Gerechnet wird im Kern; hier wird nur gefragt und
gezeigt."""

import os
import shutil

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
import cloud_notices       # noqa: E402
import cloud_nutzung       # noqa: E402
import dateien             # noqa: E402
import formats             # noqa: E402
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


def version(term, args=()):
    """`zentrale version [--check]` — --check is the self-test `update` runs
    with a new release before switching to it (zentrale_cli/aktualisieren.py)."""
    if list(args) == ["--check"]:
        from zentrale_cli import aktualisieren
        return aktualisieren.version_check(term)
    if args:
        term.fehler(t("unknown_command", cmd="version " + " ".join(args)))
        return 2
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
        choose_sync(term, {n: term.ja(t("ask_new_app", name=app_name(n)[0]))})


def choose_sync(term, choice, show_plan=True) -> bool:
    """A sync choice ({app: True|False}) through the one gate (building kit
    step 9b, core/generations.py): compile → diff → switch → apply. A change
    the compiler refuses is shown and nothing is written; a failed health
    check rolls back. → True when the choice is in effect."""
    import generations
    r = generations.choose_sync(choice, root=WURZEL)
    for e in r["errors"]:
        term.sag(t("wiring_refused", text=e["text"]), "warn")
    if r["rolled_back"]:
        term.sag(t("wiring_rolled_back", text="; ".join(r["problems"])), "warn")
    if r.ok and show_plan:
        for line in r["diff"]:
            term.sag("  " + line, "blass")
    return r.ok


def neue_apps_beim_start(term):
    """Beim Start von `zentrale`: nur mit eingeschalteter Cloud, und nur auf
    diesem Gerät nachsehen (schnell, auch offline). Was erst in der Cloud
    liegt, fragt der nächste `zentrale sync`."""
    if abgleich.cloud_an():
        neue_apps_fragen(term, cloud=False)


def _ki_werte() -> dict:
    """Die im Adapter lesbaren KI-Schlüssel (Name → Wert), um nach einem
    Abgleich zu sehen, ob neue gekommen sind."""
    try:
        return {n: adapter_geheim.lesen(adapter_geheim.KI + n) for n in adapter_geheim.ki_namen()}
    except Exception:       # noqa: BLE001 — nur für einen Hinweis
        return {}


def _ki_neu_melden(term, vorher, automatisch):
    """Kamen mit dem Abgleich KI-Schlüssel an (oder änderten sich), muss das
    Backend sie neu lesen: es legt sie nur beim Start in die Umgebung, und
    die SDK-Clients behalten den Schlüssel (core/main.py, core/cloud.py,
    core/cloud_openai.py). Läuft der Kern als Dienst, neu starten."""
    timer = timer_modul()
    nachher = _ki_werte()
    neu = sorted(n for n, w in nachher.items() if w and vorher.get(n) != w)
    if not neu:
        return
    term.sag(t("sync_keys_new", liste=", ".join(neu)), "gut")
    if timer.kern_neu_starten():
        term.sag(t("sync_keys_restarted", unit=timer.KERN))
    elif not automatisch:
        term.sag(t("sync_keys_restart"), "blass")


def _kontext_schreiben():
    """Das Kontextpaket fürs Handy auffrischen (wie scripts/abgleich.py) —
    nur ein Zusatz, darf den Abgleich nie aufhalten."""
    try:
        import mobil_kontext
        mobil_kontext.schreiben(WURZEL)
    except Exception:       # noqa: BLE001
        pass


def _self_heal(term):
    """The sync timer runs the newest code (hub/aktuell): if an old release
    updated without its keeper, run `timers install` once (timer.self_heal).
    Quiet unless something was written; never stops the sync."""
    try:
        r = timer_modul().self_heal(WURZEL)
    except Exception as e:         # noqa: BLE001 — healing is a side matter
        term.sag(t("tm_error", text=e), "warn")
        return
    if r and r.get("geschrieben"):
        term.sag(t("tm_healed", liste=", ".join(r["geschrieben"])))
    elif r and r.get("fehler"):
        term.sag(t("tm_error", text=r["fehler"]), "warn")


def sync(term, args=()):
    """`zentrale sync [--automatic]`. --automatic ist der Timer
    (zentrale_cli/timer.py): nur mit Cloud bzw. Weg „mitte", still, wenn
    nichts geschah, nie eine Frage — wie scripts/abgleich.py --automatisch."""
    automatisch = "--automatic" in args
    if set(args) - {"--automatic"}:
        term.fehler(t("unknown_command", cmd="sync " + " ".join(args)))
        return 2
    if automatisch:
        _self_heal(term)
    if abgleich.mitte_art() == "http" and not konto.angemeldet():
        if automatisch:
            return 0
        term.sag(t("not_logged_in"))
        return 1
    if automatisch and abgleich.weg() != "mitte":
        return 0                         # Timer läuft, Gerät gleicht (noch) nicht so ab
    if abgleich.mitte_art() == "http" and cloud_notices.removed():
        # Removed from the account (build step 8): the timer stays quiet,
        # `status` says why; a new login clears it.
        if automatisch:
            return 0
        term.sag(t("sync_removed"), "warn")
        return 1
    _ki_uebernehmen(term, still=True)
    vorher = _ki_werte()
    neue_apps_fragen(term)
    if automatisch:
        _kontext_schreiben()
    try:
        b = abgleich.abgleichen(WURZEL, warten=60.0 if automatisch else 120.0)
    except abgleich.Besetzt:
        if automatisch:
            return 0
        term.sag(t("sync_busy"))
        return 1
    except abgleich_mitte.MitteFehler:
        if automatisch and cloud_notices.removed():
            return 0                     # just learned it was removed: quiet from now on
        raise
    _ki_neu_melden(term, vorher, automatisch)
    if automatisch and not (b.geholt or b.gesendet or b.hinweise or b.beiseite):
        return 0
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


def held_back_lines(term, held):
    """What the last sync left out (core/abgleich.py, held back): too-large
    files one by one, a vanished cloud folder as one line."""
    if not held:
        return
    term.sag()
    term.sag(t("st_held_back"), "fett")
    folder = [h for h in held if h.get("reason") == "folder_missing"]
    for h in held:
        if h.get("reason") == "too_large":
            path = h["path"][5:] if h["path"].startswith("data/") else h["path"]
            term.sag(t("st_held_too_large", path=path, size=(h.get("size") or 0) // 2**20), "warn")
    if folder:
        term.sag(t("st_held_folder", n=len(folder)), "warn")


def _node_lines():
    """Auto-update and background (building kit 5.2, 5.3) for `status`."""
    from zentrale_cli import aktualisieren
    k = kanal(WURZEL)
    rows = []
    if k in aktualisieren.PAKETVERWALTUNGEN:
        rows.append((t("st_auto_update"), t("st_auto_package")))
    elif k == "script":
        rows.append((t("st_auto_update"), t("st_auto_on") if aktualisieren.auto_on() else t("st_auto_off")))
    on = timer_modul().linger()
    if on is not None:
        rows.append((t("st_background"), t("st_linger_on") if on else t("st_linger_off")))
    return rows


def update_hint(term):
    """One line when an update waits or failed its self-test (status, start)."""
    from zentrale_cli import aktualisieren
    line = aktualisieren.hint(WURZEL)
    if line:
        term.sag()
        term.sag(line, "warn")


def format_lines(term):
    """Formats this version found in a newer major (core/formats.py): one
    line each — "cloud data is newer than this version — read only"."""
    notes = formats.notes()
    if not notes:
        return
    term.sag()
    term.sag(t("st_formats"), "fett")
    for n in notes:
        term.sag(f"  {str(n.get('since'))[:16].replace('T', ' ')}  {n['text']}", "warn")
    term.sag(t("st_formats_hint"), "blass")


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
    zeilen += _node_lines()
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
    held_back_lines(term, z.get("held_back") or [])
    update_hint(term)
    node_notice_lines(term, logged_in=bool(d))
    format_lines(term)
    if adapter.kalender_anschluss() and not timer_modul().vdirsyncer_da():
        term.sag()
        vdirsyncer_hinweis(term)
    nutzung_warnung(term)
    return 0


def node_notice_lines(term, logged_in=True):
    """What the cloud said about this device (core/cloud_notices.py):
    insecure release (build step 7), removed from the account (step 8)."""
    removed = cloud_notices.removed() if logged_in else None
    insecure = cloud_notices.insecure()
    if not (removed or insecure):
        return
    term.sag()
    if removed:
        term.sag(t("st_removed") + ": " + t("st_removed_text", zeit=_kurzzeit(removed)), "warn")
    if insecure:
        term.sag(t("st_insecure") + ": " + t("st_insecure_text", version=insecure.get("version"),
                                              since=_kurzzeit(insecure.get("since")),
                                              link=insecure.get("link") or "—"), "fehler")


def _kurzzeit(iso):
    return str(iso or "?")[:16].replace("T", " ")


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
    import kalender_einstellung as ke
    alle = adapter.alle()
    term.sag(t("ad_title"), "fett")
    term.sag("  " + t("ad_cal_source", quelle=ke.quelle())
             + ("" if ke.eingestellt() else t("ad_cal_source_default")))
    _show_fill_pending(term)
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


def adapter_lauf(term):
    """`zentrale adapter run`: ein Lauf der Kalender-Brücke (das, was der
    Timer alle 3 min tut) — scripts/kalender_sync.py mit dem Paar „zentrale".
    Ohne Kalender-Anschluss und ohne eigene vdirsyncer-Konfiguration gibt es
    nichts zu tun: dann still 0, damit ein frisches Gerät keinen Fehler
    sammelt. Ohne vdirsyncer bleibt das Gerät Verbraucher (adapter_ablauf)."""
    import importlib.util
    import adapter_vdirsyncer
    if not adapter.kalender_google_an():
        term.sag(t("ad_run_not_google", quelle=_quelle()))
        return 0
    if adapter.kalender_anschluss() is None and not os.path.exists(adapter_vdirsyncer.vorgabe_config()):
        term.sag(t("ad_run_nothing"))
        return 0
    pfad = os.path.join(WURZEL, "scripts", "kalender_sync.py")
    spec = importlib.util.spec_from_file_location("kalender_sync", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul.main(["zentrale"])


def _quelle():
    import kalender_einstellung
    return kalender_einstellung.quelle()


class SignOfLife:
    """While kalender_quelle_setzen syncs for a long time (first fill: 590
    files, minutes): one line with the file count first, then every
    `interval` seconds "… still syncing (n s)". Real progress (file n of N)
    needs a hook in core/abgleich (memory/hub/adapter.md)."""

    def __init__(self, term, interval=15.0):
        import threading
        self.term, self.interval = term, interval
        self._stop = threading.Event()
        self._thread = None
        self._start = None

    def report(self, event, n=0, upload=False, **_kw):
        import threading
        import time
        if event == "syncing" and self._thread is None:
            self.term.sag(t("ad_cal_uploading" if upload else "ad_cal_syncing", n=n))
            self._start = time.monotonic()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        elif event == "done":
            self.stop(done=True)

    def _run(self):
        import time
        while not self._stop.wait(self.interval):
            self.term.sag(t("ad_cal_still", s=int(time.monotonic() - self._start)), "blass")

    def stop(self, done=False):
        import time
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=1)
        self._thread = None
        if done:
            self.term.sag(t("ad_cal_done", s=int(time.monotonic() - self._start)), "blass")


def _show_fill_pending(term):
    if adapter_ablauf.calendar_fill_pending(wurzel=WURZEL):
        term.sag(t("ad_cal_open"), "warn")


def adapter_kalender(term, rest=()):
    """`zentrale adapter calendar [google|zencloud|lokal]`: die Quelle der
    Kalender-App kalender-haupt zeigen bzw. umstöpseln
    (adapter_ablauf.kalender_quelle_setzen). Ändert nur den Wert, löscht
    nichts. Ohne Wort: nur zeigen."""
    import kalender_einstellung as ke
    if not rest:
        q = ke.quelle()
        term.sag(t("ad_cal_source", quelle=q) + ("" if ke.eingestellt() else t("ad_cal_source_default")))
        _show_fill_pending(term)
        term.sag(t("ad_cal_source_how"), "blass")
        return 0
    if len(rest) != 1 or rest[0] not in ke.QUELLEN:
        term.fehler(t("ad_cal_source_bad", wort=" ".join(rest), liste=" | ".join(ke.QUELLEN)))
        return 2
    alive = SignOfLife(term)
    try:
        r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, rest[0], WURZEL, report=alive.report)
    finally:
        alive.stop()
    e = r["ergebnis"]
    if e == "interrupted":
        term.sag(t("ad_cal_interrupted"), "warn")
        if r["beiseite"]:
            term.sag(t("ad_cal_aside", pfad=r["beiseite"]), "warn")
        return 130
    if e in ("continued", "incomplete"):
        if e == "continued":
            term.sag(t("ad_cal_continued"), "gut")
        else:
            term.sag(t("ad_cal_continue_failed", text=r["fehler"]), "warn")
        if r["beiseite"]:
            term.sag(t("ad_cal_aside", pfad=r["beiseite"]), "warn")
        return 0 if e == "continued" else 1
    if e == "ohne_mitte":
        term.sag(t("ad_cal_hub_no_account"), "warn")
        return 1
    if e == "unbekannt":
        term.sag(t("ad_cal_hub_unknown"), "fehler")
        return 1
    if e == "offline":
        term.sag(t("ad_cal_hub_offline", text=r["fehler"]), "fehler")
        return 1
    if e == "gleich":
        term.sag(t("ad_cal_source_same", quelle=rest[0]))
        return 0
    term.sag(t("ad_cal_set", von=r["von"], quelle=rest[0]), "gut")
    if e in ("fuellt", "uebernimmt"):
        term.sag(t("ad_cal_hub_" + e))
    if r["beiseite"]:
        term.sag(t("ad_cal_aside", pfad=r["beiseite"]), "warn")
    if r["fehler"]:
        term.sag(t("ad_cal_hub_sync_later", text=r["fehler"]), "warn")
    return 0


# ── Timer (zentrale_cli/timer.py) ──────────────────────────────────────

def timer_modul():
    from zentrale_cli import timer
    return timer


def vdirsyncer_hinweis(term):
    tm = timer_modul()
    if tm.vdirsyncer_da():
        term.sag(t("vd_ok"))
    else:
        term.sag(t("vd_missing", wie=t("vd_how")[tm.paketverwaltung()]), "warn")


def timers_installieren(term, leise=False):
    """Timer schreiben und einschalten; ohne systemd --user ein Satz. → 0/1"""
    tm = timer_modul()
    r = tm.installieren(WURZEL)
    if not r["da"]:
        term.sag(t("tm_none"), "warn")
        return 0
    if r["ersetzt"]:
        term.sag(t("tm_replaced", liste=", ".join(r["ersetzt"])), "warn")
    if r["geschrieben"] and not leise:
        term.sag(t("tm_written", liste=", ".join(r["geschrieben"])), "blass")
    elif not r["geschrieben"] and not leise:
        term.sag(t("tm_up_to_date"), "blass")
    if r["fehler"]:
        term.sag(t("tm_error", text=r["fehler"]), "fehler")
        return 1
    term.sag(t("tm_on"), "gut")
    return 0


def timers(term, args=()):
    """`zentrale timers [install|remove]`."""
    if args and args[0] == "install" and len(args) == 1:
        rc = timers_installieren(term)
        vdirsyncer_hinweis(term)
        return rc
    if args and args[0] == "remove" and len(args) == 1:
        r = timer_modul().entfernen()
        if not r["da"]:
            term.sag(t("tm_none"), "warn")
            return 0
        term.sag(t("tm_removed", liste=", ".join(r["entfernt"])) if r["entfernt"]
                 else t("tm_nothing_removed"), "gut")
        if r["liegen"]:
            term.sag(t("tm_left", liste=", ".join(r["liegen"])), "warn")
        return 0
    if args:
        term.fehler(t("tm_usage"))
        return 2
    z = timer_modul().zustand(WURZEL)
    term.sag(t("tm_title"), "fett")
    if not z["da"]:
        term.sag(t("tm_none"), "warn")
        vdirsyncer_hinweis(term)
        return 0
    datei = t("tm_file")
    kopf = t("tm_head")
    zeilen = []
    for name, d in z["timer"].items():
        arten = {d["service"], d["timer"]}
        art = next((a for a in ("fehlt", "fremd", "verweis", "alt") if a in arten), "eigen")
        naechster = d.get("naechster", "?")
        zeilen.append((name, datei[art], d.get("an", "?"), d.get("aktiv", "?"),
                       naechster if naechster not in ("", "n/a") else "—", d.get("ergebnis", "?")))
    breiten = [max(len(str(r[i])) for r in zeilen + [kopf]) + 2 for i in range(5)]
    term.sag("  " + term.f("".join(k.ljust(b) for k, b in zip(kopf, breiten)) + kopf[5], "blass"))
    for r in zeilen:
        term.sag("  " + "".join(str(v).ljust(b) for v, b in zip(r, breiten)) + str(r[5]))
    term.sag(t("tm_command", pfad=z["befehl"]), "blass")
    if any(r[1] != datei["eigen"] or r[2] != "enabled" for r in zeilen):
        term.sag(t("tm_fix"), "warn")
    vdirsyncer_hinweis(term)
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
    term.sag(t("devices_title", name=konto.lesen()["name"]), "fett")
    if not liste:
        term.sag("  " + t("devices_none"))
    for k in sorted(liste or [], key=lambda k: str(k.get("name"))):
        hw = k.get("hardware") or {}
        hat = ", ".join(t("hw")[n] for n in ("gpu", "bildschirm", "mikro", "lautsprecher")
                        if hw.get(n)) or "—"
        selbst = " " + term.f(t("dev_this"), "gut") if k.get("name") == ich["name"] else ""
        term.sag(f"  {term.f(str(k.get('name')), 'akzent')}{selbst}")
        term.sag(f"     {k.get('sorte', '?')} · {hat} · {k.get('programm', '?')} · "
                 + t("dev_seen", zeit=str(k.get("zuletzt_gesehen", "?"))[:16].replace("T", " ")),
                 "blass")
        if k.get("removed"):
            weg = (t("dev_left", zeit=_kurzzeit(k["removed"])) if k.get("removed_by") == k.get("name")
                   else t("dev_removed", zeit=_kurzzeit(k["removed"]), by=k.get("removed_by") or "?"))
            term.sag("     " + weg, "warn")
        i = k.get("insecure")
        if isinstance(i, dict):
            term.sag("     " + t("dev_insecure", since=_kurzzeit(i.get("since")), link=i.get("link") or "—"),
                     "fehler")
    node_notice_lines(term)
    return 0


# ── Leave and remove (build step 8, memory/hub/building_kit_plan.md 5.1) ──

def _local_data_paths():
    """What 'leave' may delete on request: this installation's data/ and the
    sync folder (it holds the last synced state in plain text)."""
    return [p for p in (os.path.join(WURZEL, "data"), abgleich.ordner()) if os.path.exists(p)]


def leave(term):
    """`zentrale leave`: on the device itself. Removed from the account
    (tombstone), logged out, keeper timers off; local data kept unless the
    person asks (default: keep)."""
    d = konto.lesen() if konto.angemeldet() else None
    device = (d or {}).get("knoten") or dateien.knoten()
    term.sag(t("leave_intro", device=device, name=d["name"]) if d else t("leave_local"))
    if not term.ja(t("leave_confirm"), vorgabe=False):
        term.sag(t("cancelled"))
        return 1
    offline = False
    if d:
        try:
            konto.remove_device(device)
        except konto.KontoFehler:
            offline = not cloud_notices.removed()     # removed already = nothing left to do there
        adapter_geheim.vor_abmelden()
        konto.abmelden()
    tm = timer_modul()
    if tm.verfuegbar():
        tm.entfernen()
    if offline:
        term.sag(t("leave_offline", device=device), "warn")
    pfade = _local_data_paths()
    geloescht = False
    if pfade and os.path.exists(os.path.join(WURZEL, ".git")):
        term.sag(t("leave_delete_checkout"), "blass")
    elif pfade and term.ja(t("leave_delete_ask", paths=", ".join(pfade)), vorgabe=False):
        for p in pfade:
            shutil.rmtree(p, ignore_errors=True)
        geloescht = True
    term.sag(t("leave_done_deleted" if geloescht else "leave_done", device=device), "gut")
    return 0


def devices_remove(term, args=()):
    """`zentrale devices remove <name>`: from another device. Asks "lost or
    stolen?" — only then it offers changing the account key (Sasha 30.10.)."""
    if len(args) != 1:
        term.fehler(t("rm_usage"))
        return 2
    name = args[0]
    d = konto.lesen() if konto.angemeldet() else None
    if not d:
        term.sag(t("not_logged_in"))
        return 1
    if name == d.get("knoten"):
        term.sag(t("rm_self", device=name))
        return 1
    term.sag(t("rm_intro", device=name))
    if not term.ja(t("rm_confirm", device=name), vorgabe=False):
        term.sag(t("cancelled"))
        return 1
    lost = term.ja(t("rm_lost"), vorgabe=False)
    r = konto.remove_device(name)
    term.sag(t("rm_done", device=name, n=r.get("sessions_ended", 0)), "gut")
    if lost:
        return rotate_key_dialog(term)
    return 0


def _optional_new_password(term):
    while True:
        p1 = term.geheim(t("rot_new_password"))
        if not p1:
            return None
        try:
            konto.passwort_pruefen(p1)
        except konto.KontoFehler as e:
            term.sag(str(e), "warn")
            continue
        if term.geheim(t("ask_password_again")) == p1:
            return p1
        term.sag(t("passwords_differ"), "warn")


def rotate_key_dialog(term):
    """Offer changing the account key (core/key_rotation.py). Says BEFORE
    the confirmation that all other devices must log in again."""
    import key_rotation
    term.sag()
    for zeile in t("rot_offer").splitlines():
        term.sag(zeile, "warn")
    if not term.ja(t("rot_ask"), vorgabe=False):
        term.sag(t("rot_not_now"))
        return 0
    pw = term.geheim(t("ask_password_old"))
    neu = _optional_new_password(term)
    term.sag(t("working_key"), "blass")
    draft = key_rotation.Draft(pw, neu)
    term.sag()
    term.sag("  " + t("emergency_title"), "warn", "fett")
    term.sag()
    term.sag("      " + draft.notfall_text, "fett")
    term.sag()
    for zeile in t("emergency_warning").splitlines():
        term.sag("  " + zeile, "warn")
    term.sag()
    if not term.ja(t("emergency_confirm")):
        term.sag(t("rot_emergency_not_saved"))
        return 1
    if abgleich.cloud_an() and abgleich.weg() == "mitte":
        term.sag(t("rot_sync_first"), "blass")
        abgleich.abgleichen(WURZEL)
    term.sag(t("rot_working"), "blass")
    r = key_rotation.rotate(draft, WURZEL)
    term.sag(t("rot_done", n=r["files"]), "gut")
    if r["inbox_skipped"]:
        term.sag(t("rot_inbox_skipped", n=r["inbox_skipped"]), "warn")
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
