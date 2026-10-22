# core/kachel_http.py
#
# Kachel-Quelle hinter HTTP (Hub-Grundlagen, 2026-10-22; memory/hub/
# hub_bauplan.md „Kacheln" → „Quelle über HTTP"). Eine ausgezogene App liefert
# Kacheln, indem sie es im app.toml sagt:
#
#   liefert = ["kachel:liste"]
#   [kachel.liste]                      # = ein Katalog-Eintrag (wie ARTEN)
#   titel = "liste"
#   min = [12, 7]
#   bevorzugt = [36, 12]                # optional, auch max
#   ttl = 30
#   parameter = "kachel/liste.schema.json"   # JSON Schema: Datei im App-Ordner
#                                            # oder als Tabelle direkt hier
#   kann = ["aktion", "parameter_jetzt", "pruefen", "bevorzugt"]   # optional
#
# Der Hub (core/kacheln.py) baut daraus ein Objekt mit DERSELBEN Schnittstelle
# wie eine Quelle im Prozess (APP, ARTEN, RECHTE, kachel, …) — für ihn ist
# „im Prozess" oder „über HTTP" nur ein anderer Eintrag. Die App beantwortet:
#
#   POST <adresse>/hub/kachel            {art, ref, w, h, oben}
#        200 {zeilen, text, oben?, oben_max?} | 200 {zu_klein: {w, h}}
#        404 {fehler: "weg"} | 400 {fehler: "ungueltig", text}
#   POST <adresse>/hub/kachel/aktion     {art, ref, aktion}  → 200 {zeige: {adresse}}
#   POST <adresse>/hub/kachel/parameter  {art, schema}       → 200 {schema: … | null}
#   POST <adresse>/hub/kachel/pruefen    {art, ref}          → 200 {} | 400 {fehler, text}
#   POST <adresse>/hub/kachel/bevorzugt  {art, ref}          → 200 {w, h}
#
# (Form: openapi.yaml, Pfade unter /hub/.) Zeitbudget: jede Frage darf
# ZEITBUDGET_S dauern, dann bricht der Hub ab — die Kachel heißt „aus".
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Importiert keinen
# App-Code, nur die Form-Fehler (kachel_form).

import http.client
import json
import os
from urllib.parse import urlsplit

from kachel_form import KachelFehler, KachelWeg, KachelZuKlein

ZEITBUDGET_S = 0.5
KANN = ("aktion", "parameter_jetzt", "pruefen", "bevorzugt")


class AppAntwortetNicht(RuntimeError):
    """Nicht erreichbar, zu langsam oder eine Antwort ohne Sinn → „aus"."""


def _arten(m):
    """[kachel.<art>] des Manifests → ARTEN wie bei einer Quelle im Prozess
    (nur Arten, die auch in `liefert` stehen)."""
    liefert = {str(x)[len("kachel:"):] for x in (m.get("liefert") or [])
               if str(x).startswith("kachel:")}
    tabelle = m.get("kachel") or {}
    raus = {}
    for art in sorted(liefert):
        info = dict(tabelle.get(art) or {})
        p = info.get("parameter")
        if isinstance(p, str):                    # Datei im App-Ordner
            datei = os.path.normpath(os.path.join(m["_pfad"], p))
            if not datei.startswith(os.path.normpath(m["_pfad"]) + os.sep):
                raise ValueError("parameter-datei liegt außerhalb der app: %s" % p)
            with open(datei, encoding="utf-8") as f:
                info["parameter"] = json.load(f)
        info.pop("kann", None)
        raus[art] = info
    return raus


class Quelle:
    """Eine Kachel-Quelle, die über HTTP fragt. Optionale Fragen (KANN) gibt
    es nur, wenn eine Art sie im Manifest unter `kann` nennt — wie bei einer
    Quelle im Prozess, die eine Funktion hat oder nicht."""

    RECHTE = ("lesen",)

    def __init__(self, m: dict):
        self.APP = str(m["name"])
        self.ARTEN = _arten(m)
        self._adresse = urlsplit(str(m.get("adresse") or ""))
        kann = set()
        for info in (m.get("kachel") or {}).values():
            kann |= {str(k) for k in (info.get("kann") or [])}
        for k in KANN:
            if k in kann:
                setattr(self, k, getattr(self, "_" + k))

    # ── Leitung ──────────────────────────────────────────────────────

    def _frage(self, pfad, koerper):
        """POST JSON an die App → (status, antwort-dict). Wirft
        AppAntwortetNicht bei allem, was keine verwertbare Antwort ist."""
        a = self._adresse
        if a.scheme != "http" or not a.hostname:
            raise AppAntwortetNicht("adresse taugt nicht")
        daten = json.dumps(koerper, ensure_ascii=False).encode("utf-8")
        v = http.client.HTTPConnection(a.hostname, a.port or 80, timeout=ZEITBUDGET_S)
        try:
            v.request("POST", a.path.rstrip("/") + pfad, body=daten,
                      headers={"Content-Type": "application/json"})
            r = v.getresponse()
            roh = r.read()
            status = r.status
        except (OSError, http.client.HTTPException) as e:
            raise AppAntwortetNicht("%s: %s" % (self.APP, e or type(e).__name__))
        finally:
            v.close()
        try:
            antwort = json.loads(roh.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise AppAntwortetNicht("%s: antwort ist kein json (status %d)" % (self.APP, status))
        if not isinstance(antwort, dict):
            raise AppAntwortetNicht("%s: antwort ist kein objekt" % self.APP)
        return status, antwort

    def _pruefe_status(self, status, antwort):
        """Die Fehler-Antworten der App als die Fehler, die der Hub kennt."""
        if status == 404 and antwort.get("fehler") == "weg":
            raise KachelWeg(antwort.get("text") or "weg")
        if status == 400:
            raise KachelFehler(str(antwort.get("text") or "ungültig"))
        if status != 200:
            raise AppAntwortetNicht("%s: status %d" % (self.APP, status))

    # ── Schnittstelle einer Quelle (core/kacheln.py) ────────────────

    def kachel(self, art, ref, w, h, oben=0):
        status, antwort = self._frage("/hub/kachel", {"art": art, "ref": ref, "w": w,
                                                      "h": h, "oben": oben or 0})
        self._pruefe_status(status, antwort)
        zk = antwort.get("zu_klein")
        if isinstance(zk, dict):
            raise KachelZuKlein(zk.get("w", w), zk.get("h", h))
        return antwort

    def _aktion(self, art, ref, was):
        status, antwort = self._frage("/hub/kachel/aktion", {"art": art, "ref": ref, "aktion": was})
        self._pruefe_status(status, antwort)
        return antwort

    def _parameter_jetzt(self, art, schema):
        status, antwort = self._frage("/hub/kachel/parameter", {"art": art, "schema": schema})
        self._pruefe_status(status, antwort)
        return antwort.get("schema")

    def _pruefen(self, art, ref):
        status, antwort = self._frage("/hub/kachel/pruefen", {"art": art, "ref": ref})
        self._pruefe_status(status, antwort)

    def _bevorzugt(self, art, ref):
        status, antwort = self._frage("/hub/kachel/bevorzugt", {"art": art, "ref": ref})
        self._pruefe_status(status, antwort)
        return int(antwort["w"]), int(antwort["h"])
