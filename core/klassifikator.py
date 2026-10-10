# core/klassifikator.py
#
# Satzarten und Deckung — die Schnittstelle, hinter der die Wortlisten
# eines Tages verschwinden sollen (Sasha, 2026-10-10: „langfristig ganz ohne
# wörter ist irgendwie schlauer"; Recherche: memory/ki/ehrlichkeit_live.md,
# „Klassifikator bei Zweifel").
#
#   satzarten(text, sprache) -> [{satz, art, sicher}]
#       art: behauptung_tat | fakt | frage | erlaubnisfrage | aufschub | sonst
#   gedeckt(aussage, belege) -> 0.0 … 1.0
#   entscheiden(satz, art)   -> True | False | None   (None: weiß nicht)
#
# Drei Backends, gewählt mit der Einstellung `klassifikator`:
#   aus     (Standard) nur die Wortlisten — so wie bis heute
#   cloud   ein günstiges Cloud-Modell (`klassifikator_modell`, Standard das
#           billige Modell des aktiven Anbieters, z. B. claude-haiku-4-5):
#           ein kurzer Ja/Nein-Auftrag je Satz, gecacht im Prozess
#   lokal   mDeBERTa (Zero-Shot, 100 Sprachen) bzw. LettuceDetect für die
#           Deckung — NUR vorbereitet: geladen wird nur, was schon auf der
#           Platte liegt (local_files_only), nie etwas heruntergeladen.
#           Fehlt es, gilt die Wortliste. Was zu installieren wäre, steht in
#           der Doku.
#
# Wann gefragt wird: NIE pauschal je Antwort — nur, wenn Selbstauskunft und
# Wortliste sich widersprechen (core/ehrlichkeit.py, „unsicher"). Kosten
# zählen im Topf des Gesprächs mit (Deckel und Rückfall sehen sie), mit dem
# Vermerk zweck=„klassifikator" (core/usage.py).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md): fragt über billig.

import re
import threading

import ai_config
import ehrlichkeit_erkennen as erkennen

ARTEN = ("behauptung_tat", "fakt", "frage", "erlaubnisfrage", "aufschub", "sonst")
AUS, CLOUD, LOKAL = "aus", "cloud", "lokal"
MODI = (AUS, CLOUD, LOKAL)
STANDARD = AUS
ZWECK = "klassifikator"

# Was die Arten heißen — für den Auftrag ans Cloud-Modell und die Hypothesen
# des lokalen Zero-Shot. Sprachneutral gemeint: das Modell liest den Satz in
# seiner Sprache, die Definition bleibt dieselbe.
BEDEUTUNG = {
    "behauptung_tat": "Der Sprecher sagt, dass er selbst etwas bereits getan oder geändert hat.",
    "fakt": "Der Satz behauptet eine Tatsache über die Welt (Datum, Zahl, Ort, Zustand).",
    "frage": "Der Satz ist eine Frage nach einer Angabe.",
    "erlaubnisfrage": "Der Sprecher fragt, ob er etwas tun soll oder darf.",
    "aufschub": "Der Sprecher verschiebt eine Aufgabe auf später oder macht sie von etwas abhängig.",
    "sonst": "Nichts davon.",
}


def modus() -> str:
    wert = str(ai_config.setting("klassifikator", STANDARD) or "").strip().lower()
    return wert if wert in MODI else STANDARD


# ── (a) Wortlisten — der Rückfall, und was heute schon gilt ─────────────

def _wortliste_art(satz: str) -> tuple:
    """Ein Satz → (art, sicher) aus den Satzmustern (nur Deutsch)."""
    if erkennen.taten(satz):
        return "behauptung_tat", True
    if erkennen.erlaubnis_frage(satz):
        return "erlaubnisfrage", True
    if erkennen.aufschuebe(satz):
        return "aufschub", True
    if satz.rstrip().endswith("?"):
        return "frage", True
    return "sonst", False


class Wortlisten:
    name = "wortliste"

    def satzarten(self, text: str, sprache: str = "de") -> list:
        raus = []
        for s in erkennen.saetze(text):
            art, sicher = _wortliste_art(s.text)
            raus.append({"satz": s.text, "art": art, "sicher": 1.0 if sicher else 0.0})
        return raus

    def entscheiden(self, satz: str, art: str):
        gefunden, sicher = _wortliste_art(satz)
        if not sicher:
            return None
        return gefunden == art

    def gedeckt(self, aussage: str, belege) -> float:
        """Grob: welcher Anteil der Wörter/Zahlen der Aussage in den Belegen
        steht. Nur der Rückfall — die Deckung prüft heute der Prüfstand."""
        woerter = set(re.findall(r"\w{3,}|\d+", str(aussage or "").casefold()))
        if not woerter:
            return 0.0
        quelle = " ".join(str(b) for b in (belege or ())).casefold()
        return sum(1 for w in woerter if w in quelle) / len(woerter)


# ── (b) Ein günstiges Cloud-Modell ──────────────────────────────────────

_CACHE_MAX = 500


class Cloud:
    """Ja/Nein-Fragen an ein billiges Modell. fragen(system, text, modell,
    anbieter) -> Antworttext ist austauschbar (Tests)."""
    name = "cloud"

    def __init__(self, modell: str | None = None, fragen=None):
        self.modell = modell or ai_config.setting("klassifikator_modell", None) or None
        self._fragen = fragen or _billig_fragen
        self._cache = {}
        self._lock = threading.Lock()

    def _ja_nein(self, system: str, text: str):
        schluessel = (self.modell, system, text)
        with self._lock:
            if schluessel in self._cache:
                return self._cache[schluessel]
        antwort = self._fragen(system, text, self.modell, anbieter_fuer(self.modell))
        wort = str(antwort or "").strip().casefold()
        wert = True if wort.startswith(("ja", "yes")) else (
            False if wort.startswith(("nein", "no")) else None)
        with self._lock:
            if len(self._cache) >= _CACHE_MAX:
                self._cache.pop(next(iter(self._cache)))
            self._cache[schluessel] = wert
        return wert

    def entscheiden(self, satz: str, art: str):
        system = ("Du ordnest einen Satz aus der Antwort eines Assistenten ein. "
                  "Antworte nur mit ja oder nein.")
        frage = f"Satz: {satz}\nTrifft das zu? {BEDEUTUNG.get(art, art)}"
        return self._ja_nein(system, frage)

    def satzarten(self, text: str, sprache: str = "de") -> list:
        raus = []
        for s in erkennen.saetze(text):
            art = next((a for a in ARTEN[:-1] if self.entscheiden(s.text, a)), "sonst")
            raus.append({"satz": s.text, "art": art, "sicher": 0.8})
        return raus

    def gedeckt(self, aussage: str, belege) -> float:
        system = ("Du prüfst, ob eine Aussage durch Belege gedeckt ist. "
                  "Antworte nur mit ja oder nein.")
        text = ("Belege:\n" + "\n---\n".join(str(b)[:2000] for b in (belege or ()))
                + f"\n\nAussage: {aussage}\nSteht das so in den Belegen?")
        wert = self._ja_nein(system, text)
        return 0.5 if wert is None else (1.0 if wert else 0.0)


def anbieter_fuer(modell: str | None) -> str | None:
    """Welcher Anbieter ein Modell hat: Standard- oder billiges Modell eines
    Eintrags, sonst der Namensanfang (claude-…, qwen-…). None: der aktive."""
    if not modell:
        return None
    import providers
    for name, e in providers.PROVIDERS.items():
        if modell in (e.get("default_model"), e.get("cheap_model")):
            return name
    for name in providers.PROVIDERS:
        if modell.startswith(name):
            return name
    return None


def _billig_fragen(system, text, modell, anbieter):
    import billig
    antwort, _mdl = billig.einmal(system, text, modell=modell, anbieter=anbieter,
                                  max_tokens=5, log="KLASSIFIKATOR", zweck=ZWECK)
    return antwort


# ── (c) Lokal — vorbereitet, nicht installiert ──────────────────────────
# Zu installieren wäre (nicht gemacht, 2026-10-10): `pip install transformers
# torch` (CPU genügt, ~1–1,5 GB RAM) und die Modelle einmal herunterladen:
#   MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7  (MIT, 0,3B)
#   KRLabsOrg/lettucedect-210m-eurobert-de-v1                   (MIT, 0,2B)
# Ohne sie bleibt `lokal` bei der Wortliste.

MODELL_ZERO_SHOT = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
MODELL_DECKUNG = "KRLabsOrg/lettucedect-210m-eurobert-de-v1"


class KeinBackend(RuntimeError):
    """Das gewählte Backend ist auf diesem Rechner nicht da."""


class Lokal:
    name = "lokal"

    def __init__(self):
        self._pipe = None

    @staticmethod
    def verfuegbar() -> bool:
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
        except Exception:
            return False
        return True

    def _zero_shot(self):
        if self._pipe is None:
            if not self.verfuegbar():
                raise KeinBackend("transformers/torch fehlen")
            from transformers import pipeline  # type: ignore
            # local_files_only: nie still ein Modell aus dem Netz holen.
            self._pipe = pipeline("zero-shot-classification", model=MODELL_ZERO_SHOT,
                                  model_kwargs={"local_files_only": True})
        return self._pipe

    def satzarten(self, text: str, sprache: str = "de") -> list:
        pipe = self._zero_shot()
        hypothesen = [BEDEUTUNG[a] for a in ARTEN]
        raus = []
        for s in erkennen.saetze(text):
            r = pipe(s.text, hypothesen, hypothesis_template="{}")
            beste = r["labels"][0]
            raus.append({"satz": s.text, "art": ARTEN[hypothesen.index(beste)],
                         "sicher": float(r["scores"][0])})
        return raus

    def entscheiden(self, satz: str, art: str):
        arten = self.satzarten(satz)
        if not arten:
            return None
        a = arten[0]
        if a["sicher"] < 0.5:
            return None
        return a["art"] == art

    def gedeckt(self, aussage: str, belege) -> float:
        # Vorbereitet: LettuceDetect markiert ungedeckte Stellen; hier nur
        # der Rückfall, bis es installiert und gemessen ist.
        raise KeinBackend("Deckung lokal noch nicht eingerichtet")


# ── Die Schnittstelle ───────────────────────────────────────────────────

_backends = {}


def backend(m: str | None = None):
    """Das Backend für den Modus (Standard: Einstellung). Ein Objekt je
    Modus und Prozess (der Cloud-Cache soll Züge überleben)."""
    m = m or modus()
    if m not in _backends:
        _backends[m] = {CLOUD: Cloud, LOKAL: Lokal}.get(m, Wortlisten)()
    return _backends[m]


def _mit_rueckfall(was: str, *args):
    b = backend()
    try:
        return getattr(b, was)(*args)
    except Exception as e:
        _log(f"KLASSIFIKATOR ✗ {getattr(b, 'name', '?')}: {e} — Wortliste")
        return getattr(Wortlisten(), was)(*args)


def satzarten(text: str, sprache: str = "de") -> list:
    return _mit_rueckfall("satzarten", text, sprache)


def gedeckt(aussage: str, belege) -> float:
    return _mit_rueckfall("gedeckt", aussage, belege)


def entscheiden(satz: str, art: str):
    """Ist `satz` von der Art `art`? True/False, None = unentschieden."""
    return _mit_rueckfall("entscheiden", satz, art)


def _log(zeile: str):
    try:
        import state
        state.push_log(zeile)
    except Exception:
        pass
