# core/werkzeug_fragen.py
#
# Die Ja/Nein-Fragen, die Sasha vor einem bestätigungspflichtigen Werkzeug
# sieht, und die Regeln, wann gefragt wird, die von den Argumenten abhängen.
#
# 2026-10-08 aus core/werkzeug_register.py hierher gezogen: das Register
# stand an der Riesen-Grenze (1.500 Zeilen, memory/system/bauplan_kern.md),
# und die Fragen sind ein eigenes Thema — WAS Sasha liest, nicht WAS das
# Modell sieht. Wörtlich umgezogen; der Schnappschuss
# (tests/test_werkzeug_schnappschuss.py) hält die Texte fest.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import gedaechtnis
import kalender
import ki_kalender
import sandbox
import skills


# ── Erlaubnis: Regeln und Fragen ───────────────────────────────────────
#
# Was vor der Ausführung bestätigt werden muss: alles, was schreibt, löscht,
# ins Netz geht oder Geld kostet. Das Gate kommt automatisch, das Modell
# weiß davon nichts und muss nicht selbst nachfragen (ein 9b ruft sowas nicht
# zuverlässig von selbst). Lesen und Auskunft bleibt frei. Abgefangen wird in
# werkzeug_schleife.run_tool, gefragt über erlaubnis.frage.
#
# Die Frage zeigt Sasha im Dialog (und liest sie vor). Sie muss sagen, WAS
# passiert: Sasha drückt einen Knopf, ohne den Werkzeug-Aufruf zu sehen.
#
# Geltungsbereiche (Sasha 2026-10-07: „beides einstellbar machen"): ein Ja
# gilt „nur dieses Mal", „für dieses Gespräch" oder „immer" (core/
# erlaubnis.py). „Immer" gibt es NICHT (immer_erlaubbar=False) für
#   - die Kernakten (write_note auf Hausregeln/Steckbrief/Ziele): sie stehen
#     in jedem Zug ganz oben im Kopf; was dort landet, steuert die KI auf
#     Dauer — das soll Sasha jedes Mal sehen, nicht einmal abnicken.
#   - alles, was löscht oder überschreibt (Termin löschen, Routine ändern/
#     löschen, Dossier/Skill neu schreiben, fetch_document mit einem schon
#     benutzten Namen): ein falsches Ja ist dort nicht mit „nein" vom
#     nächsten Mal wieder gut. Ein Dauer-Ja hiesse, dass ein Missverständnis
#     der KI still Daten kostet.
#   - save_from_sandbox: Behalten nur auf Sashas Initiative (07.10.).
# „Für dieses Gespräch" bleibt überall: es endet von selbst.

def _label(args: dict) -> str:
    return (args.get("label") or "").strip() or "diesen Eintrag"


def _trifft_kernakte(args: dict) -> bool:
    """write_note ist im Normalfall frei (mitschreiben ohne Rückfrage — eine
    KI, die vor jeder Notiz fragt, ist kein Sekretär, sondern eine Zumutung),
    aber NICHT, wenn es eine Kernakte trifft: Hausregeln, Steckbrief, Ziele
    (Sasha, 2026-10-06; gedaechtnis.schreibt_kernakte)."""
    return gedaechtnis.schreibt_kernakte(args.get("name")) is not None


def _frage_notiz(args: dict) -> str:
    akte = gedaechtnis.schreibt_kernakte(args.get("name")) or "die Notiz"
    herkunft = " ".join(str(args.get("herkunft") or "").split())
    if herkunft:
        # Import (2026-10-08): Zeilen bleiben als Zeilen lesbar, und Sasha
        # sieht, woher sie kommen.
        zeilen = [" ".join(z.split()) for z in str(args.get("text") or "").splitlines()
                  if z.strip()]
        text = " / ".join(zeilen)
        if len(text) > 300:
            text = text[:299] + "…"
        return (f'Soll ich aus dem Import von {herkunft} {len(zeilen)} '
                f'Zeile(n) in {akte} ergänzen: "{text}"?')
    text = " ".join(str(args.get("text") or "").split())
    if len(text) > 200:
        text = text[:199] + "…"
    return f'Soll ich in {akte} schreiben: "{text}"?'


def _frage_dokument(args: dict) -> str:
    return (f'Soll ich {args.get("url", "das")} holen und als '
            f'"{args.get("name", "Dokument")}" ablegen?')


def _frage_messkurve(args: dict) -> str:
    return f'Soll ich eine neue Messkurve "{args.get("name", "?")}" anlegen?'


def _frage_dossier_neu(args: dict) -> str:
    wie = (args.get("name") or "das Dossier").strip()
    return (f'Soll ich das Dossier "{wie}" komplett neu schreiben? '
            f'(Die bisherige Fassung bleibt als .bak liegen.)')


def _frage_termin(args: dict) -> str:
    label = _label(args)
    wann = " ".join(p for p in (
        (args.get("day") or "").strip(),
        (args.get("time") or "").strip(),
    ) if p)
    wann_txt = f' am {wann}' if wann else ''
    frage = f'Soll ich "{label}"{wann_txt}{_ende_ort(args)} eintragen?'
    # Vorab-Konflikt-Check am GEPLANTEN (noch nicht geschriebenen) Termin:
    # fällt er in eine Reise oder kollidiert er mit einem bestehenden Termin,
    # ziehen wir die fertige ⚠-Zeile schon JETZT in die JA/NEIN-Frage - so
    # entscheidet Sasha informiert, statt erst nach dem Eintragen gewarnt zu
    # werden. Python rechnet (conflicts_for_proposed), das Modell ist außen
    # vor: die Zeile wird dem Menschen direkt im Dialog gezeigt. Mit Ende
    # (gross, 2026-10-08) prüft es auch Überschneidungen.
    ende = (args.get("ende") or "").strip()
    warns = kalender.conflicts_for_proposed(
        args.get("layer", "termine"),
        args.get("day", ""),
        label,
        args.get("time"),
        **({"ende": ende} if ende else {}),
    )
    if warns:
        frage += " " + " ".join(warns)
    return frage


def _ende_ort(args: dict) -> str:
    """' bis 19:00 @ Geigenschule' — nur, wenn die gross-Schiene es mitgibt
    (2026-10-08). Ohne beides bleibt die Frage wie vorher."""
    ende = (args.get("ende") or "").strip()
    ort = (args.get("ort") or "").strip()
    return (f" bis {ende}" if ende else "") + (f" @ {ort}" if ort else "")


def _ziel(args: dict, art: str) -> str:
    """Was eine Kennung meint, für die Frage: Sasha sieht den Termin, nicht
    '#r3f9c'. Ohne Kennung: der Titel wie bisher."""
    kennung = (args.get("kennung") or "").strip()
    if not kennung:
        return f'"{_label(args)}"'
    s, fehler = ki_kalender.finden(kennung)
    if fehler:
        return f"#{kennung.lstrip('#')} (gibt es so nicht — dann passiert nichts)"
    if s.art != art:
        return f'"{s.label}" (passt nicht — dann passiert nichts)'
    if art == "routine":
        return (f'"{s.label}" ({ki_kalender.regel_text(s.rrule)} '
                f'{ki_kalender.zeit(s.time, s.ende)})')
    return f'"{s.label}" am {ki_kalender.datum(s.day)} {ki_kalender.zeit(s.time, s.ende)}'


def _frage_routine(args: dict) -> str:
    rrule = (args.get("rrule") or "").strip()
    rrule_txt = f' ({rrule})' if rrule else ''
    zeit = (args.get("time") or "").strip()
    # Seit 2026-10-08 mit Uhrzeit, Ende und Ort: Sasha sieht den Aufruf
    # nicht, und „Routine Geigenstunde eintragen?" sagt nicht, WANN.
    um = f" um {zeit}" if zeit else ""
    return f'Soll ich die Routine "{_label(args)}"{rrule_txt}{um}{_ende_ort(args)} eintragen?'


def _frage_pause(args: dict) -> str:
    von = (args.get("von") or "").strip()
    bis = (args.get("bis") or "").strip()
    spanne = (f' von {von} bis {bis}' if von and bis
              else f' am {von} (Ende noch offen)' if von else '')
    return f'Soll ich {_ziel(args, "routine")}{spanne} pausieren?'


def _frage_routine_aendern(args: dict) -> str:
    wer = _ziel(args, "routine")
    nur_am = (args.get("nur_am") or "").strip()
    am = f" nur am {nur_am}" if nur_am else ""
    if (args.get("aktion") or "").strip() == "loeschen":
        if nur_am:
            return f'Soll ich die Routine {wer} nur am {nur_am} absagen?'
        return f'Soll ich die Routine {wer} wirklich dauerhaft löschen?'
    # Die Frage nennt, WAS sich aendert. "Soll ich die Routine aendern?"
    # waere nicht zustimmungsfaehig.
    return f'Soll ich die Routine {wer}{am} ändern auf {_was_neu(args)}?'


_FELDER_ROUTINE = (("time", "Beginn"), ("ende", "Ende"), ("ort", "Ort"),
                   ("rrule", "Wiederholung"), ("neuer_titel", "Titel"))
_FELDER_TERMIN = (("neuer_tag", "Tag"), ("time", "Beginn"), ("ende", "Ende"),
                  ("ort", "Ort"), ("neuer_titel", "Titel"), ("bis", "letzter Tag"))


def _was_neu(args: dict, felder=_FELDER_ROUTINE) -> str:
    teile = []
    for feld, wort in felder:
        wert = (args.get(feld) or "").strip()
        if wert:
            teile.append(f"{wort} {wert}")
    return ", ".join(teile) if teile else "etwas"


def _frage_termin_loeschen(args: dict) -> str:
    if (args.get("kennung") or "").strip():
        return f'Soll ich {_ziel(args, "termin")} wirklich löschen?'
    day = (args.get("day") or "").strip()
    wann_txt = f' am {day}' if day else ''
    return f'Soll ich "{_label(args)}"{wann_txt} wirklich löschen?'


def _frage_termin_aendern(args: dict) -> str:
    if (args.get("kennung") or "").strip():
        wer = _ziel(args, "termin")
    else:
        day = (args.get("day") or "").strip()
        wer = f'"{_label(args)}"' + (f" am {day}" if day else "")
    return f"Soll ich den Termin {wer} ändern auf {_was_neu(args, _FELDER_TERMIN)}?"


def _frage_suche(args: dict) -> str:
    q = (args.get("query") or "").strip()
    return f'Soll ich im Internet nach "{q}" suchen?' if q else "Soll ich im Internet suchen?"


def _frage_seite(args: dict) -> str:
    u = (args.get("url") or "").strip()
    return f'Soll ich die Seite {u} aus dem Internet laden?' if u else "Soll ich eine Webseite laden?"


def _code_zeit(args: dict) -> int:
    """Das verlangte Zeitlimit von run_code in Sekunden (Standard 30)."""
    try:
        return int(args.get("zeitlimit") or sandbox.ZEITLIMIT_STANDARD_S)
    except (TypeError, ValueError):
        return sandbox.ZEITLIMIT_STANDARD_S


def _code_lang(args: dict) -> bool:
    """run_code über 2 Minuten: eigene Frage, nur „einmal" (2026-10-07).
    Ein „immer" für Programme soll nicht heimlich halbstündige Läufe decken."""
    return _code_zeit(args) > sandbox.ZEITLIMIT_OHNE_FRAGE_S


def _dauer_text(sekunden: int) -> str:
    sekunden = min(sekunden, sandbox.ZEITLIMIT_MAX_S)
    if sekunden % 60 == 0:
        m = sekunden // 60
        return "1 Minute" if m == 1 else f"{m} Minuten"
    return f"{sekunden} Sekunden"


def _frage_code(args: dict) -> str:
    """Sasha sieht die Sprache und den Anfang des Programms. Die TUI zeigt
    die Frage einzeilig, deshalb stehen die Zeilen mit ⏎ hintereinander."""
    sprache = "Shell" if args.get("sprache") == "shell" else "Python"
    zeilen = [z.rstrip() for z in str(args.get("code") or "").splitlines()
              if z.strip()]
    anfang = " ⏎ ".join(z.strip()[:80] for z in zeilen[:4])
    if len(anfang) > 300:
        anfang = anfang[:299] + "…"
    mehr = f" (+{len(zeilen) - 4} Zeilen)" if len(zeilen) > 4 else ""
    lang = (f" und darf bis zu {_dauer_text(_code_zeit(args))} laufen"
            if _code_lang(args) else "")
    skill = gedaechtnis.slug(args.get("skill"))
    mit = (f" — dazu sieht es den Skill „{skill}“ (nur lesen)" if skill else "")
    return (f"Soll ich dieses {sprache}-Programm abgeschottet ausführen "
            f"(ohne Internet, ohne Zugriff auf deine Dateien){mit}{lang}? "
            f"„{anfang}“{mehr}")


def _frage_sandbox_ablage(args: dict) -> str:
    datei = str(args.get("datei") or "").strip() or "die Datei"
    titel = str(args.get("titel") or "").strip()
    als = f' als „{titel[:80]}“' if titel else ""
    return f"Soll ich {datei[:120]} aus dem Programm-Lauf{als} in deine Ablage legen?"


def _frage_skill_neu(args: dict) -> str:
    """Sasha sieht Name, wofür der Skill ist und den Anfang der Anleitung —
    er soll entscheiden können, ohne den Werkzeug-Aufruf zu lesen."""
    name = gedaechtnis.slug(args.get("name")) or "?"
    wofuer = " ".join(str(args.get("beschreibung") or "").split())[:240]
    return (f'Soll ich mir die Anleitung „{name}“ merken? Wofür: {wofuer or "-"}. '
            f'„{skills.anfang(args.get("inhalt"))}“')


def _frage_skill_aendern(args: dict) -> str:
    name = gedaechtnis.slug(args.get("name")) or "?"
    return (f'Soll ich die Anleitung „{name}“ neu schreiben? (Die bisherige '
            f'Fassung bleibt als .bak liegen.) „{skills.anfang(args.get("inhalt"))}“')
