# core/adapter_vdirsyncer.py
#
# Der Kalender-Anschluss über vdirsyncer (memory/hub/adapter.md): aus einer
# vorhandenen vdirsyncer-Konfiguration eine abgleichbare VORLAGE machen, und
# auf jedem Gerät, das gerade Brücke ist, daraus die echte Konfiguration
# bauen. So braucht kein Gerät eine eigene Google-Anmeldung.
#
# Die Vorlage (Anschluss → einstellungen.vdirsyncer.abschnitte) ist die
# Konfiguration Abschnitt für Abschnitt, Werte als JSON (so liest vdirsyncer
# sie). Drei Dinge werden ersetzt:
#
#   Geheimnisse  client_id, client_secret, password → {"$geheim": "<storage>/<schlüssel>"}
#                (Wert in data/adapter/geheim.enc unter <anschluss>/<storage>/<schlüssel>)
#   Token-Datei  token_file → {"$datei": "<storage>", "pfad": "~/…"}; ihr
#                INHALT liegt in geheim.enc (<anschluss>/datei/<storage>).
#                Erneuert Google den Token, trägt zurueckschreiben() ihn
#                wieder ein — die nächste Brücke hat ihn.
#   Ordner       path, der in data/kalender/ zeigt → {"$ort": "kalender", "rest": …};
#                jedes Gerät setzt seinen eigenen ZENTRALE-Ordner ein.
#
# Alles andere bleibt, wie Sasha es eingerichtet hat (Paare, collections,
# conflict_resolution, read_only …). Pfade unter ~ bleiben unter ~ — auf
# jedem Gerät sein eigenes Zuhause.
#
# Fundament (Schicht 1). Den Ort des Kalenders gibt der Aufrufer herein.

import configparser
import hashlib
import json
import os
import subprocess
import sys

import adapter
import adapter_geheim
import ai_config
import dateien

GEHEIM_SCHLUESSEL = ("client_id", "client_secret", "password")


def vorgabe_config() -> str:
    """Wo eine vorhandene vdirsyncer-Konfiguration liegt (wie vdirsyncer
    selbst sucht). Einstellung `vdirsyncer_config` lenkt um (Tests)."""
    eigen = ai_config.setting("vdirsyncer_config")
    if eigen:
        return os.path.expanduser(eigen)
    if os.environ.get("VDIRSYNCER_CONFIG"):
        return os.path.expanduser(os.environ["VDIRSYNCER_CONFIG"])
    xdg = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return os.path.expanduser(os.path.join(xdg, "vdirsyncer", "config"))


def _home(p: str) -> str:
    """Pfad unter dem eigenen Zuhause als ~/… (auf jedem Gerät gültig)."""
    voll = os.path.abspath(os.path.expanduser(p))
    home = os.path.expanduser("~")
    if voll == home or voll.startswith(home + os.sep):
        return "~" + voll[len(home):]
    return p


def _wert(roh: str):
    try:
        return json.loads(roh)
    except ValueError:
        return roh.strip()


def lesen_config(text: str) -> list:
    cp = configparser.RawConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read_string(text)
    return [(kopf, [(k, _wert(v)) for k, v in cp.items(kopf)]) for kopf in cp.sections()]


def vorlage_aus(config_pfad, aid, vdir, wurzel=None) -> dict:
    """Aus einer vorhandenen Konfiguration die Vorlage machen und die
    Geheimnisse in den Adapter legen. → einstellungen für den Anschluss.
    Schreibt NICHTS an der vorhandenen Konfiguration."""
    with open(config_pfad, encoding="utf-8") as f:
        abschnitte = lesen_config(f.read())
    vdir_echt = os.path.realpath(str(vdir))
    raus = []
    for kopf, werte in abschnitte:
        teile = kopf.split(None, 1)
        storage = teile[1] if len(teile) == 2 and teile[0] == "storage" else None
        neu = []
        for k, v in werte:
            if storage and k in GEHEIM_SCHLUESSEL and isinstance(v, str):
                adapter_geheim.setzen(f"{aid}/{storage}/{k}", v, wurzel)
                v = {"$geheim": f"{storage}/{k}"}
            elif storage and k == "token_file" and isinstance(v, str):
                p = os.path.expanduser(v)
                if os.path.exists(p):
                    with open(p, "rb") as fh:
                        adapter_geheim.setzen_bytes(f"{aid}/datei/{storage}", fh.read(), wurzel)
                v = {"$datei": storage, "pfad": _home(v)}
            elif storage and k == "path" and isinstance(v, str):
                echt = os.path.realpath(os.path.expanduser(v))
                if echt == vdir_echt or echt.startswith(vdir_echt + os.sep):
                    v = {"$ort": "kalender", "rest": os.path.relpath(echt, vdir_echt)}
                else:
                    v = _home(v)
            elif kopf == "general" and k == "status_path" and isinstance(v, str):
                v = _home(v)
            neu.append([k, v])
        raus.append({"kopf": kopf, "werte": neu})
    return {"vdirsyncer": {"abschnitte": raus}}


# ── Auf dem Brücken-Gerät ──────────────────────────────────────────────

def _abschnitte(a) -> list:
    return ((a.get("einstellungen") or {}).get("vdirsyncer") or {}).get("abschnitte") or []


def status_dir(a) -> str:
    for ab in _abschnitte(a):
        if ab["kopf"] == "general":
            for k, v in ab["werte"]:
                if k == "status_path" and isinstance(v, str):
                    return os.path.expanduser(v)
    return os.path.expanduser("~/.local/share/vdirsyncer/status/")


def kalender_paare(a) -> list:
    """Die Paare, deren eine Seite data/kalender/ ist — ihr Stand reist mit."""
    return list(_lokale_seiten(a))


# Konfliktlöser für die Kalender-Paare (scripts/kalender_konflikt.py): lokal
# gewinnt nur bei einem ZENTRALE-Termin (UID …@zentrale), dessen lokale
# Fassung echt neuer ist; sonst bleibt der Konflikt ein Fehler wie bisher.
# Eingetragen nur, wo Sasha keine eigene Regel gesetzt hat (null/fehlt).
KONFLIKT_SKRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "scripts", "kalender_konflikt.py")


def konflikt_regel(seite: str) -> list:
    return ["command", sys.executable, KONFLIKT_SKRIPT, "--lokal", seite]


def _lokale_seiten(a) -> dict:
    """{Paar: 'a'|'b'} — welche Seite des Paars data/kalender/ ist."""
    lokal = set()
    for ab in _abschnitte(a):
        t = ab["kopf"].split(None, 1)
        if len(t) == 2 and t[0] == "storage":
            if any(k == "path" and isinstance(v, dict) and v.get("$ort") == "kalender"
                   for k, v in ab["werte"]):
                lokal.add(t[1])
    paare = {}
    for ab in _abschnitte(a):
        t = ab["kopf"].split(None, 1)
        if len(t) == 2 and t[0] == "pair":
            w = dict((k, v) for k, v in ab["werte"])
            if w.get("a") in lokal:
                paare[t[1]] = "a"
            elif w.get("b") in lokal:
                paare[t[1]] = "b"
    return paare


def token_dateien(a) -> dict:
    """storage → Pfad der Token-Datei auf diesem Gerät."""
    raus = {}
    for ab in _abschnitte(a):
        for k, v in ab["werte"]:
            if isinstance(v, dict) and "$datei" in v:
                raus[v["$datei"]] = os.path.expanduser(v["pfad"])
    return raus


def bauen(a, vdir, wurzel=None) -> str:
    """Die Konfiguration für DIESES Gerät schreiben (600, außerhalb von
    data/), Token-Dateien aus dem Adapter hinlegen. → Pfad der Konfiguration.
    Fehlt ein Geheimnis → AdapterFehler (dann fährt dieses Gerät nicht)."""
    aid = a["id"]
    zeilen = [f"# Erzeugt vom ZENTRALE-Adapter aus dem Anschluss '{aid}'. Nicht von Hand",
              "# ändern — es wird bei jedem Lauf neu geschrieben (memory/hub/adapter.md).", ""]
    seiten = _lokale_seiten(a)
    for ab in _abschnitte(a):
        zeilen.append(f"[{ab['kopf']}]")
        t = ab["kopf"].split(None, 1)
        paar = t[1] if len(t) == 2 and t[0] == "pair" else None
        werte = list(ab["werte"])
        if paar in seiten and not any(k == "conflict_resolution" for k, _v in werte):
            werte.append(["conflict_resolution", None])
        for k, v in werte:
            if paar in seiten and k == "conflict_resolution" and v is None:
                v = konflikt_regel(seiten[paar])
            if isinstance(v, dict) and "$geheim" in v:
                w = adapter_geheim.lesen(f"{aid}/{v['$geheim']}", wurzel)
                if w is None:
                    raise adapter.AdapterFehler(
                        f"Secret {v['$geheim']} of '{aid}' is not readable on this device.")
                v = w
            elif isinstance(v, dict) and "$datei" in v:
                roh = adapter_geheim.lesen_bytes(f"{aid}/datei/{v['$datei']}", wurzel)
                p = os.path.expanduser(v["pfad"])
                if roh is not None:
                    try:
                        with open(p, "rb") as fh:
                            gleich = fh.read() == roh
                    except OSError:
                        gleich = False
                    if not gleich:
                        dateien.atomar_schreiben(p, roh, geheim=True)
                v = v["pfad"]
            elif isinstance(v, dict) and v.get("$ort") == "kalender":
                rest = v.get("rest") or "."
                v = os.path.normpath(os.path.join(str(vdir), rest)) + "/"
            zeilen.append(f"{k} = {json.dumps(v, ensure_ascii=False)}")
        zeilen.append("")
    ziel = os.path.join(adapter.lauf_ordner(aid), "vdirsyncer.config")
    dateien.atomar_schreiben(ziel, "\n".join(zeilen), geheim=True)
    _ordner_anlegen(ziel)
    return ziel


def _ordner_anlegen(cfg) -> None:
    """Die örtlichen Ordner (filesystem-Speicher und ihre Sammlungen) auf
    diesem Gerät anlegen. Auf einer neuen Brücke fehlt z. B. die
    Nur-Lese-Kopie von Google; `vdirsyncer discover` fragte sonst, ob es sie
    anlegen soll — ohne Terminal ein Nein, und die Brücke führe nie. Nur
    örtliche Ordner; bei Google wird nie etwas angelegt."""
    with open(cfg, encoding="utf-8") as f:
        abschnitte = dict(lesen_config(f.read()))
    orte = {}
    for kopf, werte in abschnitte.items():
        t = kopf.split(None, 1)
        w = dict(werte)
        if len(t) == 2 and t[0] == "storage" and w.get("type") == "filesystem" \
                and isinstance(w.get("path"), str):
            orte[t[1]] = os.path.expanduser(w["path"])
    for kopf, werte in abschnitte.items():
        t = kopf.split(None, 1)
        if len(t) != 2 or t[0] != "pair":
            continue
        w = dict(werte)
        samml = w.get("collections")
        for seite, stelle in (("a", 1), ("b", 2)):
            basis = orte.get(w.get(seite))
            if not basis:
                continue
            os.makedirs(basis, exist_ok=True)
            for c in samml if isinstance(samml, list) else []:
                name = c if isinstance(c, str) else (c[stelle] if isinstance(c, list) and len(c) == 3 else None)
                if isinstance(name, str) and name and "/" not in name and name not in (".", ".."):
                    os.makedirs(os.path.join(basis, name), exist_ok=True)


def zurueckschreiben(a, wurzel=None) -> list:
    """Nach einem Lauf: hat vdirsyncer einen Token erneuert, ihn in den
    Adapter (gleicht ab → die nächste Brücke hat ihn). → geänderte storages."""
    raus = []
    for storage, p in token_dateien(a).items():
        try:
            with open(p, "rb") as fh:
                roh = fh.read()
        except OSError:
            continue
        if roh and adapter_geheim.setzen_bytes(f"{a['id']}/datei/{storage}", roh, wurzel):
            raus.append(storage)
    return raus


def _paare(a) -> list:
    return [ab["kopf"].split(None, 1)[1] for ab in _abschnitte(a)
            if ab["kopf"].startswith("pair ") and len(ab["kopf"].split(None, 1)) == 2]


def entdecken(a, cfg, exe="vdirsyncer") -> str | None:
    """`vdirsyncer discover` für jedes Paar, wenn sich die erzeugte
    Konfiguration seit dem letzten Mal auf diesem Gerät geändert hat (oder
    noch nie entdeckt wurde). vdirsyncer merkt sich die Sammlungen samt der
    Konfiguration und verweigert sonst den Abgleich. Entdecken liest nur.
    → None oder der Fehler in einer Zeile."""
    with open(cfg, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    merk = os.path.join(adapter.lauf_ordner(a["id"]), "entdeckt.json")
    try:
        with open(merk, encoding="utf-8") as f:
            if json.load(f).get("sha") == sha:
                return None
    except (OSError, ValueError):
        pass
    env = dict(os.environ, VDIRSYNCER_CONFIG=cfg)
    for paar in _paare(a):
        r = subprocess.run([exe, "discover", paar], env=env, input="", text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, errors="replace")
        if r.returncode != 0:
            letzte = [z for z in (r.stdout or "").splitlines() if z.strip()][-1:]
            return f"vdirsyncer discover {paar} failed" + (": " + letzte[0][:100] if letzte else "")
    dateien.json_schreiben(merk, {"sha": sha})
    return None
