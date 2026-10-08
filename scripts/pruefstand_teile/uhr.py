# Die Uhr des Prüfstands: ein Fall spielt zu SEINER Zeit.
#
# Das Gespräch vom 08.10.2026 hängt am Datum: „heute" ist Donnerstag, die
# Reise nyam läuft gerade, die Herbstferien haben schon begonnen. Liefe der
# Fall eine Woche später gegen die echte Uhr, prüfte er etwas anderes. Also
# wird die Uhr verstellt — und läuft danach normal weiter (Versatz, kein
# Standbild: Laufzeiten und Zeitstempel bleiben sinnvoll).
#
# Wie (2026-10-08): freezegun gibt es im venv nicht, und eine neue
# Abhängigkeit nur dafür lohnt nicht. Stattdessen zwei Unterklassen von
# date/datetime, deren today()/now() den Versatz addieren. Sie ersetzen
#   1. die schon gebundenen Namen in den Modulen des Codes (core/, ui/):
#      `from datetime import date` → falsche Klasse, `import datetime as dt`
#      → ein Ersatz-Modul mit den falschen Klassen,
#   2. für die Dauer des Falls sys.modules["datetime"] durch dieses Ersatz-
#      Modul (für `from datetime import datetime` IN Funktionen, wie
#      ki_werkzeuge._read_time es macht).
# Das echte Modul `datetime` selbst bleibt unverändert: pydantic (im
# anthropic-SDK) baut seine Schemas erst beim ersten Gebrauch und vergleicht
# dabei `tp is datetime.datetime` — mit einer verbogenen Klasse dort scheiterte
# jede Modell-Antwort (gefunden im ersten Probelauf, 2026-10-08).
# Fremde Bibliotheken behalten so die echten Klassen; die Unterklassen sind
# zu ihnen kompatibel (isinstance gilt in beide Richtungen, s. u.).
#
# AUSGENOMMEN: usage. Die Kosten eines Durchgangs gehören an den ECHTEN Tag
# in Sashas Buchhaltung, nicht an den 08.10., wenn der Fall im November läuft.

import datetime as _dt_modul
import os
import sys
import types
from contextlib import contextmanager

_ECHT_DATE = _dt_modul.date
_ECHT_DATETIME = _dt_modul.datetime

_versatz = [_dt_modul.timedelta(0)]

AUSGENOMMEN = {"usage"}


# isinstance muss in BEIDE Richtungen gelten: der Kern prüft
# `isinstance(x, datetime)` auf Werte, die icalendar oder dateutil mit den
# ECHTEN Klassen gebaut haben. Ohne diese Metaklassen galt ein echtes
# datetime nicht als (falsches) datetime — und jeder .ics-Termin mit Uhrzeit
# wurde zum Ganztags-Termin (gefunden im ersten Probelauf, 2026-10-08).
class _DatumArt(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _ECHT_DATE)


class _ZeitArt(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _ECHT_DATETIME)


class FalschesDatum(_ECHT_DATE, metaclass=_DatumArt):
    @classmethod
    def today(cls):
        t = _ECHT_DATETIME.now() + _versatz[0]
        return cls(t.year, t.month, t.day)


class FalscheZeit(_ECHT_DATETIME, metaclass=_ZeitArt):
    @classmethod
    def now(cls, tz=None):
        t = _ECHT_DATETIME.now(tz) + _versatz[0]
        return cls(t.year, t.month, t.day, t.hour, t.minute, t.second,
                   t.microsecond, tzinfo=t.tzinfo)

    @classmethod
    def today(cls):
        return cls.now()

    def date(self):
        # Sonst käme ein echtes date heraus, und `date.today() == jetzt.date()`
        # wäre trotzdem wahr — aber isinstance(…, FalschesDatum) nicht.
        return FalschesDatum(self.year, self.month, self.day)


def _unter(pfad: str, wurzeln) -> bool:
    pfad = os.path.abspath(pfad)
    return any(pfad.startswith(w + os.sep) for w in wurzeln)


@contextmanager
def verstellt(jetzt: _ECHT_DATETIME | None, code_wurzel: str):
    """Die Uhr auf `jetzt` (naiv, Ortszeit) stellen, solange der Block läuft.
    None → echte Zeit (nichts verstellen)."""
    if jetzt is None:
        yield
        return
    _versatz[0] = jetzt - _ECHT_DATETIME.now()
    wurzeln = [os.path.abspath(os.path.join(code_wurzel, d))
               for d in ("core", "ui")]
    ersatz = types.ModuleType("datetime")
    ersatz.__dict__.update(vars(_dt_modul))
    ersatz.date, ersatz.datetime = FalschesDatum, FalscheZeit
    tausch = {id(_ECHT_DATE): FalschesDatum, id(_ECHT_DATETIME): FalscheZeit,
              id(_dt_modul): ersatz}
    getauscht = []                      # (modul, name, alter Wert)
    for name, modul in list(sys.modules.items()):
        datei = getattr(modul, "__file__", None) or ""
        if not datei or not _unter(datei, wurzeln):
            continue
        if name.rsplit(".", 1)[-1] in AUSGENOMMEN:
            continue
        for attr, wert in list(vars(modul).items()):
            neu = tausch.get(id(wert))
            if neu is not None:
                getauscht.append((modul, attr, wert))
                setattr(modul, attr, neu)
    sys.modules["datetime"] = ersatz
    try:
        yield
    finally:
        sys.modules["datetime"] = _dt_modul
        for modul, attr, wert in getauscht:
            setattr(modul, attr, wert)
        _versatz[0] = _dt_modul.timedelta(0)
