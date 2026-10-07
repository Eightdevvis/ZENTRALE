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
     seit dem letzten Sync mehr Termine als die Löschsperre erlaubt, wird
     NICHT gesynct — sonst trüge vdirsyncer die Lücke als Löschung zu Google.
     Gewollt? Dann einmal mit ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1.
Alle Argumente werden an `vdirsyncer sync` durchgereicht (z. B. ein Paar).
Exit-Code = der von vdirsyncer (1, wenn ZENTRALE nicht auf ics steht).
"""

import json
import os
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


def _namen(vdir) -> set:
    return {str(p.relative_to(vdir)) for p in vdir.rglob("*.ics")} if vdir.exists() else set()


def _fehlende(vdir) -> list:
    """Termine, die seit dem letzten erfolgreichen Sync lokal verschwunden sind."""
    try:
        with open(STAND, encoding="utf-8") as f:
            alt = set(json.load(f).get("dateien") or [])
    except (OSError, ValueError):
        return []                      # erster Lauf: nichts kann fehlen
    return sorted(alt - _namen(vdir))


def _stand_merken(vdir) -> None:
    os.makedirs(os.path.dirname(STAND), exist_ok=True)
    tmp = STAND + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"dateien": sorted(_namen(vdir))}, f)
    os.replace(tmp, STAND)


def _google_sichern(exe) -> bool:
    """Nur-Lese-Kopie von Google holen; einmal am Tag als Archiv (14 Tage)."""
    import datetime
    import tarfile
    r = subprocess.run([exe, "sync", "google_probe"])
    if r.returncode != 0:
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
    argv = list(sys.argv[1:] if argv is None else argv)
    if kalender_speicher.modus() != "ics":
        print("Kalender steht nicht auf 'ics' (Einstellung kalender_speicher) — "
              "kein Sync. Erst umziehen: scripts/kalender_migrieren.py.")
        return 1
    exe = shutil.which("vdirsyncer")
    if not exe:
        print("vdirsyncer nicht gefunden.")
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

    fehlen = _fehlende(sp.vdir)
    if len(fehlen) > sp.loeschsperre and os.environ.get("ZENTRALE_KALENDER_SYNC_LOESCHEN_OK") != "1":
        print(f"ABBRUCH: {len(fehlen)} Termine fehlen lokal seit dem letzten Sync "
              f"(Sperre {sp.loeschsperre}). Ohne Prüfung würden sie bei Google "
              f"gelöscht. Stand davor: heutiger Snapshot / git-Spiegel. Gewollt? "
              f"Einmal mit ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1.")
        for n in fehlen[:10]:
            print("   fehlt:", n)
        return 2
    # Die Google-Sicherung gehört zum echten Paar „zentrale" (so ruft es der
    # Timer). Andere Aufrufe (ein Paar von Hand, Tests) lassen sie aus.
    if "zentrale" in argv and not _google_sichern(exe):
        print("ABBRUCH: die Sicherungskopie von Google ließ sich nicht holen — "
              "ohne frische Sicherung wird nicht gesynct.")
        return 3

    code = subprocess.run([exe, "sync", *argv]).returncode
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
