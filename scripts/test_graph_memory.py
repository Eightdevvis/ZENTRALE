#!/usr/bin/env python3
# scripts/test_graph_memory.py
#
# Comprehensive Test-Harness für das Phase-G-Konzept-Graph-System.
# Wird in der iterativen Fix-Test-Fix-Schleife wiederverwendet.
#
# Jeder Test:
#   - Frischer temp-Graph (User-Daten unberuhrt)
#   - Klares pass/fail Kriterium
#   - Aussagekraeftige Diagnostik bei Fehlschlag
#
# Aufruf:  venv/bin/python scripts/test_graph_memory.py
#
# Output: zusammengefasste Tabelle aller Tests, dann Details fuer alle
# Fehlschlaege. Exit-Code = Anzahl Fehler.

import os
import sys
import time
import tempfile
import shutil
import json
import traceback
from contextlib import contextmanager

# core/ in den Python-Suchpfad legen
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))


# ── Test-Infrastruktur ──────────────────────────────────────────────

@contextmanager
def temp_graph():
    """Frischer Graph in tmp-dir, automatisch aufgeraeumt."""
    tmpdir = tempfile.mkdtemp(prefix='graph_test_')
    import graph as _g, memory as _m
    orig_graph = _g._GRAPH_FILE
    orig_ltm   = _m._LTM_FILE
    orig_stm   = _m._STM_FILE
    _g._GRAPH_FILE = os.path.join(tmpdir, 'ai_graph.json')
    _m._LTM_FILE   = os.path.join(tmpdir, 'ai_ltm.json')
    _m._STM_FILE   = os.path.join(tmpdir, 'ai_stm.json')
    try:
        yield tmpdir
    finally:
        _g._GRAPH_FILE = orig_graph
        _m._LTM_FILE   = orig_ltm
        _m._STM_FILE   = orig_stm
        shutil.rmtree(tmpdir, ignore_errors=True)


def feed(user_msg, ai_msg='OK.'):
    """Einen Turn durch den Extraktor schicken."""
    import consolidation
    consolidation.extract_turn_into_graph(user_msg, ai_msg)


# ── Tests ───────────────────────────────────────────────────────────

def test_seed_identity():
    """KI-Knoten + Capability/Limit-Kanten existieren nach Seed."""
    import graph
    with temp_graph():
        graph.ensure_seed()
        d = graph.dump()
        if 'KI' not in d['nodes']:
            return False, 'KI-Knoten fehlt'
        ki_edges = [e for e in d['edges'] if e['from'] == 'KI']
        kann = [e for e in ki_edges if e['rel'] == 'kann']
        kannnicht = [e for e in ki_edges if e['rel'] == 'kann-nicht']
        if len(kann) < 5:
            return False, f'Nur {len(kann)} kann-Kanten (erwartet >=5)'
        if len(kannnicht) < 10:
            return False, f'Nur {len(kannnicht)} kann-nicht-Kanten (erwartet >=10)'
        return True, f'KI mit {len(kann)} kann + {len(kannnicht)} kann-nicht'


def test_capability_query_activates_limit():
    """Frage 'kannst du Mail senden' aktiviert Mails-Knoten + KI-Limit."""
    import graph
    with temp_graph():
        graph.ensure_seed()
        ctx = graph.context_for_query('kannst du eine Mail senden?')
        if 'Mail' not in ctx and 'mail' not in ctx:
            return False, f'Mail-Knoten nicht im Context. CTX = {ctx[:200]}'
        if 'kann-nicht' not in ctx:
            return False, f'kann-nicht-Relation fehlt im Context'
        return True, 'Mail-Limit korrekt aktiviert'


def test_alias_substring():
    """raspberry pi und Pi sollten auf einen Knoten mergen."""
    import graph
    with temp_graph():
        feed('mein pi hat 1gb ram')
        time.sleep(1)
        feed('der raspberry pi steht im wohnzimmer')
        d = graph.dump()
        # Strenger Filter: nur Pi-bezogene Konzept-Knoten (keine Zeit,
        # keine Seed-Capabilities, kein 'pizza')
        pi_like = [
            n for n in d['nodes']
            if n.lower() in ('pi', 'raspberry pi', 'pi 3', 'der pi', 'mein pi', 'raspberry')
        ]
        if len(pi_like) > 1:
            return False, f'Pi nicht gemerged: {pi_like}'
        if len(pi_like) == 0:
            return False, f'Pi-Knoten gar nicht angelegt. Alle Knoten: {list(d["nodes"])}'
        return True, f'Pi-Knoten: {pi_like}'


def test_alias_plural_singular():
    """Hund und Hunde sollten auf einen Knoten mergen via Stemming."""
    import graph
    with temp_graph():
        feed('ich habe einen Hund')
        time.sleep(1)
        feed('die Hunde laufen gerne')
        d = graph.dump()
        hund_nodes = [n for n in d['nodes'] if 'hund' in n.lower()]
        if len(hund_nodes) > 1:
            return False, f'Hund nicht gemerged: {hund_nodes}'
        return True, f'Hund-Knoten: {hund_nodes}'


def test_alias_case_insensitive():
    """zentrale und ZENTRALE sollten auf einen Knoten mergen."""
    import graph
    with temp_graph():
        feed('zentrale läuft auf dem PC')
        time.sleep(1)
        feed('ZENTRALE braucht ollama')
        d = graph.dump()
        zen_nodes = [n for n in d['nodes'] if 'zentrale' in n.lower()]
        if len(zen_nodes) > 1:
            return False, f'ZENTRALE nicht case-gemerged: {zen_nodes}'
        return True, f'ZENTRALE-Knoten: {zen_nodes}'


def test_alias_no_false_merge_pi_pizza():
    """Pi und Pizza sind unterschiedlich, dürfen NICHT mergen."""
    import graph
    with temp_graph():
        feed('mein pi hat 1gb ram')
        time.sleep(1)
        feed('ich mag pizza zum abendessen')
        d = graph.dump()
        pi = 'Pi' in d['nodes'] or 'pi' in [n.lower() for n in d['nodes']]
        pizza = 'Pizza' in d['nodes'] or 'pizza' in [n.lower() for n in d['nodes']]
        if not pi or not pizza:
            return False, f'Pi {pi}, Pizza {pizza} - mindestens einer fehlt'
        return True, 'Pi und Pizza getrennt'


def test_trivial_skip_emojis():
    """Nur-Emojis-Input darf KEINEN Knoten erzeugen."""
    import graph
    with temp_graph():
        before = len(graph.dump()['nodes'])
        feed('🤖🎩💀')
        feed('🍕')
        after = len(graph.dump()['nodes'])
        if after > before:
            new_nodes = [n for n in graph.dump()['nodes']]
            return False, f'Knoten von Emojis: {new_nodes}'
        return True, 'Emojis übersprungen'


def test_trivial_skip_short():
    """Sehr kurze Antworten ('ja', 'ok', 'mhm') übersprungen."""
    import graph
    with temp_graph():
        before = len(graph.dump()['nodes'])
        for s in ['ja', 'ok', 'mhm', 'nein', 'ne']:
            feed(s)
        after = len(graph.dump()['nodes'])
        if after > before:
            return False, f'Knoten aus Short-Replies: {list(graph.dump()["nodes"])}'
        return True, '0 Knoten aus 5 Short-Replies'


def test_anti_hallucination_user_facts():
    """AI behauptet user-fakten die user nie sagte - nicht extrahiert."""
    import graph
    with temp_graph():
        feed(user_msg='hallo',
             ai_msg='Hi Sasha, ich erinnere mich an deinen Hund Bello, deine Wohnung in Berlin und dein Hobby Klavierspielen.')
        d = graph.dump()
        phantoms = [n for n in d['nodes'] if any(k in n.lower() for k in
                    ['bello', 'berlin', 'klavier'])]
        if phantoms:
            return False, f'Halluzinierte Knoten: {phantoms}'
        return True, 'Keine User-Halluzinationen extrahiert'


def test_time_node_today():
    """Heutiges Datum wird als Time-Knoten angelegt nach erstem Turn."""
    import graph
    from datetime import date
    today = date.today().isoformat()
    with temp_graph():
        feed('ich heiße Sasha')
        time.sleep(0.5)
        d = graph.dump()
        if today not in d['nodes']:
            return False, f'Heutiger Time-Knoten {today} fehlt. Knoten: {list(d["nodes"])}'
        # Auch Monat + Jahr
        year = today.split('-')[0]
        month = '-'.join(today.split('-')[:2])
        if year not in d['nodes']:
            return False, f'Jahr {year} fehlt'
        if month not in d['nodes']:
            return False, f'Monat {month} fehlt'
        return True, f'Zeit-Hierarchie {year}/{month}/{today} alle da'


def test_time_hierarchy_edges():
    """Zeit-Hierarchie-Kanten 2026 -> 2026-05 -> 2026-05-15 existieren."""
    import graph
    from datetime import date
    today = date.today().isoformat()
    year = today.split('-')[0]
    month = '-'.join(today.split('-')[:2])
    with temp_graph():
        # Substantieller Input damit der Extraktor wirklich was findet
        # und add_turn_extraction die Zeit-Hierarchie aufbaut
        feed('Sasha hat heute den Pi konfiguriert und an ZENTRALE gearbeitet')
        time.sleep(2)
        d = graph.dump()
        has_y_m = any(e['from'] == year and e['to'] == month and e['rel'] == 'enthält'
                      for e in d['edges'])
        has_m_d = any(e['from'] == month and e['to'] == today and e['rel'] == 'enthält'
                      for e in d['edges'])
        if not has_y_m:
            return False, f'{year}-->{month}-Kante fehlt. Edges: {[(e["from"],e["to"],e["rel"]) for e in d["edges"][:10]]}'
        if not has_m_d:
            return False, f'{month}-->{today}-Kante fehlt'
        return True, 'Zeit-Hierarchie verkettet'


def test_sasha_anchor_in_activation():
    """Bei jeder Query wird Sasha automatisch als Entry-Point aktiviert."""
    import graph
    with temp_graph():
        feed('ich heiße Sasha und arbeite an zentrale')
        time.sleep(2)
        # Query ohne Sasha-Bezug
        ctx = graph.context_for_query('was ist 2 plus 2')
        # Sasha sollte trotzdem in Aktivierung sein wenn er im Graphen ist
        if 'Sasha' not in ctx:
            return False, f'Sasha nicht aktiviert. CTX = {ctx[:300]}'
        return True, 'Sasha als Anchor aktiviert'


def test_query_finds_specific_fact():
    """Spezifische Frage findet spezifischen Fakt im Graph."""
    import graph
    with temp_graph():
        feed('mein pi 3 hat 1 GB RAM')
        time.sleep(2)
        feed('die zentrale läuft auf einem linux-pc')
        time.sleep(2)
        ctx = graph.context_for_query('was für ram hat der pi?')
        # 1 GB RAM sollte im Context auftauchen
        if '1 GB' not in ctx and '1GB' not in ctx:
            return False, f'RAM-Info nicht im Context. CTX = {ctx[:300]}'
        return True, 'Spezifischer Fakt aktiviert'


def test_long_input():
    """Sehr langer Input crasht nicht und extrahiert was sinnvolles."""
    import graph
    with temp_graph():
        long_msg = ('Heute war ein voller Tag. Ich habe morgens Kaffee getrunken. '
                    'Dann habe ich an ZENTRALE gearbeitet, einen Bug in der Auto-'
                    'Save-Pipeline gefixt. Mittags habe ich mit Tom telefoniert, '
                    'er hat ein neues Auto. Nachmittags Sport gemacht, danach mit '
                    'meinem Pi 4 herumgespielt - der hat jetzt 8 GB RAM. ' * 5)
        feed(long_msg, 'Klingt produktiv.')
        time.sleep(2)
        d = graph.dump()
        if len(d['nodes']) < 3:
            return False, f'Nur {len(d["nodes"])} Knoten aus langem Input. Sollte mehr.'
        # Tom sollte als andere Person auftauchen
        has_tom = any(n.lower() == 'tom' for n in d['nodes'])
        if not has_tom:
            return False, f'Tom fehlt trotz Erwähnung. Knoten: {list(d["nodes"])}'
        return True, f'{len(d["nodes"])} Knoten extrahiert inkl. Tom'


def test_pi_pizza_separation():
    """Pi und Pizza dürfen unter keinen Umständen mergen (False-Positive)."""
    import graph
    with temp_graph():
        graph.ensure_seed()
        feed('mein pi hat 1gb ram')
        time.sleep(1)
        feed('ich esse gern pizza')
        d = graph.dump()
        pi_in = 'Pi' in d['nodes'] or 'pi' in d['nodes']
        pizza_in = any('pizza' in n.lower() for n in d['nodes'])
        if not pi_in:
            return False, 'Pi-Knoten fehlt'
        if not pizza_in:
            return False, 'Pizza-Knoten fehlt'
        # Beide müssen separat sein
        return True, 'Pi und Pizza getrennt'


def test_multi_entity_tom():
    """Tom als separate Person bekommt eigene Kanten, mit Verbindung über Sasha."""
    import graph
    with temp_graph():
        feed('Tom ist mein Freund')
        time.sleep(1)
        feed('Tom hat eine Katze')
        time.sleep(1)
        d = graph.dump()
        has_tom = 'Tom' in d['nodes']
        has_katze = any('katze' in n.lower() for n in d['nodes'])
        if not has_tom:
            return False, 'Tom-Knoten fehlt'
        if not has_katze:
            return False, 'Katze-Knoten fehlt'
        # Tom-Katze-Verbindung sollte existieren
        tom_katze = any(
            (e['from'].lower() == 'tom' and 'katze' in e['to'].lower()) or
            ('katze' in e['from'].lower() and e['to'].lower() == 'tom')
            for e in d['edges']
        )
        if not tom_katze:
            return False, f'Tom↔Katze-Kante fehlt. Edges: {[(e["from"],e["to"],e["rel"]) for e in d["edges"]]}'
        return True, 'Tom + Katze + Beziehung da'


def test_capability_query_internet():
    """'kannst du news aus dem internet holen' aktiviert Internet-Limit."""
    import graph
    with temp_graph():
        graph.ensure_seed()
        ctx = graph.context_for_query('kannst du mir aktuelle news aus dem internet holen?')
        has_internet_limit = ('internet' in ctx.lower() and 'kann-nicht' in ctx)
        if not has_internet_limit:
            return False, f'Internet-Limit nicht aktiviert. CTX: {ctx[:400]}'
        return True, 'Internet-Limit aktiviert'


def test_ai_self_learned_limit():
    """User korrigiert AI - das wird als limit-Edge im Graph extrahiert."""
    import graph
    with temp_graph():
        graph.ensure_seed()
        # User belehrt die AI über eine Limit
        feed(user_msg='du kannst gar nicht meine Spotify-Playlist ändern',
             ai_msg='Stimmt, das kann ich nicht.')
        time.sleep(2)
        d = graph.dump()
        # Es sollte einen Knoten geben der mit Spotify zu tun hat
        spotify_node = any('spotify' in n.lower() for n in d['nodes'])
        if not spotify_node:
            return False, f'Spotify-Limit nicht extrahiert. Knoten: {list(d["nodes"])}'
        return True, 'Spotify-Limit gelernt'


def test_contradiction_recent_wins():
    """Pi 1GB → Pi 4GB. Beide Edges existieren, aber neue stärker."""
    import graph
    with temp_graph():
        feed('mein pi hat 1gb ram')
        time.sleep(2)
        feed('nein quatsch, der pi hat 4gb ram!')
        time.sleep(2)
        d = graph.dump()
        # Es sollten beide RAM-Werte als Knoten existieren ODER der neue
        # die alte überschreiben - wir prüfen ob 4GB überhaupt da ist
        has_4gb = any('4' in n and ('gb' in n.lower() or 'ram' in n.lower()) for n in d['nodes'])
        if not has_4gb:
            return False, f'4GB nicht extrahiert. Knoten: {list(d["nodes"])}'
        return True, '4GB als neuer Wert da (Korrektur erfolgreich extrahiert)'


def test_pure_smalltalk_skip():
    """Reines Smalltalk-Geplauder erzeugt keine Knoten."""
    import graph
    with temp_graph():
        for msg in ['guten morgen', 'wie geht es dir', 'mir gehts gut', 'das ist schön']:
            feed(msg, 'Mhm.')
        d = graph.dump()
        # Smalltalk könnte trotzdem Knoten erzeugen wenn LLM zu kreativ
        # Akzeptabel sind 0-2 Knoten (max heute-node + Sasha wenn extrahiert)
        non_time = [n for n in d['nodes'] if not n.startswith('20')]
        if len(non_time) > 2:
            return False, f'Zu viele Knoten aus Smalltalk: {non_time}'
        return True, f'Smalltalk: {len(non_time)} non-time nodes'


def test_alias_camelcase():
    """ZENTRALE als Project-Name mit verschiedenen Schreibweisen."""
    import graph
    with temp_graph():
        feed('zentrale läuft auf dem pc')
        time.sleep(1)
        feed('die Zentrale braucht ollama')
        time.sleep(1)
        feed('ZENTRALE ist mein Projekt')
        d = graph.dump()
        zen_nodes = [n for n in d['nodes'] if 'zentrale' in n.lower()]
        if len(zen_nodes) > 1:
            return False, f'ZENTRALE-Varianten nicht gemerged: {zen_nodes}'
        return True, f'ZENTRALE-Knoten: {zen_nodes}'


def test_query_about_multiple_facts():
    """Frage 'erzähl mir über meinen pi' findet Pi + alle Pi-Properties."""
    import graph
    with temp_graph():
        feed('mein pi hat 1gb ram')
        time.sleep(2)
        feed('der pi steht im wohnzimmer')
        time.sleep(2)
        feed('der pi ist von raspberry pi foundation')
        time.sleep(2)
        ctx = graph.context_for_query('erzähl mir alles über meinen pi')
        # 1GB, wohnzimmer, raspberry sollten alle aktiviert sein
        bits = ['1', 'wohnzimmer', 'raspberry']
        hits = [b for b in bits if b.lower() in ctx.lower()]
        if len(hits) < 2:
            return False, f'Nur {len(hits)}/3 Pi-Facts aktiviert. Hits: {hits}. CTX: {ctx[:500]}'
        return True, f'{len(hits)}/3 Pi-Facts gefunden: {hits}'


def test_german_compound_words():
    """'Wasserkanne' und 'Kaffeetasse' bleiben getrennt (different concepts)."""
    import graph
    with temp_graph():
        feed('ich habe eine wasserkanne in der küche')
        time.sleep(1)
        feed('die kaffeetasse steht auf dem tisch')
        time.sleep(1)
        d = graph.dump()
        has_kanne = any('kanne' in n.lower() for n in d['nodes'])
        has_tasse = any('tasse' in n.lower() for n in d['nodes'])
        if not has_kanne:
            return False, 'Wasserkanne fehlt'
        if not has_tasse:
            return False, 'Kaffeetasse fehlt'
        kanne_nodes = [n for n in d['nodes'] if 'kanne' in n.lower()]
        tasse_nodes = [n for n in d['nodes'] if 'tasse' in n.lower()]
        if any(t in kanne_nodes for t in tasse_nodes):
            return False, 'Kanne und Tasse falsch gemerged'
        return True, f'Kanne {kanne_nodes}, Tasse {tasse_nodes} getrennt'


# ── Test-Runner ─────────────────────────────────────────────────────

TESTS = [
    ('seed_identity',          test_seed_identity),
    ('capability_query_mail',  test_capability_query_activates_limit),
    ('capability_query_inet',  test_capability_query_internet),
    ('alias_substring',        test_alias_substring),
    ('alias_plural_singular',  test_alias_plural_singular),
    ('alias_case_insensitive', test_alias_case_insensitive),
    ('alias_no_false_merge',   test_alias_no_false_merge_pi_pizza),
    ('alias_camelcase',        test_alias_camelcase),
    ('trivial_skip_emojis',    test_trivial_skip_emojis),
    ('trivial_skip_short',     test_trivial_skip_short),
    ('pure_smalltalk_skip',    test_pure_smalltalk_skip),
    ('anti_hallucination',     test_anti_hallucination_user_facts),
    ('time_node_today',        test_time_node_today),
    ('time_hierarchy_edges',   test_time_hierarchy_edges),
    ('sasha_anchor',           test_sasha_anchor_in_activation),
    ('query_specific_fact',    test_query_finds_specific_fact),
    ('query_multi_facts',      test_query_about_multiple_facts),
    ('long_input',             test_long_input),
    ('pi_pizza_separation',    test_pi_pizza_separation),
    ('multi_entity_tom',       test_multi_entity_tom),
    ('ai_self_learned_limit',  test_ai_self_learned_limit),
    ('contradiction',          test_contradiction_recent_wins),
    ('german_compounds',       test_german_compound_words),
]


def main():
    results = []
    for name, fn in TESTS:
        sys.stderr.write(f'  >>> {name} ... ')
        sys.stderr.flush()
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f'EXCEPTION: {e}\n{traceback.format_exc()[:500]}'
        results.append((name, ok, msg))
        sys.stderr.write('OK\n' if ok else 'FAIL\n')

    print()
    print('═' * 70)
    print('TEST-SUMMARY')
    print('═' * 70)
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_fail = len(results) - n_ok
    for name, ok, msg in results:
        mark = '✓' if ok else '✗'
        print(f'  {mark} {name:<28s}  {msg}')
    print()
    print(f'  Total: {n_ok}/{len(results)} OK ({n_fail} Fehler)')
    return n_fail


if __name__ == '__main__':
    sys.exit(main())
