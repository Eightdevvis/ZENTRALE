# core/mail_rules.py
#
# Die Triage-Keymap für das Mail-System.
#
# ── Idee (Sashas Modell) ──────────────────────────────────────────────
# Eine MAIL ist ein Brief, ein ABSENDER ist eine bekannte (oder noch
# unbekannte) Hand. Das System führt eine Keymap "Absender -> Kategorie":
#
#   Absender BEKANNT   -> die ihm einmal zugewiesene Kategorie + deren Aktion.
#   Absender UNBEKANNT -> Kategorie "sasha muss gucken" (Review-Stapel).
#                         Wird NIE automatisch gelöscht — Sasha entscheidet,
#                         und ab dann ist der Absender bekannt.
#
# Kategorien sind DYNAMISCH: Sasha legt einfach neue an, wie sie im Alltag
# auftauchen. Das Start-Set deckt den geschilderten Bedarf ab. Jede Kategorie
# trägt eine SERVER-AKTION (was im echten Postfach passiert) — siehe unten.
#
# ── Safe-by-default ───────────────────────────────────────────────────
# Alle Default-Aktionen sind UMKEHRBAR: "verschieben" und "trash" lassen die
# Mail im Zielordner bzw. Papierkorb liegen. KEIN Hard-Expunge per Default.
# Eine Kategorie kann später `hard_delete: true` bekommen — nur dann wird
# wirklich endgültig gelöscht. Unbekannte Absender lösen NIE eine destruktive
# Aktion aus (Review ist reines Verschieben).
#
# ── Reine Logik ───────────────────────────────────────────────────────
# Dieses Modul macht KEIN Netzwerk und kein IMAP. Es klassifiziert nur und
# hält die Keymap in data/mail_rules.json. Die Ausführung (IMAP MOVE/Trash)
# macht core/mail.py anhand der hier gelieferten Aktion. So ist die Triage-
# Logik ohne Postfach unit-testbar.

import os
import json
import threading
from email.utils import parseaddr

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORE = os.path.join(_DIR, "data", "mail_rules.json")
_lock = threading.Lock()

# Revision der Keymap: bei JEDEM Write hochgezählt. Der Trie-Matcher (unten)
# cacht sich und baut nur neu, wenn sich `_rev` geändert hat — so kostet ein
# classify() im Normalfall keinen Datei-Zugriff und keinen Trie-Neuaufbau.
_rev = 0
_matcher = None
_matcher_rev = -1

# Die System-Kategorie für unbekannte/unsortierte Absender. Existiert immer,
# ist nicht löschbar — sie ist das Sicherheitsnetz.
REVIEW = "sasha muss gucken"

# Start-Kategorien. `action` steuert core/mail.py:
#   "move"  -> in `folder` verschieben (Ordner wird bei Bedarf angelegt)
#   "trash" -> in den Papierkorb des Providers (special-use \Trash)
# `auto_future` markiert Absender so, dass künftige Mails automatisch dieselbe
# Aktion bekommen (für "blocken": einmal blocken, dann dauerhaft weg).
_DEFAULT_CATEGORIES = {
    REVIEW:              {"action": "move",  "folder": "ZENTRALE/Review",   "system": True},
    "löschen":           {"action": "trash", "folder": None},
    "blocken":           {"action": "trash", "folder": None, "auto_future": True},
    "zahlen":            {"action": "move",  "folder": "ZENTRALE/Zahlen"},
    "arbeit antworten":  {"action": "move",  "folder": "ZENTRALE/Arbeit"},
    "freizeit antworten":{"action": "move",  "folder": "ZENTRALE/Freizeit"},
}


def _empty():
    # tiefe Kopie der Defaults, damit Mutationen den Modul-Default nicht anfassen
    return {
        "categories": {k: dict(v) for k, v in _DEFAULT_CATEGORIES.items()},
        "senders": {},  # die Keymap: normalisierte_adresse -> kategorie-name
    }


def _load_raw():
    if not os.path.exists(_STORE):
        return _empty()
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty()
    # Defensiv: fehlende Schlüssel auffüllen, System-Kategorie garantieren.
    data.setdefault("categories", {})
    data.setdefault("senders", {})
    for name, spec in _DEFAULT_CATEGORIES.items():
        data["categories"].setdefault(name, dict(spec))
    return data


def _save_raw(data):
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    tmp = _STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STORE)
    global _rev
    _rev += 1        # Keymap geändert → Matcher-Cache ist beim nächsten Zugriff stale


def normalize(addr):
    """'Max Mustermann <Max@Beispiel.DE>' -> 'max@beispiel.de'.

    Robuste Adress-Extraktion über email.utils. Lowercase, damit die Keymap
    nicht an Groß-/Kleinschreibung scheitert.
    """
    if not addr:
        return ""
    _, email_addr = parseaddr(addr)
    return (email_addr or addr).strip().lower()


# ── Trie-Matcher: schnelles Longest-Match (Adresse ODER Domain) ───────
# Sashas Idee: damit ein Einsortieren SCHNELL matchen kann, hängen die Regeln
# in einem Knoten-Wörterbuch-Baum (Trie). Der Schlüssel ist NICHT die rohe
# Zeichenkette, sondern der **umgedrehte Domain-Pfad** plus (optional) der
# Local-Part:
#
#     maria.kern@pearl.de   ->  ["de", "pearl", "@", "maria.kern"]
#     pearl.de              ->  ["de", "pearl"]                (Domain-Regel!)
#     noreply@trips.flixbus.com -> ["com","flixbus","trips","@","noreply"]
#
# Beim Klassifizieren laufen wir den Pfad der Absender-Adresse hinab und merken
# uns die TIEFSTE angetroffene Regel → das **spezifischste** Match gewinnt:
#   • eine Domain-Regel `pearl.de` deckt automatisch ALLE Absender @pearl.de
#     (und Subdomains) ab — eine Zuweisung, viele Adressen.
#   • eine Adress-Regel `boss@pearl.de` schlägt die Domain-Regel für genau
#     diese Adresse (sie sitzt tiefer im Baum).
# Das Umdrehen der Labels macht Domains zu Präfixen mit sauberer Grenze
# (Label-für-Label), also matcht `pearl.de` NICHT `pearl.de.evil.com`.

_LABEL_LOCAL = "@"    # Sentinel-Label zwischen Domain-Pfad und Local-Part


def _key_path(key):
    """Adresse ('local@domain') ODER blanke Domain ('pearl.de') → Trie-Pfad
    (umgedrehte Domain-Labels, dann '@' + Local-Part, falls vorhanden)."""
    key = (key or "").strip().lower()
    if not key:
        return []
    if "@" in key:
        local, _, domain = key.rpartition("@")
    else:
        local, domain = None, key
    path = [lbl for lbl in reversed(domain.split(".")) if lbl]
    if local is not None:
        path.append(_LABEL_LOCAL)
        path.append(local)
    return path


class _Node:
    __slots__ = ("children", "category")

    def __init__(self):
        self.children = {}
        self.category = None


class Matcher:
    """Ein aus einem Keymap-Schnappschuss gebauter Trie. Einmal bauen, dann
    beliebig oft `classify()` aufrufen (z.B. über tausende Mails im Reconcile-
    Sweep) — ohne Lock, ohne Datei-Zugriff, ohne Neuaufbau."""

    def __init__(self, senders, valid_categories):
        self._valid = set(valid_categories or ())
        self.root = _Node()
        for key, cat in (senders or {}).items():
            node = self.root
            for label in _key_path(key):
                nxt = node.children.get(label)
                if nxt is None:
                    nxt = node.children[label] = _Node()
                node = nxt
            node.category = cat

    def classify(self, from_addr):
        """Absender → (kategorie, bekannt?). Longest-Match; unbekannt → REVIEW."""
        addr = normalize(from_addr)
        if not addr:
            return REVIEW, False
        node = self.root
        best = None
        for label in _key_path(addr):
            node = node.children.get(label)
            if node is None:
                break
            if node.category is not None:
                best = node.category
        if best is not None and best in self._valid:
            return best, True
        return REVIEW, False


def matcher():
    """Der aktuelle (gecachte) Trie-Matcher. Baut nur neu, wenn sich die Keymap
    seit dem letzten Aufruf geändert hat (`_rev`)."""
    global _matcher, _matcher_rev
    with _lock:
        if _matcher is None or _matcher_rev != _rev:
            data = _load_raw()
            _matcher = Matcher(data["senders"], data["categories"].keys())
            _matcher_rev = _rev
        return _matcher


# ── öffentliche API ───────────────────────────────────────────────────

def load():
    with _lock:
        return _load_raw()


def categories():
    return load()["categories"]


def classify(from_addr):
    """Kernfunktion: Absender -> (kategorie, bekannt?).

    Bekannt  -> die (spezifischste) zugewiesene Kategorie, known=True.
    Unbekannt-> REVIEW, known=False (landet im "sasha muss gucken"-Stapel).

    Läuft über den Trie-Matcher (Longest-Match Adresse ODER Domain). Für den
    Bulk-Fall (Reconcile über tausende Mails) EINMAL `matcher()` holen und dessen
    `.classify()` wiederverwenden, statt hier pro Mail den Cache zu prüfen.
    """
    return matcher().classify(from_addr)


def category_action(name):
    """Liefert die Server-Aktions-Spec einer Kategorie (oder die von REVIEW,
    falls der Name unbekannt ist — nie None, damit der Aufrufer safe bleibt).
    """
    cats = categories()
    return cats.get(name) or cats[REVIEW]


def ensure_category(name, action="move", folder=None, **opts):
    """Legt eine Kategorie an, falls sie noch nicht existiert (dynamisch).

    Default-Aktion ist das umkehrbare "move" in einen nach der Kategorie
    benannten Unterordner. Bestehende Kategorien werden NICHT überschrieben.
    """
    name = name.strip()
    if not name:
        raise ValueError("Kategoriename leer")
    with _lock:
        data = _load_raw()
        if name not in data["categories"]:
            if folder is None and action == "move":
                # "Reise Zeug" -> "ZENTRALE/Reise Zeug"
                folder = "ZENTRALE/" + name.strip().title()
            spec = {"action": action, "folder": folder}
            spec.update(opts)
            data["categories"][name] = spec
            _save_raw(data)
        return data["categories"][name]


def assign(from_addr, category, **cat_opts):
    """Weist einem Absender eine Kategorie zu (schreibt die Keymap).

    Existiert die Kategorie noch nicht, wird sie dynamisch angelegt
    (mit den optionalen cat_opts, sonst Default "move"). Ab jetzt ist der
    Absender BEKANNT und künftige Mails von ihm bekommen diese Kategorie.
    """
    addr = normalize(from_addr)
    if not addr:
        raise ValueError("Absender-Adresse leer")
    ensure_category(category, **cat_opts)
    with _lock:
        data = _load_raw()
        data["senders"][addr] = category
        _save_raw(data)
    return addr, category


def delete_category(name):
    """Löscht eine Kategorie. Die System-Kategorie (REVIEW) ist tabu.

    Absender, die auf die gelöschte Kategorie zeigten, werden aus der Keymap
    entfernt -> sie sind wieder UNBEKANNT und landen beim nächsten Poll im
    Review-Stapel (nie destruktiv). Liefert (geloescht?, betroffene_absender).
    """
    name = (name or "").strip()
    with _lock:
        data = _load_raw()
        spec = data["categories"].get(name)
        if spec is None:
            return False, 0
        if name == REVIEW or spec.get("system"):
            raise ValueError("System-Kategorie '%s' ist nicht löschbar" % name)
        affected = [a for a, c in data["senders"].items() if c == name]
        for a in affected:
            del data["senders"][a]
        del data["categories"][name]
        _save_raw(data)
        return True, len(affected)


def forget(from_addr):
    """Entfernt einen Absender aus der Keymap -> wieder unbekannt (Review)."""
    addr = normalize(from_addr)
    with _lock:
        data = _load_raw()
        if addr in data["senders"]:
            del data["senders"][addr]
            _save_raw(data)
            return True
    return False


def keymap():
    """Die ganze Absender->Kategorie-Tabelle (Kopie)."""
    return dict(load()["senders"])
