"""`zentrale update` — die neueste Fassung holen und daneben installieren.

Aufbau eines installierten Hubs (gleich in deploy/install.sh):

    ~/.local/share/zentrale/            HEIM (Env ZENTRALE_HEIM für Tests)
      data/                            die Daten — überleben jede Fassung
      hub/<fassung>/                   ein entpacktes Paket + eigenes venv
      hub/<fassung>/data -> ../../data
      hub/aktuell -> <fassung>         der Umschalter (atomar ersetzt)
    ~/.local/bin/zentrale -> HEIM/hub/aktuell/bin/zentrale

Die alte Fassung bleibt bis zum nächsten Update liegen (Rückweg: den
Verweis `aktuell` zurückdrehen).

Woher das Programm kam, sagt `kanal()` (memory/betrieb/verteilung.md):
apt/pacman (Datei KANAL, legt nur das Paket an — dann verweigert `update`
und verweist auf die Paketverwaltung), script (install.sh), dev (Checkout).
Ob ohne Konto aus einer öffentlichen Quelle geholt wird, steht in
VERTEILUNG.json im Paket (scripts/paket_bauen.py, deploy/verteilung.toml)."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

from zentrale_cli import WURZEL
from zentrale_cli.texte import t

import cloud_api   # noqa: E402
import knoten      # noqa: E402
import konto       # noqa: E402

_FASSUNG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PAKETVERWALTUNGEN = ("apt", "pacman")


def heim() -> str:
    return os.path.expanduser(os.environ.get("ZENTRALE_HEIM") or "~/.local/share/zentrale")


def installiert(wurzel=WURZEL) -> bool:
    hub = os.path.realpath(os.path.join(heim(), "hub"))
    return os.path.realpath(wurzel).startswith(hub + os.sep)


def kanal(wurzel=WURZEL) -> str:
    """apt | pacman | script | dev — woher dieses Programm kam."""
    try:
        with open(os.path.join(wurzel, "KANAL"), encoding="utf-8") as f:
            k = f.read().strip()
        if k in PAKETVERWALTUNGEN:
            return k
    except OSError:
        pass
    if os.path.realpath(wurzel).startswith("/usr/lib/zentrale" + os.sep) or \
            os.path.realpath(wurzel) == "/usr/lib/zentrale":
        return "apt"                 # Paket ohne KANAL-Datei: trotzdem nie selbst ersetzen
    return "script" if installiert(wurzel) else "dev"


def verteilung(wurzel=WURZEL) -> dict:
    """VERTEILUNG.json des Pakets; fehlt sie (Checkout, alte Pakete): nicht öffentlich."""
    try:
        with open(os.path.join(wurzel, "VERTEILUNG.json"), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("oeffentlich") is True:
            return d
    except (OSError, ValueError):
        pass
    return {"oeffentlich": False}


def _url(vorlage, fassung=""):
    return vorlage.replace("__CLOUD__", cloud_api.adresse()).replace("__VERSION__", fassung)


def _groesse(n):
    return f"{n / 1e6:.1f} MB" if n else "?"


REUSE_VENV = "ZENTRALE_REUSE_VENV"   # developer/test runs: link this venv (as in install.sh)


def venv_bauen(ordner):
    """venv + requirements-basis.txt. Eigene Funktion, damit Tests sie ersetzen."""
    reuse = os.environ.get(REUSE_VENV)
    if reuse:
        os.symlink(reuse, os.path.join(ordner, "venv"))
        return
    subprocess.run([sys.executable, "-m", "venv", os.path.join(ordner, "venv")], check=True)
    subprocess.run([os.path.join(ordner, "venv", "bin", "pip"), "install", "-q", "-r",
                    os.path.join(ordner, "requirements-basis.txt")], check=True)


def entpacken(tar_pfad, ziel):
    """Paket nach `ziel` entpacken. Das Paket hat genau einen obersten Ordner
    (zentrale-<fassung>/); Pfade nach draußen lehnt der Filter 'data' ab."""
    zwischen = ziel + ".teil"
    shutil.rmtree(zwischen, ignore_errors=True)
    os.makedirs(zwischen)
    with tarfile.open(tar_pfad, "r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(zwischen, filter="data")
        else:                       # Python 3.11.0–3.11.3: selbst prüfen
            for m in tar.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/") or \
                        not (m.isfile() or m.isdir()):
                    raise ValueError(f"Unsafe entry in the package: {m.name}")
            tar.extractall(zwischen)
    oben = os.listdir(zwischen)
    if len(oben) != 1 or not os.path.isdir(os.path.join(zwischen, oben[0])):
        shutil.rmtree(zwischen, ignore_errors=True)
        raise ValueError("The package has an unexpected layout.")
    shutil.rmtree(ziel, ignore_errors=True)
    os.replace(os.path.join(zwischen, oben[0]), ziel)
    os.rmdir(zwischen)


def umschalten(fassung):
    """hub/aktuell atomar auf <fassung> drehen."""
    hub = os.path.join(heim(), "hub")
    neu = os.path.join(hub, ".aktuell-neu")
    if os.path.lexists(neu):
        os.remove(neu)
    os.symlink(fassung, neu)
    os.replace(neu, os.path.join(hub, "aktuell"))


def aufraeumen(behalten):
    """Old releases go. Only folders that ARE releases (a VERSION file, every
    package has one): apps installed from the store live next to them in
    hub/ (app_register.app_ordner = the folder the release sits in) and must
    survive every update."""
    hub = os.path.join(heim(), "hub")
    for name in os.listdir(hub):
        p = os.path.join(hub, name)
        if name in behalten or name.startswith(".") or os.path.islink(p):
            continue
        if not os.path.isfile(os.path.join(p, "VERSION")):
            continue
        shutil.rmtree(p, ignore_errors=True)


def package_info(wurzel=WURZEL):
    """The newest release the cloud offers → {"version", "sha256", "groesse"},
    or None when there is no way to ask (private distribution, not logged in).
    Raises CloudFehler when the cloud cannot be reached or answers nonsense."""
    oeffentlich = verteilung(wurzel)
    if oeffentlich["oeffentlich"]:
        info = cloud_api.Client(basis=_url(oeffentlich["neueste"])).get("")
    elif konto.angemeldet():
        info = konto.client().get("/v1/paket")
    else:
        return None
    neu, sha = str(info.get("version", "")), str(info.get("sha256", "")).lower()
    if not _FASSUNG.match(neu) or len(sha) != 64:
        raise cloud_api.CloudFehler("The cloud sent an unreadable package description.")
    return {"version": neu, "sha256": sha, "groesse": info.get("groesse")}


def _download(neu, wurzel):
    oeffentlich = verteilung(wurzel)
    if oeffentlich["oeffentlich"]:
        return cloud_api.Client(basis=_url(oeffentlich["paket"], neu)).bytes_holen("")
    return konto.client().bytes_holen(f"/v1/paket/{neu}.tar.gz")


# ── State of the updater (update.json in heim()) ─────────────────────────
#
# {"available": {"from": "39", "to": "43"}, "failed": {"version": "43",
# "reason": "…"}} — what `status`, the start line and the TUI show. Written by
# `update --automatic` (also when auto-update is off: then that is all it does).

STATE_FILE = "update.json"
AUTO_SETTING = "auto_update"       # node setting (data/ai_config.json, never synced), default on


def state() -> dict:
    try:
        with open(os.path.join(heim(), STATE_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _state_write(**changes):
    d = state()
    for k, v in changes.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    try:
        os.makedirs(heim(), exist_ok=True)
        tmp = os.path.join(heim(), STATE_FILE + ".neu")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, os.path.join(heim(), STATE_FILE))
    except OSError:
        pass


def auto_on() -> bool:
    import ai_config
    return ai_config.setting(AUTO_SETTING) is not False


def set_auto(on: bool):
    import ai_config
    ai_config.set_override(AUTO_SETTING, bool(on), persist=True)


def hint(wurzel=WURZEL):
    """One line for status/start, or "": an update waits (auto-update off or a
    package manager), or the last automatic one failed its self-test."""
    d = state()
    alt = knoten.fassung(wurzel)
    failed = d.get("failed") or {}
    if failed.get("version") and failed.get("version") != alt:
        return t("upd_hint_failed", neu=failed["version"], alt=alt)
    avail = d.get("available") or {}
    if avail.get("to") and avail.get("to") != alt:
        k = kanal(wurzel)
        key = "upd_hint_package" if k in PAKETVERWALTUNGEN else "upd_hint"
        return t(key, alt=alt, neu=avail["to"])
    return ""


# ── Self-test of a new release (before the switch) ───────────────────────

CHECK_MODULES = ("zentrale_cli.befehle", "zentrale_cli.assistent", "zentrale_cli.wizard",
                 "zentrale_cli.timer", "abgleich", "abgleich_apps", "ai_config", "konto",
                 "cloud_api", "knoten")


def version_check(term) -> int:
    """`zentrale version --check`: run by `update` with the NEW release before
    `aktuell` is switched. Imports, reads the settings, reaches the cloud."""
    import importlib
    try:
        for name in CHECK_MODULES:
            importlib.import_module(name)
        term.sag(t("check_imports"))
        import ai_config
        ai_config.setting(AUTO_SETTING)
        konto.lesen()
        term.sag(t("check_settings"))
        info = package_info(WURZEL)
        term.sag(t("check_cloud") if info is not None else t("check_cloud_skipped"))
    except Exception as e:             # noqa: BLE001 — every failure is a failed self-test
        term.sag(t("check_failed", text=f"{type(e).__name__}: {e}"), "fehler")
        return 1
    return 0


def self_test(release_dir) -> tuple:
    """→ (ok, output) of `<release>/bin/zentrale version --check`."""
    exe = os.path.join(release_dir, "bin", "zentrale")
    try:
        r = subprocess.run([exe, "version", "--check"], capture_output=True, text=True,
                           timeout=180, stdin=subprocess.DEVNULL)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


# ── Commands ─────────────────────────────────────────────────────────────

def command(term, args=()):
    """`zentrale update [--automatic | auto [on|off]]`."""
    args = list(args)
    if not args:
        return update(term)
    if args == ["--automatic"]:
        return automatic(term)
    if args[0] == "auto" and len(args) <= 2:
        if len(args) == 2:
            if args[1] not in ("on", "off"):
                term.fehler(t("upd_usage"))
                return 2
            set_auto(args[1] == "on")
        term.sag(t("upd_auto_on") if auto_on() else t("upd_auto_off"), "gut")
        return 0
    term.fehler(t("upd_usage"))
    return 2


def automatic(term, venv=venv_bauen, wurzel=WURZEL, check=self_test):
    """The update timer: nothing new → quiet. New → with auto-update on:
    install beside, self-test, switch, keeper, backend restart; off or a
    package manager: only remember it for the hint. Never a question.
    Then (auto-update on) the extracted apps from the store follow their
    repository, held ones are skipped (building kit step 12)."""
    k = kanal(wurzel)
    if k == "dev":
        return 0
    rc = _automatic_core(term, venv, wurzel, check, k)
    if auto_on():
        rc = max(rc, automatic_apps(term))
    return rc


def automatic_apps(term) -> int:
    """Extracted apps (core/app_update.py): quiet when nothing moved."""
    import app_update
    rc = 0
    for r in app_update.update_installed():
        if r["result"] == "updated":
            term.sag(t("upd_app_updated", name=r["name"]), "gut")
        elif r["result"] == "held":
            term.sag(t("upd_app_held", name=r["name"]), "blass")
        elif r["result"] == "skipped":
            term.sag(t("upd_app_skipped", name=r["name"], text=r["text"]), "blass")
        elif r["result"] == "failed":
            term.sag(t("upd_app_failed", name=r["name"], text=r["text"]), "warn")
            rc = 1
    return rc


def _automatic_core(term, venv, wurzel, check, k):
    try:
        info = package_info(wurzel)
    except (cloud_api.CloudFehler, konto.KontoFehler) as e:
        term.sag(t("upd_auto_unreachable", text=e), "warn")
        return 1
    if info is None:
        return 0
    alt = knoten.fassung(wurzel)
    if info["version"] == alt:
        _state_write(available=None)
        return 0
    _state_write(available={"from": alt, "to": info["version"]})
    if (state().get("failed") or {}).get("version") not in (None, info["version"]):
        _state_write(failed=None)          # a newer release replaces the old note
    if k in PAKETVERWALTUNGEN or not auto_on():
        return 0
    if (state().get("failed") or {}).get("version") == info["version"]:
        return 0                       # one note is enough; a manual `update` tries again
    return _install(term, info, venv, wurzel, check)


def update(term, venv=venv_bauen, wurzel=WURZEL, check=self_test):
    k = kanal(wurzel)
    if k in PAKETVERWALTUNGEN:
        term.sag(t("upd_paket_" + k))
        return 1
    if k != "script":
        term.sag(t("upd_dev", wurzel=wurzel))
        return 1
    if not verteilung(wurzel)["oeffentlich"] and not konto.angemeldet():
        term.sag(t("upd_need_login"))
        return 1
    term.sag(t("upd_check"), "blass")
    info = package_info(wurzel)
    alt = knoten.fassung(wurzel)
    if info["version"] == alt:
        _state_write(available=None)
        term.sag(t("upd_current", fassung=alt), "gut")
        return 0
    return _install(term, info, venv, wurzel, check)


def _install(term, info, venv, wurzel, check):
    """Download beside, sha256, unpack, venv, self-test — only then switch
    `aktuell`, run the new release's keeper, restart a running backend."""
    neu, sha, alt = info["version"], info["sha256"], knoten.fassung(wurzel)
    term.sag(t("upd_found", neu=neu, alt=alt, groesse=_groesse(info.get("groesse"))))
    term.sag(t("upd_download"), "blass")
    daten = _download(neu, wurzel)
    if hashlib.sha256(daten).hexdigest() != sha:
        term.sag(t("upd_bad_sha"), "fehler")
        return 1
    hub = os.path.join(heim(), "hub")
    os.makedirs(hub, exist_ok=True)
    tar_pfad = os.path.join(hub, f".lade-{neu}.tar.gz")
    with open(tar_pfad, "wb") as f:
        f.write(daten)
    ziel = os.path.join(hub, neu)
    try:
        entpacken(tar_pfad, ziel)
    finally:
        os.remove(tar_pfad)
    os.makedirs(os.path.join(heim(), "data"), exist_ok=True)
    if not os.path.lexists(os.path.join(ziel, "data")):
        os.symlink(os.path.join("..", "..", "data"), os.path.join(ziel, "data"))
    vorlage, daten_ascii = os.path.join(ziel, "mitgeliefert", "ascii"), os.path.join(heim(), "data", "ascii")
    if os.path.isdir(vorlage) and not os.path.exists(daten_ascii):
        shutil.copytree(vorlage, daten_ascii)
    term.sag(t("upd_venv"), "blass")
    venv(ziel)
    term.sag(t("upd_self_test", neu=neu), "blass")
    ok, out = check(ziel)
    for line in out.splitlines()[-6:]:
        term.sag("  " + line, "blass")
    if not ok:
        shutil.rmtree(ziel, ignore_errors=True)
        _state_write(failed={"version": neu, "reason": (out.splitlines() or ["?"])[-1][:300]})
        term.sag(t("upd_self_test_failed", neu=neu, alt=alt), "fehler")
        return 1
    alt_name = os.path.basename(os.path.realpath(wurzel))
    umschalten(neu)
    aufraeumen({neu, alt_name})
    _state_write(available=None, failed=None)
    term.sag(t("upd_ok", neu=neu, alt_ordner=os.path.join(hub, alt_name)), "gut")
    run_keeper(term, ziel)
    from zentrale_cli import timer
    if timer.kern_neu_starten():
        term.sag(t("upd_backend_restarted"), "blass")
    return 0


def run_keeper(term, release_dir):
    """`timers install` of the NEW release (memory/hub/building_kit_plan.md 5.2):
    only the new code knows the units it brings, so a unit added in a later
    release reaches every node that updates. Idempotent. A failure never undoes
    the update — the timers can be repaired by hand; one line says how."""
    exe = os.path.join(release_dir, "bin", "zentrale")
    try:
        r = subprocess.run([exe, "timers", "install"], capture_output=True, text=True, timeout=120)
        ok, out = r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        ok, out = False, str(e)
    for line in out.splitlines():
        term.sag(line, "blass")
    if not ok:
        term.sag(t("upd_keeper_failed"), "warn")
    return ok
