# core/kalender_ics.py
#
# Der .ics-Speicher des Kalenders: ein vdir-Ordner (eine Datei pro Termin,
# ein Unterordner pro Ebene) plus eine kleine Nebendaten-JSON für das, was
# kein Termin ist (Fahrzeiten, Puffer, Ebenen-Farben, Archiv).
#
# Bauplan und Begründungen: memory/werkzeuge/kalender_ics_bauplan.md
#
# Die Grundidee: die Kalender-Fassade (core/kalender.py) arbeitet weiter auf
# demselben Daten-Dict wie seit Mai 2026 — laden, ändern, speichern. Dieser
# Speicher übersetzt beim LADEN alle Dateien in genau dieses Dict und
# schreibt beim SPEICHERN nur die Stücke, die sich wirklich geändert haben.
# Dafür trägt jeder Eintrag im geladenen Dict ein internes Feld `_ics`
# (UID + Position), und das Dict selbst unter `_ics_geladen` die Prüfsumme
# jedes Stücks zum Ladezeitpunkt. Die Fassade entfernt `_ics` in allem, was
# sie nach außen gibt.
#
# Warum "nur Unterschiede schreiben" so wichtig ist:
#   * Ein Schreiben fasst nie den ganzen Kalender an. Ein Fehler beim Termin
#     am Dienstag kann den am Freitag nicht beschädigen.
#   * Der Sync (rsync, neueste DATEI gewinnt) gleicht pro Termin ab: ändert
#     der PC die Geige und der Laptop den Zahnarzt, überleben beide. Mit der
#     einen großen JSON gewann eine der beiden Änderungen, die andere war weg.
#   * vdirsyncer sieht nur echte Änderungen und schickt nur die zu Google.

import copy
import hashlib
import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import state
import kalender_ics_abbildung as abb
import kalender_sicherung as sich

NEBEN_FORMAT = 1

# Interne Schlüssel im Daten-Dict. Beginnen mit "_ics", damit die Fassade sie
# mit einer einzigen Regel herausfiltern kann.
FELD = "_ics"
GELADEN = "_ics_geladen"


def ohne_interna(obj):
    """Tiefe Kopie ohne die internen `_ics`-Felder — das, was nach außen
    geht (API, KI-Werkzeuge, Migration, Rückweg in die JSON)."""
    if isinstance(obj, dict):
        return {k: ohne_interna(v) for k, v in obj.items()
                if not (isinstance(k, str) and k.startswith(FELD))}
    if isinstance(obj, list):
        return [ohne_interna(v) for v in obj]
    return copy.deepcopy(obj)


def ordner_fuer(name: str) -> str:
    """Ordnername einer Ebene. Sprechende Namen bleiben (termine, routinen);
    alles mit Sonderzeichen bekommt einen stabilen Hash-Namen, damit kein
    Ebenen-Name je aus dem vdir hinaus zeigen kann."""
    import re
    if isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        return name
    return "ebene-" + hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:10]


def _signatur(layer, art, tag, daten, pausen) -> str:
    roh = json.dumps([layer, art, tag, ohne_interna(daten),
                      [[n, p] for n, p in pausen]],
                     sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()


def pause_gehoert(p, r) -> bool:
    """Gehört Pause p zu Routine r? Dieselbe Regel wie _pause_grund in
    kalender_konflikte.py: mit `routine_uid` über die Kennung (seit
    09.10.2026, überlebt Umbenennen), sonst über den gleichen Titel."""
    if not isinstance(p, dict) or not isinstance(r, dict):
        return False
    if p.get("routine_uid"):
        intern = r.get(FELD)
        uid = intern.get("uid") if isinstance(intern, dict) else r.get("uid")
        return bool(uid) and p["routine_uid"] == uid
    return "label" in r and p.get("label") == r.get("label")


def _pausen_fuer(r: dict, pausen: list) -> list:
    """[(nr, pause)] für eine Routine (Zuordnung: pause_gehoert)."""
    if not isinstance(r, dict) or "label" not in r:
        return []
    return [(i, p) for i, p in enumerate(pausen) if pause_gehoert(p, r)]


# Lese-Cache: das Parsen aller .ics kostet bei jedem Aufruf ein paar
# Millisekunden, und open_alarms ruft den Kalender dutzendfach. Gültig,
# solange sich an keiner Datei (Name, Größe, mtime) etwas geändert hat.
_cache: dict = {}
_cache_lock = threading.Lock()


def _kopie(obj):
    """Tiefe Kopie für JSON-artige Daten — gut dreimal so schnell wie
    copy.deepcopy, und der Kalender wird pro Alarm-Rechnung dutzendfach
    gelesen. Jeder Leser bekommt seine eigene Kopie, damit eine Änderung am
    geladenen Dict nie den Cache verändert."""
    if isinstance(obj, dict):
        return {k: _kopie(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_kopie(v) for v in obj]
    return obj


# Zweite Stufe: geparste Dateien einzeln, nach (Größe, mtime). Ohne sie
# las jede Änderung ALLE Dateien neu — mit Google im Kalender (500+ Dateien)
# 2 s, und die TUI lief nach dem Speichern in ihren Timeout (07.10.2026,
# „kurz freeze dann alles weg: kalender backend?"). So wird nur die
# geänderte Datei neu geparst.
_datei_cache: dict = {}


def cache_leeren() -> None:
    """Den Gesamt-Cache verwerfen. Der Datei-Cache bleibt: er prüft sich
    selbst (Größe + mtime je Datei) und ist nach dem Schreiben genau das,
    was das nächste Lesen schnell macht."""
    with _cache_lock:
        _cache.clear()


def _datei_gelesen(f: Path) -> list:
    st = f.stat()
    schluessel = str(f)
    with _cache_lock:
        t = _datei_cache.get(schluessel)
    if t and t[0] == (st.st_mtime_ns, st.st_size):
        return _kopie(t[1])
    gelesen = abb.datei_lesen(f.read_bytes())
    with _cache_lock:
        _datei_cache[schluessel] = ((st.st_mtime_ns, st.st_size), _kopie(gelesen))
    return gelesen


class IcsSpeicher:
    art = "ics"

    def __init__(self, vdir: Path, neben: Path, verlauf: Path,
                 snapshots: Path, loeschsperre: int = 5,
                 anker: date | None = None, spiegel=None,
                 ohne_layer=frozenset({"erlebt"})):
        self.vdir = Path(vdir)
        self.neben = Path(neben)
        self.verlauf = Path(verlauf)
        self.snapshots = Path(snapshots)
        self.loeschsperre = int(loeschsperre)
        # Technischer Start für neue Routinen ohne Anfang (siehe
        # kalender_ics_abbildung.routine_kalender). None = heute.
        self.anker = anker
        # Wird nach jedem erfolgreichen Schreiben gerufen (git-Spiegel).
        # Fehler darin dürfen das Schreiben nie kippen — fängt der Aufrufer.
        self.spiegel = spiegel
        # Ebenen, die es in .ics nicht mehr gibt: ihr Inhalt wandert ins
        # Archiv der Nebendaten (Sasha: "erlebt" fällt weg, aber verlustfrei).
        self.ohne_layer = frozenset(ohne_layer)
        self.sperrdatei = self.vdir / ".zentrale.lock"

    # ── Lesen ───────────────────────────────────────────────────────────

    def _neben_lesen(self) -> dict:
        if not self.neben.exists():
            return {}
        d = json.loads(self.neben.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}

    def _ordner(self) -> list[Path]:
        if not self.vdir.exists():
            return []
        return sorted(p for p in self.vdir.iterdir()
                      if p.is_dir() and not p.name.startswith("."))

    def _stand(self) -> tuple:
        """Fingerabdruck aller Dateien, die das Lesen beeinflussen."""
        teile = []
        for o in self._ordner():
            for f in os.scandir(o):
                if f.name.endswith(".ics") or f.name in ("displayname", "color"):
                    st = f.stat()
                    teile.append((o.name, f.name, st.st_mtime_ns, st.st_size))
        for p in (self.neben,):
            if p.exists():
                st = p.stat()
                teile.append(("", p.name, st.st_mtime_ns, st.st_size))
        g = self.verlauf / "grabsteine"
        if g.exists():
            for f in os.scandir(g):
                st = f.stat()
                teile.append(("grab", f.name, st.st_mtime_ns, st.st_size))
        return tuple(sorted(teile))

    def laden(self) -> dict | None:
        """Das Daten-Dict, wie kalender.py es kennt — oder None, wenn es noch
        gar keinen .ics-Kalender gibt (dann legt die Fassade die Default-
        Ebenen an)."""
        if not self.vdir.exists() and not self.neben.exists():
            return None
        data, _index, _geister = self._lesen()
        return data

    def _lesen(self):
        """-> (data, index{uid: {pfad, layer, anker}}, geister[pfad])"""
        schluessel = str(self.vdir.resolve())
        stand = self._stand()
        with _cache_lock:
            treffer = _cache.get(schluessel)
            if treffer and treffer[0] == stand:
                return _kopie(treffer[1]), dict(treffer[2]), list(treffer[3])
        ergebnis = self._lesen_ungecacht()
        with _cache_lock:
            _cache[schluessel] = (stand, _kopie(ergebnis[0]),
                                  dict(ergebnis[1]), list(ergebnis[2]))
        return ergebnis

    def _lesen_ungecacht(self):
        neben = self._neben_lesen()
        grab = sich.grabsteine_lesen(self.verlauf)
        layer_info = [l for l in (neben.get("layer") or []) if isinstance(l, dict)]
        ordner_zu_name = {l.get("ordner"): l.get("name") for l in layer_info}

        stuecke = []          # (layer, stueck)
        index = {}
        geister = []
        for o in self._ordner():
            name = ordner_zu_name.get(o.name) or o.name
            for f in sorted(o.glob("*.ics")):
                try:
                    gelesen = _datei_gelesen(f)
                except Exception as ex:
                    # Kaputte Datei: liegen lassen, nicht anzeigen, nie
                    # löschen (sie kommt nicht in den Index, also kann
                    # speichern sie auch nicht als "gelöscht" werten).
                    state.push_log(f"[calendar] {f.name} unlesbar, übersprungen: {ex}")
                    continue
                for st in gelesen:
                    uid = st["uid"]
                    tot = grab.get(uid)
                    if tot is not None and (st["geaendert"] is None or st["geaendert"] <= tot):
                        geister.append(f)          # gelöscht, vom Sync zurückgebracht
                        continue
                    if uid in index:
                        state.push_log(f"[calendar] UID {uid} doppelt ({f.name}), zweite ignoriert")
                        continue
                    stuecke.append((name, st))
                    index[uid] = {"pfad": f, "layer": name, "anker": st.get("anker")}

        for na in neben.get("nicht_abbildbar") or []:
            if isinstance(na, dict) and "layer" in na:
                stuecke.append((na["layer"], {"art": na.get("art"), "tag": na.get("tag"),
                                              "daten": copy.deepcopy(na.get("roh")),
                                              "pos": na.get("pos"), "uid": None,
                                              "roh": True}))

        # Ebenen: zuerst in der gespeicherten Reihenfolge, dann neue Ordner
        # (z. B. ein Kalender, den vdirsyncer von Google neu angelegt hat).
        namen = [l.get("name") for l in layer_info]
        for o in self._ordner():
            n = ordner_zu_name.get(o.name) or o.name
            if n not in namen:
                namen.append(n)
        for n, _st in stuecke:
            if n not in namen:
                namen.append(n)
        layer_roh = neben.get("layer_roh") or {}
        for n in layer_roh:
            if n not in namen:
                namen.append(n)

        layers = {}
        info_nach_name = {l.get("name"): l for l in layer_info}
        for n in namen:
            if n in layer_roh:
                layers[n] = copy.deepcopy(layer_roh[n])
                continue
            info = info_nach_name.get(n)
            if info:
                meta = copy.deepcopy(info.get("meta") or {})
                felder = info.get("felder") or list(meta) + ["entries", "routines"]
            else:
                meta = self._meta_aus_ordner(n)
                felder = list(meta) + ["entries", "routines"]
            lobj = {}
            for k in felder:
                if k == "entries":
                    lobj["entries"] = {}
                elif k == "routines":
                    lobj["routines"] = []
                elif k in meta:
                    lobj[k] = meta[k]
            for k, v in meta.items():
                lobj.setdefault(k, v)
            layers[n] = lobj

        def ordnung(item):
            st = item[1]
            p = st.get("pos")
            return (p is None, p if p is not None else 0,
                    str(st.get("tag") or st.get("anker") or ""), str(st.get("uid") or ""))

        alle_pausen = []
        for n, st in sorted(stuecke, key=ordnung):
            lobj = layers.get(n)
            if lobj is None:
                continue
            daten = st["daten"]
            if st.get("uid"):
                daten[FELD] = {"uid": st["uid"], "pos": st.get("pos")}
            elif isinstance(daten, dict) and st["art"] != "tag_roh":
                # Rohes Stück aus den Nebendaten: Position mitgeben, damit es
                # beim nächsten Speichern nicht nach hinten rutscht.
                daten[FELD] = {"pos": st.get("pos")}
            if st["art"] == "routine":
                if "routines" not in lobj:
                    lobj["routines"] = []
                lobj["routines"].append(daten)
                alle_pausen.extend(st.get("pausen") or [])
            elif st["art"] == "tag_roh":
                lobj.setdefault("entries", {})[st["tag"]] = daten
            else:
                lobj.setdefault("entries", {}).setdefault(st["tag"], []).append(daten)

        for eintrag in neben.get("pausen_ohne_routine") or []:
            if isinstance(eintrag, list) and len(eintrag) == 2:
                alle_pausen.append((eintrag[0], eintrag[1]))
        gesehen, pausen = set(), []
        for nr, p in sorted(alle_pausen, key=lambda np: (np[0], json.dumps(np[1], sort_keys=True, default=str))):
            k = (nr, json.dumps(p, sort_keys=True, default=str))
            if k not in gesehen:
                gesehen.add(k)
                pausen.append(p)

        oben = copy.deepcopy(neben.get("oben") or {"version": 1})
        reihe = list(neben.get("oben_reihenfolge") or ["version", "layers"])
        if "layers" not in reihe:
            reihe.insert(1, "layers")
        if pausen and "pausen" not in reihe:
            reihe.append("pausen")
        data = {}
        for k in reihe:
            if k == "layers":
                data["layers"] = layers
            elif k == "pausen":
                data["pausen"] = pausen
            elif k in oben:
                data[k] = oben[k]
        for k, v in oben.items():
            data.setdefault(k, v)

        # Prüfsummen zum Ladezeitpunkt — speichern erkennt daran, was sich
        # geändert hat und was gelöscht wurde.
        geladen = {}
        for n, lobj in layers.items():
            if n in layer_roh:
                continue
            for tag, liste in (lobj.get("entries") or {}).items():
                if not isinstance(liste, list):
                    continue
                for e in liste:
                    u = (e.get(FELD) or {}).get("uid") if isinstance(e, dict) else None
                    if u:
                        geladen[u] = _signatur(n, "termin", tag, e, [])
            for r in lobj.get("routines") or []:
                u = (r.get(FELD) or {}).get("uid") if isinstance(r, dict) else None
                if u:
                    geladen[u] = _signatur(n, "routine", None, r, _pausen_fuer(r, pausen))
        data[GELADEN] = geladen
        return data, index, geister

    def _meta_aus_ordner(self, name) -> dict:
        """Eine Ebene ohne Eintrag in den Nebendaten (von außen angelegt):
        Titel und Farbe aus den vdir-Metadateien, die vdirsyncer schreibt."""
        o = self.vdir / ordner_fuer(name)
        if not o.exists():
            o = self.vdir / str(name)
        meta = {"label": str(name), "color": "#999999", "default_visible": True}
        for datei, feld in (("displayname", "label"), ("color", "color")):
            p = o / datei
            if p.exists():
                try:
                    t = p.read_text(encoding="utf-8").strip()
                    if t:
                        meta[feld] = t
                except OSError:
                    pass
        return meta

    # ── Schreiben ───────────────────────────────────────────────────────

    def speichern(self, data: dict, erlaube_massenloeschung: bool = False,
                  grund: str = "") -> dict:
        """Schreibt die Unterschiede zwischen `data` und dem Stand auf Platte.

        -> {"neu": n, "geaendert": n, "geloescht": n, "neben": bool}
        Wirft KalenderGesperrt (Massenlöschung, Sperre) — dann ist NICHTS
        geschrieben."""
        with sich.dateisperre(self.sperrdatei):
            bericht = self._speichern_gesperrt(data, erlaube_massenloeschung)
        cache_leeren()
        if self.spiegel and any(bericht[k] for k in ("neu", "geaendert", "geloescht", "neben")):
            try:
                self.spiegel(grund or "Kalender geändert")
            except Exception as ex:
                state.push_log(f"[calendar] git-Spiegel fehlgeschlagen: {ex}")
        return bericht

    def _plan(self, data: dict):
        """Zerlegt `data` in Stücke: was als .ics geht, was in die
        Nebendaten muss, Ebenen-Metadaten, Archiv."""
        pausen = data.get("pausen") if isinstance(data.get("pausen"), list) else []
        max_pos = -1

        def pos_von(obj):
            if isinstance(obj, dict) and isinstance(obj.get(FELD), dict):
                p = obj[FELD].get("pos")
                return p if isinstance(p, int) else None
            return None

        layers = data.get("layers") if isinstance(data.get("layers"), dict) else {}
        for lobj in layers.values():
            if not isinstance(lobj, dict):
                continue
            ents = lobj.get("entries")
            if isinstance(ents, dict):
                for liste in ents.values():
                    if isinstance(liste, list):
                        for e in liste:
                            p = pos_von(e)
                            if p is not None:
                                max_pos = max(max_pos, p)
            routinen = lobj.get("routines")
            for r in routinen if isinstance(routinen, list) else []:
                p = pos_von(r)
                if p is not None:
                    max_pos = max(max_pos, p)

        naechste = [max_pos + 1]

        def pos_neu():
            p = naechste[0]
            naechste[0] += 1
            return p

        stuecke = []        # dicts: layer, art, tag, daten(obj), uid, pos
        roh = []            # nicht abbildbar (layer, art, tag, pos, roh)
        layer_info, layer_roh, archiv = [], {}, {}
        for name, lobj in layers.items():
            if name in self.ohne_layer:
                archiv[name] = ohne_interna(lobj)
                continue
            if (not isinstance(lobj, dict)
                    or not isinstance(lobj.get("entries", {}), dict)
                    or not isinstance(lobj.get("routines", []), list)):
                layer_roh[name] = ohne_interna(lobj)
                continue
            meta = {k: ohne_interna(v) for k, v in lobj.items()
                    if k not in ("entries", "routines")}
            layer_info.append({"name": name, "ordner": ordner_fuer(name),
                               "meta": meta, "felder": list(lobj.keys())})
            for tag, liste in (lobj.get("entries") or {}).items():
                if not isinstance(liste, list) or not liste:
                    # Ein leerer Tag oder Murks statt einer Liste: kein
                    # Termin, aber Teil der Datei — roh aufheben.
                    roh.append({"layer": name, "art": "tag_roh", "tag": tag,
                                "pos": pos_neu(), "roh": ohne_interna(liste)})
                    continue
                for e in liste:
                    if not isinstance(e, dict):
                        roh.append({"layer": name, "art": "termin", "tag": tag,
                                    "pos": pos_neu(), "roh": ohne_interna(e)})
                        continue
                    info = e.get(FELD) if isinstance(e.get(FELD), dict) else {}
                    pos = info.get("pos") if isinstance(info.get("pos"), int) else pos_neu()
                    stuecke.append({"layer": name, "art": "termin", "tag": tag,
                                    "obj": e, "uid": info.get("uid"), "pos": pos})
            for r in lobj.get("routines") or []:
                if not isinstance(r, dict):
                    roh.append({"layer": name, "art": "routine", "tag": None,
                                "pos": pos_neu(), "roh": ohne_interna(r)})
                    continue
                info = r.get(FELD) if isinstance(r.get(FELD), dict) else {}
                pos = info.get("pos") if isinstance(info.get("pos"), int) else pos_neu()
                stuecke.append({"layer": name, "art": "routine", "tag": None,
                                "obj": r, "uid": info.get("uid"), "pos": pos})
        return stuecke, roh, layer_info, layer_roh, archiv, pausen

    def _speichern_gesperrt(self, data, erlaube_massenloeschung):
        alt_data, index, geister = self._lesen_ungecacht_mit_cache()
        alt_neben = self._neben_lesen()
        geladen = data.get(GELADEN) if isinstance(data.get(GELADEN), dict) else {}

        stuecke, roh, layer_info, layer_roh, archiv, pausen = self._plan(data)

        # 1. Für jedes Stück entscheiden: unverändert / neu / geändert, und
        #    für neue+geänderte die .ics bauen (das ist auch die Probe, ob es
        #    überhaupt als .ics geht).
        schreiben = []          # (stueck, kalender)
        behalten = set()        # UIDs, die als Datei bleiben
        gemappte_routinen = []  # für die Zuordnung der Pausen
        for st in stuecke:
            obj, uid = st["obj"], st["uid"]
            p_liste = _pausen_fuer(obj, pausen) if st["art"] == "routine" else []
            sig = _signatur(st["layer"], st["art"], st["tag"], obj, p_liste)
            unveraendert = (uid is not None and geladen.get(uid) == sig
                            and uid in index and index[uid]["layer"] == st["layer"])
            if unveraendert:
                behalten.add(uid)
                if st["art"] == "routine":
                    gemappte_routinen.append(obj)
                continue
            if uid is not None and uid in geladen and uid not in index and geladen.get(uid) == sig:
                # Zwischen Laden und Speichern von außen gelöscht (vdirsyncer)
                # und hier nicht angefasst: die Löschung gilt, nicht
                # wiederbeleben.
                continue
            neu_uid = uid or abb.neue_uid()
            kern = ohne_interna(obj)
            try:
                if st["art"] == "routine":
                    anker = (index.get(uid, {}).get("anker") if uid else None) \
                        or self.anker or date.today()
                    kal = abb.routine_kalender(kern, neu_uid, pos=st["pos"],
                                               pausen=p_liste, anker=anker)
                    gemappte_routinen.append(obj)
                else:
                    kal = abb.termin_kalender(st["tag"], kern, neu_uid, pos=st["pos"])
            except abb.NichtAbbildbar as ex:
                state.push_log(f"[calendar] nicht als .ics abbildbar, roh in die "
                               f"Nebendaten: {ex}")
                roh.append({"layer": st["layer"], "art": st["art"], "tag": st["tag"],
                            "pos": st["pos"], "roh": kern})
                continue
            st["uid"] = neu_uid
            schreiben.append((st, kal))
            behalten.add(neu_uid)

        # Pausen ohne eine (als .ics geschriebene) Routine gleichen Namens
        # liegen in den Nebendaten — sonst gingen sie verloren.
        ohne = [[i, ohne_interna(p)] for i, p in enumerate(pausen)
                if not any(pause_gehoert(p, r)
                           for r in gemappte_routinen)]

        # 2. Löschungen: was beim Laden da war, jetzt fehlt und noch als
        #    Datei existiert. Vor JEDEM Schreiben prüfen — die Sperre soll
        #    alles oder nichts sein.
        weg = [u for u in geladen if u not in behalten and u in index]
        sich.loeschungen_pruefen(len(weg), self.loeschsperre,
                                 erlaubt=erlaube_massenloeschung)

        neben_neu = self._neben_bauen(alt_neben, data, layer_info, layer_roh,
                                      archiv, roh, ohne)
        neben_aendert = (json.dumps(neben_neu, sort_keys=True, default=str)
                         != json.dumps(alt_neben, sort_keys=True, default=str))

        bericht = {"neu": 0, "geaendert": 0, "geloescht": 0, "neben": neben_aendert,
                   "geister": len(geister)}
        if not (schreiben or weg or neben_aendert or geister):
            return bericht

        # 3. Erst der Tages-Snapshot (Stand VOR der ersten Änderung heute).
        try:
            self.snapshot()
        except Exception as ex:
            state.push_log(f"[calendar] Snapshot fehlgeschlagen: {ex}")

        jetzt = datetime.now(timezone.utc)
        for st, kal in schreiben:
            uid = st["uid"]
            ordner = self.vdir / ordner_fuer(st["layer"])
            alt = index.get(uid)
            ziel = alt["pfad"] if alt and alt["layer"] == st["layer"] else \
                ordner / f"{sich.sicherer_name(uid)}.ics"
            alt_bytes = None
            if alt and alt["pfad"].exists():
                alt_bytes = alt["pfad"].read_bytes()
                sich.verlauf_ablegen(self.verlauf, alt_bytes, alt["layer"], uid,
                                     "geaendert", jetzt=jetzt)
            inhalt = abb.zusammenfuehren(alt_bytes, kal, uid)
            sich.atomar_schreiben(ziel, inhalt)
            if alt and alt["pfad"] != ziel and alt["pfad"].exists():
                alt["pfad"].unlink()          # Ebene gewechselt
            sich.grabstein_entfernen(self.verlauf, uid)
            bericht["geaendert" if alt else "neu"] += 1
            # Damit ein zweites Speichern desselben Dicts nichts doppelt tut.
            st["obj"][FELD] = {"uid": uid, "pos": st["pos"]}

        for uid in weg:
            info = index[uid]
            if info["pfad"].exists():
                sich.verlauf_ablegen(self.verlauf, info["pfad"].read_bytes(),
                                     info["layer"], uid, "geloescht", jetzt=jetzt)
                sich.grabstein_setzen(self.verlauf, uid, info["layer"], jetzt=jetzt)
                self._entfernen(info["pfad"], uid)
                bericht["geloescht"] += 1

        for g in geister:
            if g.exists():
                sich.verlauf_ablegen(self.verlauf, g.read_bytes(), g.parent.name,
                                     g.stem, "geist", jetzt=jetzt)
                g.unlink()

        for info in layer_info:
            self._ordner_metadaten(info)
        if neben_aendert:
            if self.neben.exists():
                sich.verlauf_ablegen(self.verlauf, self.neben.read_bytes(), "_neben",
                                     "neben", "geaendert", endung=".json", jetzt=jetzt)
            sich.atomar_schreiben(self.neben, json.dumps(neben_neu, ensure_ascii=False, indent=1))

        # Neue Prüfsummen ins Dict, damit es sich wie frisch geladen verhält.
        neu_geladen = {}
        for st in stuecke:
            if st["uid"] and st["uid"] in behalten:
                p_liste = _pausen_fuer(st["obj"], pausen) if st["art"] == "routine" else []
                neu_geladen[st["uid"]] = _signatur(st["layer"], st["art"], st["tag"],
                                                   st["obj"], p_liste)
        data[GELADEN] = neu_geladen
        return bericht

    def _lesen_ungecacht_mit_cache(self):
        # Unter der Sperre IMMER frisch lesen: zwischen dem Laden durch die
        # Fassade und jetzt kann vdirsyncer Dateien geändert haben.
        cache_leeren()
        return self._lesen()

    def _entfernen(self, pfad: Path, uid: str) -> None:
        """Eine Datei löschen — aber nur die Komponenten dieser UID. Lagen in
        derselben Datei Ereignisse anderer UIDs (von außen so angelegt),
        bleiben sie stehen."""
        try:
            from icalendar import Calendar
            kal = Calendar.from_ical(pfad.read_bytes())
            andere = [k for k in kal.subcomponents
                      if k.name == "VEVENT" and str(k.get("UID") or "") != uid]
        except Exception:
            andere = []
        if not andere:
            pfad.unlink()
            return
        rest = Calendar()
        for name, wert in kal.property_items(recursive=False):
            if name not in ("BEGIN", "END"):
                rest.add(name, wert)
        for k in kal.subcomponents:
            if not (k.name == "VEVENT" and str(k.get("UID") or "") == uid):
                rest.add_component(k)
        sich.atomar_schreiben(pfad, rest.to_ical())

    def _ordner_metadaten(self, info: dict) -> None:
        """Ordner der Ebene anlegen und `displayname`/`color` schreiben — die
        vdir-Metadaten, die vdirsyncer (metasync) mit dem Server abgleicht."""
        o = self.vdir / info["ordner"]
        o.mkdir(parents=True, exist_ok=True)
        meta = info.get("meta") or {}
        for datei, feld in (("displayname", "label"), ("color", "color")):
            wert = meta.get(feld)
            if not isinstance(wert, str) or not wert:
                continue
            p = o / datei
            try:
                if p.exists() and p.read_text(encoding="utf-8").strip() == wert:
                    continue
            except OSError:
                pass
            sich.atomar_schreiben(p, wert + "\n")

    def _neben_bauen(self, alt, data, layer_info, layer_roh, archiv, roh, ohne):
        # Was die Migration hinterlegt (Marker, alte Ebenen-Reihenfolge für den
        # Rückweg), bleibt bei jedem Speichern stehen.
        neu = {k: v for k, v in alt.items()
               if k.startswith("migriert") or k.startswith("zurueck")}
        neu["format"] = NEBEN_FORMAT
        neu["oben"] = {k: ohne_interna(v) for k, v in data.items()
                       if not k.startswith(FELD) and k not in ("layers", "pausen")}
        neu["oben_reihenfolge"] = [k for k in data.keys() if not k.startswith(FELD)]
        neu["layer"] = layer_info
        if layer_roh:
            neu["layer_roh"] = layer_roh
        if ohne:
            neu["pausen_ohne_routine"] = ohne
        if roh:
            neu["nicht_abbildbar"] = sorted(roh, key=lambda r: r["pos"])
        arch = dict(alt.get("archiv") or {})
        arch.update(archiv)          # nie etwas aus dem Archiv entfernen
        if arch:
            neu["archiv"] = arch
        return neu

    # ── Sicherung ───────────────────────────────────────────────────────

    def snapshot(self, heute: date | None = None):
        """Tages-Snapshot von vdir + Nebendaten, danach alte wegrotieren.
        Ein noch leerer Kalender (erste Migration) braucht keinen."""
        if not self.neben.exists() and not any(self.vdir.rglob("*.ics")):
            return None
        p = sich.snapshot_machen(self.snapshots, self.vdir.parent,
                                 [self.vdir, self.neben], heute=heute)
        if p:
            sich.snapshots_rotieren(self.snapshots, heute=heute)
        return p

    def aufraeumen(self) -> int:
        """Geister (vom Sync zurückgebrachte, längst gelöschte Dateien)
        wegräumen — vor jedem vdirsyncer-Lauf, sonst lädt er sie wieder zu
        Google hoch. -> Anzahl."""
        with sich.dateisperre(self.sperrdatei):
            cache_leeren()
            _data, _index, geister = self._lesen()
            for g in geister:
                if g.exists():
                    sich.verlauf_ablegen(self.verlauf, g.read_bytes(), g.parent.name,
                                         g.stem, "geist")
                    g.unlink()
        cache_leeren()
        return len(geister)

    def wiederherstellen(self, verlauf_datei: Path) -> str:
        """Eine Fassung aus dem Verlauf zurück in den Kalender legen.

        Die jetzige Fassung (falls es eine gibt) wandert vorher selbst in den
        Verlauf — Wiederherstellen ist also wieder rückgängig zu machen.
        -> die UID."""
        verlauf_datei = Path(verlauf_datei)
        inhalt = verlauf_datei.read_bytes()
        stuecke = abb.datei_lesen(inhalt)
        if len(stuecke) != 1:
            raise sich.KalenderGesperrt(
                f"{verlauf_datei.name}: erwartet genau einen Termin, gefunden {len(stuecke)}")
        uid = stuecke[0]["uid"]
        teile = verlauf_datei.stem.split("~")
        ordner_name = teile[2] if len(teile) == 5 else "termine"
        with sich.dateisperre(self.sperrdatei):
            cache_leeren()
            _data, index, _g = self._lesen()
            if uid in index and index[uid]["pfad"].exists():
                ziel = index[uid]["pfad"]
                sich.verlauf_ablegen(self.verlauf, ziel.read_bytes(),
                                     index[uid]["layer"], uid, "vor-wiederherstellen")
            else:
                ziel = self.vdir / ordner_name / f"{sich.sicherer_name(uid)}.ics"
            # LAST-MODIFIED auf jetzt, sonst hielte ein Grabstein die
            # wiederhergestellte Datei gleich wieder für einen Geist.
            from icalendar import Calendar
            kal = Calendar.from_ical(inhalt)
            jetzt = datetime.now(timezone.utc).replace(microsecond=0)
            for ev in kal.walk("VEVENT"):
                if "LAST-MODIFIED" in ev:
                    del ev["LAST-MODIFIED"]
                ev.add("LAST-MODIFIED", jetzt)
            sich.atomar_schreiben(ziel, kal.to_ical())
            sich.grabstein_entfernen(self.verlauf, uid)
        cache_leeren()
        return uid
