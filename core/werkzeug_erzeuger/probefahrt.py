# core/werkzeug_erzeuger/probefahrt.py
#
# Die Probefahrt einer Anbindung (2026-10-11, Pipe-Schritt 3 im Hub-Bauplan):
# je Aktion ausprobieren, ob die Beschreibung stimmt — OHNE Modell und ohne
# Geld, gegen eine Test-Kopie oder ein Test-Konto des Programms.
#
#   anlegen   anlegen → nachlesen → vergleichen → zurückbauen (weg?)
#   ändern    Probe-Objekt anlegen → ändern → nachlesen/vergleichen →
#             alten Stand zurückschreiben (steht er wieder da?) → aufräumen
#   löschen   Probe-Objekt anlegen → löschen (weg?) → wiederherstellen
#             (steht es wieder da?) → aufräumen
#   lesen     ein Aufruf mit den Probe-Argumenten
#
# Alles läuft durch dieselbe Schutzschicht wie im Gespräch (harness.ausfuehren):
# was die Probefahrt besteht, besteht auch das Werkzeug. Aktionen ohne Beleg-
# Stufe (gefragt/einmalig) lassen sich nicht zurückbauen — sie werden nur mit
# alles=True ausgeführt (und hinterlassen dann Reste in der Test-Kopie).
#
# Bericht je Aktion: {aktion, art, stufe, ok, warum, schritte:[{schritt, ok,
# text}]}. Die Probe-Argumente stehen in der Beschreibung (`probe`).

from . import anbindung, harness, schema as erz_schema, vergleich, vorlage
from .allgemein import quelle_aus


def _schritt(zeilen, name, ok, text=""):
    zeilen.append({"schritt": name, "ok": bool(ok), "text": " ".join(str(text).split())[:300]})
    return bool(ok)


class _Spur:
    """Merkt sich die Kennung, die der Adapter beim letzten Schreiben meldete."""

    def __init__(self, adapter):
        self.adapter, self.kennung = adapter, None
        self._orig = adapter.ausfuehren
        adapter.ausfuehren = self._ausfuehren

    def _ausfuehren(self, name, args):
        erg = self._orig(name, args)
        self.kennung = getattr(erg, "kennung", None) or self.kennung
        return erg

    def ende(self):
        self.adapter.ausfuehren = self._orig


def _ok(ergebnis) -> bool:
    from werkzeug_befund import OK, status_von
    return status_von(ergebnis) == OK


def _pseudo_args(regeln: dict, alt: dict) -> dict:
    """Aus einem Eintrag die Angaben, wie man sie verlangen würde — um zu
    prüfen, ob ein Eintrag dem alten Stand wieder entspricht."""
    raus = {}
    for name, regel in regeln.items():
        wert = vorlage.zeiger_eins(alt, regel.get("feld") or "/" + name)
        if wert is not None:
            raus[name] = wert
    return raus


def _entspricht(regeln: dict, alt: dict, jetzt: dict, zone) -> list:
    """Welche verglichenen Felder von `jetzt` vom alten Stand abweichen. Beide
    Seiten kommen aus dem Programm: gleiche Schreibweise, daher text-genau
    nur dort, wo keine Normalisierung nötig ist — sonst wie im Vergleich."""
    falsch = []
    for name, regel in regeln.items():
        feld = regel.get("feld") or "/" + name
        a, j = vorlage.zeiger_eins(alt, feld), vorlage.zeiger_eins(jetzt, feld)
        if a is None and j is None:
            continue
        if a is None or j is None:
            falsch.append(f"{name}: vorher {a!r}, jetzt {j!r}")
            continue
        try:
            if not vergleich.gleich(regel["norm"], a, j, zone):
                falsch.append(f"{name}: vorher {a!r}, jetzt {j!r}")
        except vergleich.NichtVergleichbar as e:
            falsch.append(f"{name}: {e}")
    return falsch


class _Fahrt:
    def __init__(self, besch, quelle, alles):
        self.besch, self.quelle, self.alles = besch, quelle, alles
        self.adapter = quelle.adapter
        self.aktionen = {a["name"]: a for a in besch["aktionen"]}
        self.erz = {a["name"]: a for a in quelle.aktionen}

    def laufen(self, name, args):
        return harness.ausfuehren(self.quelle, self.erz[name], args)

    def nachlesen(self, a, kennung):
        return self.adapter.lesen_eintrag(self.besch["nachlesen"][a["nachlesen"]], kennung)

    # -- Probe-Objekt (für ändern/löschen) --
    def basis(self, zeilen, a):
        pr = a["probe"]
        v = self.aktionen[pr["vorher"]]
        if anbindung.stufe(self.besch, v) != anbindung.VOLL:
            _schritt(zeilen, "Probe-Objekt anlegen", False,
                     f"{v['name']} hat keine volle Schutzschicht — ohne sie lässt sich das Objekt nicht sauber aufräumen")
            return None
        spur = _Spur(self.adapter)
        try:
            r = self.laufen(v["name"], v["probe"]["argumente"])
        finally:
            spur.ende()
        if not _schritt(zeilen, f"Probe-Objekt anlegen ({v['name']})", _ok(r) and spur.kennung, r):
            return None
        return v, spur.kennung

    def aufraeumen(self, zeilen, v, kennung):
        try:
            self.adapter.zurueckbauen(v, kennung, v["probe"]["argumente"], None)
            weg = self.nachlesen(v, kennung) is None
            _schritt(zeilen, "Probe-Objekt aufräumen", weg,
                     "weg" if weg else "steht nach dem Aufräumen noch da — von Hand entfernen: " + kennung)
        except Exception as e:      # noqa: BLE001 — Aufräumen darf den Bericht nie sprengen
            _schritt(zeilen, "Probe-Objekt aufräumen", False, f"{e} — von Hand entfernen: {kennung}")

    # -- je Art --
    def lesen(self, a, zeilen):
        pr = a["probe"]
        args, basis = dict(pr["argumente"]), None
        if pr.get("vorher"):
            basis = self.basis(zeilen, a)
            if not basis:
                return False
            if pr.get("kennung_in"):
                args[pr["kennung_in"]] = basis[1]
        try:
            r = self.laufen(a["name"], args)
            ok = _schritt(zeilen, "lesen", _ok(r) and str(r).strip(), str(r)[:120])
            if ok and pr.get("erwartet"):
                ok &= _schritt(zeilen, "enthält das Probe-Objekt", pr["erwartet"] in str(r),
                               f"„{pr['erwartet']}“ " + ("steht drin" if pr["erwartet"] in str(r) else "fehlt"))
            return ok
        finally:
            if basis:
                self.aufraeumen(zeilen, *basis)

    def anlegen(self, a, zeilen):
        spur = _Spur(self.adapter)
        try:
            r = self.laufen(a["name"], a["probe"]["argumente"])
        finally:
            spur.ende()
        k = spur.kennung
        ok = _schritt(zeilen, "anlegen", _ok(r) and k, r)
        if not k:
            return False
        e = self.nachlesen(a, k)
        ok &= _schritt(zeilen, "nachlesen", e is not None, f"Kennung {k}" if e else "steht nicht da")
        if e is not None:
            falsch = vergleich.abweichungen(a.get("vergleich") or {}, a["probe"]["argumente"], e, self.besch.get("zeitzone"))
            ok &= _schritt(zeilen, "vergleichen", not falsch,
                           "; ".join(falsch) or f"{len(a.get('vergleich') or {})} Felder gleich")
        try:
            self.adapter.zurueckbauen(a, k, a["probe"]["argumente"], None)
            weg = self.nachlesen(a, k) is None
            ok &= _schritt(zeilen, "zurückbauen", weg, "weg" if weg else "steht nach dem Löschen noch da")
        except Exception as ex:     # noqa: BLE001
            ok &= _schritt(zeilen, "zurückbauen", False, f"{ex} — von Hand entfernen: {k}")
        return ok

    def aendern(self, a, zeilen):
        b = self.basis(zeilen, a)
        if not b:
            return False
        v, k = b
        arg = a["kennung_aus"]["argument"]
        args = {**a["probe"]["argumente"], arg: k}
        alt = self.nachlesen(a, k)
        try:
            r = self.laufen(a["name"], args)
            ok = _schritt(zeilen, "ändern", _ok(r), r)
            if ok:
                e = self.nachlesen(a, k)
                falsch = (vergleich.abweichungen(a.get("vergleich") or {}, args, e, self.besch.get("zeitzone"))
                          if e is not None else ["steht nicht mehr da"])
                ok &= _schritt(zeilen, "nachlesen + vergleichen", not falsch,
                               "; ".join(falsch) or f"{len(a.get('vergleich') or {})} Felder gleich")
                try:
                    self.adapter.zurueckbauen(a, k, args, alt)
                    zurueck = self.nachlesen(a, k)
                    falsch = (_entspricht(a.get("vergleich") or {}, alt, zurueck, self.besch.get("zeitzone"))
                              if zurueck is not None else ["steht nicht mehr da"])
                    ok &= _schritt(zeilen, "zurückbauen (alter Stand)", not falsch,
                                   "; ".join(falsch) or "alter Stand steht wieder da")
                except Exception as ex:     # noqa: BLE001
                    ok &= _schritt(zeilen, "zurückbauen (alter Stand)", False, str(ex))
            return ok
        finally:
            self.aufraeumen(zeilen, v, k)

    def loeschen(self, a, zeilen):
        b = self.basis(zeilen, a)
        if not b:
            return False
        v, k = b
        arg = a["kennung_aus"]["argument"]
        args = {**a["probe"]["argumente"], arg: k}
        alt = self.nachlesen(v, k)
        try:
            r = self.laufen(a["name"], args)
            ok = _schritt(zeilen, "löschen", _ok(r), r)
            if ok:
                ok &= _schritt(zeilen, "nachlesen (weg?)", self.nachlesen(v, k) is None, "weg")
                try:
                    self.adapter.zurueckbauen(a, k, args, alt)
                    zurueck = self.nachlesen(v, k)
                    falsch = (_entspricht(v.get("vergleich") or {}, alt, zurueck, self.besch.get("zeitzone"))
                              if zurueck is not None else ["steht nach dem Wiederherstellen nicht da"])
                    ok &= _schritt(zeilen, "wiederherstellen", not falsch,
                                   "; ".join(falsch) or "steht wieder da wie vorher")
                except Exception as ex:     # noqa: BLE001
                    ok &= _schritt(zeilen, "wiederherstellen", False, str(ex))
            return ok
        finally:
            self.aufraeumen(zeilen, v, k)

    def ohne_beleg(self, a, art, zeilen):
        """Aktion ohne Beleg-Stufe (nur mit alles=True): ausführen und
        sagen, was die Probefahrt selbst sehen kann."""
        args = dict(a["probe"]["argumente"])
        basis = None
        if art in ("aendern", "loeschen"):
            basis = self.basis(zeilen, a)
            if not basis:
                return False
            args[a["kennung_aus"]["argument"]] = basis[1]
        r = self.laufen(a["name"], args)
        ok = _schritt(zeilen, "ausführen (nicht belegt)", _ok(r) and "NICHT belegt" in str(r), r)
        if basis:
            v, k = basis
            da = self.nachlesen(v, k) is not None
            if art == "loeschen":
                _schritt(zeilen, "Probefahrt sieht nach", not da, "weg" if not da else "steht noch da")
            if da:
                self.aufraeumen(zeilen, v, k)
        else:
            _schritt(zeilen, "Reste", True, "Die Aktion hat in der Test-Kopie etwas hinterlassen, "
                     "das die Probefahrt nicht zurückbauen kann — von Hand wegräumen.")
        return ok

    def aktion(self, a) -> dict:
        art = erz_schema.art(a)
        st = anbindung.stufe(self.besch, a)
        zeilen = []
        row = {"aktion": a["name"], "art": art, "stufe": st, "ok": False, "warum": "", "schritte": zeilen}
        if not a.get("probe"):
            row["warum"] = "keine Probe-Argumente in der Beschreibung (probe) — nicht geprüft"
            return row
        if art != "lesen" and st not in (anbindung.VOLL,) and not self.alles:
            row["ok"] = True
            row["warum"] = (f"Stufe „{anbindung.STUFEN_TEXT[st]}“: lässt sich nicht zurückbauen — "
                            "nicht ausgeführt (mit alles=True gegen eine Test-Kopie)")
            row["uebersprungen"] = True
            return row
        try:
            if art == "lesen":
                ok = self.lesen(a, zeilen)
            elif st != anbindung.VOLL:
                ok = self.ohne_beleg(a, art, zeilen)
            else:
                ok = getattr(self, {"anlegen": "anlegen", "aendern": "aendern", "loeschen": "loeschen"}[art])(a, zeilen)
        except Exception as e:      # noqa: BLE001 — ein Fehler in einer Aktion bricht die Fahrt nicht ab
            ok = _schritt(zeilen, "Fehler", False, f"{e.__class__.__name__}: {e}")
        row["ok"] = bool(ok)
        schlecht = [s for s in zeilen if not s["ok"]]
        row["warum"] = ("; ".join(f"{s['schritt']}: {s['text']}" for s in schlecht)
                        if schlecht else "alle Schritte in Ordnung")
        return row


def fahren(besch: dict, quelle=None, nur=None, alles: bool = False, sender=None) -> list:
    """Die Probefahrt. `quelle` (aus allgemein.quelle_aus) bringt den
    gewünschten Transport mit; ohne: aus der Beschreibung gebaut."""
    p = anbindung.pruefen(besch, vertrauen=True)
    kopf = {"aktion": "(Beschreibung)", "art": "-", "stufe": "-", "ok": p.ok,
            "warum": "; ".join(p.fehler) or ("in Ordnung" + (f" ({len(p.warnungen)} Hinweise)" if p.warnungen else "")),
            "schritte": [{"schritt": "Hinweis", "ok": True, "text": w} for w in p.warnungen]}
    if not p.ok:
        return [kopf]
    quelle = quelle or quelle_aus(besch, sender=sender)
    fahrt = _Fahrt(besch, quelle, alles)
    raus = [kopf]
    for a in besch["aktionen"]:
        if nur and a["name"] not in nur:
            continue
        raus.append(fahrt.aktion(a))
    return raus


def gruen(zeilen: list) -> bool:
    return all(z["ok"] for z in zeilen)


def bericht(zeilen: list, ausfuehrlich: bool = False) -> str:
    """Der Bericht als Text — Alltagswörter, je Aktion eine Zeile."""
    out = []
    for z in zeilen:
        zeichen = "ok  " if z["ok"] else "FEHLER"
        out.append(f"{zeichen:6} {z['aktion']:<28} [{z['stufe']}] {z['warum']}")
        if ausfuehrlich or not z["ok"]:
            for s in z["schritte"]:
                out.append(f"         {'+' if s['ok'] else '-'} {s['schritt']}: {s['text']}")
    ok = sum(1 for z in zeilen if z["ok"])
    out.append(f"{ok} von {len(zeilen)} in Ordnung")
    return "\n".join(out)


def wsgi_sender(client):
    """Ein HTTP-Absender, der statt des Netzes einen WSGI-Test-Client (Flask
    `app.test_client()`) benutzt — für Tests und für „Probefahrt gegen den
    eigenen Kalender“ ohne laufenden Server. Passt zu HttpTransport(sender=…)."""
    def senden(methode, url, kopf, body, zeitlimit):
        pfad = url[url.index("/", url.index("//") + 2):]
        r = client.open(pfad, method=methode, data=body, headers=kopf)
        return r.status_code, r.get_data()
    return senden
