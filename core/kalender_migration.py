# core/kalender_migration.py
#
# Der Umzug des Kalenders von data/ai_calendar.json in den .ics-Ordner —
# prüfen, ausführen, und der Rückweg.
#
# Sasha, 2026-10-06: "bisherige daten übertragen ohne verluste". Deshalb
# steht hier vor allem eine PRÜFUNG, die streng genug ist, um ihr zu glauben:
#   1. Die alte JSON wird in einen Wegwerf-Ordner als .ics geschrieben und
#      durch den neuen Speicher zurückgelesen.
#   2. Das zurückgelesene Daten-Dict muss dem alten exakt gleichen (ohne die
#      Ebene `erlebt`, die mit Sasha entschieden ins Archiv wandert — dort
#      muss sie ihrerseits exakt stehen).
#   3. Alle öffentlichen Lesefunktionen der Fassade liefern über beide
#      Speicher dieselben Ergebnisse: entries_in_range über ±2 Jahre (und
#      über die ganze Spanne der Daten), Wochen- und Monatsansichten,
#      read_calendar-Text, Imprint, nächster Termin, offene Alarme,
#      Konflikt-Vorschau, Routinen-Suche.
#   4. Feld-Inventar: jedes einzelne Feld der alten Datei taucht im neuen
#      Bestand wieder auf, und es wird gezählt, WOHIN es ging.
# Eine einzige Abweichung = kein Umzug.
#
# Bauplan: memory/werkzeuge/kalender_ics_bauplan.md

import copy
import json
import shutil
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from icalendar import Calendar

import kalender
import kalender_ics
import kalender_ics_abbildung as abb
import kalender_sicherung as sich
import kalender_speicher
from kalender_ics import IcsSpeicher, ohne_interna
from kalender_json import JsonSpeicher

WEGGEFALLEN = ("erlebt",)


class MigrationAbgebrochen(Exception):
    pass


# ── Hilfen ──────────────────────────────────────────────────────────────

def erster_tag(alt: dict) -> date:
    """Der früheste Tag, an dem die alte Datei etwas weiß (ohne `erlebt`).
    Ab hier zeigt Google die Routinen, die im alten Modell keinen Anfang
    hatten (ZENTRALE rechnet sie weiter "seit immer")."""
    tage = []
    for name, lobj in (alt.get("layers") or {}).items():
        if name in WEGGEFALLEN or not isinstance(lobj, dict):
            continue
        for k in (lobj.get("entries") or {}) if isinstance(lobj.get("entries"), dict) else {}:
            try:
                tage.append(date.fromisoformat(k))
            except (TypeError, ValueError):
                pass
    for p in alt.get("pausen") or []:
        try:
            tage.append(date.fromisoformat(p.get("von")))
        except Exception:
            pass
    return min(tage) if tage else date.today()


def erwartet_aus(alt: dict) -> dict:
    """Was der .ics-Speicher zurückgeben MUSS: das alte Dict ohne die
    weggefallenen Ebenen."""
    e = copy.deepcopy(alt)
    for n in WEGGEFALLEN:
        (e.get("layers") or {}).pop(n, None)
    return e


def _blaetter(obj, pfad=()):
    """Alle Blätter eines JSON-Baums als (pfad, wert-als-json)."""
    if isinstance(obj, dict):
        if not obj:
            yield pfad, "{}"
        for k, v in obj.items():
            yield from _blaetter(v, pfad + (str(k),))
    elif isinstance(obj, list):
        if not obj:
            yield pfad, "[]"
        for i, v in enumerate(obj):
            yield from _blaetter(v, pfad + (i,))
    else:
        yield pfad, json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _unterschiede(a, b, pfad="", raus=None, grenze=30):
    """Wo unterscheiden sich zwei JSON-Bäume (auch in der Listen-Reihenfolge)?"""
    raus = [] if raus is None else raus
    if len(raus) >= grenze:
        return raus
    if type(a) is not type(b):
        raus.append(f"{pfad or '/'}: {a!r:.80} ≠ {b!r:.80}")
    elif isinstance(a, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if k not in a:
                raus.append(f"{pfad}/{k}: fehlt im alten, neu {b[k]!r:.80}")
            elif k not in b:
                raus.append(f"{pfad}/{k}: FEHLT im neuen (alt {a[k]!r:.80})")
            else:
                _unterschiede(a[k], b[k], f"{pfad}/{k}", raus, grenze)
    elif isinstance(a, list):
        if len(a) != len(b):
            raus.append(f"{pfad}: Länge {len(a)} ≠ {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _unterschiede(x, y, f"{pfad}[{i}]", raus, grenze)
    elif a != b:
        raus.append(f"{pfad}: {a!r:.80} ≠ {b!r:.80}")
    return raus


def _reihenfolge(erwartet: dict, neu: dict) -> list:
    """Die Reihenfolge der Schlüssel, die für die Ausgabe zählt: Ebenen und
    die Tage innerhalb jeder Ebene. Ein Dict-Vergleich übersieht sie, aber
    sie bestimmt, in welcher Folge gleichzeitige Termine erscheinen — und
    damit den Wortlaut der Alarme."""
    raus = []
    if list(erwartet.get("layers") or {}) != list(neu.get("layers") or {}):
        raus.append(f"Reihenfolge der Ebenen: {list(erwartet.get('layers') or {})} ≠ "
                    f"{list(neu.get('layers') or {})}")
    for n, lobj in (erwartet.get("layers") or {}).items():
        a = list((lobj.get("entries") or {}) if isinstance(lobj, dict) else {})
        b = list(((neu.get("layers") or {}).get(n) or {}).get("entries") or {})
        if a != b:
            raus.append(f"Reihenfolge der Tage in {n}: weicht ab")
    return raus


def _ics_speicher(ordner: Path, anker: date) -> IcsSpeicher:
    return IcsSpeicher(ordner / "kalender", ordner / "kalender_neben.json",
                       ordner / "kalender_verlauf", ordner / "kalender_snapshots",
                       loeschsperre=kalender_speicher.loeschsperre(), anker=anker,
                       spiegel=None)


# ── Öffentliche Funktionen über beide Speicher vergleichen ──────────────

def _aufrufe(alt: dict, heute: date, jahre: int):
    """Die Liste der Vergleichs-Aufrufe: (name, funktion). Jede Funktion ruft
    die Fassade und liefert ein JSON-fähiges Ergebnis."""
    von = heute - timedelta(days=365 * jahre)
    bis = heute + timedelta(days=365 * jahre)
    # Zusätzlich die ganze Spanne, über die die Daten überhaupt reichen.
    tage = []
    for lobj in (alt.get("layers") or {}).values():
        if isinstance(lobj, dict) and isinstance(lobj.get("entries"), dict):
            for k in lobj["entries"]:
                try:
                    tage.append(date.fromisoformat(k))
                except (TypeError, ValueError):
                    pass
    d_min = min(tage + [von]) - timedelta(days=31)
    d_max = max(tage + [bis]) + timedelta(days=400)

    layer_namen = [n for n in (alt.get("layers") or {}) if n not in WEGGEFALLEN]
    routinen = sorted({r.get("label") for lobj in (alt.get("layers") or {}).values()
                       if isinstance(lobj, dict)
                       for r in (lobj.get("routines") or []) if isinstance(r, dict)
                       and isinstance(r.get("label"), str)})
    labels = sorted({e.get("label") for lobj in (alt.get("layers") or {}).values()
                     if isinstance(lobj, dict) and isinstance(lobj.get("entries"), dict)
                     for liste in lobj["entries"].values() if isinstance(liste, list)
                     for e in liste if isinstance(e, dict) and isinstance(e.get("label"), str)})

    k = kalender
    yield ("entries_in_range ±%d Jahre" % jahre, lambda: k.entries_in_range(von, bis))
    yield ("entries_in_range ganze Datenspanne", lambda: k.entries_in_range(d_min, d_max))
    for n in layer_namen:
        yield (f"entries_in_range Ebene {n}", lambda n=n: k.entries_in_range(von, bis, layers=[n]))
    mo = von - timedelta(days=von.weekday())
    while mo <= bis:
        yield (f"week_view {mo}", lambda mo=mo: k.week_view(mo))
        mo += timedelta(days=7)
    m = von.replace(day=1)
    while m <= bis:
        yield (f"month_view {m:%Y-%m}", lambda m=m: k.month_view(m))
        yield (f"month_view alle Ebenen {m:%Y-%m}",
               lambda m=m: k.month_view(m, only_default_visible=False))
        ende = k._month_last_day(m)
        yield (f"read_calendar {m:%Y-%m}", lambda m=m, e=ende: k.render_range_for_tool(m, e))
        m = ende + timedelta(days=1)
    for lab in labels + routinen:
        yield (f"read_calendar suche {lab!r}",
               lambda lab=lab: k.render_range_for_tool(von, bis, suche=lab))
    for lab in routinen:
        yield (f"routine_finden {lab!r}", lambda lab=lab: k.routine_finden(lab))
    for h in (0, 30, 90, 400):
        yield (f"open_alarms {h} Tage", lambda h=h: k.open_alarms(h))
    for t in range(0, 8):
        yield (f"imprint {t} Tage", lambda t=t: k.imprint_for_prompt(t))
    for d in range(-7, 31):
        for uhr in (0, 8, 12, 17, 18, 21, 23):
            jetzt = datetime.combine(heute + timedelta(days=d), time(uhr, 0))
            yield (f"naechster_termin {jetzt:%Y-%m-%d %H:%M}",
                   lambda j=jetzt: k.naechster_termin(j))
    for d in range(-60, 121):
        tag = (heute + timedelta(days=d)).isoformat()
        yield (f"conflicts_for_proposed {tag}",
               lambda tag=tag: k.conflicts_for_proposed("termine", tag, "Prüftermin", "18:00"))
    yield ("_away_blocks", lambda: [{**b, "von": str(b["von"]), "bis": str(b["bis"])}
                                    for b in k._away_blocks(d_min, d_max)])
    yield ("_load_config", lambda: list(k._load_config()))


def funktionen_vergleichen(sp_a, sp_b, alt: dict, heute: date | None = None,
                           jahre: int = 2) -> tuple[int, list]:
    """Ruft alle Vergleichs-Aufrufe gegen beide Speicher. -> (anzahl, abweichungen)"""
    heute = heute or date.today()
    abweichungen, n = [], 0
    for name, f in _aufrufe(alt, heute, jahre):
        with kalender.mit_speicher(sp_a):
            a = _sicher(f)
        with kalender.mit_speicher(sp_b):
            b = _sicher(f)
        n += 1
        a, b = _ohne_kennung(a), _ohne_kennung(b)
        if json.dumps(a, sort_keys=True, ensure_ascii=False, default=str) != \
                json.dumps(b, sort_keys=True, ensure_ascii=False, default=str):
            abweichungen.append(f"{name}: alt≠neu " +
                                "; ".join(_unterschiede(a, b, grenze=3)))
    return n, abweichungen


def _ohne_kennung(obj):
    """Die Kennung (seit 09.10.2026, core/kalender_kennung.py) entsteht in den
    beiden Speichern bewusst verschieden — .ics hat seine UID, die JSON
    bekommt erst beim ersten Zugriff eine. Für den Vergleich zählt sie nicht."""
    if isinstance(obj, dict):
        return {k: _ohne_kennung(v) for k, v in obj.items() if k != "kennung"}
    if isinstance(obj, list):
        return [_ohne_kennung(v) for v in obj]
    return obj


def _sicher(f):
    try:
        return {"ok": f()}
    except Exception as ex:          # auch ein Fehler muss auf beiden Seiten gleich sein
        return {"fehler": f"{type(ex).__name__}: {ex}"}


# ── Feld-Inventar ───────────────────────────────────────────────────────

_ZIEL_PROPERTY = {
    "label": "SUMMARY", "ort": "LOCATION", "time": "DTSTART", "ende": "DTEND",
    "bis": "DTEND / RRULE COUNT", "times": "RECURRENCE-ID-Abweichungen",
    "enden": "RECURRENCE-ID-Abweichungen", "rrule": "RRULE",
    "aus": "EXDATE + X-ZENTRALE-AUS", "absage_noetig": "X-ZENTRALE-ABSAGE-NOETIG",
    "seit": "DTSTART", "abweichungen": "RECURRENCE-ID",
}


def feld_inventar(alt: dict, sp: IcsSpeicher) -> dict:
    """Wohin ist jedes Feld gegangen? Und ist jedes Blatt wieder da?

    -> {"wohin": {feld: {ziel: anzahl}}, "fehlend": [pfad, ...],
        "erlebt_im_archiv": bool}"""
    neben = json.loads(sp.neben.read_text(encoding="utf-8")) if sp.neben.exists() else {}
    neu = ohne_interna(sp.laden() or {})
    erwartet = erwartet_aus(alt)

    # 1. Gegenprobe Blatt für Blatt (zusätzlich zum Dict-Vergleich, weil
    #    sie benennt, WAS fehlt).
    neu_blaetter = set(_blaetter(neu))
    fehlend = [p for p, w in _blaetter(erwartet) if (p, w) not in neu_blaetter]
    archiv = neben.get("archiv") or {}
    erlebt_ok = all(archiv.get(n) == alt["layers"][n]
                    for n in WEGGEFALLEN if n in (alt.get("layers") or {}))

    # 2. Wohin: Extras und Rohes aus den Dateien selbst ablesen.
    wohin: dict = {}

    def zaehle(feld, ziel):
        wohin.setdefault(feld, {}).setdefault(ziel, 0)
        wohin[feld][ziel] += 1

    for f in sp.vdir.rglob("*.ics"):
        kal = Calendar.from_ical(f.read_bytes())
        for st in abb.lesen(kal):
            master = next(e for e in kal.walk("VEVENT")
                          if str(e.get("UID")) == st["uid"] and e.get("RECURRENCE-ID") is None)
            extras = abb._xdekodieren(master.get(abb.X_EXTRAS)) or {}
            roh_rrule = master.get(abb.X_RRULE_ROH) is not None
            zeit_roh = abb._xdekodieren(master.get(abb.X_ZEIT_ROH)) or {}
            zeit_roh_felder = {str(k).partition("/")[0] for k in zeit_roh}
            for feld, wert in st["daten"].items():
                if feld in ("times", "enden", "abweichungen") and isinstance(extras.get(feld), dict):
                    teil_extra = len(extras[feld])
                    teil_prop = len(wert) - teil_extra if isinstance(wert, dict) else 0
                    if teil_prop:
                        zaehle(feld, _ZIEL_PROPERTY[feld])
                    if teil_extra or (isinstance(wert, dict) and not wert):
                        zaehle(feld, "X-ZENTRALE-EXTRAS")
                elif feld in extras:
                    zaehle(feld, "X-ZENTRALE-EXTRAS")
                elif feld == "rrule" and roh_rrule:
                    zaehle(feld, "RRULE + X-ZENTRALE-RRULE-ROH")
                elif feld in zeit_roh_felder:
                    zaehle(feld, _ZIEL_PROPERTY.get(feld, "?") + " + X-ZENTRALE-ZEIT-ROH (Originaltext)")
                else:
                    zaehle(feld, _ZIEL_PROPERTY.get(feld, "?"))
            for _nr, _p in st["pausen"]:
                zaehle("pausen[] (an Routine)", "EXDATE + X-ZENTRALE-PAUSE")
    for _ in neben.get("pausen_ohne_routine") or []:
        zaehle("pausen[] (ohne Routine)", "Nebendaten pausen_ohne_routine")
    for na in neben.get("nicht_abbildbar") or []:
        zaehle(f"{na.get('art')} (nicht abbildbar)", "Nebendaten nicht_abbildbar")
    for k in (neben.get("oben") or {}):
        zaehle(k, "Nebendaten oben")
    for li in neben.get("layer") or []:
        for k in (li.get("meta") or {}):
            zaehle(f"layer.{k}", "Nebendaten layer (+ displayname/color im vdir)")
    for n in archiv:
        zaehle(f"Ebene {n}", "Nebendaten archiv (unverändert)")
    return {"wohin": wohin, "fehlend": fehlend, "erlebt_im_archiv": erlebt_ok}


# ── Prüfen ──────────────────────────────────────────────────────────────

def zahlen(alt: dict) -> dict:
    z = {"ebenen": 0, "termine": 0, "spannen": 0, "spannen_mit_zeiten": 0,
         "routinen": 0, "pausen": len(alt.get("pausen") or []), "erlebt": 0}
    for name, lobj in (alt.get("layers") or {}).items():
        if not isinstance(lobj, dict):
            continue
        z["ebenen"] += 1
        anzahl = sum(len(l) for l in (lobj.get("entries") or {}).values() if isinstance(l, list))
        if name in WEGGEFALLEN:
            z["erlebt"] += anzahl
            continue
        for liste in (lobj.get("entries") or {}).values():
            for e in liste if isinstance(liste, list) else []:
                if isinstance(e, dict) and "bis" in e:
                    z["spannen"] += 1
                    if e.get("times"):
                        z["spannen_mit_zeiten"] += 1
                else:
                    z["termine"] += 1
        z["routinen"] += len(lobj.get("routines") or [])
    return z


def pruefen(json_pfad: Path, arbeits_dir: Path | None = None,
            heute: date | None = None, jahre: int = 2) -> dict:
    """Prüft den Umzug, ohne irgendetwas an den echten Daten zu ändern.

    -> Bericht {gleich, zahlen, dateien, abweichungen, aufrufe, inventar,
                nicht_abbildbar, arbeits_dir}"""
    json_pfad = Path(json_pfad)
    alt = json.loads(json_pfad.read_text(encoding="utf-8"))
    eigener_ordner = arbeits_dir is None
    arbeits = Path(arbeits_dir or tempfile.mkdtemp(prefix="kalender_pruefung_"))
    try:
        anker = erster_tag(alt)
        sp_ics = _ics_speicher(arbeits / "ics", anker)
        sp_ics.speichern(copy.deepcopy(alt), erlaube_massenloeschung=True,
                         grund="Prüfung")
        kalender_ics.cache_leeren()
        neu = ohne_interna(sp_ics.laden() or {})
        erwartet = erwartet_aus(alt)
        abweichungen = [f"Daten-Dict: {u}" for u in _unterschiede(erwartet, neu)]
        abweichungen += _reihenfolge(erwartet, neu)

        # Vergleichsbasis für die Funktionen: die alte JSON ohne `erlebt`
        # (alle Ebenen) und die alte JSON vollständig (nur sichtbare Ebenen
        # — dort darf `erlebt` ohnehin nie auftauchen).
        (arbeits / "json").mkdir(parents=True, exist_ok=True)
        sp_json = JsonSpeicher(arbeits / "json" / "ai_calendar.json")
        sp_json.speichern(erwartet)
        n_aufrufe, abw_f = funktionen_vergleichen(sp_json, sp_ics, alt, heute, jahre)
        abweichungen += abw_f

        (arbeits / "json_voll").mkdir(parents=True, exist_ok=True)
        sp_voll = JsonSpeicher(arbeits / "json_voll" / "ai_calendar.json")
        sp_voll.speichern(alt)
        heute_ = heute or date.today()
        for name, f in (("imprint (alte Datei vollständig)", lambda: kalender.imprint_for_prompt()),
                        ("week_view heute (alte Datei vollständig)", lambda: kalender.week_view(heute_)),
                        ("month_view heute (alte Datei vollständig)", lambda: kalender.month_view(heute_))):
            with kalender.mit_speicher(sp_voll):
                a = _sicher(f)
            with kalender.mit_speicher(sp_ics):
                b = _sicher(f)
            n_aufrufe += 1
            if _ohne_kennung(a) != _ohne_kennung(b):
                abweichungen.append(f"{name}: alt≠neu")

        inventar = feld_inventar(alt, sp_ics)
        for p in inventar["fehlend"]:
            abweichungen.append(f"Feld-Inventar: fehlt {'/'.join(map(str, p))}")
        if not inventar["erlebt_im_archiv"]:
            abweichungen.append("Feld-Inventar: Ebene erlebt nicht exakt im Archiv")

        neben = json.loads(sp_ics.neben.read_text(encoding="utf-8"))
        return {
            "gleich": not abweichungen,
            "zahlen": zahlen(alt),
            "dateien": len(list(sp_ics.vdir.rglob("*.ics"))),
            "abweichungen": abweichungen,
            "aufrufe": n_aufrufe,
            "inventar": inventar,
            "nicht_abbildbar": len(neben.get("nicht_abbildbar") or []),
            "anker": anker.isoformat(),
            "arbeits_dir": str(arbeits),
        }
    finally:
        kalender_ics.cache_leeren()
        if eigener_ordner:
            shutil.rmtree(arbeits, ignore_errors=True)


# ── Ausführen ───────────────────────────────────────────────────────────

def _einstellung_setzen(wert: str) -> None:
    import ai_config
    ai_config.set_override("kalender_speicher", wert, persist=True)


def ausfuehren(json_pfad: Path, heute: date | None = None,
               einstellung_setzen=_einstellung_setzen) -> dict:
    """Der echte Umzug — nur nach bestandener Prüfung.

    Reihenfolge mit Absicht:
      1. prüfen (Wegwerf-Ordner) — Abweichung = Abbruch, nichts passiert;
      2. Ziel muss leer sein (kein halber alter Umzug wird überschrieben);
      3. vdir + Nebendaten schreiben, sofort zurücklesen und vergleichen;
      4. Marker `migriert_am` in die Nebendaten — ab jetzt verweigert ein
         Knoten, der noch auf json steht, das Schreiben;
      5. Einstellung kalender_speicher=ics;
      6. alte JSON umbenennen (nie löschen).
    """
    json_pfad = Path(json_pfad)
    p = kalender_speicher.pfade(json_pfad)
    if not json_pfad.exists():
        raise MigrationAbgebrochen(f"{json_pfad} gibt es nicht")
    if p["neben"].exists() or (p["vdir"].exists() and any(p["vdir"].iterdir())):
        raise MigrationAbgebrochen(
            f"Ziel nicht leer ({p['vdir']} / {p['neben'].name}) — da liegt schon "
            f"ein .ics-Kalender. Nichts geändert.")
    bericht = pruefen(json_pfad, heute=heute)
    if not bericht["gleich"]:
        raise MigrationAbgebrochen("Prüfung nicht bestanden:\n  " +
                                   "\n  ".join(bericht["abweichungen"][:30]))

    alt = json.loads(json_pfad.read_text(encoding="utf-8"))
    anker = erster_tag(alt)
    sp = IcsSpeicher(p["vdir"], p["neben"], p["verlauf"], p["snapshots"],
                     loeschsperre=kalender_speicher.loeschsperre(), anker=anker)
    sp.speichern(copy.deepcopy(alt), erlaube_massenloeschung=True, grund="Migration")
    kalender_ics.cache_leeren()
    zurueck = ohne_interna(sp.laden() or {})
    unterschied = _unterschiede(erwartet_aus(alt), zurueck) + _reihenfolge(erwartet_aus(alt), zurueck)
    if unterschied:
        raise MigrationAbgebrochen(
            "Nach dem Schreiben weicht der echte .ics-Ordner ab (die alte JSON "
            "ist unverändert, Einstellung nicht umgestellt):\n  " + "\n  ".join(unterschied))

    neben = json.loads(p["neben"].read_text(encoding="utf-8"))
    neben["migriert_am"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    neben["migriert_aus"] = json_pfad.name
    neben["migriert_von"] = sich.knoten()
    neben["migriert_layer_reihenfolge"] = list((alt.get("layers") or {}).keys())
    sich.atomar_schreiben(p["neben"], json.dumps(neben, ensure_ascii=False, indent=1))

    einstellung_setzen("ics")

    ziel = json_pfad.with_name(f"{json_pfad.name}.vor-ics-{(heute or date.today()).isoformat()}")
    n = 2
    while ziel.exists():
        ziel = json_pfad.with_name(f"{json_pfad.name}.vor-ics-{(heute or date.today()).isoformat()}-{n}")
        n += 1
    json_pfad.rename(ziel)
    kalender_ics.cache_leeren()

    spiegel = kalender_speicher.git_spiegel_pfad()
    if spiegel is not None:
        import kalender_spiegel
        kalender_spiegel.spiegeln({"kalender": p["vdir"], "kalender_neben.json": p["neben"]},
                                  spiegel, "Migration aus ai_calendar.json", warten=True)
    bericht["umbenannt"] = str(ziel)
    return bericht


def zurueck(json_pfad: Path, einstellung_setzen=_einstellung_setzen) -> dict:
    """Der Rückweg: aus dem .ics-Ordner wieder eine ai_calendar.json.

    Holt die Ebene `erlebt` aus dem Archiv an ihren alten Platz zurück, hebt
    die Rückfall-Sperre auf (Marker raus) und stellt auf json. Der vdir-Ordner
    bleibt liegen. Verweigert, wenn es die JSON schon gibt."""
    json_pfad = Path(json_pfad)
    if json_pfad.exists():
        raise MigrationAbgebrochen(f"{json_pfad} gibt es schon — nichts überschrieben.")
    p = kalender_speicher.pfade(json_pfad)
    sp = IcsSpeicher(p["vdir"], p["neben"], p["verlauf"], p["snapshots"])
    data = sp.laden()
    if data is None:
        raise MigrationAbgebrochen("kein .ics-Kalender gefunden")
    data = ohne_interna(data)
    neben = json.loads(p["neben"].read_text(encoding="utf-8")) if p["neben"].exists() else {}
    archiv = neben.get("archiv") or {}
    reihe = neben.get("migriert_layer_reihenfolge") or []
    layers = data.get("layers") or {}
    neu_layers = {}
    for n in reihe:
        if n in layers:
            neu_layers[n] = layers[n]
        elif n in archiv:
            neu_layers[n] = copy.deepcopy(archiv[n])
    for n, v in layers.items():
        neu_layers.setdefault(n, v)
    for n, v in archiv.items():
        neu_layers.setdefault(n, copy.deepcopy(v))
    data["layers"] = neu_layers
    sich.atomar_schreiben(json_pfad, json.dumps(data, ensure_ascii=False, indent=2))
    if "migriert_am" in neben:
        neben["zurueck_am"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        neben["migriert_am_vorher"] = neben.pop("migriert_am")
        sich.atomar_schreiben(p["neben"], json.dumps(neben, ensure_ascii=False, indent=1))
    einstellung_setzen("json")
    kalender_ics.cache_leeren()
    return {"geschrieben": str(json_pfad), "zahlen": zahlen(data)}
