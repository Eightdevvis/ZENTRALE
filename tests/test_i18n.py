"""UI text through gettext (core/i18n.py, CLAUDE.md "Language"): the compiled
table matches the .po, every reason code has a German text, placeholders
survive translation, an unknown language falls back to English."""
import gettext
import os
import re

import abgleich_vorschlaege as vs
import i18n

PO = os.path.join(i18n.LOCALE_DIR, "de", "LC_MESSAGES", "zentrale.po")
MO = os.path.join(i18n.LOCALE_DIR, "de", "LC_MESSAGES", "zentrale.mo")


def _po_entries():
    """msgid → msgstr from the .po (also multi-line entries and \\n escapes)."""
    import ast
    out, key, cur, field = {}, None, None, None
    for line in open(PO, encoding="utf-8").read().splitlines() + [""]:
        line = line.strip()
        if line.startswith("msgid "):
            if key:
                out[key] = cur
            key, cur, field = ast.literal_eval(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            cur, field = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"'):
            if field == "id":
                key += ast.literal_eval(line)
            else:
                cur += ast.literal_eval(line)
    if key:
        out[key] = cur
    return out


def test_compiled_table_matches_po():
    with open(MO, "rb") as f:
        mo = gettext.GNUTranslations(f)
    po = _po_entries()
    assert po
    for msgid, msgstr in po.items():
        assert mo.gettext(msgid) == msgstr, f"zentrale.mo is stale — run msgfmt ({msgid!r})"


def test_every_reason_has_german_text_with_same_placeholders():
    po = _po_entries()
    for code, msgid in vs.REASONS.items():
        assert msgid in po, f"no German text for reason {code}"
        assert set(re.findall(r"\{(\w+)\}", msgid)) == set(re.findall(r"\{(\w+)\}", po[msgid]))


def test_german_is_default_and_unknown_language_falls_back(monkeypatch):
    monkeypatch.delenv("ZENTRALE_LANG", raising=False)
    assert i18n._(vs.REASONS["not_found"]) == "den Termin gibt es nicht"
    monkeypatch.setenv("ZENTRALE_LANG", "xx")
    assert i18n._(vs.REASONS["not_found"]) == "the event does not exist"
