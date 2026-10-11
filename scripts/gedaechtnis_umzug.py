#!/usr/bin/env python3
# scripts/gedaechtnis_umzug.py
#
# Zieht das Gedächtnis vom alten Aufbau (nach Datenformat: dossiers/,
# kataloge/, notizen/, quellen/, tagebuch/, sasha.md …) in den neuen (nach
# Thema, Kopf wie Claudes Datei-Gedächtnis, siehe core/gedaechtnis_ablage.py).
#
# 2026-10-11, Sasha: „wir sortieren momentan nach datenformat, FALSCH."
#
# Ablauf — NUR von Hand, nie beim Start des Backends:
#   1. venv/bin/python scripts/gedaechtnis_umzug.py [--tabelle vorschlag.md]
#        → zeigt die Tabelle alt → neu (Thema, Name, Art, Haken). Ändert nichts.
#   2. Sasha korrigiert die Tabelle (Thema/Name/Art/Haken), wenn er will.
#   3. venv/bin/python scripts/gedaechtnis_umzug.py --plan vorschlag.md --wirklich
#
# Ohne Verlust: der alte Bestand liegt danach vollständig unter
# data/gedaechtnis/_alt_vor_themen_<datum>/ (nichts wird gelöscht), die
# Messreihen-Werte aus data/g_*.json ebenso (Unterordner data/). Die neuen
# Dateien entstehen erst in einem Zwischenordner und werden dann an ihren
# Platz gelegt; bricht es mittendrin ab, setzt der nächste Lauf dort fort.
# Ein zweiter Lauf findet nichts Altes mehr und tut nichts (idempotent).
#
# Skills (skills/ → ki/skills/) werden nur umbenannt, nicht kopiert: ihr
# Inhalt ändert sich nicht. Projekte (projekte/) bleiben, wo sie sind — ob
# sie als Thema mit art: projekt aufgehen, ist ein eigener späterer Schritt
# (memory/ki/gedaechtnis_dateien.md).

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "core"))

import gedaechtnis_ablage as ablage  # noqa: E402
import gedaechtnis_katalog as katalog  # noqa: E402

ALT_BEREICHE = {"dossiers": "dossier", "notizen": "notiz", "kataloge": "katalog",
                "quellen": "quelle"}
ZWISCHEN = ".umzug_zwischen"

# Thema nach Stichwort — zuerst im Namen, dann im Text. Was nichts trifft,
# kommt nach „allgemein"; Sasha korrigiert in der Tabelle.
THEMEN_REGELN = [
    ("allgemein", ("vorhaben",)),       # Übersicht über alle Themen hinweg
    ("gesundheit", ("sleep", "schlaf", "headache", "kopfschmerz", "periode", "bauch",
                    "appetit", "tired", "muede", "stress", "krank", "gesund")),
    ("sport", ("training", "spagat", "parkour", "gym", "calisthenics", "l-sit",
               "lauf", "zugspitze", "beweglichkeit")),
    ("studium", ("studium", "modul", "vorlesung", "biophysik", "organoid",
                 "zellbio", "uni-", "semester")),
    ("wohnen", ("umzug", "wohnung", "kueche", "küche", "moebel")),
    ("alltag", ("fahrschule", "fuehrerschein", "führerschein", "wegzeit", "geige")),
    ("basteln", ("elektronik", "ideen", "fraktal", "maker", "arduino", "loet",
                 "rendering", "oszi")),
]


def thema_raten(name: str, text: str) -> str:
    for quelle in (name.lower(), (text or "")[:600].lower()):
        for thema, woerter in THEMEN_REGELN:
            if any(w in quelle for w in woerter):
                return thema
    return ablage.ALLGEMEIN


def _lesen(pfad: str) -> str:
    try:
        with open(pfad, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _ohne_titel(text: str) -> str:
    zeilen = (text or "").replace("\r\n", "\n").split("\n")
    while zeilen and not zeilen[0].strip():
        zeilen.pop(0)
    if zeilen and zeilen[0].startswith("# "):
        zeilen.pop(0)
    return "\n".join(zeilen).strip("\n")


def haken_raten(art: str, text: str) -> str:
    """Die eine Zeile für den Index, aus dem Text geraten."""
    kopf = katalog.kopf_lesen(text) if art != "katalog" else {}
    if kopf:
        status = kopf.get("status", "").strip()
        return kopf["titel"] + (f" ({status})" if status and status != "-" else "")
    m = re.search(r"^> (?:Geholt|Uebernommen) am \S+ von (\S+)", text, re.M)
    if m:
        quelle = m.group(1)
        return "Dokument von " + (quelle if len(quelle) <= 80 else quelle[:79] + "…")
    absatz, im_code = [], False
    for z in _ohne_titel(text).splitlines():
        if z.strip().startswith("```"):
            im_code = not im_code
            continue
        roh = z.strip()
        if im_code or roh.startswith((">", "|", "#")) or not roh \
                or re.match(r"^-\s*[a-zA-Z]+\s*:", roh):
            if absatz:
                break
            continue
        absatz.append(" ".join(roh.lstrip("-*").split()))
    satz = " ".join(absatz).replace("**", "")
    if not satz and art == "katalog":
        titel = katalog.titel_liste(text)
        satz = "Einträge wie " + ", ".join(titel[:3]) + (" …" if len(titel) > 3 else "") \
            if titel else ""
    satz = re.split(r"(?<=[.!?])\s", satz, maxsplit=1)[0]
    return satz if len(satz) <= 120 else satz[:119] + "…"


# ── Der Plan ──────────────────────────────────────────────────────────

def plan_bauen(wurzel: str, daten: str = "") -> list:
    """[{alt, thema, name, art, haken, fest}] — eine Zeile je alter Datei.
    `fest`: Ziel steht fest (Kernakten, Vorlagen, Skills), Sasha ändert es nicht."""
    zeilen = []

    def zeile(alt, thema, name, art, haken, fest=False):
        zeilen.append({"alt": alt, "thema": thema, "name": name, "art": art,
                       "haken": haken, "fest": fest})

    for alt, thema, name, art, haken in (
            ("hausregeln.md", "ki", "hausregeln", "regel",
             "Verhaltensregeln, die Sasha im Gespräch gesetzt hat — stehen in jedem Zug ganz oben"),
            ("sasha.md", "person", "steckbrief", "steckbrief",
             "Wer Sasha ist und was für ihn gilt — Sasha pflegt das"),
            ("ziele.md", "person", "ziele", "ziel",
             "Sashas Ziele mit Horizont — Sasha pflegt, KI schlägt vor")):
        if os.path.isfile(os.path.join(wurzel, alt)):
            zeile(alt, thema, name, art, haken, True)
    for bereich, art in ALT_BEREICHE.items():
        ordner = os.path.join(wurzel, bereich)
        if not os.path.isdir(ordner):
            continue
        for f in sorted(os.listdir(ordner)):
            if not f.endswith(".md"):
                continue
            text = _lesen(os.path.join(ordner, f))
            name = f[:-3]
            zeile(f"{bereich}/{f}", thema_raten(name, text), name, art, haken_raten(art, text))
    ordner = os.path.join(wurzel, "vorlagen")
    if os.path.isdir(ordner):
        for f in sorted(os.listdir(ordner)):
            if f.endswith(".md"):
                zeile(f"vorlagen/{f}", "ki", f[:-3], "vorlage", "", True)
    ordner = os.path.join(wurzel, "tagebuch")
    if os.path.isdir(ordner):
        for f in sorted(os.listdir(ordner)):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", f):
                zeile(f"tagebuch/{f}", ablage.TAGEBUCH, f[:7], "tagebuch", "", True)
    if os.path.isdir(os.path.join(wurzel, "skills")):
        zeile("skills/", "ki", "skills", "skills", "unverändert verschoben", True)
    for g in _reihen(daten):
        zeile(f"data/{g['id']}.json", thema_raten(g["id"][2:] + " " + g.get("name", ""), ""),
              ablage.reihe_stamm(g["id"]), "messreihe", _reihe_haken(g))
    return zeilen


def _reihen(daten: str) -> list:
    """Graphen aus data/graphs.json, deren Werte-Datei in data/ liegt."""
    if not daten:
        return []
    try:
        with open(os.path.join(daten, "graphs.json"), encoding="utf-8") as f:
            graphen = json.load(f)
    except (OSError, ValueError):
        return []
    return [g for g in graphen if isinstance(g, dict) and str(g.get("id", "")).startswith("g_")
            and re.fullmatch(r"g_[a-z0-9_]+", g["id"])
            and os.path.isfile(os.path.join(daten, g["id"] + ".json"))]


def _reihe_haken(g: dict) -> str:
    typ = {"number": "Zahl", "scale": "Skala 1–5", "time": "Uhrzeit",
           "period": "Zeitspanne"}.get(g.get("type"), g.get("type") or "")
    einheit = f" in {g['unit']}" if g.get("unit") else ""
    return f"Messreihe {g.get('name') or g['id']} ({typ}{einheit})"


def _ziel(z: dict) -> str:
    """Relativer Zielpfad einer Planzeile."""
    if z["art"] == "skills":
        return "ki/skills/"
    if z["thema"] == "ki":
        return f"ki/vorlagen/{z['name']}.md" if z["art"] == "vorlage" else f"ki/{z['name']}.md"
    if z["art"] == "messreihe":
        return f"themen/{z['thema']}/{z['name']}{ablage.REIHE_JSON}"
    return f"themen/{z['thema']}/{z['name']}{ablage.endung(z['art'])}"


def tabelle(zeilen: list) -> str:
    kopf = ("| alt | thema | name | art | haken | → neu |\n"
            "|---|---|---|---|---|---|\n")
    return kopf + "".join(
        f"| {z['alt']} | {z['thema']} | {z['name']} | {z['art']} | "
        f"{z['haken'].replace('|', '/')} | {_ziel(z)}{' (fest)' if z['fest'] else ''} |\n"
        for z in zeilen)


def plan_lesen(text: str, zeilen: list) -> list:
    """Sashas korrigierte Tabelle über den Vorschlag legen (nach `alt`).
    Feste Zeilen bleiben fest; Thema und Name gehen durch slug."""
    nach_alt = {z["alt"]: z for z in zeilen}
    for roh in text.splitlines():
        teile = [t.strip() for t in roh.strip().strip("|").split("|")]
        if len(teile) < 5 or teile[0] in ("alt", "") or set(teile[0]) <= {"-"}:
            continue
        z = nach_alt.get(teile[0])
        if not z or z["fest"]:
            continue
        thema, name = ablage.slug(teile[1]), ablage.slug(teile[2])
        art = ablage.slug(teile[3]) or z["art"]
        if z["art"] == "messreihe":
            art, name = "messreihe", z["name"]   # die id hängt am Dateinamen
        if thema in ("ki", ablage.TAGEBUCH):
            thema = z["thema"]
        z.update(thema=thema or z["thema"], name=name or z["name"], art=art,
                 haken=teile[4])
    return zeilen


# ── Ausführen ─────────────────────────────────────────────────────────

def _neue_datei(z: dict, text: str) -> str:
    rumpf = _ohne_titel(text)
    if z["art"] == "vorlage":
        return text
    kopf = ablage.neuer_kopf(z["name"], z["haken"], z["art"])
    return ablage.text_bauen(kopf, rumpf)


def _zusammen(alt_ziel: str, neu: str, art: str) -> str:
    """Ziel gibt es schon (z. B. hat die KI nach dem Update dort geschrieben):
    der alte Inhalt kommt dazu, nichts wird überschrieben."""
    if not alt_ziel:
        return neu
    k_ziel, r_ziel = ablage.zerlegen(alt_ziel)
    _, r_neu = ablage.zerlegen(neu)
    if r_neu.strip() in r_ziel:
        return alt_ziel
    if art == "tagebuch":   # die alten Tage zuerst, sie sind älter
        return ablage.text_bauen(k_ziel or ablage.zerlegen(neu)[0],
                                 r_neu.rstrip() + "\n\n" + r_ziel)
    return ablage.text_bauen(k_ziel, r_ziel.rstrip() + "\n\n## Aus dem alten Bestand "
                             f"(umgezogen {date.today().isoformat()})\n\n" + r_neu)


def _tagebuch(texte: list, monat: str) -> str:
    teile = [f"## {tag}\n{_ohne_titel(t).strip()}" for tag, t in sorted(texte)]
    j, m = monat.split("-")
    monate = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
              "September", "Oktober", "November", "Dezember")
    kopf = ablage.neuer_kopf(monat, f"Tagebuch {monate[int(m) - 1]} {j}", "tagebuch")
    return ablage.text_bauen(kopf, "\n\n".join(teile))


def ausfuehren(wurzel: str, zeilen: list, daten: str = "", heute: str = "") -> dict:
    """Den Plan umsetzen. → {neu: [...], alt_ordner: pfad}. Siehe Kopf."""
    heute = heute or date.today().isoformat()
    zwischen = os.path.join(wurzel, ZWISCHEN)
    alt_ordner = os.path.join(wurzel, f"_alt_vor_themen_{heute}")
    if os.path.isdir(zwischen):            # ein abgebrochener Lauf: fertig machen
        _einsetzen(wurzel, zwischen)
    neu, tage = {}, {}
    for z in zeilen:
        if z["art"] == "skills":
            continue
        quelle = os.path.join(daten, z["alt"][5:]) if z["alt"].startswith("data/") \
            else os.path.join(wurzel, z["alt"])
        if not os.path.isfile(quelle):
            continue
        if z["art"] == "tagebuch":
            tage.setdefault(z["name"], []).append(
                (os.path.basename(z["alt"])[:10], _lesen(quelle)))
        elif z["art"] == "messreihe":
            if os.path.exists(os.path.join(wurzel, _ziel(z))):
                continue        # schon unter dem Thema; die alte kommt beiseite
            with open(quelle, "rb") as f:
                neu[_ziel(z)] = f.read()
            kopf = ablage.neuer_kopf(z["name"], z["haken"], "messreihe",
                                     reihe=z["alt"][5:-5])
            neu[_ziel(z)[:-len(ablage.REIHE_JSON)] + ".reihe.md"] = ablage.text_bauen(
                kopf, f"Die Werte liegen in {z['name']}{ablage.REIHE_JSON} "
                      f"(Kurve „{z['alt'][7:-5]}“ im Graph-Werkzeug).")
        else:
            ziel = _ziel(z)
            neu[ziel] = _zusammen(neu.get(ziel, ""), _neue_datei(z, _lesen(quelle)), z["art"])
    for monat, texte in tage.items():
        neu[f"themen/{ablage.TAGEBUCH}/{monat}.md"] = _tagebuch(texte, monat)
    # Binärdateien der Quellen ziehen ins Thema ihres Vermerks mit.
    dateien_alt = os.path.join(wurzel, "quellen", "dateien")
    if os.path.isdir(dateien_alt):
        themen_quellen = {z["name"]: z["thema"] for z in zeilen if z["art"] == "quelle"}
        for f in sorted(os.listdir(dateien_alt)):
            thema = themen_quellen.get(os.path.splitext(f)[0], ablage.ALLGEMEIN)
            with open(os.path.join(dateien_alt, f), "rb") as d:
                neu[f"themen/{thema}/dateien/{f}"] = d.read()

    # 1. alles Neue in den Zwischenordner (bestehende Ziele zusammengeführt)
    for rel, inhalt in neu.items():
        if isinstance(inhalt, str):
            inhalt = _zusammen(_lesen(os.path.join(wurzel, rel)), inhalt,
                               "tagebuch" if "/tagebuch/" in rel else "")
        ziel = os.path.join(zwischen, rel)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb" if isinstance(inhalt, bytes) else "w",
                  **({} if isinstance(inhalt, bytes) else {"encoding": "utf-8"})) as f:
            f.write(inhalt)
    # 2. den alten Bestand beiseite (nichts löschen)
    for name in ("hausregeln.md", "sasha.md", "ziele.md", "tagebuch", "vorlagen") \
            + tuple(ALT_BEREICHE):
        _beiseite(os.path.join(wurzel, name), os.path.join(alt_ordner, name))
    for z in zeilen:
        if z["art"] == "messreihe" and z["alt"].startswith("data/"):
            _beiseite(os.path.join(daten, z["alt"][5:]), os.path.join(alt_ordner, z["alt"]))
    _skills_umziehen(wurzel, alt_ordner)
    # 3. Neues an seinen Platz, Index bauen
    _einsetzen(wurzel, zwischen)
    ablage.index_schreiben(wurzel)
    return {"neu": sorted(neu), "alt_ordner": alt_ordner}


def _beiseite(quelle: str, ziel: str) -> None:
    if not os.path.exists(quelle):
        return
    if os.path.exists(ziel):
        ziel += ".2"
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    os.replace(quelle, ziel)


def _skills_umziehen(wurzel: str, alt_ordner: str) -> None:
    alt, neu = os.path.join(wurzel, "skills"), os.path.join(wurzel, "ki", "skills")
    if not os.path.isdir(alt):
        return
    if not os.path.isdir(neu):
        os.makedirs(os.path.dirname(neu), exist_ok=True)
        os.replace(alt, neu)
        return
    for name in os.listdir(alt):        # beide da: Fehlendes rüber, Rest beiseite
        ziel = os.path.join(neu, name)
        if not os.path.exists(ziel):
            os.replace(os.path.join(alt, name), ziel)
    _beiseite(alt, os.path.join(alt_ordner, "skills"))


def _einsetzen(wurzel: str, zwischen: str) -> None:
    for ordner, _dirs, files in os.walk(zwischen):
        for f in files:
            quelle = os.path.join(ordner, f)
            ziel = os.path.join(wurzel, os.path.relpath(quelle, zwischen))
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            os.replace(quelle, ziel)
    shutil.rmtree(zwischen, ignore_errors=True)


def main(argv=None) -> int:
    basis = os.path.normpath(os.path.join(HIER, ".."))
    ap = argparse.ArgumentParser(description="Gedächtnis nach Themen umziehen.")
    ap.add_argument("--wurzel", default=os.path.join(basis, "data", "gedaechtnis"))
    ap.add_argument("--daten", default=os.path.join(basis, "data"),
                    help="Ordner mit graphs.json und g_*.json (Messreihen)")
    ap.add_argument("--tabelle", help="Vorschlag zusätzlich in diese Datei schreiben")
    ap.add_argument("--plan", help="von Sasha korrigierte Tabelle übernehmen")
    ap.add_argument("--trocken", action="store_true", help="nur zeigen (Standard)")
    ap.add_argument("--wirklich", action="store_true", help="wirklich umziehen")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.wurzel):
        print(f"Kein Gedächtnis-Ordner: {a.wurzel}")
        return 1
    zeilen = plan_bauen(a.wurzel, a.daten)
    if a.plan:
        zeilen = plan_lesen(_lesen(a.plan), zeilen)
    text = tabelle(zeilen)
    if not zeilen:
        print("Nichts Altes gefunden — schon umgezogen.")
        return 0
    if a.tabelle:
        os.makedirs(os.path.dirname(os.path.abspath(a.tabelle)), exist_ok=True)
        with open(a.tabelle, "w", encoding="utf-8") as f:
            f.write("# Gedächtnis-Umzug — Vorschlag\n\nSpalten thema, name, art, haken "
                    "ändern; Zeilen mit (fest) bleiben, wie sie sind.\n\n" + text)
    print(text)
    if not a.wirklich or a.trocken:
        print("Trocken — nichts geändert. Umziehen mit --wirklich (ggf. --plan <tabelle>).")
        return 0
    erg = ausfuehren(a.wurzel, zeilen, a.daten)
    print(f"Umgezogen: {len(erg['neu'])} Datei(en). Alter Bestand: {erg['alt_ordner']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
