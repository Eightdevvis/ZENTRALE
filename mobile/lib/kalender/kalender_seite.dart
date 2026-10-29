// Die Kalender-Seite: heute und die nächsten Tage als Liste (Agenda).
//
// Drei Ebenen, drei Gewichte: Termine (zugesagt) voll, „vielleicht“
// (uncommitted) leiser und kursiv, der Rhythmus (Schlaf, Essen) als eine
// dezente Zeile je Tag. Deadlines mit Muss- und Soll-Zeit, „soll verpasst“
// in Warnfarbe. Abgeschaltete Vorkommen fehlen. Eigene, noch nicht
// abgeglichene Termine tragen „wartet auf Abgleich“.
//
// Zeichnet nur; die Logik steht in kalender_steuerung.dart und kalender.dart.
// Lesbar auch auf E-Ink: nichts unter 12 px, nichts blasser als
// onSurfaceVariant.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../dienste.dart';
import '../l10n/app_localizations.dart';
import '../thema/farben.dart';
import 'eintrag_seite.dart';
import 'kalender.dart';
import 'kalender_steuerung.dart';
import 'regel.dart';
import 'views/calendar_item.dart';
import 'views/calendar_pager.dart';
import 'views/calendar_source.dart';
import 'views/view_mode.dart';
import 'table_page.dart';

/// Für die Liste `bereiche` auf der Startseite.
Widget kalenderSeite(BuildContext context) {
  final d = Dienste.von(context);
  return KalenderSeite(steuerung: d.kalender, abgleichen: d.abgleich.jetzt, viewMemory: _viewMemory);
}

final _viewMemory = FileViewModeMemory();

const _wt = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
const _tageZeigen = 21;

/// Farbe einer Ebene: die aus dem vdir („color“), sonst eine aus dem Auge.
Color ebenenFarbe(BuildContext context, Kalender k, String ebene) {
  final roh = k.ebene(ebene)?.farbe;
  final m = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(roh ?? '');
  if (m != null) return Color(0xFF000000 | int.parse(m.group(1)!, radix: 16));
  final a = AugeFarben.von(context);
  return switch (ebene) { ebeneVielleicht => a.schatten, ebeneRhythmus => a.falte, _ => a.iris };
}

class KalenderSeite extends StatefulWidget {
  const KalenderSeite({super.key, required this.steuerung, this.abgleichen, this.initialMode, this.viewMemory});
  final KalenderSteuerung steuerung;
  final Future<void> Function()? abgleichen;

  /// Start in this mode instead of the remembered one (tests).
  final CalendarViewMode? initialMode;

  /// Where the last mode is remembered (per device, not synced).
  final ViewModeMemory? viewMemory;

  @override
  State<KalenderSeite> createState() => _KalenderSeiteState();
}

class _KalenderSeiteState extends State<KalenderSeite> {
  late CalendarViewMode _mode = widget.initialMode ?? CalendarViewMode.week;
  late DateTime _focus = tagVon(widget.steuerung.jetzt);
  KalenderItemSource? _source;
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    widget.steuerung.laden();
    if (widget.initialMode == null) {
      widget.viewMemory?.load().then((m) {
        if (m != null && mounted) setState(() => _mode = m);
      });
    }
    // The now line moves once a minute.
    _clock = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  Future<void> _neu({DateTime? day, TimeOfDay? start, bool allDay = false}) async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => EintragSeite(
              steuerung: widget.steuerung,
              initialDay: day,
              initialStart: start,
              initialAllDay: allDay,
            )));
  }

  void _setMode(CalendarViewMode m) {
    setState(() => _mode = m);
    widget.viewMemory?.save(m);
  }

  String _title(BuildContext context) {
    final locale = Localizations.localeOf(context).toLanguageTag();
    final l = AppLocalizations.of(context);
    return switch (_mode) {
      CalendarViewMode.agenda => 'Kalender',
      CalendarViewMode.day => DateFormat.MMMEd(locale).format(_focus),
      CalendarViewMode.week => '${DateFormat.yMMM(locale).format(weekStart(_focus))} · '
          '${l.calendarWeekNumber(isoWeek(_focus))}',
      CalendarViewMode.month => DateFormat.yMMMM(locale).format(_focus),
    };
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final labels = {
      CalendarViewMode.day: (l.calendarViewDay, Icons.view_day_outlined),
      CalendarViewMode.week: (l.calendarViewWeek, Icons.view_week_outlined),
      CalendarViewMode.month: (l.calendarViewMonth, Icons.calendar_view_month_outlined),
      CalendarViewMode.agenda: (l.calendarViewAgenda, Icons.view_agenda_outlined),
    };
    return Scaffold(
      appBar: AppBar(
        title: Text(_title(context)),
        actions: [
          IconButton(
            key: const Key('calendar-table'),
            tooltip: l.calendarTableOpen,
            icon: const Icon(Icons.table_restaurant_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => CalendarTablePage(controller: widget.steuerung))),
          ),
          IconButton(
            key: const ValueKey('calendar-today'),
            tooltip: l.calendarToday,
            icon: const Icon(Icons.today_outlined),
            onPressed: () => setState(() => _focus = tagVon(widget.steuerung.jetzt)),
          ),
          PopupMenuButton<CalendarViewMode>(
            key: const ValueKey('calendar-mode'),
            tooltip: l.calendarViewSwitch,
            icon: Icon(labels[_mode]!.$2),
            initialValue: _mode,
            onSelected: _setMode,
            itemBuilder: (_) => [
              for (final MapEntry(key: m, value: (text, icon)) in labels.entries)
                PopupMenuItem(
                  key: ValueKey('calendar-mode-${m.name}'),
                  value: m,
                  child: Row(children: [Icon(icon, size: 20), const SizedBox(width: 12), Text(text)]),
                ),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        tooltip: 'Neuer Termin',
        onPressed: () => _neu(day: _mode == CalendarViewMode.agenda ? null : _focus),
        child: const Icon(Icons.add),
      ),
      body: ListenableBuilder(
        listenable: widget.steuerung,
        builder: (context, _) {
          final s = widget.steuerung;
          if (_mode == CalendarViewMode.agenda) return _agenda(context);
          if (!identical(_source?.kalender, s.kalender)) _source = KalenderItemSource(s.kalender);
          return RefreshIndicator(
            onRefresh: () async {
              await widget.abgleichen?.call();
              await s.laden();
            },
            // Only the grid's own vertical scroll pulls to refresh.
            notificationPredicate: (n) => n.depth == 1 && n.metrics.axis == Axis.vertical,
            child: CalendarPager(
              mode: _mode,
              focus: _focus,
              source: _source!,
              now: s.jetzt,
              onFocusChanged: (d) => setState(() => _focus = d),
              onDayOpen: (d) => _openDay(d),
              onItemTap: (i) {
                final v = i.payload;
                if (v is Vorkommen) showOccurrenceDetails(context, v, s.kalender);
              },
              onSlotTap: (at, {required allDay}) => _neu(
                  day: tagVon(at),
                  start: allDay ? null : TimeOfDay(hour: at.hour, minute: at.minute),
                  allDay: allDay),
            ),
          );
        },
      ),
    );
  }

  void _openDay(DateTime d) => setState(() {
        _focus = d;
        _mode = CalendarViewMode.day;
      });

  Widget _agenda(BuildContext context) {
    final s = widget.steuerung;
    final jetzt = s.jetzt;
    final heute = tagVon(jetzt);
    final tage = s.kalender.vorkommen(heute, heute.add(const Duration(days: _tageZeigen - 1)));
    final kinder = <Widget>[];
    for (var i = 0; i < _tageZeigen; i++) {
      final tag = heute.add(Duration(days: i));
      final l = [for (final v in tage[isoTag(tag)] ?? const <Vorkommen>[]) if (!v.versteckt) v];
      if (l.isEmpty && i > 0) continue;
      kinder.add(_TagKopf(tag: tag, heute: heute));
      final rhythmus = [for (final v in l) if (v.ebene == ebeneRhythmus) v];
      final rest = [for (final v in l) if (v.ebene != ebeneRhythmus) v];
      if (rest.isEmpty) {
        kinder.add(Padding(
          padding: const EdgeInsets.fromLTRB(20, 2, 16, 6),
          child: Text('nichts eingetragen', style: _leise(context)),
        ));
      }
      for (final v in rest) {
        kinder.add(_Zeile(v: v, kalender: s.kalender, jetzt: jetzt));
      }
      if (rhythmus.isNotEmpty) kinder.add(_Rhythmus(l: rhythmus, kalender: s.kalender));
    }
    if (s.kalender.istLeer) {
      kinder.add(Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
            'Noch kein Kalender auf dem Handy. Er kommt über die Mitte, sobald du '
            'angemeldet bist und ein Rechner den Kalender in die Cloud gibt.',
            style: _leise(context)),
      ));
    }
    kinder.add(const SizedBox(height: 88));
    return RefreshIndicator(
      onRefresh: () async {
        await widget.abgleichen?.call();
        await s.laden();
      },
      child: ListView(physics: const AlwaysScrollableScrollPhysics(), children: kinder),
    );
  }
}

/// ISO 8601 week number.
int isoWeek(DateTime d) {
  final thursday = addDays(dayOf(d), 4 - d.weekday);
  return daysBetween(DateTime.utc(thursday.year), thursday) ~/ 7 + 1;
}

TextStyle _leise(BuildContext context) => TextStyle(
    fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant);

class _TagKopf extends StatelessWidget {
  const _TagKopf({required this.tag, required this.heute});
  final DateTime tag, heute;

  @override
  Widget build(BuildContext context) {
    final d = tag.difference(heute).inDays;
    final vorn = d == 0 ? 'Heute' : d == 1 ? 'Morgen' : _wt[tag.weekday - 1];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 4),
      child: Text('$vorn · ${tag.day}.${tag.month}.',
          style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
    );
  }
}

class _Zeile extends StatelessWidget {
  const _Zeile({required this.v, required this.kalender, required this.jetzt});
  final Vorkommen v;
  final Kalender kalender;
  final DateTime jetzt;

  @override
  Widget build(BuildContext context) {
    final schema = Theme.of(context).colorScheme;
    final vielleicht = v.ebene == ebeneVielleicht;
    final farbe = ebenenFarbe(context, kalender, v.ebene);
    final zeit = v.zeit == null ? 'ganztags' : v.zeit!;
    final unten = <Widget>[];
    if (v.ort != null) unten.add(Text(v.ort!, style: _leise(context)));
    if (v.deadline) {
      final s = v.sollBeginn;
      if (s != null) {
        unten.add(Text(
            'Soll ${_wt[s.weekday - 1].substring(0, 2)} ${s.day}.${s.month}. '
            '${s.hour.toString().padLeft(2, '0')}:${s.minute.toString().padLeft(2, '0')} · Muss $zeit',
            style: _leise(context)));
      }
      if (v.sollVerpasst(jetzt)) {
        unten.add(Text('soll verpasst', style: TextStyle(fontSize: 13, color: schema.error, fontWeight: FontWeight.w600)));
      }
    }
    if (v.wartet) {
      unten.add(Row(children: [
        Icon(Icons.cloud_upload_outlined, size: 14, color: schema.onSurfaceVariant),
        const SizedBox(width: 4),
        Text('wartet auf Abgleich', style: _leise(context)),
      ]));
    }
    final titel = Text(
      v.deadline ? '⚑ ${v.label}' : v.label,
      style: TextStyle(
        fontSize: 15,
        fontStyle: vielleicht ? FontStyle.italic : FontStyle.normal,
        color: vielleicht ? schema.onSurfaceVariant : (v.deadline ? schema.error : schema.onSurface),
      ),
    );
    return InkWell(
      onTap: () => _ansehen(context),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
        child: IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            SizedBox(
              width: 64,
              child: Text(v.ende != null && v.zeit != null ? '$zeit\n${v.ende}' : zeit,
                  style: _leise(context).copyWith(height: 1.3)),
            ),
            Container(
              width: 3,
              margin: const EdgeInsets.only(right: 10),
              decoration: BoxDecoration(
                color: vielleicht ? null : farbe,
                border: vielleicht ? Border.all(color: farbe, width: 1) : null,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [titel, ...unten]),
            ),
          ]),
        ),
      ),
    );
  }

  void _ansehen(BuildContext context) => showOccurrenceDetails(context, v, kalender);
}

/// The detail sheet of one occurrence (agenda and the grid views).
void showOccurrenceDetails(BuildContext context, Vorkommen v, Kalender kalender) {
  final ebene = kalender.ebene(v.ebene)?.titel ?? v.ebene;
  showModalBottomSheet<void>(
    context: context,
    builder: (_) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(v.label, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Text('${v.tag.day}.${v.tag.month}.${v.tag.year} · ${v.zeit ?? 'ganztags'}'
            '${v.ende != null ? '–${v.ende}' : ''} · $ebene${v.serie ? ' · wiederkehrend' : ''}'),
        if (v.ort != null) Text(v.ort!),
        const SizedBox(height: 14),
        Text(
            v.wartet
                ? 'Am Handy eingetragen — kommt mit dem nächsten Abgleich auf die Rechner.'
                : 'Ändern und Löschen geht am Handy noch nicht — das kommt als nächster Schritt. '
                    'Bis dahin am Rechner.',
            style: _leise(context)),
      ]),
    ),
  );
}

class _Rhythmus extends StatelessWidget {
  const _Rhythmus({required this.l, required this.kalender});
  final List<Vorkommen> l;
  final Kalender kalender;

  @override
  Widget build(BuildContext context) {
    final text = l.map((v) => '${v.label} ${v.zeit ?? ''}${v.ende != null ? '–${v.ende}' : ''}').join(' · ');
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 2, 16, 4),
      child: Row(children: [
        const SizedBox(width: 64),
        Icon(Icons.waves, size: 14, color: ebenenFarbe(context, kalender, ebeneRhythmus)),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: _leise(context).copyWith(fontSize: 12))),
      ]),
    );
  }
}
