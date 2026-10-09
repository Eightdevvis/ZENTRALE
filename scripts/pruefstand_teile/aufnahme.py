# Aufzeichnen und kostenlos Abspielen (2026-10-09, Sasha: Kosten senken).
#
# Ein bezahlter Lauf schreibt jede Modell-Antwort mit (je Fall, Zug, Runde):
# was gestreamt kam (Denken, Text) und die fertige Nachricht (Werkzeug-
# Aufrufe, stop_reason, Verbrauch). `--abspielen <ordner>` fährt denselben
# Fall danach OHNE Modell: die Werkzeuge laufen echt gegen die aktuelle
# Werkzeug-Schicht, statt des Modells kommt die Aufnahme. So kostet es
# nichts, eine Werkzeug-Änderung gegen echte Gesprächsverläufe zu prüfen.
#
# Gültig ist das nur, solange die aufgezeichnete nächste Antwort noch zu dem
# passt, was die Werkzeuge jetzt zurückgeben. Die Regel: dieselbe Zahl von
# Werkzeug-Ergebnissen mit demselben Ausgang (Status-Zeile „[ergebnis: …]",
# Fehler ja/nein). Anderer Wortlaut bei gleichem Ausgang wird nur gezählt
# (abweichend) — das ist ja meist genau die Änderung, die man prüfen will.
# Passt es nicht mehr: „Abspielen ab Zug n nicht mehr gültig", der Fall
# endet dort.
#
# Nur der Anthropic-Weg (core/cloud.py, _get_client) wird aufgezeichnet.
# Nebenaufrufe über billig.einmal (Gesprächstitel u. ä.) bekommen beim
# Abspielen eine feste Antwort — sie sind für die Prüfung belanglos.

import hashlib
import json
from types import SimpleNamespace


class NichtMehrGueltig(RuntimeError):
    pass


def _als_dict(block) -> dict:
    if isinstance(block, dict):
        return dict(block)
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json", exclude_none=True)
        except TypeError:
            return dump()
    return {k: v for k, v in vars(block).items() if v is not None and not k.startswith("_")}


def _als_objekt(d: dict):
    return SimpleNamespace(**d)


def _verbrauch(u) -> dict:
    return {k: int(getattr(u, k, 0) or 0) for k in
            ("input_tokens", "output_tokens", "cache_read_input_tokens",
             "cache_creation_input_tokens")}


def ergebnisse(anfrage: dict) -> list:
    """Die Werkzeug-Ergebnisse, auf die das Modell in dieser Runde antwortet:
    [[status, fehler, prüfsumme]] aus der letzten user-Nachricht."""
    msgs = anfrage.get("messages") or []
    if not msgs or msgs[-1].get("role") != "user" or not isinstance(msgs[-1].get("content"), list):
        return []
    raus = []
    for b in msgs[-1]["content"]:
        if not isinstance(b, dict) or b.get("type") != "tool_result":
            continue
        inhalt = b.get("content")
        if isinstance(inhalt, list):
            inhalt = "".join(str(x.get("text", "")) for x in inhalt if isinstance(x, dict))
        text = str(inhalt or "")
        erste = text.lstrip().split("\n", 1)[0]
        status = erste if erste.startswith("[") else ""
        raus.append([status[:60], bool(b.get("is_error")),
                     hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]])
    return raus


# ── Aufzeichnen ────────────────────────────────────────────────────────

class _AufnahmeStrom:
    def __init__(self, echt_cm, runde: dict):
        self._cm, self._runde = echt_cm, runde

    def __enter__(self):
        self._strom = self._cm.__enter__()
        return self

    def __exit__(self, *a):
        return self._cm.__exit__(*a)

    def __iter__(self):
        for ev in self._strom:
            if getattr(ev, "type", "") == "content_block_delta":
                d = ev.delta
                if d.type == "thinking_delta":
                    self._runde["thinking"].append(d.thinking or "")
                elif d.type == "text_delta":
                    self._runde["text"].append(d.text or "")
            yield ev

    def get_final_message(self):
        final = self._strom.get_final_message()
        self._runde["final"] = {
            "stop_reason": final.stop_reason,
            "content": [_als_dict(b) for b in final.content],
            "usage": _verbrauch(getattr(final, "usage", None))}
        return final


class Aufnahme:
    """Hängt sich zwischen cloud.py und den echten Client."""

    def __init__(self, fall_id: str):
        self.daten = {"fall": fall_id, "runden": []}
        self.zug = 0

    def vor_zug(self, n):
        self.zug = n

    def nach_zug(self, n):
        return None

    def client(self, echt):
        aufnahme = self

        class Nachrichten:
            def stream(self, **kw):
                runde = {"zug": aufnahme.zug, "modell": kw.get("model"),
                         "ergebnisse": ergebnisse(kw), "thinking": [], "text": [],
                         "final": None}
                aufnahme.daten["runden"].append(runde)
                return _AufnahmeStrom(echt.messages.stream(**kw), runde)

            def __getattr__(self, name):
                return getattr(echt.messages, name)

        return SimpleNamespace(messages=Nachrichten())

    def einhaengen(self):
        import cloud
        alt = cloud._get_client
        cloud._get_client = lambda: self.client(alt())

        def zurueck():
            cloud._get_client = alt
        return zurueck

    def speichern(self, pfad: str):
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(self.daten, f, ensure_ascii=False, default=str)


# ── Abspielen ──────────────────────────────────────────────────────────

class _AbspielStrom:
    def __init__(self, runde: dict):
        self._r = runde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for t in self._r.get("thinking") or []:
            yield SimpleNamespace(type="content_block_delta",
                                  delta=SimpleNamespace(type="thinking_delta", thinking=t))
        for t in self._r.get("text") or []:
            yield SimpleNamespace(type="content_block_delta",
                                  delta=SimpleNamespace(type="text_delta", text=t))

    def get_final_message(self):
        f = self._r["final"]
        # Verbrauch 0: Abspielen kostet nichts und soll auch nichts buchen.
        return SimpleNamespace(stop_reason=f["stop_reason"],
                               content=[_als_objekt(b) for b in f["content"]],
                               usage=SimpleNamespace(input_tokens=0, output_tokens=0,
                                                     cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))


class Abspielen:
    """Spielt eine Aufnahme statt des Modells ab und merkt, ab wann sie nicht
    mehr passt."""

    def __init__(self, daten: dict):
        self.runden = [r for r in daten.get("runden") or [] if r.get("final")]
        self.pos = 0
        self.zug = 0
        self.ungueltig = None          # (zug, grund)
        self.abweichend = []           # gleicher Ausgang, anderer Wortlaut
        self.modell = next((r.get("modell") for r in self.runden if r.get("modell")), None)

    @classmethod
    def laden(cls, pfad: str):
        with open(pfad, encoding="utf-8") as f:
            return cls(json.load(f))

    def vor_zug(self, n):
        self.zug = n

    def nach_zug(self, n):
        if self.ungueltig:
            return f"Abspielen ab Zug {self.ungueltig[0]} nicht mehr gültig: {self.ungueltig[1]}"
        rest = [r for r in self.runden[self.pos:] if r.get("zug") == n]
        if rest:
            self.ungueltig = (n, f"Zug endete nach weniger Runden als aufgezeichnet "
                                 f"({len(rest)} übrig)")
            return self.nach_zug(n)
        return None

    def _ungueltig(self, grund: str):
        if not self.ungueltig:
            self.ungueltig = (self.zug, grund)
        raise NichtMehrGueltig(f"Abspielen ab Zug {self.zug} nicht mehr gültig: {grund}")

    def stream(self, **kw):
        if self.ungueltig:
            self._ungueltig(self.ungueltig[1])
        if self.pos >= len(self.runden):
            self._ungueltig("das Modell würde jetzt mehr Runden brauchen als aufgezeichnet")
        r = self.runden[self.pos]
        if r.get("zug") != self.zug:
            self._ungueltig(f"aufgezeichnet ist als nächstes Zug {r.get('zug')}, "
                            f"hier läuft noch Zug {self.zug}")
        jetzt, damals = ergebnisse(kw), r.get("ergebnisse") or []
        if [e[:2] for e in jetzt] != [e[:2] for e in damals]:
            self._ungueltig(
                f"Werkzeug-Ergebnisse anders ausgegangen (Runde {self.pos + 1}): "
                f"jetzt {[e[0] or ('Fehler' if e[1] else 'ok') for e in jetzt]}, "
                f"damals {[e[0] or ('Fehler' if e[1] else 'ok') for e in damals]}")
        for i, (a, b) in enumerate(zip(jetzt, damals)):
            if a[2] != b[2]:
                self.abweichend.append(f"Zug {self.zug}, Runde {self.pos + 1}, Ergebnis {i + 1}")
        self.pos += 1
        return _AbspielStrom(r)

    def client(self):
        return SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def einhaengen(self):
        """Modell, Anbieter und Nebenaufrufe auf die Aufnahme. -> Rückweg."""
        import ai_backends
        import billig
        import cloud
        alt = []

        def setzen(modul, attr, wert):
            alt.append((modul, attr, getattr(modul, attr)))
            setattr(modul, attr, wert)

        setzen(cloud, "_get_client", self.client)
        setzen(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
        setzen(ai_backends, "chat_cloud_kind", lambda: "anthropic")
        setzen(ai_backends, "cloud_provider", lambda: "claude")
        if self.modell:
            setzen(cloud, "_model", lambda: self.modell)
        setzen(billig, "einmal", lambda *a, **k: ("Abgespielt", "abspielen"))

        def zurueck():
            for modul, attr, wert in reversed(alt):
                setattr(modul, attr, wert)
        return zurueck

    def bericht(self) -> dict:
        return {"gueltig": self.ungueltig is None,
                "ungueltig_ab_zug": self.ungueltig[0] if self.ungueltig else None,
                "grund": self.ungueltig[1] if self.ungueltig else None,
                "runden_abgespielt": self.pos, "runden_aufgezeichnet": len(self.runden),
                "abweichend": self.abweichend}
