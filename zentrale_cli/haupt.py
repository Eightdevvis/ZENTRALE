"""Einstieg von `zentrale`: Befehl lesen, weiterreichen, Fehler als einen
Satz zeigen. Ohne Befehl → TUI (beim allerersten Start erst der Assistent)."""

import os

from zentrale_cli import WURZEL, aktualisieren, assistent, befehle
from zentrale_cli.ausgabe import Terminal, hilfe
from zentrale_cli.texte import t

BEFEHLE = {
    ("welcome",): befehle.welcome,
    ("setup",): assistent.setup,
    ("login",): befehle.login,
    ("logout",): befehle.logout,
    ("account", "create"): befehle.account_create,
    ("account", "recover"): befehle.account_recover,
    ("account", "password"): befehle.account_password,
    ("sync",): befehle.sync,
    ("status",): befehle.status,
    ("devices",): befehle.devices,
    ("adapter",): befehle.adapter_liste,
    ("adapter", "setup"): befehle.adapter_setup,
    ("cloud", "usage"): befehle.cloud_usage,
    ("update",): aktualisieren.update,
    ("version",): befehle.version,
    ("--version",): befehle.version,
}


def _entwickler_checkout() -> bool:
    """Sashas Checkout (mit .git) startet nie ungefragt den Assistenten."""
    return os.path.exists(os.path.join(WURZEL, ".git"))


def main(argv=None, term=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    term = term or Terminal()
    if argv and argv[0] in ("-h", "--help", "help"):
        hilfe(term)
        return 0
    try:
        if not argv:
            if not befehle.eingerichtet() and not _entwickler_checkout():
                rc = assistent.setup(term, erster_start=True)
                if rc != 0:
                    return rc
            befehle.nutzung_warnung(term)      # eine Zeile, nur Betreiber; nie blockierend
            befehle.neue_apps_beim_start(term)
            return befehle.tui(term)
        fn = BEFEHLE.get(tuple(argv[:2])) or BEFEHLE.get(tuple(argv[:1]))
        if fn is None:
            term.fehler(t("unknown_command", cmd=" ".join(argv)))
            return 2
        return fn(term)
    except befehle.FEHLER as e:
        term.fehler(str(e))
        return 1
    except (KeyboardInterrupt, EOFError):
        term.sag(t("interrupted"))
        return 130
