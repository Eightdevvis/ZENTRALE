# core/erlaubnis.py
#
# Das Erlaubnis-Gate: welche Werkzeuge vor der Ausführung bestätigt werden
# müssen, und die Ja/Nein-Frage, die Sasha dazu sieht.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 stand das
# in core/ai.py, und die Werkzeug-Schleife musste dafür den ganzen lokalen
# Weg importieren — einer der Knoten im Import-Kreis. Aufbau des KI-Kerns:
# memory/ki/kern_aufbau.md.
#
# Seit 2026-10-07 steht WAS bestätigt wird und WIE gefragt wird beim
# Werkzeug selbst, im Werkzeug-Register (core/werkzeug_register.py: Felder
# erlaubnis und frage). Eine zweite Liste hier lief früher neben den Schemas
# her und konnte ein neues Werkzeug still vergessen. Dieses Modul bleibt die
# Tür, durch die die Schleife (werkzeug_schleife.run_tool) fragt.
#
# Das Gate kommt automatisch vor der Ausführung, das Modell weiß nichts davon
# (bewusst NICHT modellgetrieben: ein 9b ruft sowas nicht zuverlässig von
# selbst). Geprüft wird immer gegen den kanonischen Namen, sonst rutschte ein
# Werkzeug unter einem Alias am Gate vorbei — der stillste denkbare Fehler.

import werkzeug_register


# Die Werkzeuge, die IMMER bestätigt werden (kanonische Namen). Abgeleitet,
# nur zum Lesen für Skripte und Tests — entschieden wird über
# braucht_erlaubnis, denn write_note hängt von den Argumenten ab.
PERMISSION_REQUIRED_TOOLS = frozenset(werkzeug_register.immer_bestaetigen())


def braucht_erlaubnis(name: str, args: dict | None = None) -> bool:
    """Muss dieser Tool-Call vor der Ausführung bestätigt werden?

    Der Name kommt vom Modell und trägt die Schreibweise seiner Schiene.
    write_note ist frei, ausser es trifft eine Kernakte (Hausregeln,
    Steckbrief, Ziele, Sasha 2026-10-06) — dafür braucht es die Argumente.
    """
    return werkzeug_register.braucht_erlaubnis(name, args)


def frage(name: str, args: dict) -> str:
    """Die menschenlesbare Ja/Nein-Frage für ein gegatetes Tool (wird Sasha
    im Dialog gezeigt + vorgelesen). Vorlage pro Werkzeug im Register,
    allgemeiner Rückfall für eins ohne."""
    return werkzeug_register.frage(name, args)
