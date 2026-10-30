// Calendar colours on the phone = the core's (core/calendar_colours.py):
// key, slot lookup, precedence and final hex day/night against the vectors
// written by the real core (scripts/calendar_colour_vectors.py), the synced
// table read through the Mitte rules, every view using it, contrast, and
// preview PNGs (build/kalender_vorschau/colours_*.png, not in the repo).

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/colours.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/termin_lesen.dart';
import 'package:zen_mobile/kalender/views/calendar_item.dart';
import 'package:zen_mobile/kalender/views/calendar_palette.dart';
import 'package:zen_mobile/kalender/views/view_mode.dart';
import 'package:zen_mobile/mitte/regeln.dart';
import 'package:zen_mobile/thema/farben.dart';

import 'calendar_views_test.dart' show app, at, loadFonts, now, phone, previewPage, snapshot;
import 'vectors.dart';

final vectors = jsonDecode(File(vectorPath('calendar_colour_vectors.json')).readAsStringSync()) as Map<String, dynamic>;
final palette = CalendarColourPalette.fromJson(File(CalendarColourPalette.asset).readAsStringSync());

void main() {
  setUpAll(() => CalendarColourPalette.current = palette);

  group('the core vectors', () {
    final table = parseTable(vectors['table_file'] as String);

    test('table, fallback slots, course keys, constants', () {
      expect(table, (vectors['table'] as Map).cast<String, int>());
      expect(parseTable(vectors['old_flat_table_file'] as String),
          (vectors['parsed_old_flat_table'] as Map).cast<String, int>());
      expect(parseTable('kaputt'), isEmpty);
      for (final e in (vectors['fallback_slots'] as Map).entries) {
        expect(fallbackSlot(e.key as String), e.value, reason: e.key as String);
      }
      for (final e in (vectors['course_keys'] as Map).entries) {
        expect(courseKey(e.key as String), e.value, reason: e.key as String);
      }
      expect(shortForms, (vectors['short_forms'] as Map).cast<String, String>());
      expect(groupCatalog, (vectors['group_catalog'] as Map).cast<String, String>());
      expect(css3Colours, (vectors['css3_colours'] as Map).cast<String, String>());
      expect(slotCount, vectors['slot_count']);
    });

    for (final c in (vectors['cases'] as List).cast<Map<String, dynamic>>()) {
      test(c['name'], () {
        final x = c['expect'] as Map<String, dynamic>;
        final s = stueckeLesen(c['ics'] as String).single;
        final col = s.colour;
        expect(s.label, x['label']);
        expect(col.sourceId, (x['quelle'] as Map?)?['id']);
        expect(col.groupKey, x['group_key']);
        expect(col.style, x['style'] == null ? isNull : (x['style'] as Map).cast<String, String>());
        final span = s.art == 'termin' && s.daten['bis'] != null && s.daten['bis'] != s.daten['tag'];
        expect(span, x['span']);
        final key = entryKey(s.label, col.sourceId);
        expect(key, x['key']);
        expect(slotFor(col.groupKey, table), x['group_slot']);
        final r = ResolvedColour.resolve(col.style, key, table, span: span);
        expect((r.source, r.role, r.slot), (x['source'], x['role'], x['slot']));
        for (final theme in ['day', 'night']) {
          final b = blockColours(r, palette.of(night: theme == 'night'), layerDefault: vectors['layer_default'] as String);
          final want = x[theme] as Map;
          expect((b.fill, b.text, b.border), (want['fill'], want['text'], want['border']), reason: theme);
        }
      });
    }
  });

  test('the phone fetches the synced table, the calendar uses it', () async {
    expect(holen('calendar_colours.json'), isTrue);
    expect(eigene('calendar_colours.json'), isFalse);
    final ab = SpeicherAblage();
    final cases = (vectors['cases'] as List).cast<Map<String, dynamic>>();
    for (final (i, c) in cases.indexed) {
      await ab.schreiben('kalender/${c['layer']}/$i.ics', c['ics'] as String);
    }
    await ab.schreiben(tableFile, vectors['table_file'] as String);
    final k = await Kalender.laden(ab);
    final occ = k.vorkommen(DateTime.utc(2026, 11, 1), DateTime.utc(2026, 11, 30)).values.expand((l) => l);
    final analysis = occ.firstWhere((v) => v.label == 'Analysis I @ HS 1');
    expect((analysis.colour.source, analysis.colour.role), ('course', 't0'));
    final messe = occ.where((v) => v.label == 'Messe').toList();
    expect(messe.length, 3);
    expect(messe.every((v) => v.colour.role == 'sp1'), isTrue);
    final todo = occ.firstWhere((v) => v.label == 'todo');
    expect(todo.colour.key, 'quelle:l_todo');
    expect(todo.colour.slot, 11);
    // Without the table: the crc32 fallback, like the core.
    await ab.loeschen(tableFile);
    final k2 = await Kalender.laden(ab);
    final a2 = k2.vorkommen(DateTime.utc(2026, 11, 2), DateTime.utc(2026, 11, 2)).values.expand((l) => l)
        .firstWhere((v) => v.label == 'Analysis I @ HS 1');
    expect(a2.colour.slot, fallbackSlot('analysis'));
  });

  test('palette asset is the core file, and every look reads at 4.5:1', () {
    expect(File(CalendarColourPalette.asset).readAsStringSync(),
        File('../core/calendar_palette.json').readAsStringSync());
    for (final night in [false, true]) {
      final p = CalendarPalette.forTheme(zentraleThema(night ? Brightness.dark : Brightness.light));
      expect(p.colours, isNotNull);
      for (final role in [for (var i = 0; i < slotCount; i++) 't$i', 'sp1']) {
        for (final kind in [ItemKind.event, ItemKind.tentative]) {
          for (final style in <Map<String, String>?>[null, {'background-color': '#ffd700'},
            {'color': '#ff8800'}, {'background-color': '#102030', 'color': '#102031'}]) {
            final item = CalendarItem(id: 'x', kind: kind, label: 'x', start: now,
                colour: ResolvedColour(source: 'course', role: role, style: style));
            final l = p.lookOf(item);
            expect(contrast(l.text, l.fill), greaterThanOrEqualTo(4.5),
                reason: 'night=$night $role $kind $style');
          }
        }
      }
    }
  });

  test('committed colours are exactly the TUI palette (no night softening)', () {
    for (final night in [false, true]) {
      final p = CalendarPalette.forTheme(zentraleThema(night ? Brightness.dark : Brightness.light));
      final role = palette.of(night: night).roles['t3']!;
      final l = p.lookOf(CalendarItem(id: 'x', kind: ItemKind.event, label: 'x', start: now,
          colour: const ResolvedColour(source: 'course', role: 't3', slot: 3)));
      expect(l.fill, hexColor(role.fill));
      // The TUI's text colour where it reaches 4.5:1 (day t3: 4.2 → black).
      final want = hexColor(role.onFill);
      expect(l.text, contrast(want, l.fill) >= 4.5 ? want : p.readableOn(l.fill));
    }
  });

  // ── Preview images: several courses, a styled event, uncommitted ──────────

  List<CalendarItem> courses() {
    final table = {'analysis': 0, 'experimentalphysik': 3, 'theoretische': 1, 'chemie': 11, 'parkour': 2};
    CalendarItem e(String id, String label, DateTime s, DateTime? end,
        {ItemKind kind = ItemKind.event, Map<String, String>? style, bool allDay = false, bool span = false}) {
      return CalendarItem(id: id, kind: kind, label: label, start: s, end: end, allDay: allDay,
          color: const Color(0xFFFF5500),
          colour: ResolvedColour.resolve(style, entryKey(label, null), table, span: span));
    }

    return [
      for (final d in [16, 18, 20]) e('a$d', 'Analysis I', at(d, 8, 30), at(d, 10)),
      for (final d in [16, 19]) e('x$d', 'ExPhy Übung', at(d, 10, 15), at(d, 11, 45)),
      for (final d in [17, 19]) e('t$d', 'Theoretische Physik Ia', at(d, 8), at(d, 10)),
      e('c17', 'Allgemeine Chemie (Di)', at(17, 12, 15), at(17, 13, 45)),
      e('ana', 'Ana Tutorium Jäger', at(18, 14), at(18, 15)),
      e('p', 'Parkour', at(20, 18), at(20, 19, 30)),
      e('z', 'Zahnarzt', at(17, 15), at(17, 16), style: {'background-color': '#ffd700'}),
      e('k', 'Klausur Analysis', at(21, 10), at(21, 12), style: {'border-color': '#ff0000'}),
      e('kino', 'Kino?', at(19, 19), at(19, 21), kind: ItemKind.tentative),
      e('ws', 'Analysis Nachhilfe?', at(18, 16), at(18, 17), kind: ItemKind.tentative),
      e('m1', 'Messe', at(16, 0), null, allDay: true, span: true),
      e('m2', 'Messe', at(17, 0), null, allDay: true, span: true),
    ];
  }

  for (final night in [false, true]) {
    final tag = night ? 'night' : 'day';
    testWidgets('preview images: course colours ($tag)', (t) async {
      await t.runAsync(loadFonts);
      phone(t);
      final src = ListItemSource(courses());
      final key = GlobalKey();
      for (final (mode, focus, title, name) in [
        (CalendarViewMode.week, now, 'KW 47 · Kursfarben', 'colours_week'),
        (CalendarViewMode.day, DateTime.utc(2026, 11, 18), 'Mi., 18. Nov.', 'colours_day'),
        (CalendarViewMode.month, now, 'November 2026', 'colours_month'),
      ]) {
        await t.pumpWidget(RepaintBoundary(key: key, child: app(previewPage(mode, focus, title, src), night: night)));
        await t.pumpAndSettle();
        await snapshot(t, key, '${name}_$tag');
      }
    });
  }
}
