# core/ki_einstellungen.py
#
# Die Chat-Einstellungen lesen und setzen: Anbieter, Modell, Effort, Budget,
# Weg (lokal/Cloud/auto). Für die Route /api/ai/einstellungen und damit für
# die Slash-Befehle im TUI-Chat (/modell, /anbieter, /effort, /budget,
# /lokal, /cloud, /auto).
#
# Warum ein eigenes Modul (2026-10-07, Claude-Web-Plan Phase 1): die Setter
# in ai_backends gab es schon, aber ohne Aufrufer — und sie prüfen nur, ob
# ein Wert technisch erlaubt ist, nicht ob er Sinn ergibt (ein Anbieter ohne
# Schlüssel ist „erlaubt", macht den Chat aber stumm). Diese Prüfung, mit
# Klartext für Sasha, gehört nicht in die Route (dünner Adapter) und nicht
# in ai_backends (wer denken darf) — sondern hierher.
#
# Schicht 3 (memory/system/bauplan_kern.md).

import os

import ai_backends
import providers

# Was „auto" bei der Wahl des Wegs heißen darf — Sasha tippt Deutsch.
_WEGE = {"lokal": ai_backends.LOCAL, "local": ai_backends.LOCAL,
         "cloud": ai_backends.CLOUD, "auto": "auto"}

BUDGET_HOECHSTENS = 10000.0     # Euro im Monat; alles darüber ist ein Tippfehler


class Ungueltig(ValueError):
    """Ein Wert, der so nicht geht. Der Text geht wörtlich an Sasha."""


def hat_schluessel(name: str) -> bool:
    """Liegt für diesen Anbieter ein Schlüssel vor (ohne ihn zu zeigen)?"""
    env = providers.get(name).get("key_env") or ""
    return bool(env and os.environ.get(env))


def modelle(name: str) -> list:
    """Die Modelle, die zur Wahl stehen: Standard und billig aus der
    Anbieter-Tabelle, dazu das gespeicherte. Ohne Dopplungen, in dieser
    Reihenfolge."""
    p = providers.get(name)
    raus = []
    for m in (p.get("default_model"), p.get("cheap_model"),
              ai_backends.chat_model(name)):
        if m and m not in raus:
            raus.append(m)
    return raus


def lesen() -> dict:
    """Der ganze Stand auf einmal (für /modell ohne Namen, /budget usw.)."""
    aktiv = ai_backends.cloud_provider()
    liste = []
    for name in providers.PROVIDERS:
        liste.append({
            "name": name,
            "schluessel": hat_schluessel(name),
            "spricht": bool(ai_backends.cloud_kind_for(name)),
            "modell": ai_backends.chat_model(name),
            "modelle": modelle(name),
        })
    return {
        "anbieter": ai_backends.chat_provider(),
        "anbieter_aktiv": aktiv,
        "modell": ai_backends.chat_model(aktiv) if aktiv else "",
        "effort": ai_backends.chat_effort(),
        "effort_stufen": list(ai_backends.EFFORT_STUFEN),
        "effort_wirkt": ai_backends.cloud_kind_for(aktiv) == "anthropic",
        "budget": ai_backends.budget_monat(),
        "budget_lage": ai_backends.budget_lage(),
        "weg": ai_backends.chat_backend(),
        "anbieter_liste": liste,
    }


# ── Prüfen ─────────────────────────────────────────────────────────────

def _anbieter_pruefen(wert) -> str:
    name = str(wert or "").strip().lower()
    if name == "auto":
        return name
    if name not in providers.PROVIDERS:
        raise Ungueltig(f"Den Anbieter „{name}“ kenne ich nicht. Es gibt: "
                        f"{', '.join(providers.PROVIDERS)} oder auto.")
    if not ai_backends.cloud_kind_for(name):
        raise Ungueltig(f"Mit {name} kann ZENTRALE nicht reden.")
    if not hat_schluessel(name):
        raise Ungueltig(f"Für {name} ist kein Schlüssel hinterlegt.")
    return name


def _modell_pruefen(wert) -> str:
    name = str(wert or "").strip()
    if not name:
        raise Ungueltig("Welches Modell? Der Name fehlt.")
    if len(name) > 80 or any(c.isspace() for c in name):
        raise Ungueltig(f"„{name[:40]}“ sieht nicht nach einem Modellnamen aus.")
    return name


def _modell_anbieter(modell: str, anbieter: str | None) -> str:
    """Zu welchem Anbieter das Modell gehört. Ausdrücklich genannt → der.
    Steht es bei genau EINEM Anbieter mit Schlüssel in der Liste → der
    (sonst ginge z. B. 'qwen-plus' an Anthropic). Sonst der aktuelle: ein
    neues Modell, das noch in keiner Liste steht, soll trotzdem gehen."""
    if anbieter and anbieter != "auto":
        return anbieter
    treffer = [n for n in providers.PROVIDERS
               if hat_schluessel(n) and modell in modelle(n)]
    if len(treffer) == 1:
        return treffer[0]
    aktiv = ai_backends.cloud_provider()
    if not aktiv:
        raise Ungueltig("Gerade ist kein Anbieter aktiv — erst einen wählen "
                        "(/anbieter).")
    return aktiv


def _effort_pruefen(wert) -> str:
    stufe = str(wert or "").strip().lower()
    if stufe not in ai_backends.EFFORT_STUFEN:
        raise Ungueltig("Effort gibt es in diesen Stufen: "
                        + ", ".join(ai_backends.EFFORT_STUFEN) + ".")
    return stufe


def budget_lesen(wert):
    """'20', '12,50', 20, 'aus' → float oder None (kein Deckel)."""
    if wert is None:
        return None
    if isinstance(wert, bool):
        raise Ungueltig("Budget bitte als Euro-Betrag, z. B. 20 oder 12,50 — "
                        "oder „aus“.")
    if isinstance(wert, (int, float)):
        euro = float(wert)
    else:
        text = str(wert).strip().lower().replace("€", "").replace(",", ".").strip()
        if text in ("", "aus", "off", "kein", "keins", "none"):
            return None
        try:
            euro = float(text)
        except ValueError:
            raise Ungueltig("Budget bitte als Euro-Betrag, z. B. 20 oder "
                            "12,50 — oder „aus“.") from None
    if euro != euro or euro <= 0 or euro > BUDGET_HOECHSTENS:
        raise Ungueltig(f"Ein Monatsbudget zwischen 0 und "
                        f"{BUDGET_HOECHSTENS:.0f} € bitte — oder „aus“.")
    return round(euro, 2)


def _weg_pruefen(wert) -> str:
    weg = _WEGE.get(str(wert or "").strip().lower())
    if weg is None:
        raise Ungueltig("Der Weg ist lokal, cloud oder auto.")
    return weg


# ── Setzen ─────────────────────────────────────────────────────────────

FELDER = ("anbieter", "modell", "effort", "budget", "weg")


def setzen(daten: dict) -> dict:
    """Einstellungen setzen (dauerhaft, data/ai_config.json). Erst ALLES
    prüfen, dann setzen: ein Unsinn in einem Feld lässt die anderen
    unangetastet. Wirft Ungueltig mit Klartext. -> lesen() danach."""
    if not isinstance(daten, dict) or not any(k in daten for k in FELDER):
        raise Ungueltig("Nichts zu setzen — erwartet: " + ", ".join(FELDER) + ".")

    plan = {}
    if "anbieter" in daten:
        plan["anbieter"] = _anbieter_pruefen(daten["anbieter"])
    if "modell" in daten:
        modell = _modell_pruefen(daten["modell"])
        ziel = _modell_anbieter(modell, plan.get("anbieter"))
        plan["modell"] = (modell, ziel)
        # Gehört das Modell zu einem anderen Anbieter, wechselt der mit —
        # sonst bliebe die Wahl wirkungslos.
        if "anbieter" not in plan and ziel != ai_backends.cloud_provider():
            plan["anbieter"] = _anbieter_pruefen(ziel)
    if "effort" in daten:
        plan["effort"] = _effort_pruefen(daten["effort"])
    if "budget" in daten:
        plan["budget"] = budget_lesen(daten["budget"])
    if "weg" in daten:
        plan["weg"] = _weg_pruefen(daten["weg"])

    if "anbieter" in plan:
        ai_backends.set_chat_provider(plan["anbieter"], persist=True)
    if "modell" in plan:
        ai_backends.set_chat_model(*plan["modell"])
    if "effort" in plan:
        ai_backends.set_chat_effort(plan["effort"], persist=True)
    if "budget" in plan:
        ai_backends.set_budget_monat(plan["budget"], persist=True)
    if "weg" in plan:
        ai_backends.set_chat_backend(plan["weg"], persist=True)
    return lesen()
