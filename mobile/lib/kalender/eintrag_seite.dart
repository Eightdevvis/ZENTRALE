// Neuer Termin: Titel, Tag, Beginn oder ganztägig, Dauer, Ebene (Vorgabe
// „termine“). Mehr nicht — der Rest (Ort, Wiederholung, Deadline) kommt,
// wenn das Handy auch ändern darf (nächster Schritt).

import 'package:flutter/material.dart';

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
  const EintragSeite({super.key, required this.steuerung});
  final KalenderSteuerung steuerung;

  @override
  State<EintragSeite> createState() => _EintragSeiteState();
}

class _EintragSeiteState extends State<EintragSeite> {
  final _titel = TextEditingController();
  late DateTime _tag = tagVon(widget.steuerung.jetzt);
  bool _ganztags = false;
  late TimeOfDay _beginn = TimeOfDay(hour: (widget.steuerung.jetzt.hour + 1) % 24, minute: 0);
  int _dauer = 60;
  String _ebene = ebeneTermine;
  String? _fehler;
  bool _speichert = false;

  @override
  void dispose() {
    _titel.dispose();
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
      await widget.steuerung.eintragen(NeuerTermin(titel: titel, tag: _tag, zeit: zeit, ende: ende), ebene: _ebene);
      if (mounted) Navigator.of(context).pop();
    } on TerminFehler catch (e) {
      setState(() => _fehler = e.meldung);
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
      appBar: AppBar(title: const Text('Neuer Termin')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          controller: _titel,
          autofocus: true,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Titel'),
        ),
        const SizedBox(height: 12),
        ListTile(
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
              for (final d in dauern)
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
        FilledButton(onPressed: _speichert ? null : _speichern, child: const Text('Eintragen')),
        const SizedBox(height: 8),
        Text('Der Termin steht sofort hier und geht beim nächsten Abgleich als Vorschlag '
            'an die Rechner. Ändern und Löschen kommt später.',
            style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ]),
    );
  }
}
