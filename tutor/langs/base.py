# tutor/langs/base.py
#
# Gemeinsames Handwerkszeug für die Sprach-Pakete + das Profil-Schema.
#
# Ein Sprach-Paket (tutor/langs/<code>/) beschreibt EINE Sprache vollständig:
# wer die Persona ist, wie sie redet (Prompt in der ZIELSPRACHE), wie ihre Tools
# beschriftet sind, welche Lesehilfe die Vokabeln tragen und welche Themen sie
# beiläufig aufbringt. Eine Sprache dazubauen = einen Ordner anlegen; hier drin
# und in tools.py muss dafür NICHTS angefasst werden.
#
# ── Warum Pakete statt einer PROFILES-Tabelle ───────────────────────────
# Bis 2026-07-16 lag alles in EINER langs.py: der chinesische Prompt, der
# Vokabel-Hinweis und die Register-Leiter als eingebettete Python-Konstanten.
# Bei fünf hand-getunten Sprachen wäre das eine Monsterdatei aus fremdsprachigen
# String-Literalen. Und getunt MÜSSEN sie sein — siehe unten.
#
# ── Die wichtigste Regel (aus memory/tutor_persona_tuning.md) ───────────
# Der System-Prompt einer LIVE-Sprache ist in der ZIELSPRACHE verfasst. Das ist
# der Hebel, der das Modell zuverlässig in der Zielsprache hält; ein deutscher
# Prompt ließ qwen zu ~95% auf Deutsch antworten. Dasselbe gilt für die
# Tool-Beschreibungen und die Regie-Sätze der Tools. Die generische
# build_prompt() unten ist NUR der schlanke deutsche Fallback für Skizzen —
# beim Aktivieren einer Sprache: eigenen prompt.md in ihrer Sprache hand-tunen.

import os
import io
import json


# ── Loader: Textbausteine liegen als Datei NEBEN dem Paket ──────────────
# (Prompts sind lange Prosa — die gehören nicht als String-Literal in .py.)

def load_text(pkg_file: str, name: str, default: str = "") -> str:
    """Text-Datei aus dem Sprach-Paket lesen. pkg_file = __file__ des Pakets."""
    path = os.path.join(os.path.dirname(os.path.abspath(pkg_file)), name)
    try:
        return io.open(path, encoding="utf-8").read()
    except Exception:
        return default


def load_json(pkg_file: str, name: str, default=None):
    """JSON aus dem Sprach-Paket (Seeds, Register-Leiter)."""
    path = os.path.join(os.path.dirname(os.path.abspath(pkg_file)), name)
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return default if default is not None else []


# ── Register-Leiter als DATEN ───────────────────────────────────────────
# Die Sprechweise skaliert mit dem Wortschatz: fast nichts → Einzelwörter +
# Gestik; mehr Wörter → vollere Sätze. So redet ein Mensch mit einem Fast-
# Anfänger. Jede Sprache bringt ihre eigene Leiter in IHRER Sprache mit
# (expect.json: [[grenze, text], …], aufsteigend; über der letzten Grenze
# keine Bremse mehr). War vorher eine zh-feste if-Kaskade in langs.py.

def expect_from_ladder(ladder, n: int) -> str:
    """n (bekannte + lernende Wörter/Strukturen) → Erwartungs-Bremse oder ''."""
    for limit, text in (ladder or []):
        if n <= limit:
            return text
    return ""


# ── Generischer Fallback-Prompt (deutsch, NUR für Skizzen) ──────────────

def build_prompt(persona_name: str, language: str, country: str,
                 flavor: str = "") -> str:
    """
    Schlanker GENERISCHER Fallback-Prompt (deutsch) für noch nicht hand-getunte
    Sprachen. Live-Sprachen bekommen einen eigenen prompt.md in der Zielsprache
    (siehe Kopf). Bewusst KURZ — wenige, treffende Regeln statt einer Litanei.
    """
    return (
        f"Du bist {persona_name}, Sashas Mitbewohner:in. Sasha ist {language}-"
        "Anfängerin; ihr quatscht einfach so. Kein Lehrer, kein Kurs, keine Prüfung.\n\n"
        "So redest du:\n"
        f"- Antworte NUR auf {language} (in der Schrift der Sprache). Kurz, wie unter "
        "Mitbewohnern: 1–2 Sätze, einfachste Wörter.\n"
        f"- Lesehilfe nur bei wirklich neuen, schwierigen Wörtern. {flavor}\n"
        "- Kein Lob ('super!', 'richtig gesagt!'), kein Korrigieren, kein Benoten — "
        "red einfach normal weiter.\n"
        f"- {country} (Essen, Wetter, Alltag) kennst du gut; höchstens beiläufig mal "
        "EIN Satz dazu — nie lang, kein Geschichts-/Politik-Vortrag, kein Reiseführer. "
        "Nicht am selben Thema kleben.\n"
        "- Eine Sache einmal sagen, nicht dreifach erklären.\n\n"
        "Nur wenn Sasha ausdrücklich fragt, was ein Wort heißt: EIN kurzer deutscher "
        f"Halbsatz, dann sofort zurück auf {language}.\n\n"
        f"Du bist eine KI, ein Programm, kein Mensch — hast in {country} nie gelebt. "
        "Fragt sie, sag ehrlich, du bist eine KI (spiel keine Nationalität), erfinde "
        "keine Vergangenheit.\n\n"
        "Du bist in einem Zimmer und kannst dich bewegen — herumgehen, auf und ab, "
        "hinsetzen, winken, sie ansehen: nutz dafür das express-Tool (schreib die "
        "Bewegung NICHT als Text). Ist Sasha eine Weile still, kannst du sie ansehen, "
        "winken oder leise fragen, ob sie noch da ist."
    )


# ── Profil-Defaults ─────────────────────────────────────────────────────
# Ein Sprach-Paket überschreibt nur, was es braucht. So bleibt ein neuer
# Ordner klein und ein neues Feld hier bricht keine bestehende Sprache.

DEFAULTS = {
    "enabled":     False,      # SKIZZE, bis jemand den Prompt hand-tunt
    "reading":     "none",     # Lesehilfe im Vokabel-Datensatz: pinyin | stress
                               # | translit | none. Der Wert ist die Bedeutung
                               # des 'reading'-Feldes in data/<lang>/vocab.json.
    "reading_label": "",       # wie die Lesehilfe im Tool-Schema heißt (Zielsprache)
    "script":      "ltr",      # ar = rtl
    "stt_lang":    None,       # default: der Sprach-Code selbst
    "tts_lang":    None,
    "provider":    "qwen",
    "model":       None,       # None → default_model des Providers
    "vocab_hint":  "",         # {words}-Template, in session gefüllt
    "vocab_labels": {},        # Beschriftung des Vokabel-Blocks (solid/learn/
                               # structs/plain + join/sep), Zielsprache
    "expect_ladder": [],       # [[grenze, text], …] — leer = keine Bremse
    "tool_texts":  {},         # Tool-Beschriftung in der Zielsprache (tools.py)
    "phrases":     {},         # Rückgaben/Regie-Sätze der Tools, Zielsprache
    "seeds":       {},         # news/tv-Inhalte der Sprache
}


def profile(code: str, **fields) -> dict:
    """Baut ein vollständiges Profil aus DEFAULTS + den Angaben des Pakets."""
    p = dict(DEFAULTS)
    p.update(fields)
    p["code"] = code
    p.setdefault("name", code)
    p.setdefault("persona_name", code)
    p.setdefault("country", "")
    if not p.get("stt_lang"):
        p["stt_lang"] = code
    if not p.get("tts_lang"):
        p["tts_lang"] = code
    return p
