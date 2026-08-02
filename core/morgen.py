# core/morgen.py
#
# Der Morgen-Messenger — die LOGIK. Gezeichnet wird woanders
# (scripts/morgen_messenger.py), gestartet auch (scripts/morgen_watcher.py).
#
# Idee: ZENTRALE meldet sich von selbst, sobald der Laptop morgens aufgeht —
# auch (und gerade) wenn das Backend noch gar nicht läuft. Bisher gab es die
# Schlaf-Abfrage nur DRIN: der Reminder des »sleep«-Graphen (graphs.py,
# remind_at 05:00) nagt im Dashboard/in der TUI, aber eben erst, wenn man
# ZENTRALE selbst öffnet. Hier läuft dieselbe Fälligkeit losgelöst weiter.
#
# Zwei Dinge fragt der Messenger:
#   1. Schlaf — Einschlaf- und Aufwachzeit, direkt in den »sleep«-Graphen
#      (Zeitspanne: value = Einschlaf-Minute, end = Aufwach-Minute). Genau
#      derselbe Eintrag, den das Graph-Werkzeug schreiben würde.
#   2. Die oberste offene Aufgabe der »week«-Liste (die Kalender-Sidebar) —
#      übernehmen, erledigen oder auf später legen.
#
# EIGENE Datenhaltung gibt es nur für das, was sonst nirgends hingehört:
# data/morgen_state.json hält pro Tag, ob der Messenger schon durch ist, und
# pro Aufgabe, ob sie übernommen oder auf einen Zeitpunkt vertagt wurde. Der
# Schlafwert lebt im Graphen, der Erledigt-Status in der Liste — beides wird
# NICHT hier gespiegelt, sonst gäbe es zwei Wahrheiten.
#
# Kein Netz, kein Backend, keine KI: alles läuft direkt über core/graphs.py
# und core/lists.py auf die Dateien in data/. Das ist der ganze Trick daran,
# dass sich der Messenger melden kann, bevor ZENTRALE wach ist.

import os
import json
from datetime import datetime, date, timedelta

import graphs
import lists

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
_STATE = os.path.join(_DATA_DIR, 'morgen_state.json')

# Name des Schlaf-Graphen. Per Env umstellbar, damit der Messenger auch auf
# einem Knoten funktioniert, wo der Graph anders heißt.
SLEEP_GRAPH_NAME = os.environ.get('ZENTRALE_MORGEN_GRAPH', 'sleep')

# Ab wann der Messenger überhaupt aufmachen darf, wenn der Graph keine eigene
# Reminder-Uhrzeit trägt. 05:00 ist Sashas Wert im »sleep«-Graphen.
DEFAULT_EARLIEST = '05:00'


# ── Zustand ──────────────────────────────────────────────────────────────
#
# {"days":   {"2026-08-02": {"sleep": "logged"|"skipped", "closed": true}},
#  "taken":  {"l_week:12": "2026-08-02T07:12:00"},
#  "snooze": {"l_week:12": "2026-08-02T14:00"}}
#
# Die Schlüssel unter taken/snooze sind "<lid>:<iid>" — stabil genug, solange
# das Item lebt, und beim Löschen des Items einfach verwaist (wird beim Lesen
# ignoriert, weil die id in der Liste nicht mehr auftaucht).

def _load_state():
    if not os.path.exists(_STATE):
        return {}
    try:
        with open(_STATE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}                      # kaputte Datei = kein Zustand, kein Crash
    return data if isinstance(data, dict) else {}


def _save_state(st):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_STATE, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
    try:
        from datasync import notify_change
        notify_change(_STATE)
    except Exception:
        pass


def item_key(lid, iid):
    """Stabiler Schlüssel für taken/snooze."""
    return '%s:%s' % (lid, iid)


# ── Schlaf ───────────────────────────────────────────────────────────────

def sleep_graph():
    """
    Die Definition des Schlaf-Graphen (oder None). Erst über den Namen
    (»sleep«), sonst der erste Zeitspannen-Graph mit eingeschaltetem
    Reminder — damit eine Umbenennung den Messenger nicht stumm schaltet.
    """
    defs = graphs.list_graphs()
    want = SLEEP_GRAPH_NAME.strip().lower()
    for g in defs:
        if (g.get('name') or '').strip().lower() == want:
            return g
    for g in defs:
        if g.get('type') == 'period' and g.get('remind'):
            return g
    return None


def earliest_time():
    """Ab wann der Messenger aufmachen darf — 'HH:MM'. Quelle ist die
    Reminder-Uhrzeit des Schlaf-Graphen, damit es genau EINE Stellschraube
    gibt (im Graph-Werkzeug einstellbar)."""
    g = sleep_graph() or {}
    at = (g.get('remind_at') or '').strip()
    return at if len(at) == 5 and at[2] == ':' else DEFAULT_EARLIEST


def sleep_open(day=None):
    """Steht die Schlaf-Abfrage für `day` (Default heute) noch offen?
    Erfüllt ist sie, sobald für den Tag ein Wert im Graphen steht — egal ob
    über den Messenger, das Dashboard oder die TUI eingetragen."""
    g = sleep_graph()
    if not g:
        return False
    day = day or date.today().isoformat()
    if graphs.logged_on(g.get('id'), day):
        return False
    return _load_state().get('days', {}).get(day, {}).get('sleep') != 'skipped'


def log_sleep(eingeschlafen, aufgewacht, day=None):
    """
    Schlaf für `day` (Default heute) eintragen. Beide Werte sind Minuten seit
    Mitternacht; »eingeschlafen« liegt in aller Regel VOR Mitternacht und ist
    damit größer als »aufgewacht« — genau so kodiert der period-Typ die Nacht
    (end < value = über Mitternacht). Liefert den geschriebenen Eintrag.
    """
    g = sleep_graph()
    if not g:
        raise RuntimeError('kein schlaf-graph (%s)' % SLEEP_GRAPH_NAME)
    day = day or date.today().isoformat()
    entry = graphs.log_value(g.get('id'), day, int(eingeschlafen), end=int(aufgewacht))
    st = _load_state()
    st.setdefault('days', {}).setdefault(day, {})['sleep'] = 'logged'
    _save_state(st)
    return entry


def skip_sleep(day=None):
    """Schlaf-Abfrage für heute übergehen — sie kommt heute nicht wieder."""
    day = day or date.today().isoformat()
    st = _load_state()
    st.setdefault('days', {}).setdefault(day, {})['sleep'] = 'skipped'
    _save_state(st)


def sleep_duration(eingeschlafen, aufgewacht):
    """Schlafdauer in Minuten (über Mitternacht gerechnet)."""
    return (int(aufgewacht) - int(eingeschlafen)) % 1440


# ── Aufgaben (die »week«-Liste = Kalender-Sidebar) ───────────────────────

def open_tasks(now=None):
    """
    Die offenen Aufgaben der »week«-Liste in Listen-Reihenfolge — die erste
    ist die, die der Messenger anbietet. Draußen bleiben: erledigte und
    solche, die auf einen noch nicht erreichten Zeitpunkt vertagt sind.

    Jede Aufgabe: {lid, iid, key, text, taken (bool), snooze (iso|None)}.
    """
    now = now or datetime.now()
    wl = lists.week_items()
    lid = wl.get('lid')
    if not lid:
        return []
    st = _load_state()
    taken, snoozed = st.get('taken', {}), st.get('snooze', {})
    out = []
    for it in wl.get('items', []):
        if it.get('done'):
            continue
        key = item_key(lid, it.get('id'))
        until = snoozed.get(key)
        if until and _parse_iso(until) and _parse_iso(until) > now:
            continue                   # liegt noch in der Zukunft → heute nicht zeigen
        out.append({'lid': lid, 'iid': it.get('id'), 'key': key,
                    'text': it.get('text') or '', 'taken': key in taken,
                    'snooze': until})
    return out


def next_task(now=None, skip=()):
    """Die oberste offene Aufgabe, die nicht in `skip` (Schlüssel) steht."""
    for t in open_tasks(now):
        if t['key'] not in skip:
            return t
    return None


def take_on(key, now=None):
    """Aufgabe übernehmen (der Zustand überlebt das Fenster und den Tag)."""
    st = _load_state()
    st.setdefault('taken', {})[key] = (now or datetime.now()).isoformat(timespec='seconds')
    _save_state(st)


def drop(key):
    """Übernahme zurücknehmen."""
    st = _load_state()
    if st.get('taken', {}).pop(key, None) is not None:
        _save_state(st)


def conclude(lid, iid):
    """Aufgabe abhaken — über core/lists.py, damit der week-Kopie-Link zur
    Quell-Liste mitgezogen wird. Die Übernahme fällt dabei weg."""
    item = lists.toggle_item(lid, iid)
    st = _load_state()
    changed = st.get('taken', {}).pop(item_key(lid, iid), None) is not None
    changed = (st.get('snooze', {}).pop(item_key(lid, iid), None) is not None) or changed
    if changed:
        _save_state(st)
    return item


def snooze(key, when):
    """
    Aufgabe auf `when` (datetime) vertagen — bis dahin bietet der Messenger
    sie nicht mehr an. Kein eigener Wecker: der Messenger schaut beim nächsten
    Aufmachen nach, ob der Zeitpunkt durch ist.
    """
    st = _load_state()
    st.setdefault('snooze', {})[key] = when.isoformat(timespec='minutes')
    _save_state(st)


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def parse_when(datum, uhrzeit, today=None):
    """
    'TT.MM.' / 'TT.MM.JJJJ' / ISO / leer  +  'HH:MM'  →  datetime (oder None).
    Leeres Datum = heute; das ist der Default, den das Fenster vorschlägt.
    Jahreszahl weggelassen: das Jahr wird so gewählt, dass der Termin nicht in
    der Vergangenheit liegt (31.12. am 2. Januar meint nächsten Dezember nicht,
    aber 05.01. am 30.12. schon).
    """
    today = today or date.today()
    datum = (datum or '').strip()
    minute = _parse_hhmm(uhrzeit)
    if minute is None:
        return None
    if not datum:
        d = today
    else:
        d = _parse_date(datum, today)
        if d is None:
            return None
    return datetime.combine(d, datetime.min.time()) + timedelta(minutes=minute)


def _parse_date(s, today):
    s = s.strip().rstrip('.')
    if '-' in s:                                   # ISO: 2026-08-02
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    parts = [p for p in s.replace('/', '.').split('.') if p != '']
    if not parts or not all(p.isdigit() for p in parts):
        return None
    try:
        if len(parts) == 1:                        # nur der Tag
            d = today.replace(day=int(parts[0]))
        elif len(parts) == 2:                      # Tag.Monat → Jahr raten
            d = date(today.year, int(parts[1]), int(parts[0]))
            if d < today:
                d = date(today.year + 1, int(parts[1]), int(parts[0]))
        else:
            year = int(parts[2])
            year += 2000 if year < 100 else 0
            d = date(year, int(parts[1]), int(parts[0]))
    except ValueError:
        return None
    return d


def _parse_hhmm(s):
    """'23:15' | '2315' | '7' → Minuten seit Mitternacht, sonst None.
    Bewusst dieselbe Nachsicht wie parse_clock in der TUI, aber ohne 24:00 —
    ein Termin um 24:00 ist der nächste Tag, nicht dieser."""
    if not isinstance(s, str):
        return None
    s = s.strip().replace('.', ':')
    if not s:
        return None
    if ':' in s:
        a, _, b = s.partition(':')
        if not a.isdigit() or (b and not b.isdigit()):
            return None
        h, m = int(a), int(b) if b else 0
    elif s.isdigit():
        if len(s) <= 2:
            h, m = int(s), 0
        else:
            s = s.zfill(4)
            h, m = int(s[:-2]), int(s[-2:])
    else:
        return None
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def fmt_clock(m):
    """Minuten → 'HH:MM'."""
    m = int(m)
    if m >= 1440:
        return '24:00'
    return '%02d:%02d' % (m // 60, m % 60)


# ── Fälligkeit: soll das Fenster überhaupt aufgehen? ─────────────────────

def is_closed(day=None):
    """Ist der Messenger für `day` schon durch (erledigt oder weggeklickt)?"""
    day = day or date.today().isoformat()
    return bool(_load_state().get('days', {}).get(day, {}).get('closed'))


def close_day(day=None):
    """Für heute erledigt — bis morgen früh macht der Messenger nicht wieder auf."""
    day = day or date.today().isoformat()
    st = _load_state()
    st.setdefault('days', {}).setdefault(day, {})['closed'] = True
    _prune(st)
    _save_state(st)


def is_due(now=None):
    """
    Soll der Messenger JETZT aufmachen? Drei Bedingungen, alle nötig:
      1. Die Uhrzeit ist durch (earliest_time(), Default 05:00).
      2. Heute wurde er noch nicht geschlossen.
      3. Es gibt überhaupt etwas zu sagen — offene Schlaf-Abfrage oder eine
         offene Aufgabe. Sonst bleibt er still, statt ein leeres Fenster
         aufzureißen.
    """
    now = now or datetime.now()
    day = now.date().isoformat()
    if now.strftime('%H:%M') < earliest_time():
        return False
    if is_closed(day):
        return False
    return bool(sleep_open(day) or open_tasks(now))


def _prune(st, keep_days=30):
    """Alte Tages-Einträge wegräumen — die Datei soll nicht ewig wachsen.
    taken/snooze bleiben unangetastet: die hängen an Aufgaben, nicht am Tag."""
    days = st.get('days')
    if not isinstance(days, dict) or len(days) <= keep_days:
        return
    for d in sorted(days)[:-keep_days]:
        days.pop(d, None)
