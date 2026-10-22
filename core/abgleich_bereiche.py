# core/abgleich_bereiche.py
#
# Die wählbaren Einheiten des Abgleichs (memory/hub/knoten_beitritt.md,
# „Bauplan v1 — Wählbare Einheiten"): bis es eine leere Hub-Fassung gibt,
# sind das die BEREICHE der Daten, gruppiert aus der Positivliste
# (core/abgleich_auswahl.py), dazu echte Apps (der Tutor).
#
# Die Wahl gilt je Gerät (Einstellung `abgleich_bereiche` in
# data/ai_config.json, die nie abgeglichen wird). Ein nicht gewählter Bereich
# wird auf diesem Gerät weder geholt noch gesendet; in der Mitte bleibt er
# unberührt. Nicht gesetzt = alles (so bleibt Sashas git-Weg wie er war).
#
# Jedes Muster aus auswahl.ABGLEICH gehört zu GENAU einem Bereich — der Test
# (tests/test_abgleich_bereiche.py) wird rot, wenn ein neues Muster in der
# Positivliste keinen Bereich hat.

import ai_config
import abgleich_auswahl as auswahl

# (id, Art, Muster). Die id ist fest (steht in den Einstellungen); Name und
# Beschreibung für Menschen stehen in der Oberfläche (zentrale_cli/texte.py).
BEREICHE = [
    ("lists", "daten", ["data/lists.json", "data/features.json"]),
    ("notes", "daten", ["data/notes.json"]),
    ("calendar", "daten", ["data/kalender_neben.json"]),
    ("graphs", "daten", ["data/graphs.json", "data/g_*.json", "data/sleep_quality.json"]),
    ("memory", "daten", ["data/gedaechtnis/**"]),
    ("conversations", "daten", ["data/gespraeche/**", "data/ai_transcripts/*.jsonl",
                                "data/rueckmeldungen/*.jsonl", "data/mobil/kontext.json",
                                "data/ai_usage.json"]),
    ("documents", "daten", ["data/ablage/**"]),
    ("desk", "daten", ["data/desk/**"]),
    ("apps", "daten", ["data/apps/**", "data/shop/**"]),
    ("mail", "daten", ["data/mail_rules.json"]),
    ("music", "daten", ["data/melodies.json"]),
    ("tutor", "app", ["tutor/data/tutor_config.json", "tutor/data/aktiver_stand",
                      "tutor/data/staende/**", "tutor/data/es/**"]),
]
IDS = [b[0] for b in BEREICHE]
EINSTELLUNG = "abgleich_bereiche"


def gewaehlt():
    """→ Liste der gewählten ids, oder None = nie gewählt (alles)."""
    w = ai_config.setting(EINSTELLUNG)
    if w is None:
        return None
    if isinstance(w, str):
        w = [t.strip() for t in w.split(",") if t.strip()]
    return [i for i in IDS if i in w]


def setzen(ids):
    """Die Wahl dieses Geräts ablegen. [] = clean slate (nichts abgleichen)."""
    unbekannt = [i for i in ids if i not in IDS]
    if unbekannt:
        raise ValueError(f"Unknown areas: {', '.join(unbekannt)}")
    # [] ist eine echte Wahl (clean slate), kein „löschen" — set_override
    # nimmt nur None und "" als löschen.
    ai_config.set_override(EINSTELLUNG, [i for i in IDS if i in ids], persist=True)


def muster(ids=None):
    """Die Muster der Positivliste, die dieses Gerät abgleicht."""
    ids = gewaehlt() if ids is None else ids
    if ids is None:
        return list(auswahl.ABGLEICH)
    raus = []
    for i, _art, m in BEREICHE:
        if i in ids:
            raus.extend(x for x in m if x in auswahl.ABGLEICH)
    return raus


def bereich_von(rel: str):
    """Zu welchem Bereich gehört ein Pfad? → id oder None."""
    for i, _art, m in BEREICHE:
        if auswahl.passt(rel, m):
            return i
    return None
