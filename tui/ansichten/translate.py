# tui/ansichten/translate.py
#
# Human-facing TUI text through gettext (CLAUDE.md "Language", one table per
# front): msgids are English, German is the first UI language. The table is
# tui/ansichten/locale/<lang>/LC_MESSAGES/zentrale_tui.po, compiled to .mo
# next to it (msgfmt; tests/test_cloud_folder.py checks both match). Lives
# inside tui/ansichten/ so every node that gets the TUI gets the table too
# (deploy/aussenposten.txt). Same language switch as the core (env
# ZENTRALE_LANG, default German) — but no import from core: the TUI door
# does not grow (memory/system/bauplan_kern.md "Türen").
#
# Old German TUI text stays until the renaming wave; new text goes here.

import gettext
import os

from .basis import PROJEKT

DOMAIN = "zentrale_tui"
LOCALE_DIR = os.path.join(PROJEKT, "tui", "ansichten", "locale")
DEFAULT_LANGUAGE = "de"

_tables = {}


def language() -> str:
    return (os.environ.get("ZENTRALE_LANG") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def _(msgid: str) -> str:
    lang = language()
    if lang not in _tables:
        _tables[lang] = gettext.translation(DOMAIN, LOCALE_DIR, languages=[lang], fallback=True)
    return _tables[lang].gettext(msgid)
