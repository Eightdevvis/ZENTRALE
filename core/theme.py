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


def ist_arbeitskopie():
    """Laeuft dieses Modul aus einem Worktree statt aus dem Haupt-Checkout?

    Worktrees isolieren, was IM Repo liegt. ~/.config/zentrale/ liegt
    ausserhalb — da kommt jede Arbeitskopie gleichermassen ran, und genau so
    hat ein Testlauf aus einem Worktree am 2026-08-18 Sashas echtes Theme
    umgeschaltet, obwohl der Worktree ansonsten sauber isoliert war.
    """
    return "/.claude/worktrees/" in os.path.abspath(__file__)


def _echte_konfiguration(pfad):
    """Zeigt `pfad` auf Sashas LAUFENDE Konfiguration (nicht auf ein tmp)?"""
    echt = os.path.realpath(os.path.expanduser("~/.config/zentrale"))
    return os.path.realpath(pfad).startswith(echt + os.sep)


def darf_schreiben(pfad):
    """Darf DIESER Prozess `pfad` schreiben? → (bool, Grund)

    Ein Nein gibt es nur in genau einer Lage: Code aus einer Arbeitskopie will
    die echte Konfiguration anfassen. Die laufende TUI aus dem Haupt-Checkout
    schaltet weiter wie immer, und ein Test, der auf sein tmp_path umgelenkt
    ist, ebenso — sonst waere der Riegel schlimmer als das Problem.
    """
    if ist_arbeitskopie() and _echte_konfiguration(pfad):
        return False, "arbeitskopie"
    return True, ""


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
        """Die GELTENDE Farbe ("day"/"night").

        Kommt aus theme.now, also von `scripts/zentrale-themed` — der einzigen
        Stelle, die `auto` auflöst. Nur wenn es die Datei noch nicht gibt (der
        Dienst lief nie), rechnen wir selbst, damit eine frische Installation
        nicht im Dunkeln steht; `stunde` erzwingt das für Tests.
        """
        if stunde is not None:
            return resolve(self.mode(), stunde)
        jetzt = read_now(default=None)
        if jetzt is not None:
            return jetzt
        return resolve(self.mode())

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
        erlaubt, grund = darf_schreiben(self.path)
        if not erlaubt:
            self.log(grund, self._mode, neu)
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


# ═══════════════════════════════════════════════════════════════════════════
# Der Dienst: EINE Stelle löst auf, alle anderen lesen nur noch das Ergebnis
# ═══════════════════════════════════════════════════════════════════════════
#
# Vorher rechnete JEDER Teilnehmer die 05/21-Regel selbst: die vier Bash-
# Applier, dieses Modul, nvims Lua, der Morgen-Messenger, das Tutor-Zimmer —
# acht Implementierungen derselben zwei Zahlen, jede mit eigenem Timing (mal
# ein Minuten-Timer, mal ein 60-s-Tick, mal beim nächsten Bildaufbau). Deshalb
# lief immer wieder irgendein Teilnehmer für eine Weile gegen den Rest, und
# jede Reparatur betraf nur die Stelle, an der es gerade auffiel.
#
# Jetzt gibt es ZWEI Dateien mit klaren Rollen:
#
#   ~/.config/zentrale/theme      WUNSCH    auto | day | night   ← ZENTRALE schreibt
#   ~/.config/zentrale/theme.now  ERGEBNIS  day | night          ← der Dienst schreibt
#
# Der Dienst (`scripts/zentrale-themed`) ist der einzige, der `auto` auflöst.
# Er wartet auf zwei Dinge: eine Änderung des Wunsches (inotify) und den
# nächsten Zeitpunkt, an dem die Uhr das Ergebnis kippt — und schläft bis
# dahin, statt jede Minute nachzusehen. Ändert sich das Ergebnis, schreibt er
# theme.now und stößt die Applier an.
#
# Alle Konsumenten lesen nur noch theme.now. Sie brauchen keine Uhr, keinen
# Timer und keine Fallunterscheidung mehr — nur ein Wort aus einer Datei.

def now_file():
    """Pfad der Ergebnis-Datei (day|night). ZENTRALE_THEME_NOW sticht."""
    override = os.environ.get("ZENTRALE_THEME_NOW")
    if override:
        return override
    return theme_file() + ".now"


def read_now(default="day"):
    """Die effektive Farbe lesen — das ist ALLES, was ein Konsument tun muss.

    Fehlt die Datei (Dienst läuft noch nicht), fällt der Aufrufer auf `default`
    zurück statt selbst die Uhrzeit zu befragen: eine zweite Auflösung wäre
    genau die Doppelung, die hier abgeschafft wird.
    """
    try:
        with open(now_file()) as fh:
            wert = fh.read().strip()
    except OSError:
        return default
    return wert if wert in ("day", "night") else default


def naechster_wechsel(jetzt=None):
    """Sekunden bis zum nächsten uhrzeitbedingten Wechsel (im auto-Modus).

    Nur an den beiden Grenzen kippt die Farbe; dazwischen gibt es nichts zu
    tun. Der Dienst schläft deshalb genau bis dahin, statt zu pollen. Es wird
    immer mindestens eine Sekunde zurückgegeben, damit ein Rundungsfehler
    genau auf der Grenze keine enge Schleife auslöst.
    """
    jetzt = jetzt or time.localtime()
    sek_heute = jetzt.tm_hour * 3600 + jetzt.tm_min * 60 + jetzt.tm_sec
    for grenze in (TAG_START * 3600, TAG_ENDE * 3600):
        if sek_heute < grenze:
            return grenze - sek_heute
    return 24 * 3600 - sek_heute + TAG_START * 3600      # morgen früh


class ThemeDaemon:
    """Löst den Wunsch auf, schreibt das Ergebnis, stößt die Applier an.

    Bewusst ohne eigenen Zustand über die Dateien hinaus: was gilt, steht in
    theme.now; was gewünscht ist, in theme. Ein Neustart des Dienstes ändert
    nichts, ein zweiter Dienst ebenso wenig (er schriebe dasselbe).
    """

    def __init__(self, state=None, appliers=None, runner=None):
        self.state = state or ThemeState()
        self.appliers = appliers if appliers is not None else APPLIERS
        # runner injizierbar, damit Tests keine echten Prozesse starten
        self.runner = runner or _start_applier

    def effektiv(self, stunde=None):
        """Was JETZT gelten soll — die eine Auflösung im ganzen Projekt."""
        return resolve(self.state.mode(), stunde)

    def tick(self, stunde=None):
        """Einmal abgleichen. → die effektive Farbe, oder None ohne Änderung."""
        soll = self.effektiv(stunde)
        if soll == read_now(default=None):
            return None
        if not darf_schreiben(now_file())[0]:
            # Aus einer Arbeitskopie fassen wir weder die Datei noch die
            # Applier an: ein Dienst aus einem Worktree wuerde sonst Sashas
            # Terminal, nvim und Desktop umfaerben.
            return None
        self._schreibe(soll)
        for applier in self.appliers:
            self.runner(applier)
        return soll

    def _schreibe(self, farbe):
        pfad = now_file()
        if not darf_schreiben(pfad)[0]:
            return
        try:
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            tmp = pfad + ".tmp"          # atomar, wie überall (siehe set())
            with open(tmp, "w") as fh:
                fh.write(farbe + "\n")
            os.replace(tmp, pfad)
        except OSError:
            pass


#: Die Applier, die nach einer Änderung angestoßen werden. bat ist dabei,
#: obwohl es nichts umfärbt: es liest seine Config bei jedem Aufruf neu.
APPLIERS = ("zentrale-term-theme", "zentrale-browser-theme",
            "zentrale-desktop-theme", "zentrale-bat-theme")


def _start_applier(name):
    """Applier best-effort im Hintergrund starten (fehlt einer: egal)."""
    import subprocess
    try:
        subprocess.Popen([name], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass
