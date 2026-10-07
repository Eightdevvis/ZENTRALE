# core/skill_format.py
#
# Das Datei-Format eines Skills — dasselbe wie bei Claude (Anthropic):
#
#   <name>/
#   ├── SKILL.md        YAML-Kopf (name, description; optional license,
#   │                   compatibility, allowed-tools, metadata …) + Anleitung
#   ├── scripts/        Programme (laufen bei uns NUR in der Sandbox)
#   ├── references/     Nachlesestoff, holt die KI bei Bedarf
#   ├── assets/         Vorlagen, Schriften, Bilder für Ausgaben
#   └── _zentrale.json  NUR ZENTRALE: status, herkunft, erstellt, braucht …
#
# 2026-10-07, Sasha: Claudes Skill-Format übernehmen, damit echte Claude-
# Skills sich ohne Umbau hineinkopieren lassen. Deshalb steht alles, was nur
# ZENTRALE braucht (an/aus, von wem), NICHT in der SKILL.md, sondern daneben
# in _zentrale.json — die SKILL.md bleibt Wort für Wort Claude-tauglich.
#
# Hier nur das Lesen und Schreiben des Formats, kein Ordner, keine Regeln,
# wann ein Skill gilt (das macht core/skills.py).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import re
import textwrap

SKILL_MD = "SKILL.md"
ZENTRALE_JSON = "_zentrale.json"

# Claudes Regeln (agentskills-Spezifikation, quick_validate.py im
# skill-creator): Name in Kleinbuchstaben/Ziffern/Bindestrich, ≤ 64 Zeichen,
# kein Bindestrich am Rand oder doppelt; Beschreibung ≤ 1024 Zeichen.
NAME_MAX = 64
BESCHREIBUNG_MAX = 1024
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def gueltiger_name(name) -> bool:
    return (isinstance(name, str) and len(name) <= NAME_MAX
            and bool(_NAME.match(name)))


# ── Lesen ─────────────────────────────────────────────────────────────

def zerlegen(text: str) -> tuple:
    """SKILL.md-Text → (kopf_roh, felder, anleitung).

    kopf_roh: der YAML-Text zwischen den beiden `---` (None ohne Kopf),
    felder: dict der Kopf-Felder (fremde bleiben drin), anleitung: der Rest.
    Wirft nie — ein kaputter Kopf ergibt so viele Felder, wie lesbar sind."""
    text = (text or "").replace("\r\n", "\n").lstrip("﻿")
    zeilen = text.split("\n")
    if not zeilen or zeilen[0].rstrip() != "---":
        return None, {}, text.strip()
    for i in range(1, len(zeilen)):
        if zeilen[i].rstrip() in ("---", "..."):
            roh = "\n".join(zeilen[1:i])
            rest = "\n".join(zeilen[i + 1:]).strip()
            return roh, kopf_lesen(roh), rest
    return None, {}, text.strip()


def kopf_lesen(roh: str) -> dict:
    """YAML-Kopf → dict. Mit PyYAML, wenn da (genau wie Claude); sonst und
    bei kaputtem YAML ein kleiner eigener Leser für die flachen Felder.
    Warum zwei Wege (2026-10-07): PyYAML steht nicht in requirements.txt —
    ein Rechner ohne darf trotzdem name und description lesen."""
    try:
        import yaml
        daten = yaml.safe_load(roh or "")
        if isinstance(daten, dict):
            return {str(k): v for k, v in daten.items()}
    except Exception:
        pass
    return _kopf_einfach(roh or "")


def _skalar(wert: str) -> str:
    wert = wert.strip()
    if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
        innen = wert[1:-1]
        if wert[0] == '"':
            try:
                return json.loads(wert)
            except ValueError:
                return innen
        return innen.replace("''", "'")
    return wert


def _kopf_einfach(roh: str) -> dict:
    """Flache `schluessel: wert`-Zeilen, Block-Texte (`>`, `|`, mit `-`/`+`)
    und eingerückte Fortsetzungszeilen. Verschachteltes (metadata: …) kommt
    als roher Text zurück — gebraucht werden nur die flachen Felder."""
    felder, schluessel, art, teile = {}, None, None, []

    def abschliessen():
        if schluessel is None:
            return
        block = textwrap.dedent("\n".join(teile)).strip("\n")
        if art and art.startswith("|"):
            wert = block
        elif art and art.startswith(">"):
            wert = "\n".join(" ".join(a.split()) for a in block.split("\n\n"))
        elif len(teile) == 1:
            wert = _skalar(teile[0])
        else:
            wert = " ".join(block.split())
        felder[schluessel] = wert.strip()

    for zeile in roh.split("\n"):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$", zeile)
        if m and not zeile[:1].isspace():
            abschliessen()
            schluessel, wert = m.group(1), (m.group(2) or "").strip()
            if wert[:1] in ("|", ">") and re.fullmatch(r"[|>][+-]?\d?", wert):
                art, teile = wert, []
            else:
                art, teile = None, ([wert] if wert else [])
        elif schluessel is not None:
            teile.append(zeile)
    abschliessen()
    return felder


def text_feld(felder: dict, name: str) -> str:
    """Ein Kopf-Feld als einzeiliger Text ('' wenn fehlt oder kein Text)."""
    wert = felder.get(name)
    if not isinstance(wert, str):
        return ""
    return " ".join(wert.split())


# ── Schreiben ─────────────────────────────────────────────────────────

def rendern(name: str, beschreibung: str, anleitung: str) -> str:
    """Eine neue SKILL.md, so wie Claude sie erwartet. Die Beschreibung als
    YAML-Text in Anführungszeichen (JSON-Schreibweise ist gültiges YAML) —
    so bricht kein Doppelpunkt oder `#` darin den Kopf."""
    return ("---\n"
            f"name: {name}\n"
            f"description: {json.dumps(beschreibung, ensure_ascii=False)}\n"
            "---\n\n" + (anleitung or "").strip() + "\n")


def mit_neuer_anleitung(alt: str, anleitung: str) -> str:
    """Die Anleitung ersetzen, den Kopf Zeichen für Zeichen behalten —
    fremde Felder eines Claude-Skills gehen so nie verloren."""
    roh, _, _ = zerlegen(alt)
    kopf = f"---\n{roh}\n---\n\n" if roh is not None else ""
    return kopf + (anleitung or "").strip() + "\n"
