# core/titel_wochentag.py
#
# Welcher Wochentag steht in einem Titel — und passt er zum Tag, an dem der
# Eintrag stattfindet?
#
# Anlass 22.10.2026 (Gespräch 20261022-111358-dd6127): qwen trug Sashas
# „Mittwoch 16:15 - 17:15 Uhr: Jonas Schömer" als Serie mit BYDAY=WE ein,
# aber mit dem Titel „Sprechstunde Jonas Schömer (Mo)". Sasha: „der
# wochentausch ist doch ziemlich böse." Der Titel hatte einen erfundenen
# Wochentag, und der war falsch.
#
# Erkannt wird nur, was sicher ein Wochentag ist, damit gewöhnliche Titel
# nie anschlagen:
#   - ausgeschriebene Namen als ganzes Wort („Montag", „mittwochs");
#     Zusammensetzungen wie „Montagsrunde" nicht
#   - Kürzel (Mo, Di, Mi, Do, Fr, Sa, So) nur in Klammern, die sonst nur
#     Wochentage, Trenner und Uhrzeiten enthalten („(Mo)", „[Mo, Mi]",
#     „(Fr 14:00)"), oder als Anhang nach „ - ", „ – ", „, ", „ · ", „ | "
#     ganz am Ende („Sprechstunde – Mi"). „To Do", „So geht's", „Fr. Meier"
#     zählen damit nicht.
#
# Reines Python ohne Imports aus ZENTRALE (Fundament, Schicht 1): der
# Kalender-Kern darf es für eine eigene Warnung mitbenutzen.

import re
from datetime import date

KUERZEL = ("mo", "di", "mi", "do", "fr", "sa", "so")
_LANG = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4,
         "samstag": 5, "sonnabend": 5, "sonntag": 6}
_ICAL = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

_WORT_LANG = re.compile(r"(?<![\wäöüß])(" + "|".join(_LANG) + r")s?(?![\wäöüß])")
_KURZ = r"(?:mo|di|mi|do|fr|sa|so)\.?"
_TRENN = r"[\s,/&+–\-]|und"
_ZEIT = r"\d{1,2}(?:[:.]\d{2})?(?:\s*uhr)?"
_KLAMMER = re.compile(r"[(\[]\s*((?:" + _KURZ + r"|" + _TRENN + r"|" + _ZEIT + r")+)\s*[)\]]")
_ANHANG = re.compile(r"(?:\s[-–·|]\s|,\s*)((?:" + _KURZ + r")(?:\s*(?:,|/|und|&)\s*"
                     + _KURZ + r")*)\s*$")
_KURZ_WORT = re.compile(r"(?<![\wäöüß])(mo|di|mi|do|fr|sa|so)\b")


def im_titel(titel: str) -> set:
    """Die Wochentage (0 = Montag), die ein Titel sicher nennt — leer, wenn keiner."""
    t = (titel or "").casefold()
    tage = {_LANG[m.group(1)] for m in _WORT_LANG.finditer(t)}
    for m in _KLAMMER.finditer(t):
        kurz = _KURZ_WORT.findall(m.group(1))
        if kurz:
            tage |= {KUERZEL.index(k) for k in kurz}
    m = _ANHANG.search(t)
    if m:
        tage |= {KUERZEL.index(k) for k in _KURZ_WORT.findall(m.group(1))}
    return tage


def aus_regel(rrule: str, start: date | None = None) -> set | None:
    """Die Wochentage einer Wiederholung. None, wenn die Regel sie nicht
    festlegt (monatlich am 1., ohne erkennbaren Start …) — dann wird nicht
    geprüft. Täglich: alle Tage."""
    teile = {}
    for stueck in str(rrule or "").upper().replace("RRULE:", "").split(";"):
        if "=" in stueck:
            k, v = stueck.split("=", 1)
            teile[k.strip()] = v.strip()
    freq = teile.get("FREQ")
    if "BYDAY" in teile:
        tage = {_ICAL[m] for m in re.findall(r"(MO|TU|WE|TH|FR|SA|SU)", teile["BYDAY"])}
        return tage or None
    if freq == "DAILY":
        return set(range(7))
    if freq == "WEEKLY" and start is not None:
        return {start.weekday()}
    return None


def kuerzel(tage) -> str:
    return ", ".join(KUERZEL[t] for t in sorted(tage))


def widerspruch(titel: str, tage) -> str | None:
    """Nennt der Titel einen Wochentag, an dem der Eintrag NICHT stattfindet?
    -> Satz („nennt mo, findet mi statt") oder None (passt, oder nicht prüfbar)."""
    if not tage:
        return None
    genannt = im_titel(titel)
    falsch = genannt - set(tage)
    if not falsch:
        return None
    return f"nennt {kuerzel(falsch)}, findet {kuerzel(tage)} statt"
