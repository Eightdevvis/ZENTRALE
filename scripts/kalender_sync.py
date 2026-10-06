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

Alle Argumente werden an `vdirsyncer sync` durchgereicht (z. B. ein Paar).
Exit-Code = der von vdirsyncer (1, wenn ZENTRALE nicht auf ics steht).
"""

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

    code = subprocess.run([exe, "sync", *argv]).returncode

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
