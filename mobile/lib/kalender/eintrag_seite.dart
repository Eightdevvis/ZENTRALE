// Neuer Termin: Titel, Tag, Beginn oder ganztägig, Dauer, Ebene (Vorgabe
// „termine“). Mehr nicht — der Rest (Ort, Wiederholung, Deadline) kommt,
// wenn das Handy auch ändern darf (nächster Schritt).

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import 'event_edit.dart';
import 'kalender.dart';
import 'kalender_steuerung.dart';
import 'regel.dart';
import 'termin_schreiben.dart';

const dauern = [15, 30, 45, 60, 90, 120, 180, 240];

String dauerText(int min) => min < 60
    ? '$min min'
    : min % 60 == 0
        ? '${min ~/ 60} h'
        : '${min ~/ 60} h ${min % 60} min';

/// Ende aus Beginn und Dauer — oder null, wenn es über Mitternacht ginge
/// (ein Termin endet am selben Tag; „24:00“ ist erlaubt).
String? endeAus(TimeOfDay beginn, int minuten) {
  final e = beginn.hour * 60 + beginn.minute + minuten;
  if (e > 24 * 60) return null;
  return '${(e ~/ 60).toString().padLeft(2, '0')}:${(e % 60).toString().padLeft(2, '0')}';
}

class EintragSeite extends StatefulWidget {
  const EintragSeite({
    super.key,
    required this.steuerung,
    this.initialDay,
    this.initialStart,
    this.initialAllDay = false,
    this.editing,
  });
  final KalenderSteuerung steuerung;

  /// Prefill from a tapped slot in the day/week grid (or a month day).
  final DateTime? initialDay;
  final TimeOfDay? initialStart;
  final bool initialAllDay;

  /// Edit this existing occurrence instead of entering a new event
  /// (series: the whole series; its first day stays).
  final Vorkommen? editing;

  @override
  State<EintragSeite> createState() => _EintragSeiteState();
}

class _EintragSeiteState extends State<EintragSeite> {
  late final _titel = TextEditingController(text: widget.editing?.label);
  late final _place = TextEditingController(text: widget.editing?.ort);
  late DateTime _tag = tagVon(widget.editing?.tag ?? widget.initialDay ?? widget.steuerung.jetzt);
  late bool _ganztags = widget.editing == null ? widget.initialAllDay : widget.editing!.zeit == null;
  late TimeOfDay _beginn = _timeOf(widget.editing?.zeit) ??
      widget.initialStart ??
      TimeOfDay(hour: (widget.steuerung.jetzt.hour + 1) % 24, minute: 0);
  late int _dauer = _durationOf(widget.editing) ?? 60;
  late String _ebene = widget.editing?.ebene ?? ebeneTermine;

  static TimeOfDay? _timeOf(String? hhmm) {
    final m = RegExp(r'^(\d\d):(\d\d)$').firstMatch(hhmm ?? '');
    return m == null ? null : TimeOfDay(hour: int.parse(m.group(1)!), minute: int.parse(m.group(2)!));
  }

  static int? _durationOf(Vorkommen? v) {
    final s = _timeOf(v?.zeit), e = v?.ende == '24:00' ? const TimeOfDay(hour: 24, minute: 0) : _timeOf(v?.ende);
    if (s == null || e == null) return null;
    final d = e.hour * 60 + e.minute - s.hour * 60 - s.minute;
    return d > 0 ? d : null;
  }
  String? _fehler;
  bool _speichert = false;

  @override
  void dispose() {
    _titel.dispose();
    _place.dispose();
    super.dispose();
  }

  String _hhmm(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  Future<void> _speichern() async {
    setState(() => _fehler = null);
    final titel = _titel.text.trim();
    if (titel.isEmpty) return setState(() => _fehler = 'Bitte einen Titel eingeben.');
    String? zeit, ende;
    if (!_ganztags) {
      zeit = _hhmm(_beginn);
      ende = endeAus(_beginn, _dauer);
      if (ende == null) return setState(() => _fehler = 'Der Termin muss vor Mitternacht enden.');
    }
    setState(() => _speichert = true);
    try {
      final v = widget.editing;
      if (v != null) {
        await widget.steuerung.change(
            v,
            EventChange(
                title: titel, place: _place.text, day: _tag, start: zeit, end: ende, allDay: _ganztags),
            layer: _ebene == v.ebene ? null : _ebene);
        if (mounted) Navigator.of(context).pop();
        return;
      }
      await widget.steuerung.eintragen(NeuerTermin(titel: titel, tag: _tag, zeit: zeit, ende: ende), ebene: _ebene);
      if (mounted) Navigator.of(context).pop();
    } on TerminFehler catch (e) {
      setState(() => _fehler = e.meldung);
    } on EditError catch (e) {
      setState(() => _fehler = e.message);
    } finally {
      if (mounted) setState(() => _speichert = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ebenen = widget.steuerung.ebenenZumEintragen;
    final namen = ebenen.isEmpty ? [ebeneTermine] : [for (final e in ebenen) e.name];
    if (!namen.contains(_ebene)) _ebene = namen.first;
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.editing == null ? 'Neuer Termin' : AppLocalizations.of(context).calendarEditTitle)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          controller: _titel,
          autofocus: true,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Titel'),
        ),
        if (widget.editing != null) ...[
          const SizedBox(height: 12),
          TextField(
            controller: _place,
            decoration: InputDecoration(
                border: const OutlineInputBorder(), labelText: AppLocalizations.of(context).calendarPlace),
          ),
        ],
        if (widget.editing?.serie == true) ...[
          const SizedBox(height: 8),
          Text(AppLocalizations.of(context).calendarSeriesHint,
              style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ],
        const SizedBox(height: 12),
        if (widget.editing?.serie != true) ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.event),
          title: Text('${_tag.day}.${_tag.month}.${_tag.year}'),
          onTap: () async {
            final d = await showDatePicker(
                context: context,
                initialDate: DateTime(_tag.year, _tag.month, _tag.day),
                firstDate: DateTime(_tag.year - 1),
                lastDate: DateTime(_tag.year + 5));
            if (d != null) setState(() => _tag = DateTime.utc(d.year, d.month, d.day));
          },
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Ganztägig'),
          value: _ganztags,
          onChanged: (w) => setState(() => _ganztags = w),
        ),
        if (!_ganztags) ...[
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.schedule),
            title: Text('Beginn ${_hhmm(_beginn)}'),
            onTap: () async {
              final t = await showTimePicker(context: context, initialTime: _beginn);
              if (t != null) setState(() => _beginn = t);
            },
          ),
          DropdownButtonFormField<int>(
            initialValue: _dauer,
            decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Dauer'),
            items: [
              for (final d in {...dauern, _dauer}.toList()..sort())
                DropdownMenuItem(value: d, child: Text(dauerText(d))),
            ],
            onChanged: (d) => setState(() => _dauer = d ?? 60),
          ),
        ],
        const SizedBox(height: 16),
        if (namen.length > 1)
          SegmentedButton<String>(
            segments: [
              for (final n in namen)
                ButtonSegment(value: n, label: Text(widget.steuerung.kalender.ebene(n)?.titel ?? n)),
            ],
            selected: {_ebene},
            onSelectionChanged: (s) => setState(() => _ebene = s.first),
          ),
        if (_fehler != null) ...[
          const SizedBox(height: 12),
          Text(_fehler!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: 20),
        FilledButton(
            onPressed: _speichert ? null : _speichern,
            child: Text(widget.editing == null ? 'Eintragen' : AppLocalizations.of(context).calendarSave)),
        const SizedBox(height: 8),
        Text(AppLocalizations.of(context).calendarProposalHint,
            style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ]),
    );
  }
}
