# tui/ansichten/text.py
#
# Text für schmale Kästen: wortweise umbrechen und das bisschen Markdown, das
# die KI wirklich schreibt. Reine Funktionen, ohne curses — Chat, Tutor und
# Post teilen sie. Lag bis 06.10.2026 in tui/zentrale_tui.py (Markdown auf
# Modulebene, _wrap als Closure in run_ui), siehe memory/system/tui_bauplan.md.

import re


# ── Markdown, so viel wie die KI wirklich benutzt ──────────────────────
#
# Ihre Antworten sind Markdown — der Prompt erlaubt ihr Listen ausdruecklich,
# und Ueberschriften benutzt sie von selbst. Gezeichnet wurde bisher der
# ROHTEXT: Sasha sah "**fett**" und "## Titel" als Zeichen.
#
# WAS HIER NICHT PASSIERT: Auszeichnung INNERHALB einer Zeile. Dafuer
# muesste eine Zeile in Segmente mit eigenen Attributen zerfallen, und das
# ginge quer durch addclip und jeden Aufrufer. Die Marker werden deshalb
# entfernt und der Text bleibt — das loest den sichtbaren Aerger, ohne den
# Zeichen-Pfad umzubauen. Blockweise (Ueberschrift, Code, Liste) gibt es
# sehr wohl eigene Stile, denn die haengen an der ganzen Zeile.
#
# DIE HARTE REGEL: es geht nie Inhalt verloren. Entfernt werden nur die
# Marker selbst, und nur wenn sie sauber gepaart sind. Ein Renderer, der
# bei kaputtem Markdown Text verschluckt, ist schlimmer als gar keiner —
# man merkt es nicht.

_MD_FETT    = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_MD_KURSIV  = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_MD_UNTER   = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_MD_CODE    = re.compile(r"`([^`\n]+)`")
_MD_LINK    = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_MD_LISTE   = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
_MD_KOPF    = re.compile(r"^(#{1,6})\s+(.*)$")


def md_inline(text):
    """Inline-Marker entfernen, Inhalt behalten.

    Links werden zu "Text (URL)" — die Adresse wegzuwerfen waere genau das
    Verschlucken, das hier nicht passieren darf.
    """
    if not isinstance(text, str):
        text = str(text)
    text = _MD_LINK.sub(lambda m: "%s (%s)" % (m.group(1), m.group(2)), text)
    text = _MD_FETT.sub(r"\1", text)
    text = _MD_KURSIV.sub(r"\1", text)
    text = _MD_UNTER.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    return text


def md_zeilen(text, breite):
    """Markdown -> [(zeile, stil)] mit stil aus {"", "kopf", "code", "liste"}.

    `stil` ist ABSICHTLICH ein Wort und keine curses-Konstante: so bleibt
    die Funktion rein, ist ohne Terminal testbar, und der Zeichner
    entscheidet allein ueber Farben.

    Umgebrochen wird wortweise; Listen ruecken in der Folgezeile unter den
    Text ein statt unter das Bullet. Code-Zaeune werden NICHT umgebrochen
    (ein umgebrochener Befehl ist ein falscher Befehl) sondern hart
    abgeschnitten — der Zeichner kuerzt ohnehin.
    """
    try:
        breite = int(breite)
    except (TypeError, ValueError):
        breite = 40
    if breite < 6:
        breite = 6
    if not isinstance(text, str):
        text = "" if text is None else str(text)

    aus = []
    im_code = False
    for roh in text.replace("\r", "").split("\n"):
        if roh.strip().startswith("```"):
            im_code = not im_code
            continue                      # der Zaun selbst ist kein Inhalt
        if im_code:
            aus.append((roh[:breite], "code"))
            continue

        kopf = _MD_KOPF.match(roh)
        if kopf:
            for z in _md_umbruch(md_inline(kopf.group(2)), breite, ""):
                aus.append((z, "kopf"))
            continue

        liste = _MD_LISTE.match(roh)
        if liste:
            tiefe = min(len(liste.group(1)) // 2, 4)
            kopfzeichen = " " * (2 * tiefe) + "• "
            einzug = " " * len(kopfzeichen)
            zeilen = _md_umbruch(md_inline(liste.group(3)),
                                 breite - len(kopfzeichen), einzug)
            if not zeilen:
                zeilen = [""]
            aus.append((kopfzeichen + zeilen[0], "liste"))
            for z in zeilen[1:]:
                aus.append((z, "liste"))
            continue

        if not roh.strip():
            aus.append(("", ""))
            continue
        for z in _md_umbruch(md_inline(roh), breite, ""):
            aus.append((z, ""))
    return aus


def _md_umbruch(text, breite, einzug):
    """Wortweise umbrechen, Folgezeilen mit `einzug`. Ueberlange Woerter
    hart trennen — sonst waechst eine URL ueber den Kasten hinaus."""
    if breite < 4:
        breite = 4
    aus, cur, erste = [], "", True
    for wort in (text or "").split():
        platz = breite if erste else breite - len(einzug)
        if platz < 2:
            platz = 2
        while len(wort) > platz:
            if cur:
                aus.append((cur if erste else einzug + cur))
                erste, cur = False, ""
                platz = max(2, breite - len(einzug))
            aus.append((wort[:platz] if erste else einzug + wort[:platz]))
            erste = False
            wort = wort[platz:]
            platz = max(2, breite - len(einzug))
        kand = (cur + " " + wort) if cur else wort
        if len(kand) > platz:
            aus.append(cur if erste else einzug + cur)
            erste, cur = False, wort
        else:
            cur = kand
    if cur:
        aus.append(cur if erste else einzug + cur)
    return aus


def _wrap(text, width):
    """Text auf `width` umbrechen (wortweise), Zeilenumbrüche erhalten."""
    out = []
    for para in (text or "").replace("\r", "").split("\n"):
        if not para:
            out.append("")
            continue
        while len(para) > width:
            cut = para.rfind(" ", 0, width)
            if cut <= 0:
                cut = width
            out.append(para[:cut])
            para = para[cut:].lstrip()
        out.append(para)
    return out
