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

import 'package:flutter/material.dart';

import '../dienste.dart';
import '../thema/farben.dart';
import 'eintrag_seite.dart';
import 'kalender.dart';
import 'kalender_steuerung.dart';
import 'regel.dart';

/// Für die Liste `bereiche` auf der Startseite.
Widget kalenderSeite(BuildContext context) {
  final d = Dienste.von(context);
  return KalenderSeite(steuerung: d.kalender, abgleichen: d.abgleich.jetzt);
}

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
  const KalenderSeite({super.key, required this.steuerung, this.abgleichen});
  final KalenderSteuerung steuerung;
  final Future<void> Function()? abgleichen;

  @override
  State<KalenderSeite> createState() => _KalenderSeiteState();
}

class _KalenderSeiteState extends State<KalenderSeite> {
  @override
  void initState() {
    super.initState();
    widget.steuerung.laden();
  }

  Future<void> _neu() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => EintragSeite(steuerung: widget.steuerung)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Kalender')),
      floatingActionButton: FloatingActionButton(
        tooltip: 'Neuer Termin',
        onPressed: _neu,
        child: const Icon(Icons.add),
      ),
      body: ListenableBuilder(
        listenable: widget.steuerung,
        builder: (context, _) {
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
        },
      ),
    );
  }
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

  void _ansehen(BuildContext context) {
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
