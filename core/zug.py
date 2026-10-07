# core/zug.py
#
# Was zum GERADE LAUFENDEN Chat-Zug gehört: in welchem Gespräch er läuft, und
# was ein Werkzeug unterwegs an die TUI melden will (z. B. „ein Dokument liegt
# jetzt in der Ablage").
#
# 2026-10-07, Claude-Web-Plan Phase 5 (memory/ki/ablage.md). Warum ein eigenes
# Modul: ein Werkzeug-Ausführer (ki_werkzeuge) gibt nur einen Text ans Modell
# zurück, er kann kein Event in den SSE-Strom legen. Die Schleife
# (werkzeug_schleife.run_tool) dafür umzubauen hieße, jedes neue Ereignis dort
# einzutragen. Stattdessen: die Chat-Route öffnet einen Zug, ein Ausführer
# legt Ereignisse hier ab, die Route holt sie nach jedem Werkzeug ab und
# schickt sie mit. Dieselbe Tür gibt den Ausführern die Gesprächs-id (run_code
# benennt seinen Arbeitsordner danach).
#
# contextvars statt einer globalen Variable: zwei Züge können gleichzeitig
# laufen (zwei Rechner am selben Backend, Erinnerung + Chat), jeder in seinem
# Thread. Ein Zug lebt in dem Thread, der den SSE-Strom abarbeitet — dort
# laufen auch die Werkzeuge (werkzeug_schleife ist ein Generator im selben
# Strom).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import contextvars

_aktuell = contextvars.ContextVar("zentrale_zug", default=None)


class _Zug:
    def __init__(self, gespraech, abbruch=None):
        self.gespraech = gespraech
        self.abbruch = abbruch
        self.ereignisse = []


def beginnen(gespraech=None, abbruch=None):
    """Einen Zug öffnen. -> Marke für beenden(). Ohne Zug (Takt, Tutor,
    Skripte) melden Werkzeuge ins Leere — das ist gewollt.

    abbruch: das Stopp-Signal des Zugs (threading.Event, state.
    chat_zug_beginnen). Seit 2026-10-07 hier, damit ein Werkzeug, das selbst
    lange läuft (run_code), mitten drin aufhören kann — die Schleife prüft
    das Signal nur ZWISCHEN den Werkzeugen."""
    return _aktuell.set(_Zug(gespraech, abbruch))


def beenden(marke) -> None:
    try:
        _aktuell.reset(marke)
    except (ValueError, RuntimeError):
        # In einem anderen Kontext beendet (sollte nicht vorkommen): dann
        # wenigstens leeren statt einen alten Zug stehen zu lassen.
        _aktuell.set(None)


def gespraech():
    """Die Gesprächs-id des laufenden Zugs, oder None."""
    z = _aktuell.get()
    return z.gespraech if z else None


def abbruch():
    """Das Stopp-Signal des laufenden Zugs (hat is_set/wait), oder None."""
    z = _aktuell.get()
    return z.abbruch if z else None


def melden(ereignis: dict) -> None:
    """Ein Ereignis für die TUI vormerken (z. B. {"ablage": {...}})."""
    z = _aktuell.get()
    if z is not None:
        z.ereignisse.append(dict(ereignis))


def abholen() -> list:
    """Alle vorgemerkten Ereignisse — und danach leer."""
    z = _aktuell.get()
    if z is None or not z.ereignisse:
        return []
    raus, z.ereignisse = z.ereignisse, []
    return raus
