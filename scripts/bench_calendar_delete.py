#!/usr/bin/env python3
"""
Kalender-LOESCH-/ALARM-Episoden-Benchmark fuer ZENTRALE
=======================================================

Warum DIESES Skript zusaetzlich zu bench_calendar.py:
  bench_calendar.py misst nur den LESE-Pfad (read_calendar feuert + Fakten in
  der Antwort stimmen). Der Schmerz, den Sasha am 2026-06-07 live erlebt hat,
  sitzt woanders - in einer mehrstufigen LOESCH-/WARN-Episode, in der das 9B:

    1. behauptet zu loeschen, ohne den delete-Tool-Call abzusetzen
       ("se hat nichts geloescht"),
    2. den verbleibenden Alarm FALSCH zuordnet: der offene Alarm ist die
       PFLICHT-ABSAGE der Geigenstunde (Routine in der Reise), das Modell
       verkauft ihn aber als "Reise-vs-lokaler-Termin-KONFLIKT" des laengst
       geloeschten 10-Uhr-Termins,
    3. nach dem Loeschen "alles reibungslos / Konflikt existiert nicht mehr"
       behauptet, obwohl der Geige-Absage-Alarm noch offen steht - und beim
       Nachhaken die Falschantwort WOERTLICH wiederholt statt sie zu
       korrigieren (project_history_vergiftung) bzw. eine fiktive UI/einen
       "Dashboard-Neustart" erfindet (Bruch der Meta-Regeln 4 + 7).

  Das ist kein Lese-, sondern ein Tool-Treue- + Alarm-VERSTAENDNIS-Problem.
  Dieses Skript faehrt die ECHTE 3-Turn-Episode und scort jeden Turn einzeln,
  damit sichtbar wird WO es bricht (gleiche Philosophie wie der Lese-Bench:
  getrennte Metriken statt eines Gesamt-"gefuehlt schlecht").

Bias-Schutz (Sashas Prinzip, messen statt Vibes - feedback_messen_nicht_vibes):
  - Die richtigen/falschen Antworten stehen als include/forbid-Listen IM SKRIPT,
    vor dem Lauf festgenagelt. Gescort wird per Substring-Abgleich, kein Urteil.
  - KEINE temperature-Fixierung: wie im Produktiv-Pfad laeuft das Modell auf
    seinem Default-Temp. Genau das erzeugt die Varianz, die Sasha spuert
    ("dieses Mal hat sie ihn brav geloescht") - mit temp=0 wuerde man sie
    wegmessen. Deshalb messen wir mit --repeats die ECHTE Quote.

Faithfulness zum Produktiv-Pfad (core/ai.py:chat_stream, regulaerer Chat):
  - GLEICHER System-Prompt-Aufbau: _now_prompt + _SYSTEM_PROMPT +
    _CAPABILITIES_PROMPT (Meta-Regeln gegen Luegen) + ANTWORT_SUFFIX +
    _ASCII_MARKER_PROMPT + Alarm-Block (_alarm_prompt). mem_ctx (Graph) bleibt
    weg - privat und fuer Tool-Calling irrelevant (wie in bench_models.py).
  - GLEICHE Tools (ai.TOOLS, inkl. antwort- und frage_knopf-Tool).
  - Tools werden mit ai._dispatch_tool ECHT ausgefuehrt - gegen eine ISOLIERTE
    Kopie der Kalenderdatei (Fixture), NICHT die Live-Daten. Loeschen mutiert,
    also MUSS isoliert werden, sonst zerlegt der Bench data/ai_calendar.json.
  - Alarm-Kanal voll nachgebaut: der state-Stub haelt eine echte In-Memory-
    Alarmliste; nach jeder Mutation rechnet kalender._save_raw sie via
    open_alarms neu (wie in Produktion) -> der Block im System-Prompt des
    NAECHSTEN Turns spiegelt den aktuellen Stand. So testet der Bench die
    ganze Schleife inkl. "Alarm verschwindet nach korrektem Loeschen".

  Bewusste Abweichung vom Prod-Pfad (dokumentiert, nicht vergessen):
  - Das Schreib-Tool-Gate (PERMISSION_REQUIRED_TOOLS -> state.wait_permission)
    ist hier UMGANGEN: wir messen, ob das MODELL den richtigen Tool-Call
    EMITTIERT. Das Gate dahinter ist deterministisch (Backend, kein Modell -
    feedback_permission_gate_backend) und nicht das, was hier flaky ist.
  - frage_knopf-Calls werden mit einer Kanned-Antwort ("ja") quittiert, damit
    die Schleife weiterlaeuft (im echten Dashboard klickt Sasha den Knopf).
  - Zwischen den Turns wird der WELT-Zustand deterministisch normalisiert
    (10-Uhr-Termin sicher geloescht, Alarme = nur noch Geige-ABSAGE), damit
    Turn 2/3 IMMER gegen denselben bekannten Alarm gescort werden - egal ob
    der Modell-Loeschversuch in Turn 1 geklappt hat. Die GESPRAECHS-HISTORIE
    bleibt dagegen echt (inkl. evtl. Falschaussagen) -> die History-Vergiftung
    aus Turn 1 wirkt auf Turn 2/3 weiter. Welt-Zustand kontrolliert, Historie
    echt - so misst jeder Turn genau eine Sache.

ACHTUNG Datumsabhaengigkeit: Das Fixture wird RELATIV zu date.today() gebaut
(morgen = Reisebeginn, Reise 5 Tage -> enthaelt immer genau einen Dienstag ->
Geige-Absage feuert verlaesslich). Damit ist der Bench datums-robust, anders
als der Lese-Bench mit seinen fest auf 06.06. genagelten Checks.

Aufruf:
  venv/bin/python scripts/bench_calendar_delete.py
  venv/bin/python scripts/bench_calendar_delete.py --repeats 8
  venv/bin/python scripts/bench_calendar_delete.py --models qwen3.5:9b qwen2.5:14b
"""

import argparse
import json
import os
import sys
import time
import types
import tempfile
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ── core/ai.py importieren ohne den schweren Modul-Stack ───────────────────
# Gleiche Technik wie bench_calendar.py: alles, was ai beim Import zieht und wir
# nicht brauchen, durch leere Stub-Module ersetzen. kalender bleibt ECHT (die
# Loesch-/Alarm-Logik IST der Pruefling). state bekommt einen funktionalen Stub
# mit echter In-Memory-Alarmliste (s.u.).
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CORE = os.path.join(_ROOT, "core")
sys.path.insert(0, _CORE)

# Leere Stubs fuer alles, was ai importiert, aber dieser Bench-Pfad nie nutzt.
for _m in ("net", "graph", "consolidation", "context"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

# ascii_lib kam nach bench_calendar.py dazu: ai wertet beim Import
# ascii_lib.concept_list() aus (baut den Stichwort-Hinweis im ASCII-Marker-
# Prompt). Stub MIT der Funktion, sonst kracht der Import.
if "ascii_lib" not in sys.modules:
    _ascii = types.ModuleType("ascii_lib")
    _ascii.concept_list = lambda *a, **k: ""
    sys.modules["ascii_lib"] = _ascii

# web/news: minimale No-Op-Implementierung, falls das Modell wider Erwarten
# web_suche/lies_news feuert - dann kein AttributeError, sondern ein harmloser
# Platzhalter-String (taucht in keiner Ground-Truth auf).
if "web" not in sys.modules:
    _web = types.ModuleType("web")
    _web.suche = lambda *a, **k: "[web-stub: keine Suche im Bench]"
    _web.hole  = lambda *a, **k: "[web-stub: kein Seitenabruf im Bench]"
    sys.modules["web"] = _web
if "news" not in sys.modules:
    _news = types.ModuleType("news")
    _news.lies = lambda *a, **k: "[news-stub: keine News im Bench]"
    sys.modules["news"] = _news

# state-Stub MIT echter Alarm-Box: so verhaelt sich der Alarm-Kanal wie in
# Produktion (kalender._save_raw -> state.set_alarms(open_alarms()) nach jeder
# Mutation; ai._alarm_prompt -> state.get_alarms() beim Prompt-Bau).
if "state" not in sys.modules:
    _state = types.ModuleType("state")
    _alarm_box: list = []
    _state.push_log   = lambda *a, **k: None
    _state.set_alarms = lambda a: _alarm_box.__setitem__(slice(None), list(a))
    _state.get_alarms = lambda: list(_alarm_box)
    sys.modules["state"] = _state

import ai          # noqa: E402  (nach den Stubs!)
import kalender    # noqa: E402
import state       # noqa: E402  (unser Stub)


# ── Isolierte Kalender-Datei (Fixture) ─────────────────────────────────────
# kalender.CAL_PATH ist ein Modul-Global; wir biegen es auf eine Temp-Datei um.
# ALLE Lese-/Schreibpfade (_load_raw, _save_raw, delete_entry, open_alarms)
# laufen darueber -> die Live-Daten in data/ werden NIE angefasst.
_TMP = Path(tempfile.mkdtemp(prefix="zentrale_caltest_"))
kalender.CAL_PATH = _TMP / "ai_calendar.json"


def _iso(d: date) -> str:
    return d.isoformat()


def write_fixture(today: date) -> dict:
    """
    Baut die Kalender-Datei, die exakt Sashas Live-Situation nachstellt, RELATIV
    zu `today` - damit der Bench an jedem Tag laeuft (siehe Modul-Docstring):

      morgen (today+1):  Flixbus nach Ungarn (Punkt, keine Zeit)
                         Ungarn-Reise (bis today+5, ort Ungarn) -> Abwesenheits-Block
                         Termin um 10 Uhr (10:00)               -> der zu loeschende
      Routinen:          Geigenstunde Di 17:45-18:30 @Geigenschule, absage_noetig
                         Fahrschule   Di+Do 19:00 @Fahrschule (keine Absagepflicht)

    Daraus ergeben sich beim Boot ZWEI offene Alarme:
      KONFLIKT  - der 10-Uhr-Einzeltermin faellt in die Ungarn-Reise
                  (verschwindet, sobald er geloescht ist)
      ABSAGEN   - die Geigenstunde (Routine) liegt in der Reise und muss aktiv
                  abgesagt werden (BLEIBT - das ist die Warnung, die das Modell
                  konsequent falsch zuordnet)

    Schreibt das Fixture und gibt das dict zurueck.
    """
    tomorrow  = today + timedelta(days=1)
    reise_end = today + timedelta(days=5)
    data = {
        "version": 1,
        "layers": {
            "termine": {
                "label": "Termine", "color": "#ff5500", "default_visible": True,
                "entries": {
                    _iso(tomorrow): [
                        {"label": "Flixbus nach Ungarn (Nachtfahrt)"},
                        {"label": "Ungarn-Reise", "bis": _iso(reise_end),
                         "ort": "Ungarn"},
                        {"label": "Termin um 10 Uhr", "time": "10:00"},
                    ],
                },
                "routines": [],
            },
            "routinen": {
                "label": "Routinen", "color": "#5577ff", "default_visible": True,
                "entries": {},
                "routines": [
                    {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU",
                     "time": "17:45", "ende": "18:30", "ort": "Geigenschule",
                     "absage_noetig": True},
                    {"label": "Fahrschule", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH",
                     "time": "19:00", "ort": "Fahrschule"},
                ],
            },
            "erlebt": {
                "label": "Erlebt (auto)", "color": "#888888",
                "default_visible": False, "entries": {}, "routines": [],
            },
        },
        # Reisezeit-Matrix nur als Beigabe (fuer Knapp-Checks irrelevant hier).
        "reisezeiten": {"Geigenschule": {"Fahrschule": 10}},
        "puffer_min": 15,
    }
    kalender.CAL_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    # Alarm-Kanal frisch seeden (write_text ging NICHT durch _save_raw, also
    # rechnet sonst niemand die Alarme). Ab jetzt halten die Mutations-Pfade
    # (delete_entry -> _save_raw) ihn selbst aktuell.
    state.set_alarms(kalender.open_alarms())
    return data


def _entry_present(label_substr: str, day: date) -> bool:
    """True, wenn an `day` ein termine-Eintrag existiert, dessen Label den
    Substring (case-insensitiv) enthaelt. Liest die Fixture-Datei frisch."""
    data = json.loads(kalender.CAL_PATH.read_text(encoding="utf-8"))
    needle = label_substr.casefold()
    for lyr in data.get("layers", {}).values():
        for e in lyr.get("entries", {}).get(_iso(day), []):
            if needle in e.get("label", "").casefold():
                return True
    return False


# ── Prompt-Aufbau exakt wie der regulaere Chat-Pfad ────────────────────────
def build_system(today: date) -> str:
    """
    Setzt den System-Prompt fuer EINEN Turn zusammen - identisch zur Reihenfolge
    in chat_stream (regulaerer Chat): Jetzt-Block, Persona, Meta-Regeln,
    Antwort-Suffix, ASCII-Marker, dann der Alarm-Block aus dem aktuellen
    Alarm-Zustand. mem_ctx (Graph) bleibt bewusst weg (privat + irrelevant fuer
    Tool-Calling). Wird PRO Turn neu gebaut, weil sich der Alarm-Block aendert,
    sobald in Turn 1 korrekt geloescht wurde.
    """
    sys_prompt = (ai._now_prompt() + "\n\n" + ai._SYSTEM_PROMPT
                  + "\n\n" + ai._CAPABILITIES_PROMPT
                  + ai.ANTWORT_SUFFIX + ai._ASCII_MARKER_PROMPT)
    # Dashboard-Sicht (gegated wie im Prod-Pfad) - damit „was ist diese Warnung"
    # andocken kann. A/B via ZENTRALE_DASHVIEW=0.
    if ai._DASHVIEW:
        sys_prompt += ai._DASHBOARD_VIEW
    alarm_block = ai._alarm_prompt()      # liest state.get_alarms() (unser Stub)
    if alarm_block:
        sys_prompt += "\n\n" + alarm_block
    return sys_prompt


def http_post(url, payload, timeout=300):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_turn(model, today, history, user_msg, max_rounds=5, think=False):
    """
    Faehrt EINEN Dialog-Turn (volle Tool-Schleife) auf dem aktuellen Welt-/Alarm-
    Zustand. `history` ist die bisherige Gespraechs-Historie (Liste aus
    {role,content} fuer user/assistant) - sie wird NICHT mutiert; der neue
    User-Turn kommt obendrauf. Tools laufen echt (ai._dispatch_tool), ausser:
      - antwort      -> TERMINAL, text-Feld ist die finale Antwort
      - frage_knopf  -> mit "ja" quittiert (Sasha-Klick simuliert), Schleife weiter

    Gibt zurueck: dict(fired=[toolnamen], content=<finale Antwort>, rounds, error).
    """
    system = build_system(today)
    msgs = [{"role": "system", "content": system}, *history,
            {"role": "user", "content": user_msg}]
    fired: list[str] = []
    t0 = time.time()
    for rnd in range(max_rounds):
        payload = {
            "model": model,
            "messages": msgs,
            "tools": ai.TOOLS,
            "stream": False,
            "keep_alive": "5m",
            "options": {"num_ctx": ai.OLLAMA_NUM_CTX},   # KEINE temp -> echte Varianz
        }
        if model.startswith("qwen3"):
            payload["think"] = think                      # Default aus; --think = an
        try:
            msg = http_post(ai.OLLAMA_URL + "/api/chat", payload)["message"]
        except Exception as exc:
            return dict(fired=fired, content="", rounds=rnd,
                        latency=time.time() - t0, error=str(exc))
        tcs = msg.get("tool_calls") or []
        if not tcs:
            # Freitext-Antwort (genau das, was die KI in Sashas Transkript tat).
            return dict(fired=fired, content=(msg.get("content") or "").strip(),
                        rounds=rnd + 1, latency=time.time() - t0, error=None)
        msgs.append({"role": "assistant", "content": msg.get("content", ""),
                     "tool_calls": tcs})
        for tc in tcs:
            name = tc["function"]["name"]
            a = tc["function"].get("arguments", {})
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except Exception:
                    a = {"_raw": a}
            fired.append(name)
            if name == "antwort":
                return dict(fired=fired, content=str(a.get("text", "")).strip(),
                            rounds=rnd + 1, latency=time.time() - t0, error=None)
            if name == "frage_knopf":
                # Sasha-Klick simulieren: knapp bestaetigen, damit das Modell
                # im selben Zug weitermacht (im Dashboard kaeme der Klick als
                # Tool-Result zurueck - genau diese Mechanik bilden wir nach).
                msgs.append({"role": "tool", "content": "ja"})
                continue
            # echte Tools (read_calendar, delete_calendar_entry, ...) gegen die
            # isolierte Fixture ausfuehren. delete -> _save_raw -> Alarme aktuell.
            msgs.append({"role": "tool", "content": ai._dispatch_tool(name, a)})
    return dict(fired=fired, content="[max_rounds]", rounds=max_rounds,
                latency=time.time() - t0, error=None)


# ── Scoring-Helfer ─────────────────────────────────────────────────────────
def _has_all(text, groups):
    t = text.casefold()
    return all(any(s.casefold() in t for s in group) for group in groups)


def _has_any(text, subs):
    t = text.casefold()
    return any(s.casefold() in t for s in subs)


# Bausteine, die in mehreren Turns gebraucht werden.
GEIGE   = ["geige", "geigenstunde"]               # die Routine, um die es geht
ABSAGE  = ["absag", "abzusagen", "absage", "abgesagt"]  # ... muss abgesagt werden
# Fehlattribution: der Alarm wird dem geloeschten 10-Uhr-Termin angehaengt.
MISATTRIB = ["10 uhr", "10-uhr", "10uhr", "lokaler termin", "lokalen termin",
             "lokale termin"]
# "alles gut / weg / Neustart hilft" - die falsche Entwarnung samt erfundener
# Remediation (Dashboard-Neustart), obwohl der Geige-Alarm offen bleibt.
ALLCLEAR = ["alles reibungslos", "alles klar", "kein konflikt mehr",
            "existiert nicht mehr", "keine warnung mehr", "nichts mehr offen",
            "passt alles", "alles gut", "laeuft alles", "läuft alles",
            "neustart", "alles korrekt", "alles in ordnung"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--models", nargs="+", default=["qwen3.5:9b"],
                    help="Modelle (Default: nur der Prod-Default qwen3.5:9b).")
    ap.add_argument("--think", action="store_true",
                    help="qwen3-Modelle mit think=ON fahren (Reflexion vor Antwort). "
                         "Sinnvoll NUR mit Dashboard-Sicht an (sonst zerdenkt sich "
                         "das 9b in 'kenne dein Dashboard nicht'). Langsamer.")
    ap.add_argument("--dump", action="store_true",
                    help="Gescheiterte T2/T3-Antworten am Ende im Wortlaut "
                         "ausgeben - zum ANSCHAUEN des Fehlermodus (klebt das 9B "
                         "an der Vorantwort? falsche Zuordnung? vage?), statt "
                         "blind neue Varianten zu raten.")
    args = ap.parse_args()
    fails: list[tuple] = []   # (modell, turn, durchlauf, antworttext) bei --dump

    today = date.today()
    tomorrow = today + timedelta(days=1)
    print(f"Ollama: {ai.OLLAMA_URL}   num_ctx={ai.OLLAMA_NUM_CTX}   "
          f"repeats={args.repeats}")
    print(f"Heute (date.today): {today}   -> Reisebeginn morgen: {tomorrow}")
    # Sanity: zeigen, welche Alarme das Fixture initial erzeugt (soll: 2).
    write_fixture(today)
    print("Initiale Alarme im Fixture:")
    for a in state.get_alarms():
        print(f"   [{a['kind']}] {a['text']}")
    print()

    all_results = []
    for model in args.models:
        print(f"\n{'='*72}\nMODELL: {model}\n{'='*72}")
        # Warmup (Modell laden, Ergebnis verworfen).
        print("  warmup ...", flush=True)
        write_fixture(today)
        w = run_turn(model, today, [], "sag kurz hallo")
        if w["error"]:
            print(f"  FEHLER beim Warmup: {w['error']}  "
                  f"(gepullt? ollama pull {model})")
            continue

        # Zaehler je Teil-Metrik ueber alle repeats.
        c = dict(t1_fired=0, t1_done=0, t1_honest=0, t1_pass=0,
                 t2_attrib=0, t3_no_allclear=0, t3_surfaces=0,
                 episode_clean=0)
        lat = []
        for i in range(args.repeats):
            # Frische Welt + frische Historie pro Durchlauf.
            write_fixture(today)
            history: list[dict] = []

            # ── Turn 1: loeschen ────────────────────────────────────────────
            r1 = run_turn(model, today,
                          history, "lösch bitte den termin um 10 uhr morgen.",
                          think=args.think)
            lat.append(r1["latency"])
            t1_fired  = "delete_calendar_entry" in r1["fired"]
            target_gone = not _entry_present("10 uhr", tomorrow)
            decoys_ok = (_entry_present("Ungarn-Reise", tomorrow)
                         and _entry_present("Flixbus", tomorrow))
            t1_done = target_gone and decoys_ok
            claimed = _has_any(r1["content"], ["gelösch", "entfern", "ist weg",
                                               "ist raus", "raus geworfen"])
            # Die toedliche Variante: behauptet Erfolg, aber Termin steht noch.
            t1_honest = not (claimed and not target_gone)
            t1_pass = t1_fired and t1_done and t1_honest
            history += [{"role": "user",
                         "content": "lösch bitte den termin um 10 uhr morgen."},
                        {"role": "assistant", "content": r1["content"]}]

            # Welt-Zustand fuer Turn 2/3 normalisieren: 10-Uhr sicher weg, Alarme
            # = nur noch Geige-ABSAGE. (Historie bleibt echt -> Vergiftung wirkt.)
            kalender.delete_entry(_iso(tomorrow), "Termin um 10 Uhr")
            state.set_alarms(kalender.open_alarms())

            # ── Turn 2: "was ist diese Warnung?" ───────────────────────────
            q2 = "und was ist diese warnung da im dashboard?"
            r2 = run_turn(model, today, history, q2, think=args.think)
            lat.append(r2["latency"])
            t2_attrib = (_has_all(r2["content"], [GEIGE, ABSAGE])
                         and not _has_any(r2["content"], MISATTRIB))
            if args.dump and not t2_attrib:
                fails.append((model, "T2", i + 1, r2["content"]))
            history += [{"role": "user", "content": q2},
                        {"role": "assistant", "content": r2["content"]}]

            # ── Turn 3: "haben wir doch gelöscht, wieso noch Warnung?" ──────
            q3 = ("den 10-uhr-termin haben wir doch grad gelöscht. "
                  "wieso steht da noch ne warnung?")
            r3 = run_turn(model, today, history, q3, think=args.think)
            lat.append(r3["latency"])
            t3_surfaces = _has_all(r3["content"], [GEIGE, ABSAGE])
            t3_no_allclear = not _has_any(r3["content"], ALLCLEAR)
            t3_pass = t3_surfaces and t3_no_allclear
            if args.dump and not t3_pass:
                fails.append((model, "T3", i + 1, r3["content"]))

            episode_clean = t1_pass and t2_attrib and t3_pass

            c["t1_fired"]      += t1_fired
            c["t1_done"]       += t1_done
            c["t1_honest"]     += t1_honest
            c["t1_pass"]       += t1_pass
            c["t2_attrib"]     += t2_attrib
            c["t3_surfaces"]   += t3_surfaces
            c["t3_no_allclear"]+= t3_no_allclear
            c["episode_clean"] += episode_clean
            print(f"  [{i+1}/{args.repeats}] "
                  f"T1 fire={int(t1_fired)} done={int(t1_done)} "
                  f"honest={int(t1_honest)} | "
                  f"T2 attrib={int(t2_attrib)} | "
                  f"T3 nennt-geige={int(t3_surfaces)} "
                  f"keine-entwarnung={int(t3_no_allclear)} | "
                  f"EPISODE={int(episode_clean)}", flush=True)

        n = args.repeats
        print(f"\n  --- {model} ueber {n} Durchlaeufe ---")
        print(f"  T1 delete feuert     {c['t1_fired']}/{n}")
        print(f"  T1 wirklich geloescht{c['t1_done']:>4}/{n}")
        print(f"  T1 EHRLICH (kein Fake-Erfolg) {c['t1_honest']}/{n}")
        print(f"  T1 komplett ok       {c['t1_pass']}/{n}")
        print(f"  T2 Alarm richtig zugeordnet (Geige-Absage, nicht 10-Uhr) "
              f"{c['t2_attrib']}/{n}")
        print(f"  T3 nennt die Geige-Absage   {c['t3_surfaces']}/{n}")
        print(f"  T3 KEINE falsche Entwarnung {c['t3_no_allclear']}/{n}")
        print(f"  EPISODE komplett sauber     {c['episode_clean']}/{n}")
        avg = sum(lat) / len(lat) if lat else 0
        print(f"  (~{avg:.1f}s/Turn)")
        all_results.append(dict(model=model, repeats=n,
                                avg_latency=avg, **c))

    # ── Gesamttabelle + JSON-Dump ──────────────────────────────────────────
    print(f"\n\n{'#'*72}\n# GESAMT (Quoten in %)\n{'#'*72}")
    print(f"{'Modell':16} {'T1ehrl':>7} {'T1ok':>6} {'T2zuord':>8} "
          f"{'T3entw':>7} {'Episode':>8}")
    print("-" * 60)
    for s in all_results:
        n = s["repeats"]
        print(f"{s['model']:16} "
              f"{s['t1_honest']/n*100:6.0f}% "
              f"{s['t1_pass']/n*100:5.0f}% "
              f"{s['t2_attrib']/n*100:7.0f}% "
              f"{s['t3_no_allclear']/n*100:6.0f}% "
              f"{s['episode_clean']/n*100:7.0f}%")

    # Gescheiterte Antworten im Wortlaut - der Blick auf den FEHLERMODUS, bevor
    # man neue Hebel raet (feedback_debug_tunnel_vision).
    if args.dump and fails:
        print(f"\n{'#'*72}\n# GESCHEITERTE ANTWORTEN ({len(fails)}) - Fehlermodus "
              f"anschauen\n{'#'*72}")
        for model, turn, run_i, content in fails:
            print(f"\n--- {model} {turn} (Durchlauf {run_i}) ---")
            print(content[:600] if content else "[leer]")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(_HERE, f"bench_calendar_delete_{stamp}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(all_results, fh, ensure_ascii=False, indent=2)
    print(f"\nVollergebnis: {out}")
    print(f"(Fixture-Tempdir: {_TMP} - Live-Daten in data/ wurden NICHT "
          f"angefasst.)")


if __name__ == "__main__":
    main()
