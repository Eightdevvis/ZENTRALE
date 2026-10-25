#!/usr/bin/env python3
"""vdirsyncer für den ZENTRALE-Kalender — mit den Sicherungen drumherum.

Warum nicht vdirsyncer direkt (memory/werkzeuge/kalender_ics_bauplan.md):
  1. Der data/-Abgleich zwischen PC und Laptop löscht nie. Ein auf dem Laptop
     gelöschter Termin kann als "Geist" zurückkommen. ZENTRALE erkennt ihn am
     Grabstein und zeigt ihn nicht — vdirsyncer kennt keine Grabsteine und
     würde ihn wieder zu Google hochladen. Deshalb vorher aufräumen.
  2. Vor dem Lauf den Tages-Snapshot sicherstellen und den git-Spiegel
     committen; danach noch einmal. So ist JEDE Änderung, die vom Server
     kommt, in der Geschichte — auch eine falsche.
  3. Danach zählen: sind auf einen Schlag viele Termine verschwunden, laut
     melden (rückgängig machen kann man es dann aus Snapshot/git/Verlauf).

  4. (07.10.2026, Sasha: „bitte bitte lösch nix aus google calendar aus
     versehen") Vorher eine Nur-Lese-Kopie von Google holen (Paar
     google_probe) und einmal am Tag als Archiv ablegen. Und: fehlen lokal
     seit dem letzten Abgleich mehr Termine als die Löschsperre erlaubt, wird
     NICHT gesynct — sonst trüge vdirsyncer die Lücke als Löschung zu Google.
     Gewollt? Dann einmal mit ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1.
     (25.10.2026) Gezählt wird nur die Ebene termine (nur sie geht zu
     Google), eine UID, die lokal in einem anderen Ordner liegt, fehlt nicht,
     und verglichen wird mit dem vdirsyncer-Status (Stand nach dem letzten
     Abgleich), nicht mit einer nur bei Exit 0 erneuerten Liste.
  5. (16.10.2026) Nach JEDEM Lauf den Zustand festhalten (core/
     kalender_sync_zustand.py): letzter Versuch, letzter Erfolg, Fehler im
     Klartext („Google-Zugang abgelaufen — neu anmelden"). ZENTRALE zeigt ihn
     an — ein abgelaufener Zugang blieb vorher tagelang unbemerkt.
  6. (24.10.2026, der Adapter — memory/hub/adapter.md) Gibt es einen
     Kalender-Anschluss, fährt immer nur EIN Gerät die Brücke zu Google: wer
     den Mietvertrag hält (core/adapter_bruecke.py). Jeder Lauf auf jedem
     Gerät: Brücke frei oder meine? → nehmen → abgleichen → kam mein Name
     zurück, Google abgleichen, sonst nichts tun. Die Konfiguration erzeugt
     der Adapter aus dem Anschluss (core/adapter_vdirsyncer.py), Zugang und
     Token kommen verschlüsselt aus der Cloud. Ohne Anschluss: wie bisher.
Alle Argumente werden an `vdirsyncer sync` durchgereicht (z. B. ein Paar).
Exit-Code = der von vdirsyncer (1, wenn ZENTRALE nicht auf ics steht;
2 Löschsperre; 3 Google-Sicherung fehlgeschlagen).
"""

import json
import os
import re
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORE = os.path.join(_ROOT, "core")
for _p in (_CORE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kalender            # noqa: E402
import kalender_ics        # noqa: E402
import kalender_speicher   # noqa: E402
import kalender_sync_zustand  # noqa: E402


def _anzahl(vdir) -> int:
    return sum(1 for _ in vdir.rglob("*.ics")) if vdir.exists() else 0


def _spiegeln(grund: str) -> None:
    ziel = kalender_speicher.git_spiegel_pfad()
    if ziel is None:
        return
    import kalender_spiegel
    p = kalender_speicher.pfade(kalender.CAL_PATH, kalender.ICS_DIR)
    kalender_spiegel.spiegeln({"kalender": p["vdir"], "kalender_neben.json": p["neben"]},
                              ziel, grund, warten=True)


# Umlenkbar, damit ein Testlauf nie den echten Merkzettel liest/schreibt
# (tests/conftest.py und der venv-Riegel setzen die Variable).
STAND = os.path.expanduser(os.environ.get("ZENTRALE_KALENDER_SYNC_STAND")
                           or "~/.local/share/vdirsyncer/zentrale_stand.json")
SICHERUNG = os.path.expanduser("~/.local/share/zentrale/google-sicherung")
KOPIE = os.path.expanduser("~/.local/share/vdirsyncer/google_kopie")


# Nur diese Ebene geht zu Google (Paar „zentrale“, collections = termine).
# uncommitted/ und rhythmus/ bleiben lokal — was dort fehlt, kann bei Google
# nichts löschen und zählt für die Sperre nicht.
GESYNCT = "termine"

_UID = re.compile(r"^UID[;:](?:[^:\r\n]*:)?(.+?)\r?$", re.M)


def _namen(vdir) -> set:
    """Dateien der gesyncten Ebene, relativ zum vdir („termine/x.ics“)."""
    o = vdir / GESYNCT
    return {str(p.relative_to(vdir)) for p in o.glob("*.ics")} if o.exists() else set()


def _uid_aus(pfad) -> str | None:
    """Die (erste) UID einer .ics-Datei, ohne sie ganz zu parsen."""
    try:
        text = pfad.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _UID.search(re.sub(r"\r?\n[ \t]", "", text))
    return m.group(1).strip() if m else None


def _lokale_uids(vdir) -> set:
    """UIDs aller lokalen Dateien, über ALLE Ebenen. Eine UID, die nur den
    Ordner gewechselt hat (uncommitted → termine), ist nicht verschwunden."""
    if not vdir.exists():
        return set()
    return {u for u in (_uid_aus(p) for p in vdir.rglob("*.ics")) if u}


# ── Vergleichsbasis: Stand nach dem letzten Abgleich ─────────────────────
# (25.10.2026) Erste Wahl ist der Status von vdirsyncer selbst: er führt je
# Termin, was nach dem letzten Abgleich auf BEIDEN Seiten lag — und genau
# das, was davon lokal fehlt, würde vdirsyncer bei Google löschen. Er wird
# je Termin fortgeschrieben, auch wenn ein anderer Termin im selben Lauf
# einen Konflikt hat; eine mit ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1
# bestätigte Löschung ist danach aus ihm verschwunden und zählt nie wieder.
# Vorher war die Basis die eigene Liste STAND, die nur bei Exit 0 neu
# geschrieben wurde — ein einziger Konflikt hielt so die bestätigten
# Löschungen fest, die Sperre griff 5,5 h lang alle 3 min (24./25.10.2026).
# STAND bleibt Rückfall, wenn der Status nicht lesbar ist.

def _config_pfad() -> str:
    # ZENTRALE_VDIRSYNCER_CONFIG lenkt in Tests um (nie Sashas echte);
    # VDIRSYNCER_CONFIG setzt der Adapter für den Lauf.
    for k in ("ZENTRALE_VDIRSYNCER_CONFIG", "VDIRSYNCER_CONFIG"):
        if os.environ.get(k):
            return os.path.expanduser(os.environ[k])
    xdg = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return os.path.expanduser(os.path.join(xdg, "vdirsyncer", "config"))


def _wert(roh):
    try:
        return json.loads(roh)
    except ValueError:
        return roh.strip()


def _status_quellen(vdir) -> list:
    """[(status-Datei, Seite 'a'|'b', lokaler Ordnername)] für die Paare, deren
    eine Seite dieses vdir ist. Liest aus der Konfiguration NUR Pfade, Paare
    und Sammlungen — Zugangsdaten werden weder gelesen noch ausgegeben."""
    import configparser
    cp = configparser.RawConfigParser(interpolation=None)
    cp.optionxform = str
    with open(_config_pfad(), encoding="utf-8") as f:
        cp.read_file(f)
    w = lambda kopf, k: _wert(cp.get(kopf, k)) if cp.has_option(kopf, k) else None
    status = w("general", "status_path") if cp.has_section("general") else None
    if not isinstance(status, str):
        return []
    echt = os.path.realpath(str(vdir))
    lokal = set()
    for kopf in cp.sections():
        t = kopf.split(None, 1)
        pfad = w(kopf, "path")
        if len(t) == 2 and t[0] == "storage" and isinstance(pfad, str) \
                and os.path.realpath(os.path.expanduser(pfad)) == echt:
            lokal.add(t[1])
    raus = []
    for kopf in cp.sections():
        t = kopf.split(None, 1)
        if len(t) != 2 or t[0] != "pair":
            continue
        for seite, stelle in (("a", 1), ("b", 2)):
            if w(kopf, seite) not in lokal:
                continue
            for c in w(kopf, "collections") or []:
                if isinstance(c, str) and not c.startswith("from "):
                    name, ordner = c, c
                elif isinstance(c, list) and len(c) == 3:
                    name, ordner = c[0], c[stelle]
                else:
                    raise ValueError("Sammlung %r nicht auflösbar" % (c,))
                raus.append((os.path.join(os.path.expanduser(status), t[1], name + ".items"),
                             seite, ordner))
    return raus


def _basis_status(vdir) -> dict | None:
    """{„termine/x.ics“: uid} aus dem vdirsyncer-Status, None = nicht lesbar."""
    import sqlite3
    from urllib.parse import quote
    quellen = _status_quellen(vdir)
    if not quellen:
        return None
    raus = {}
    for datei, seite, ordner in quellen:
        if not os.path.isfile(datei):
            return None
        c = sqlite3.connect("file:%s?mode=ro" % quote(datei), uri=True)
        try:
            for ident, href in c.execute("SELECT ident, href_%s FROM status" % seite):
                if href:
                    raus[ordner + "/" + href] = ident
        finally:
            c.close()
    return raus


def _basis_stand() -> dict | None:
    """Rückfall: die eigene Liste vom letzten Lauf mit Exit 0."""
    try:
        with open(STAND, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    uids = d.get("uids") or {}
    return {n: uids.get(n) for n in (d.get("dateien") or [])
            if n.startswith(GESYNCT + "/")}


def _basis(vdir) -> tuple:
    """(Basis, Quelle) — Basis {Datei: uid oder None} oder None (erster Lauf)."""
    try:
        b = _basis_status(vdir)
        if b is not None:
            return b, "vdirsyncer-Status"
    except FileNotFoundError:
        pass                    # keine Konfiguration: still der Rückfall
    except Exception as e:      # noqa: BLE001 — dann gilt der Rückfall
        print("vdirsyncer-Status nicht lesbar (%s) — Vergleich mit der eigenen Liste."
              % type(e).__name__)
    return _basis_stand(), "eigene Liste"


def _fehlende(vdir, basis=None) -> list:
    """Termine der gesyncten Ebene, die seit dem letzten Abgleich lokal
    verschwunden sind — und nicht bloß in einen anderen Ordner gewandert.
    `basis` = Ergebnis von _basis() (sonst wird sie hier geholt)."""
    alt = (basis or _basis(vdir))[0]
    if not alt:
        return []                      # erster Lauf: nichts kann fehlen
    weg = {n: u for n, u in alt.items() if n.startswith(GESYNCT + "/")
           and not (vdir / n).exists()}
    if not weg:
        return []
    da = _lokale_uids(vdir)
    return sorted(n for n, u in weg.items()
                  if (u or os.path.splitext(os.path.basename(n))[0]) not in da)


def _stand_merken(vdir) -> None:
    namen = sorted(_namen(vdir))
    os.makedirs(os.path.dirname(STAND), exist_ok=True)
    tmp = STAND + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"dateien": namen,
                   "uids": {n: _uid_aus(vdir / n) for n in namen}}, f)
    os.replace(tmp, STAND)


# Was vdirsyncer in diesem Lauf ausgab — daraus liest der Zustand den Grund
# („invalid_grant" → Zugang abgelaufen). Wird trotzdem durchgereicht, damit
# das Journal des Timers alles behält.
_AUSGABE: list = []


def _vdirsyncer(exe, *args) -> int:
    r = subprocess.run([exe, "sync", *args], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace")
    text = r.stdout or ""
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()
    _AUSGABE.append(text[-20000:])
    return r.returncode


def _google_sichern(exe) -> bool:
    """Nur-Lese-Kopie von Google holen; einmal am Tag als Archiv (14 Tage)."""
    import datetime
    import tarfile
    if _vdirsyncer(exe, "google_probe") != 0:
        return False
    os.makedirs(SICHERUNG, exist_ok=True)
    heute = datetime.date.today().isoformat()
    if not any(n.startswith("google_" + heute) for n in os.listdir(SICHERUNG)):
        ziel = os.path.join(SICHERUNG, "google_%s.tar.gz" % heute)
        with tarfile.open(ziel, "w:gz") as t:
            t.add(KOPIE, arcname="google_kopie")
        os.chmod(ziel, 0o600)
        alle = sorted(n for n in os.listdir(SICHERUNG) if n.startswith("google_"))
        for alt in alle[:-14]:
            os.remove(os.path.join(SICHERUNG, alt))
    return True


def main(argv=None) -> int:
    """Ein Lauf. Mit Kalender-Anschluss über den Adapter (nur die Brücke
    fährt), sonst wie bisher mit der eigenen Konfiguration."""
    a = _anschluss()
    if a is None:
        return _ein_lauf(argv)
    return _ueber_adapter(a, argv)


def _anschluss():
    try:
        import adapter
        return adapter.kalender_anschluss()
    except Exception as e:      # noqa: BLE001 — ohne Adapter gilt der alte Weg
        print("Adapter nicht lesbar:", e)
        return None


def _ueber_adapter(a, argv) -> int:
    import adapter_ablauf
    from pathlib import Path
    cal = Path(kalender.CAL_PATH)
    vdir = kalender_speicher.pfade(cal, kalender.ICS_DIR)["vdir"]
    lauf = adapter_ablauf.bruecke_lauf(a, cal.parent.parent, vdir, lambda _cfg: _ein_lauf(argv))
    if lauf.art == "gefahren":
        return lauf.code
    if lauf.art == "andere":
        m = lauf.miete or {}
        print(f"Google-Seite fährt {m.get('inhaber')} (bis {m.get('ablauf')}) — hier nichts zu tun.")
        kalender_sync_zustand.uebernehmen(m.get("zustand"))
        return 0
    if lauf.art == "fehlt":
        print("Nicht gesynct:", lauf.text)
        kalender_sync_zustand.schreiben(1, "einrichtung", lauf.text)
        return 1
    print(f"Nicht gesynct ({lauf.art}): {lauf.text}")
    return 0


def _ein_lauf(argv=None) -> int:
    """Ein Lauf; danach steht sein Ergebnis im Sync-Zustand — auch bei einer
    Ausnahme (die danach weiterfliegt, damit das Journal sie zeigt)."""
    _AUSGABE.clear()
    stufe = [""]
    try:
        code = _lauf(argv, stufe)
    except BaseException as e:
        if isinstance(e, SystemExit) and not e.code:
            _zustand(0, "")
        else:
            _zustand(1, "sonstig", "Absturz: %s: %s" % (type(e).__name__, str(e)[:80]))
        raise
    _zustand(code, stufe[0])
    return code


def _zustand(code, stufe, fehler=None) -> None:
    """Den Zustand schreiben; ein Fehler dabei darf den Sync nicht kippen."""
    try:
        if fehler:
            kalender_sync_zustand.schreiben(code, stufe, fehler)
            return
        art, text = kalender_sync_zustand.erkennen(code, "\n".join(_AUSGABE), stufe)
        kalender_sync_zustand.schreiben(code, art, text)
    except Exception as e:
        print("Sync-Zustand ließ sich nicht schreiben:", e)


def _lauf(argv, stufe) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if kalender_speicher.modus(kalender.CAL_PATH) != "ics":
        print("Kalender steht nicht auf 'ics' (Einstellung kalender_speicher) — "
              "kein Sync. Erst umziehen: scripts/kalender_migrieren.py.")
        stufe[0] = "einrichtung"
        return 1
    exe = shutil.which("vdirsyncer")
    if not exe:
        print("vdirsyncer nicht gefunden.")
        stufe[0] = "einrichtung"
        return 1
    sp = kalender_speicher.ics_speicher(kalender.CAL_PATH, kalender.ICS_DIR,
                                        mit_spiegel=False)
    geister = sp.aufraeumen()
    if geister:
        print(f"{geister} zurückgebrachte, längst gelöschte Termine weggeräumt "
              f"(liegen im Verlauf).")
    sp.snapshot()
    _spiegeln("vor vdirsyncer")
    vorher = _anzahl(sp.vdir)

    basis = _basis(sp.vdir)
    fehlen = _fehlende(sp.vdir, basis)
    if len(fehlen) > sp.loeschsperre and os.environ.get("ZENTRALE_KALENDER_SYNC_LOESCHEN_OK") != "1":
        print(f"ABBRUCH: {len(fehlen)} Termine fehlen lokal seit dem letzten Sync "
              f"(Sperre {sp.loeschsperre}). Ohne Prüfung würden sie bei Google "
              f"gelöscht. Verglichen mit: {basis[1]} (Stand nach dem "
              f"letzten Abgleich); der Stand davor liegt auch im heutigen Snapshot "
              f"und im git-Spiegel. Gewollt? Einmal mit ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1.")
        for n in fehlen[:10]:
            print("   fehlt:", n)
        stufe[0] = "loeschsperre"
        return 2
    # Die Google-Sicherung gehört zum echten Paar „zentrale" (so ruft es der
    # Timer). Andere Aufrufe (ein Paar von Hand, Tests) lassen sie aus.
    if "zentrale" in argv and not _google_sichern(exe):
        print("ABBRUCH: die Sicherungskopie von Google ließ sich nicht holen — "
              "ohne frische Sicherung wird nicht gesynct.")
        stufe[0] = "sicherung"
        return 3

    code = _vdirsyncer(exe, *argv)
    if code == 0:
        _stand_merken(sp.vdir)

    kalender_ics.cache_leeren()
    nachher = _anzahl(sp.vdir)
    _spiegeln("nach vdirsyncer")
    weg = vorher - nachher
    if weg > sp.loeschsperre:
        print(f"ACHTUNG: {weg} Termine sind bei diesem Abgleich verschwunden "
              f"({vorher} -> {nachher}). Wenn das nicht gewollt war: der Stand "
              f"davor liegt im heutigen Snapshot und im git-Spiegel.")
        try:
            import state
            state.push_log(f"[calendar] vdirsyncer: {weg} Termine verschwunden")
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
