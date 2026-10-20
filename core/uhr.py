# core/uhr.py
#
# Die eine Uhr: woher „jetzt" und „heute" kommen — und das Tageswechsel-
# Ereignis. Anlass 20.10.2026: die TUI lief über Mitternacht und der
# Kalender stand am Morgen noch auf dem 19.10. (Anker beim Öffnen gesetzt,
# Antwort mit `today` ohne Datum im Schlüssel gepuffert). Im Dauerbetrieb
# auf einem Server wird so etwas zur stillen Falle.
#
# Regel (memory/system/gefahrzonen.md, „Eingefrorener Tag"):
#   * „heute" wird bei JEDEM Gebrauch gefragt (uhr.heute()), nie beim Import,
#     im __init__ oder als Default einer Signatur festgehalten.
#   * Wer sich etwas mit Tagesbezug merkt (Anker, Puffer, „schon gezeigt"),
#     meldet sich bei einem Tageswechsel an und rückt/verwirft dort.
#   * Wächter: tests/test_tageswechsel.py (AST über core/, ui/, tui/).
#
# Stdlib-only, ohne Kern-Imports: die TUI darf es (Tür in
# memory/system/bauplan_kern.md), und es steht in deploy/aussenposten.txt.
#
# Einfrieren in Tests: uhr.stellen(datetime(...)) bzw. `with uhr.gestellt(..)`.
# Die Bildschirm-Tests (tests/tui_schirm/sitecustomize.py) und der Prüfstand
# (scripts/pruefstand_teile/uhr.py) verbiegen datetime selbst — das greift
# hier mit, weil jetzt() datetime.now() erst beim Aufruf fragt.

from contextlib import contextmanager
from datetime import date, datetime, timedelta

_fest = [None]            # gestellte Zeit (datetime) oder None = echte Uhr
_versatz = [timedelta(0)]  # bei gestellter Zeit: wie weit sie seitdem lief


def jetzt() -> datetime:
    """Die aktuelle Ortszeit (naiv, wie datetime.now())."""
    if _fest[0] is not None:
        return _fest[0] + _versatz[0]
    return datetime.now()


def heute() -> date:
    """Der heutige Tag — bei jedem Aufruf neu gefragt."""
    return jetzt().date()


def stellen(dt: datetime | None) -> None:
    """Uhr auf dt stellen (None = wieder die echte Uhr). Nur für Tests."""
    _fest[0] = dt
    _versatz[0] = timedelta(0)


def vorstellen(**dauer) -> None:
    """Die gestellte Uhr weiterlaufen lassen, z. B. vorstellen(minutes=2)."""
    if _fest[0] is None:
        raise RuntimeError("uhr.vorstellen nur bei gestellter Uhr")
    _versatz[0] += timedelta(**dauer)


@contextmanager
def gestellt(dt: datetime):
    """with uhr.gestellt(datetime(2026, 10, 19, 23, 59)): …"""
    alt = (_fest[0], _versatz[0])
    stellen(dt)
    try:
        yield
    finally:
        _fest[0], _versatz[0] = alt


class Tageswechsel:
    """Das Tageswechsel-Ereignis für eine Schleife (TUI-Hauptschleife,
    Backend-Schleife in core/main.py). pruefen() ist billig und gehört in
    jeden Durchlauf; wechselt der Tag (auch nach Tagen Ruhezustand), ruft
    es die Angemeldeten EINMAL mit (alter_tag, neuer_tag).

    Gezählt wird ab dem Tag beim Bau — der einzige Ort, an dem ein Tag
    festgehalten werden soll: genau dafür, ihn zu erneuern."""

    def __init__(self, uhr=heute):
        self._uhr = uhr
        self._tag = uhr()
        self._hoerer = []

    @property
    def tag(self) -> date:
        return self._tag

    def anmelden(self, fn):
        """fn(alt: date, neu: date) — Fehler eines Hörers stören die anderen nicht."""
        self._hoerer.append(fn)
        return fn

    def pruefen(self) -> date | None:
        """-> der neue Tag, wenn er gerade gewechselt hat, sonst None."""
        neu = self._uhr()
        if neu == self._tag:
            return None
        alt, self._tag = self._tag, neu
        for fn in list(self._hoerer):
            try:
                fn(alt, neu)
            except Exception:
                pass
        return neu
