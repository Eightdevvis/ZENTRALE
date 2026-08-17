"""
theme — der Tag/Nacht-Modus von ZENTRALE, mit der Datei als EINZIGER Wahrheit.

Quelle ist ~/.config/zentrale/theme (ein Wort: auto | day | night). Daran
hängen Terminal, Browser, Desktop, bat und nvim; die TUI ist nur ein weiterer
Teilnehmer, kein Besitzer.

WARUM ES DIESES MODUL GIBT
--------------------------
Der Modus lag früher doppelt vor: als lokale Variable in der TUI UND als Datei,
abgeglichen über drei Hilfspuffer (zuletzt geschriebener Modus, zuletzt
gesehene mtime, zuletzt gemeldete Farbe). Dieser Abgleich ist nicht atomar —
zwischen »Taste ändert die Variable« und »Schleife schreibt die Datei« liegt
ein Fenster, in dem ein Lesevorgang die Variable wieder überschreibt. Sichtbar
wurde das als Theme, das kurz umsprang und wieder zurück; im Protokoll standen
Fremd-Einträge mit exakt den Werten, die die TUI selbst eine Zeile vorher
geschrieben hatte. Sie las ihr eigenes Echo.

Die Antwort ist nicht ein weiterer Puffer, sondern das Wegnehmen des zweiten
Zustands:

  * `mode()` liest die Datei (per mtime gecacht, damit es in einer
    Bildschleife billig bleibt). Der Cache widerspricht der Datei nie — er
    wird verworfen, sobald die mtime abweicht, und nie gegen sie behauptet.
  * `set()` schreibt die Datei. Das ist der einzige Schreibweg.
  * `cycle()` rechnet auf dem DATEI-Stand, nicht auf einer mitgeführten
    Variablen — zwei schnelle Tastendrücke können sich nicht überholen.

Damit ist eine Rückkopplung strukturell unmöglich statt nur unwahrscheinlich:
es gibt nichts mehr, das man zurückziehen müsste.

Getestet in tests/test_theme_state.py.
"""
import os
import time

MODI = ("auto", "day", "night")
ZYKLUS = {"auto": "day", "day": "night", "night": "auto"}

#: Ab dieser Stunde gilt hell, ab TAG_ENDE wieder dunkel. Dieselbe Regel wie in
#: scripts/zentrale-term-theme, monolith.html computeTheme() und
#: nvim/lua/zentrale_theme (dort je in der Sprache der Umgebung).
TAG_START, TAG_ENDE = 5, 21


def theme_file():
    """Pfad der Theme-Datei. ZENTRALE_THEME_FILE sticht (wie in allen Appliern)."""
    return (os.environ.get("ZENTRALE_THEME_FILE")
            or os.path.expanduser("~/.config/zentrale/theme"))


def resolve(mode, stunde=None):
    """Modus → sichtbare Farbe ("day"/"night"). auto löst nach der Uhrzeit auf."""
    if mode in ("day", "night"):
        return mode
    if stunde is None:
        stunde = int(time.strftime("%H"))
    return "day" if TAG_START <= stunde < TAG_ENDE else "night"


class ThemeState:
    """Lesender und schreibender Zugriff auf den Modus — Datei als Wahrheit.

    :param path: Theme-Datei (Default: :func:`theme_file`).
    :param log_path: Änderungsprotokoll; None schaltet es ab.
    """

    def __init__(self, path=None, log_path=None):
        self.path = path or theme_file()
        if log_path is None:
            cache = (os.environ.get("XDG_CACHE_HOME")
                     or os.path.expanduser("~/.cache"))
            log_path = os.path.join(cache, "zentrale", "theme-changes.log")
        self.log_path = log_path
        self._mode = self._read()
        self._stamp = self._file_stamp()

    # ── lesen ────────────────────────────────────────────────────────────
    def _file_stamp(self):
        """mtime in ns — oder None, wenn es die Datei nicht gibt."""
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def _read(self):
        """Dateiinhalt → gültiger Modus. Kaputt/fehlend/LEER = auto.

        Leer ist dabei nicht besonders behandelt: anders als bei nvim, das auf
        jedes fs_event reagiert, lesen wir nur beim Bildaufbau — den
        Sekundenbruchteil zwischen truncate und write treffen wir praktisch
        nicht, und wenn doch, korrigiert der nächste Durchlauf ihn sofort.
        Geschrieben wird hier ohnehin atomar (tmp + rename), also entsteht
        dieses Fenster durch UNS gar nicht erst.
        """
        try:
            with open(self.path) as fh:
                raw = fh.read().strip()
        except OSError:
            return "auto"
        return raw if raw in MODI else "auto"

    def mode(self):
        """Aktueller Modus, frisch aus der Datei (per mtime gecacht)."""
        stamp = self._file_stamp()
        if stamp != self._stamp:
            alt = self._mode
            self._stamp = stamp
            self._mode = self._read()
            if self._mode != alt:
                self.log("fremd", alt, self._mode)
        return self._mode

    def resolved(self, stunde=None):
        """Sichtbare Farbe zum aktuellen Modus ("day"/"night")."""
        return resolve(self.mode(), stunde)

    # ── schreiben ────────────────────────────────────────────────────────
    def set(self, neu, quelle="tui"):
        """Modus setzen = Datei schreiben. → True, wenn sich etwas geändert hat.

        Kein Spiegel, kein Zurückschreiben, keine Echo-Unterdrückung: nach dem
        Schreiben ziehen wir den Cache direkt auf denselben Stand. Selbst wenn
        die gemerkte mtime danebenläge, entstünde daraus nichts Falsches — der
        nächste `mode()` liest ja wieder die Datei, und in der steht genau das,
        was wir geschrieben haben. Genau daran scheiterte die alte Fassung: sie
        hatte einen zweiten Zustand, der der Datei widersprechen konnte.
        """
        if neu not in MODI or neu == self.mode():
            return False
        self.log(quelle, self._mode, neu)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Atomar: mit "w" wäre die Datei zwischen truncate und write kurz
            # leer — nvims fs_event feuert schon beim truncate und läse dann
            # nichts. Ein rename ist für jeden Leser unteilbar.
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                fh.write(neu + "\n")
            os.replace(tmp, self.path)
        except OSError:
            return False
        self._mode = neu
        self._stamp = self._file_stamp()
        return True

    def cycle(self, quelle="tui"):
        """auto → day → night → auto, gerechnet auf dem Datei-Stand."""
        return self.set(ZYKLUS[self.mode()], quelle)

    # ── protokollieren ───────────────────────────────────────────────────
    def log(self, quelle, alt, neu):
        """Wechsel mitschreiben — wer, wann, von wo nach wo.

        `quelle=tui` heißt: wir waren es (Taste oder Befehl). `quelle=fremd`
        heißt: die Datei hat sich unter uns geändert, es war also ein anderer
        Prozess — welcher, hält `scripts/zentrale-theme-watch` fest.
        """
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a") as fh:
                fh.write("%s  %-5s  %s -> %s\n"
                         % (time.strftime("%F %T"), quelle, alt, neu))
        except OSError:
            pass
