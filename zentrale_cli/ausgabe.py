"""Ein- und Ausgabe des Befehls: Farben (nur am Terminal und ohne NO_COLOR),
Fragen, Passwörter, Auswahl-Listen. Nur stdlib — läuft auch über ssh.

Alles läuft über ein `Terminal`-Objekt, damit Tests es durch ein gespieltes
ersetzen können (tests/test_zentrale_cli.py)."""

import getpass
import os
import sys

from zentrale_cli.texte import t

BACK = "\0back"          # Terminal.choose: the person asked to go one step back

_FARBEN = {"fett": "1", "blass": "2", "akzent": "36", "gut": "32", "warn": "33",
           "fehler": "31"}


class Terminal:
    def __init__(self, aus=None, ein=None):
        self.aus = aus or sys.stdout
        self.ein = ein or sys.stdin
        self.farbig = (hasattr(self.aus, "isatty") and self.aus.isatty()
                       and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb")
        # Darf ungefragt eine Frage kommen (neue App mit Daten)? Nur, wenn
        # jemand am Terminal sitzt — nie in einem Skript oder Timer.
        self.interaktiv = hasattr(self.ein, "isatty") and self.ein.isatty()

    # ── Ausgabe ─────────────────────────────────────────────────────
    def f(self, text, *arten):
        if not self.farbig or not arten:
            return text
        return "\033[" + ";".join(_FARBEN[a] for a in arten) + "m" + text + "\033[0m"

    def sag(self, text="", *arten):
        print(self.f(text, *arten), file=self.aus, flush=True)

    def fehler(self, text):
        print(self.f(t("error", text=text), "fehler"), file=sys.stderr if self.aus is sys.stdout
              else self.aus, flush=True)

    # ── Eingabe ─────────────────────────────────────────────────────
    def frage(self, aufforderung) -> str:
        print(aufforderung, end="", file=self.aus, flush=True)
        zeile = self.ein.readline()
        if not zeile:
            raise EOFError
        return zeile.rstrip("\n")

    def geheim(self, aufforderung) -> str:
        if self.ein is sys.stdin and sys.stdin.isatty():
            return getpass.getpass(aufforderung)
        return self.frage(aufforderung)

    def ja(self, frage, vorgabe=None) -> bool:
        anhang = (t("yes_no_default_yes") if vorgabe else
                  t("yes_no_default_no") if vorgabe is False else t("yes_no"))
        while True:
            a = self.frage(frage + anhang).strip().lower()
            if not a and vorgabe is not None:
                return vorgabe
            if a in ("y", "yes", "j", "ja"):
                return True
            if a in ("n", "no", "nein"):
                return False

    def eins_von(self, frage, optionen):
        """optionen = [(wert, text)] → wert. Nummern, damit es überall geht."""
        self.sag(frage, "fett")
        for i, (_w, text) in enumerate(optionen, 1):
            self.sag(f"  {self.f(str(i), 'akzent')}  {text}")
        while True:
            a = self.frage(t("number_choice", n=len(optionen))).strip()
            if a.isdigit() and 1 <= int(a) <= len(optionen):
                return optionen[int(a) - 1][0]

    def choose(self, question, options, default=None, back=False):
        """options = [(value, text)] → value, or BACK when `back` is allowed
        and asked for ('b'). Enter takes `default` (a value, shown as such).
        Numbers, so it works everywhere (setup wizard, zentrale_cli/wizard.py)."""
        self.sag(question, "fett")
        values = [v for v, _text in options]
        for i, (v, text) in enumerate(options, 1):
            mark = " " + self.f(t("choice_default"), "blass") if v == default else ""
            self.sag(f"  {self.f(str(i), 'akzent')}  {text}{mark}")
        prompt = t("choice_prompt", n=len(options))
        if default in values:
            prompt += t("choice_prompt_default", n=values.index(default) + 1)
        if back:
            prompt += t("choice_prompt_back")
        while True:
            a = self.frage(prompt + ": ").strip().lower()
            if not a and default in values:
                return default
            if back and a == "b":
                return BACK
            if a.isdigit() and 1 <= int(a) <= len(options):
                return values[int(a) - 1]

    def ankreuzen(self, titel, eintraege, an):
        """eintraege = [(wert, name, beschreibung)], an = Menge der Werte, die
        anfangs gewählt sind → Menge der gewählten Werte, oder None (abgebrochen).
        Am echten Terminal mit Pfeiltasten, sonst über Nummern."""
        an = set(an)
        if self.ein is sys.stdin and sys.stdin.isatty() and self.aus.isatty():
            try:
                return _ankreuzen_roh(self, titel, eintraege, an)
            except (ImportError, OSError):
                pass
        while True:
            self.sag(titel, "fett")
            for i, (w, name, besch) in enumerate(eintraege, 1):
                kreuz = "[x]" if w in an else "[ ]"
                self.sag(f"  {i:>2} {kreuz} {name}  " + self.f(besch, "blass"))
            a = self.frage(t("setup_pick_fallback")).strip().lower()
            if not a:
                return an
            if a == "q":
                return None
            if a == "a":
                an = {w for w, _n, _b in eintraege}
                continue
            if a == "n":
                an = set()
                continue
            for teil in a.replace(",", " ").split():
                if teil.isdigit() and 1 <= int(teil) <= len(eintraege):
                    an ^= {eintraege[int(teil) - 1][0]}


def _ankreuzen_roh(term, titel, eintraege, an):
    import termios
    import tty
    fd = sys.stdin.fileno()
    alt = termios.tcgetattr(fd)
    pos, zeilen = 0, len(eintraege) + 2
    out = term.aus

    def malen(erstes):
        if not erstes:
            out.write(f"\033[{zeilen}F")
        out.write("\033[J" + term.f(titel, "fett") + "\r\n")
        for i, (w, name, besch) in enumerate(eintraege):
            kreuz = term.f("[x]", "gut") if w in an else "[ ]"
            zeiger = term.f("›", "akzent") if i == pos else " "
            out.write(f" {zeiger} {kreuz} {name}  {term.f(besch, 'blass')}\r\n")
        out.write(term.f(t("setup_pick_help"), "blass") + "\r\n")
        out.flush()

    try:
        tty.setraw(fd)
        malen(True)
        while True:
            c = os.read(fd, 1)
            if c == b"\x1b":
                rest = os.read(fd, 2)
                c = {b"[A": b"k", b"[B": b"j"}.get(rest, b"")
            if c in (b"k",) and pos > 0:
                pos -= 1
            elif c in (b"j",) and pos < len(eintraege) - 1:
                pos += 1
            elif c == b" ":
                an ^= {eintraege[pos][0]}
            elif c == b"a":
                an = {w for w, _n, _b in eintraege}
            elif c == b"n":
                an = set()
            elif c in (b"\r", b"\n"):
                return an
            elif c in (b"q", b"\x03"):
                return None
            malen(False)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, alt)
        out.write("\r\n")
        out.flush()


# ── Hilfe ───────────────────────────────────────────────────────────────

GRUPPEN = [
    ("group_start", ["cmd_tui", "cmd_welcome", "cmd_setup"]),
    ("group_account", ["cmd_login", "cmd_logout", "cmd_account_create",
                       "cmd_account_recover", "cmd_account_password", "cmd_leave"]),
    ("group_sync", ["cmd_sync", "cmd_status", "cmd_devices", "cmd_devices_remove", "cmd_adapter", "cmd_adapter_setup",
                    "cmd_adapter_run", "cmd_adapter_calendar", "cmd_timers", "cmd_timers_install", "cmd_timers_remove"]),
    ("group_program", ["cmd_apps_install", "cmd_apps_plug", "cmd_cloud_usage", "cmd_update", "cmd_version", "cmd_help"]),
]


def banner(term):
    for zeile in t("banner").splitlines():
        term.sag("  " + zeile, "akzent", "fett")
    term.sag("  " + t("tagline"), "blass")


def hilfe(term):
    banner(term)
    term.sag()
    term.sag(t("usage"), "fett")
    term.sag("  " + t("usage_line"))
    term.sag("  " + t("usage_none"), "blass")
    breite = max(len(t(k)[0]) for _g, ks in GRUPPEN for k in ks) + 2
    for gruppe, befehle in GRUPPEN:
        term.sag()
        term.sag(t(gruppe), "fett")
        for k in befehle:
            name, was = t(k)
            term.sag("  " + term.f(name.ljust(breite), "akzent") + was)
    term.sag()
    term.sag(t("examples"), "fett")
    bsp_breite = max(len(b) for b, _w in t("ex")) + 2
    for befehl, was in t("ex"):
        term.sag("  " + term.f(befehl.ljust(bsp_breite), "gut") + term.f("# " + was, "blass"))
    term.sag()
    term.sag("  " + t("more_help"), "blass")
