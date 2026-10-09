# core/profil/modelle/__init__.py
#
# Modell-Profile: eine eigene Umgebung je MODELL, über der Schiene.
#
# ── Warum (2026-10-09) ──────────────────────────────────────────────────
# Beim Budget-Rückfall fuhr qwen-plus auf der gross-Schiene, die für Claude
# gebaut und gemessen ist: es rief kein Werkzeug, schrieb „Alles korrigiert"
# und erfand Kennungen. Sasha: schwache Modelle brauchen manchmal Strategien,
# die starke stören — also nicht nur das Modell tauschen, sondern Umgebung
# und Einstellungen mit.
#
# Die Schiene (klein/gross) bleibt, was die Ausführer wissen müssen (Kennungen,
# Prüfer, Umschlag). Ein Profil legt sich DARÜBER und darf überschreiben:
# System-Text, Werkzeug-Auswahl und -Beschreibungen, Temperatur, Ausgabe-
# Länge, wann ein Werkzeug Pflicht ist, und einen zusätzlichen Prüfer.
# Ohne Profil kommt die Schiene selbst zurück — dasselbe Objekt, byte-gleich
# (tests/test_modell_profile.py).
#
# Welches Modell welches Profil bekommt, sagt die Einstellung
# `modell_profile` (ai_config): {"qwen-plus": "qwen", "qwen-*": "qwen"}.
# Genauer Name vor Muster (fnmatch); {} schaltet alle ab. Ein Profil ist eine
# Datei hier daneben (qwen.py) — wer ein weiteres Modell zähmt, legt eine
# weitere an, statt an einem geteilten Prompt zu ziehen.
#
# Teil des Pakets profil (Schicht 3, memory/system/bauplan_kern.md).
# Doku: memory/ki/modell_profile.md.

import fnmatch
import json

from . import qwen

PROFILE = {
    "qwen": qwen,
}

# Ohne Einstellung: welches Modell welches Profil bekommt. Claude-Modelle
# stehen bewusst nicht drin.
STANDARD = {}


def zuordnung() -> dict:
    """Muster → Profilname, aus der Einstellung oder STANDARD."""
    try:
        import ai_config
        wert = ai_config.setting("modell_profile", None)
    except Exception:
        wert = None
    if isinstance(wert, str):
        try:
            wert = json.loads(wert)
        except ValueError:
            wert = None
    return wert if isinstance(wert, dict) else dict(STANDARD)


def name_fuer(modell: str | None) -> str | None:
    """Das Profil für ein Modell, oder None. Genauer Name gewinnt vor einem
    Muster; unter Mustern das erste in der Reihenfolge der Einstellung."""
    if not modell:
        return None
    z = zuordnung()
    name = z.get(modell)
    if name is None:
        name = next((p for muster, p in z.items()
                     if fnmatch.fnmatchcase(modell, muster)), None)
    return name if name in PROFILE else None


def fuer(modell: str | None, basis):
    """Die Schiene für dieses Modell: `basis` selbst ohne Profil, sonst eine
    ModellSchiene darüber."""
    name = name_fuer(modell)
    if name is None:
        return basis
    return ModellSchiene(basis, PROFILE[name])


class ModellSchiene:
    """Eine Schiene mit Profil darüber. Hat dieselbe Schnittstelle wie die
    Schienen-Module (NAME, TOOLS, system() …) — der Kern muss nicht wissen,
    ob ein Profil fährt. NAME bleibt der der Schiene: danach richten sich
    Ausführer und Prüfer, und die sollen für qwen genauso streng sein."""

    def __init__(self, basis, profil):
        self.basis = basis
        self.profil = profil
        self.NAME = basis.NAME
        self.PROFIL = profil.NAME
        anpassen = getattr(profil, "werkzeuge", None)
        self.TOOLS = anpassen(basis.TOOLS) if anpassen else basis.TOOLS

    def __getattr__(self, name):
        # Alles, was das Profil nicht ändert (MERKMALE, TERMINAL, MIC_HINT …),
        # kommt von der Schiene.
        return getattr(self.basis, name)

    def system(self, override=None, **kw) -> str:
        text = self.basis.system(override, **kw)
        anpassen = getattr(self.profil, "system", None)
        return anpassen(text) if anpassen else text

    def wert(self, name: str, standard=None):
        """Ein Schleifen-/Aufruf-Wert des Profils (TEMPERATUR, MAX_TOKENS …)."""
        return getattr(self.profil, name, standard)

    def tool_choice(self, **lage):
        """Muss diese Runde ein Werkzeug rufen? -> "required" | None."""
        f = getattr(self.profil, "tool_choice", None)
        return f(**lage) if f else None

    def pruefer(self, basis_pruefer, **lage):
        f = getattr(self.profil, "pruefer", None)
        return f(basis_pruefer, **lage) if f else basis_pruefer


def profil_von(schiene) -> str | None:
    """Name des Profils einer Schiene (für Log/Prüfstand), oder None."""
    return getattr(schiene, "PROFIL", None)
