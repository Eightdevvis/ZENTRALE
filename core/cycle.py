# core/cycle.py
#
# Zyklus-Vorhersage aus dem »periode«-Graphen (PMS-Rechner).
#
# Idee: es gibt KEINE eigene Datenhaltung. Quelle ist genau der Graph, der
# ohnehin schon gepflegt wird — ein Lifestyle-Graph namens »periode«
# (core/graphs.py, Werte in data/<gid>.json über /api/log). Getippt wird
# jeden Tag der Blutung ihre Stärke; dieses Modul liest die Werte nur und
# rechnet daraus:
#
#   letzter Start  = erster Tag des JÜNGSTEN zusammenhängenden Log-Blocks
#                    (mehrere Tage hintereinander = EINE Periode, nicht
#                    mehrere — sonst wäre jeder Blutungstag ein Zyklus)
#   zykluslänge    = Schnitt der echten Abstände zwischen den Block-Starts
#                    (28 nur als Fallback, solange zu wenig Historie da ist)
#   nächste        = letzter Start + zykluslänge
#   PMS-Fenster    = die 7 Tage VOR der nächsten (next-7 … next-1)
#
# Bewusst reine Rechnung ohne Anzeige-Entscheidung: die Fronten (monolith/
# laptop-Browser, TUI) holen das Ergebnis über /api/cycle bzw. mitgeliefert
# in /api/calendar und zeichnen es dezent. Keine Datei wird geschrieben.
#
# Wichtig: das ist eine GROBE Schätzung auf Basis eines Mittelwerts, kein
# medizinisches Werkzeug — Zyklen schwanken. Deshalb liefert predict() immer
# auch `spread` (Schwankung der letzten Abstände) mit, damit die Front die
# Unsicherheit mit anzeigen kann statt eine Scheingenauigkeit zu behaupten.

import os
import json
from datetime import date, timedelta

import graphs   # Registry (Definitionen) + _slug/_DATA_DIR — dieselbe Quelle

# Name des Graphen, der den Zyklus trägt. Gesucht wird über den SLUG des
# Namens (graphs._slug), nicht über eine harte id: der Graph heißt für Sasha
# »periode«, seine id ist ein Implementierungsdetail der Registry.
GRAPH_SLUG = 'periode'

# Ab welcher Lücke zwischen zwei geloggten Tagen ein NEUER Block (= neue
# Periode) beginnt. 3 Tage Toleranz, damit ein vergessener Eintrag mitten in
# der Blutung den Block nicht künstlich zerreißt; echte Zyklen liegen weit
# darüber (~4 Wochen), also gibt es hier keine Verwechslungsgefahr.
BLOCK_GAP = 3

DEFAULT_LEN = 28    # Fallback-Zykluslänge, solange kein echter Abstand da ist
PMS_DAYS = 7        # Breite des PMS-Fensters vor der nächsten Periode
AVG_OVER = 6        # über wie viele der letzten Abstände gemittelt wird
PLAUSIBLE = (15, 60)   # Abstände außerhalb gelten als Tipp-/Logfehler
CLAMP = (18, 45)       # Ergebnis-Zykluslänge in einen sinnvollen Rahmen ziehen


def _find_graph():
    """Die »periode«-Graph-Definition (oder None). Über den Namens-Slug, damit
    Groß-/Kleinschreibung und Umlaute egal sind."""
    for g in graphs.list_graphs():
        if not isinstance(g, dict):
            continue
        if graphs._slug(g.get('name') or '') == GRAPH_SLUG:
            return g
    return None


def _logged_days(gid):
    """Alle Tage mit echtem Wert, sortiert. Liest dieselbe Messwert-Datei, die
    /api/log schreibt. Kaputte/leere Datei → []."""
    path = os.path.join(graphs._DATA_DIR, gid + '.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception:
        return []
    days = set()
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict) or e.get('value') in (None, ''):
            continue
        try:
            days.add(date.fromisoformat(str(e.get('date'))))
        except (TypeError, ValueError):
            continue
    return sorted(days)


def block_starts(days):
    """Log-Tage → Start-Tage der zusammenhängenden Blöcke (= Perioden-Anfänge).
    Eine Lücke von mehr als BLOCK_GAP Tagen trennt zwei Blöcke."""
    starts = []
    prev = None
    for d in days:
        if prev is None or (d - prev).days > BLOCK_GAP:
            starts.append(d)
        prev = d
    return starts


def _cycle_len(starts):
    """(länge, quelle, n_abstände, schwankung) aus den Block-Starts.

    quelle: 'avg' = aus echten Abständen gemittelt, 'default' = noch zu wenig
    Historie, es gilt DEFAULT_LEN. schwankung = max-min der genutzten
    Abstände (0 bei einem einzigen) — Maß dafür, wie fest der Rhythmus ist.
    """
    gaps = [(b - a).days for a, b in zip(starts, starts[1:])]
    gaps = [g for g in gaps if PLAUSIBLE[0] <= g <= PLAUSIBLE[1]][-AVG_OVER:]
    if not gaps:
        return DEFAULT_LEN, 'default', 0, 0
    avg = int(round(sum(gaps) / len(gaps)))
    avg = max(CLAMP[0], min(CLAMP[1], avg))
    return avg, 'avg', len(gaps), max(gaps) - min(gaps)


def predict(today=None):
    """
    Zyklus-Vorhersage oder None (kein »periode«-Graph / noch keine Werte).

    Liefert:
      {graph_id, graph_name, last_start, cycle_len, len_source ('avg'|'default'),
       n_cycles, spread, next_start, pms_from, pms_to, days_to_next (kann
       negativ sein = überfällig), overdue (bool), phase}

    phase: 'periode'  – heute liegt im laufenden Log-Block
           'pms'      – heute liegt im PMS-Fenster
           'ueberfaellig' – die vorhergesagte Periode ist vorbei, nichts geloggt
           'ruhig'    – dazwischen
    """
    g = _find_graph()
    if not g:
        return None
    gid = g.get('id')
    days = _logged_days(gid)
    if not days:
        return None

    today = today or date.today()
    starts = block_starts(days)
    last_start = starts[-1]
    length, source, n_gaps, spread = _cycle_len(starts)

    next_start = last_start + timedelta(days=length)
    pms_from = next_start - timedelta(days=PMS_DAYS)
    pms_to = next_start - timedelta(days=1)
    days_to_next = (next_start - today).days

    # Läuft die Periode HEUTE noch? (letzter Log-Tag höchstens BLOCK_GAP her
    # und der Block hat vor der Vorhersage begonnen)
    in_period = (today - days[-1]).days <= BLOCK_GAP and days[-1] >= last_start
    if in_period and today >= last_start:
        phase = 'periode'
    elif pms_from <= today <= pms_to:
        phase = 'pms'
    elif days_to_next < 0:
        phase = 'ueberfaellig'
    else:
        phase = 'ruhig'

    return {
        'graph_id': gid,
        'graph_name': g.get('name'),
        'last_start': last_start.isoformat(),
        'cycle_len': length,
        'len_source': source,
        'n_cycles': n_gaps,
        'spread': spread,
        'next_start': next_start.isoformat(),
        'pms_from': pms_from.isoformat(),
        'pms_to': pms_to.isoformat(),
        'days_to_next': days_to_next,
        'overdue': days_to_next < 0,
        'phase': phase,
    }


def day_marks(start, end, pred=None):
    """
    Tages-Marker für einen Zeitraum [start, end] (date-Objekte) — die Form, in
    der Kalender-Fronten einfärben, ohne selbst rechnen zu müssen:

      {"2026-08-02": "next", "2026-07-27": "pms", ...}

    'next' = vorhergesagter Perioden-Start, 'pms' = einer der 7 Tage davor.
    'next' gewinnt, falls sich beides überlappt. Leeres dict, wenn es keine
    Vorhersage gibt oder sie außerhalb des Zeitraums liegt.
    """
    pred = pred if pred is not None else predict()
    if not pred:
        return {}
    out = {}
    try:
        nxt = date.fromisoformat(pred['next_start'])
        pf = date.fromisoformat(pred['pms_from'])
        pt = date.fromisoformat(pred['pms_to'])
    except (KeyError, TypeError, ValueError):
        return {}
    d = max(pf, start)
    while d <= min(pt, end):
        out[d.isoformat()] = 'pms'
        d += timedelta(days=1)
    if start <= nxt <= end:
        out[nxt.isoformat()] = 'next'
    return out


def summary(pred=None):
    """
    Einzeiler für die Fronten (klein geschrieben, im Stil der Boxen). Sagt je
    nach Phase das Wichtigste ZUERST und wiederholt sich nicht — läuft das
    PMS-Fenster schon, braucht niemand mehr »pms ab …«:

      ruhig       'nächste periode 02.08. (in 6 t) · pms ab 26.07. · ø 26 t'
      pms         'pms läuft seit 26.07. · periode ab 02.08. (6 t) · ø 26 t'
      periode     'periode läuft seit 07.07. · nächste ~02.08. · ø 26 t'
      überfällig  'periode überfällig seit 02.08. (4 t) · ø 26 t'

    Bewusst kurz genug für die schmale TUI-Box. None, wenn es nichts zu sagen
    gibt (kein »periode«-Graph / keine Werte).
    """
    pred = pred if pred is not None else predict()
    if not pred:
        return None
    nxt = date.fromisoformat(pred['next_start'])
    pf = date.fromisoformat(pred['pms_from'])
    ls = date.fromisoformat(pred['last_start'])
    laenge = ('ø %d t' % pred['cycle_len']) if pred['len_source'] == 'avg' \
        else ('%d t (geschätzt)' % pred['cycle_len'])

    if pred['overdue']:
        kopf = 'periode überfällig seit %s (%d t)' % (nxt.strftime('%d.%m.'),
                                                      -pred['days_to_next'])
    elif pred['phase'] == 'periode':
        kopf = 'periode läuft seit %s · nächste ~%s' % (ls.strftime('%d.%m.'),
                                                        nxt.strftime('%d.%m.'))
    elif pred['phase'] == 'pms':
        kopf = 'pms läuft seit %s · periode ab %s (%d t)' % (
            pf.strftime('%d.%m.'), nxt.strftime('%d.%m.'), pred['days_to_next'])
    else:
        kopf = 'nächste periode %s (in %d t) · pms ab %s' % (
            nxt.strftime('%d.%m.'), pred['days_to_next'], pf.strftime('%d.%m.'))
    return '%s · %s' % (kopf, laenge)
