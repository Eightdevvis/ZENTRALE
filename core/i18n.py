# core/i18n.py
#
# Human-facing text for core/TUI/CLI goes through gettext (CLAUDE.md
# "Language", Sasha 2026-10-29): msgids are English, German is the first UI
# language. One table for the core: core/locale/<lang>/LC_MESSAGES/zentrale.po,
# compiled to zentrale.mo next to it (msgfmt; tests/test_i18n.py checks both
# match). A missing table or message falls back to the English msgid — never
# an error.
#
# Usage:  from i18n import _      _("the event does not exist")
#         _("the layer “{layer}” does not exist").format(layer=x)
# Placeholders are always named ({name}), so translations may reorder them.

import gettext
import os

DOMAIN = "zentrale"
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
DEFAULT_LANGUAGE = "de"

_tables = {}


def language() -> str:
    """The UI language: env ZENTRALE_LANG, else German."""
    return (os.environ.get("ZENTRALE_LANG") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def _table(lang):
    if lang not in _tables:
        _tables[lang] = gettext.translation(DOMAIN, LOCALE_DIR, languages=[lang], fallback=True)
    return _tables[lang]


def _(msgid: str) -> str:
    """Translate `msgid` into the current UI language."""
    return _table(language()).gettext(msgid)


def pgettext(context: str, msgid: str) -> str:
    """Translate `msgid` within `context` (gettext `msgctxt`): for short words
    that mean different things in different places — "off" as a wire state
    is not "off" as a setting (zentrale_cli: "Auto-update off")."""
    return _table(language()).pgettext(context, msgid)
