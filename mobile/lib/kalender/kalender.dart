// Der Kalender des Handys: liest data/kalender/** aus der Ablage (kommt über
// die Mitte) und rechnet die Vorkommen eines Zeitraums — dieselbe Regel wie
// core/kalender.entries_in_range (Einmal-Termine, Spannen über Tage,
// Routinen mit Aus-Tagen, Pausen, verschobenen Vorkommen; Deadlines mit
// Soll-Zeit). Die Seiten zeichnen nur, was hier steht.
//
// Die Ebene ist der Ordner, kein Feld (data/kalender/<ebene>/*.ics, dazu die
// vdir-Dateien „color“ und „displayname“). Ein Termin, den das Handy selbst
// vorgeschlagen hat und der noch nicht aus der Mitte zurück ist, trägt
// [Vorkommen.wartet] („wartet auf Abgleich“).

import '../ablage/ablage.dart';
import 'colours.dart';
import 'regel.dart';
import 'termin_lesen.dart';

const kalenderOrdner = 'kalender';
const ebeneRhythmus = 'rhythmus';
const ebeneTermine = 'termine';
const ebeneVielleicht = 'uncommitted';

/// Wie kalender_deadline.SOLL_HOECHSTENS: Soll höchstens 28 Tage vor Muss.
const sollHoechstens = 28 * 24 * 60;

/// Reihenfolge der bekannten Ebenen (fest zugesagt, dann Optionen, dann Rhythmus).
const ebenenReihe = [ebeneTermine, ebeneVielleicht, ebeneRhythmus];

class Ebene {
  Ebene(this.name, {this.titel, this.farbe});
  final String name;
  final String? titel;

  /// vdir „color“, z. B. "#3b82f6" — oder null.
  final String? farbe;
}

class Vorkommen {
  Vorkommen({
    required this.tag,
    required this.ebene,
    required this.kennung,
    required this.label,
    this.zeit,
    this.ende,
    this.ort,
    this.versteckt = false,
    this.deadline = false,
    this.vorwarnung,
    this.sollZeit,
    this.ueberNacht = false,
    this.motiv,
    this.absageNoetig = false,
    this.erinnerungen = const [],
    this.wartet = false,
    this.serie = false,
    this.switchedOff = false,
    this.colour = const ResolvedColour(source: 'layer'),
    this.groupColourKey,
    DateTime? occurrenceDay,
  }) : occurrenceDay = occurrenceDay ?? tag;

  final DateTime tag;
  final String ebene;
  final String? kennung;
  final String label;

  /// "HH:MM" oder null (ganztägig).
  final String? zeit;
  final String? ende;
  final String? ort;

  /// Einzeln abgeschaltet (X-ZENTRALE-AUS/EXDATE/abgesagt) oder in einer
  /// Pause — wird nicht gezeigt und erinnert nicht.
  final bool versteckt;
  final bool deadline;
  final int? vorwarnung;

  /// Soll-Zeit dieses Vorkommens "YYYY-MM-DDTHH:MM" (nur Deadlines mit Soll).
  final String? sollZeit;
  final bool ueberNacht;
  final String? motiv;
  final bool absageNoetig;
  final List<Erinnerung> erinnerungen;
  final bool wartet;

  /// Aus einer Regel (Routine) — am Handy nicht einzeln änderbar.
  final bool serie;

  /// Hidden because this one occurrence was switched off (X-ZENTRALE-AUS /
  /// EXDATE) — not a pause, not cancelled. Can be switched back on.
  final bool switchedOff;

  /// The series day this occurrence belongs to (before a moved occurrence's
  /// new day) — the key for EXDATE / X-ZENTRALE-AUS.
  final DateTime occurrenceDay;

  /// Where this occurrence's colour comes from (colours.dart, same rule as
  /// core/calendar_colours.py): own style, span, course slot or layer.
  final ResolvedColour colour;

  /// Group key ("gruppe:uni") — for views that group like the TUI's month.
  final String? groupColourKey;

  /// Beginn als Ortszeit (UTC-Träger); ganztägig = Mitternacht.
  DateTime get beginn {
    final z = _minuten(zeit);
    return tag.add(Duration(minutes: z ?? 0));
  }

  /// Muss-Zeit einer Deadline = der Beginn.
  DateTime? get sollBeginn {
    final s = sollZeit;
    if (s == null) return null;
    return DateTime.utc(int.parse(s.substring(0, 4)), int.parse(s.substring(5, 7)),
        int.parse(s.substring(8, 10)), int.parse(s.substring(11, 13)), int.parse(s.substring(14, 16)));
  }

  /// Soll vorbei, Muss noch nicht (tui/ansichten/kalender_deadline.py „soll verpasst“).
  bool sollVerpasst(DateTime jetzt) {
    final s = sollBeginn;
    return deadline && s != null && !jetzt.isBefore(s) && jetzt.isBefore(beginn);
  }

  DateTime? get endeZeit {
    final e = _minuten(ende);
    if (e == null) return null;
    return tag.add(Duration(minutes: e, days: ueberNacht ? 1 : 0));
  }
}

int? _minuten(String? hhmm) {
  final m = RegExp(r'^(\d{1,2})(?::(\d\d))?$').firstMatch(hhmm ?? '');
  if (m == null) return null;
  return int.parse(m.group(1)!) * 60 + int.parse(m.group(2) ?? '0');
}

/// Ein Stück mit seiner Ebene und Datei.
class _Eintrag {
  _Eintrag(this.ebene, this.pfad, this.stueck);
  final String ebene, pfad;
  final Stueck stueck;
}

class Kalender {
  Kalender._(this.ebenen, this._eintraege, this._wartend, [this.colourTable = const {}]);

  final List<Ebene> ebenen;

  /// The synced course colour table (data/calendar_colours.json, written by
  /// the computers — the phone only reads it).
  final Map<String, int> colourTable;
  final List<_Eintrag> _eintraege;
  final Set<String> _wartend;

  static Kalender get leer => Kalender._([], [], {});

  /// Alle UIDs (für neue Termine: nie eine doppelt).
  Set<String> get uids => {for (final e in _eintraege) e.stueck.uid};

  bool get istLeer => _eintraege.isEmpty;

  /// Aus der Ablage laden. [wartend] = Ablage-Pfade eigener Vorschläge, die
  /// die Mitte noch nicht bestätigt hat (Abgleich.wartend).
  static Future<Kalender> laden(Ablage ablage, {Set<String> wartend = const {}}) async {
    final namen = <String>{};
    final eintraege = <_Eintrag>[];
    final dateien = await ablage.alleDateien(kalenderOrdner)
      ..sort();
    for (final pfad in dateien) {
      final teile = pfad.split('/');
      if (teile.length != 3) continue;
      namen.add(teile[1]);
      if (!pfad.endsWith('.ics') || teile[2].startsWith('.')) continue;
      final text = await ablage.lesen(pfad);
      if (text == null) continue;
      try {
        for (final s in stueckeLesen(text)) {
          // UID doppelt (wie im Kern): die zweite wird übergangen.
          if (eintraege.any((e) => e.stueck.uid == s.uid)) continue;
          eintraege.add(_Eintrag(teile[1], pfad, s));
        }
      } catch (_) {
        continue; // kaputte Datei: nicht anzeigen, nie anfassen
      }
    }
    final reihe = [
      ...ebenenReihe.where(namen.contains),
      ...(namen.difference(ebenenReihe.toSet()).toList()..sort()),
    ];
    final ebenen = <Ebene>[];
    for (final n in reihe) {
      final titel = (await ablage.lesen('$kalenderOrdner/$n/displayname'))?.trim();
      final farbe = (await ablage.lesen('$kalenderOrdner/$n/color'))?.trim();
      ebenen.add(Ebene(n,
          titel: titel == null || titel.isEmpty ? null : titel,
          farbe: farbe == null || farbe.isEmpty ? null : farbe));
    }
    final table = parseTable(await ablage.lesen(tableFile));
    return Kalender._(ebenen, eintraege, wartend, table);
  }

  /// Ablage path of the file holding [uid] (null = unknown).
  String? pathOf(String uid) => _eintraege.where((e) => e.stueck.uid == uid).firstOrNull?.pfad;

  /// The parsed entry of [uid]: its kind ('termin' | 'routine') and data.
  Stueck? entryOf(String uid) => _eintraege.where((e) => e.stueck.uid == uid).firstOrNull?.stueck;

  Ebene? ebene(String name) => ebenen.where((e) => e.name == name).firstOrNull;

  /// Alle Vorkommen in [von, bis] (Tage, inklusive) — auch die versteckten
  /// (für Prüfung und „fällt aus“); Anzeigen filtern sie weg.
  Map<String, List<Vorkommen>> vorkommen(DateTime von, DateTime bis) {
    von = tagVon(von);
    bis = tagVon(bis);
    final pausen = [for (final e in _eintraege) ...e.stueck.pausen];
    final raus = <String, List<Vorkommen>>{};
    void dazu(String tag, Vorkommen v) => raus.putIfAbsent(tag, () => []).add(v);

    for (final ebene in ebenen) {
      for (final e in _eintraege.where((e) => e.ebene == ebene.name)) {
        final s = e.stueck, d = s.daten;
        final wartet = _wartend.contains(e.pfad);
        if (s.art == 'termin') {
          final d0 = isoTagLesen(d['tag'] as String?);
          if (d0 == null) continue;
          final bisS = d['bis'] as String?;
          if (bisS != null) {
            var d1 = isoTagLesen(bisS) ?? d0;
            if (d1.isBefore(d0)) d1 = d0;
            final times = (d['times'] as Map?) ?? const {};
            final enden = (d['enden'] as Map?) ?? const {};
            for (var cur = d0.isAfter(von) ? d0 : von;
                !cur.isAfter(d1.isBefore(bis) ? d1 : bis);
                cur = cur.add(const Duration(days: 1))) {
              final ci = isoTag(cur);
              dazu(ci, _bauen(ebene.name, s, cur, d, zeit: times[ci] as String?,
                  ende: enden[ci] as String?, wartet: wartet));
            }
          } else if (!d0.isBefore(von) && !d0.isAfter(bis)) {
            dazu(isoTag(d0), _bauen(ebene.name, s, d0, d,
                zeit: d['time'] as String?, ende: d['ende'] as String?, wartet: wartet));
          }
          continue;
        }
        List<DateTime> tage;
        try {
          tage = routinenTage(s, von, bis);
        } catch (_) {
          continue; // Regel unlesbar: wie im Kern übergangen
        }
        final aus = {...((d['aus'] as List?) ?? const []).map((x) => '$x')};
        for (final occ in tage) {
          var tag = isoTag(occ);
          final paused = _pausiert(s, occ, pausen);
          final off = aus.contains(tag) && !paused;
          var versteckt = aus.contains(tag) || paused;
          String? zeit = d['time'] as String?, ende = d['ende'] as String?,
              label = d['label'] as String?, ort = d['ort'] as String?;
          final ab = s.abweichungen[tag];
          var cancelled = false;
          if (ab != null) {
            if (ab.entfaellt) {
              versteckt = true;
              cancelled = true;
            } else {
              tag = ab.tag ?? tag;
              final t = isoTagLesen(tag);
              if (t == null || t.isBefore(von) || t.isAfter(bis)) continue;
              zeit = ab.zeit ?? zeit;
              ende = ab.ende ?? ende;
              label = ab.label ?? label;
              ort = ab.ort ?? ort;
            }
          }
          dazu(tag, _bauen(ebene.name, s, isoTagLesen(tag)!, d,
              zeit: zeit, ende: ende, label: label, ort: ort, versteckt: versteckt,
              wartet: wartet, serie: true, switchedOff: off && !cancelled, occurrenceDay: occ));
        }
      }
    }
    for (final l in raus.values) {
      _stabilSortieren(l);
    }
    return Map.fromEntries(raus.entries.toList()..sort((a, b) => a.key.compareTo(b.key)));
  }

  /// Wie Pythons stabiles sort nach time (ohne Zeit = "00:00").
  static void _stabilSortieren(List<Vorkommen> l) {
    final mitNr = [for (final (i, v) in l.indexed) (i, v)];
    mitNr.sort((a, b) {
      final c = (a.$2.zeit ?? '00:00').compareTo(b.$2.zeit ?? '00:00');
      return c != 0 ? c : a.$1.compareTo(b.$1);
    });
    l
      ..clear()
      ..addAll(mitNr.map((x) => x.$2));
  }

  /// kalender_konflikte._pause_grund: mit routine_uid über die Kennung,
  /// sonst über den gleichen Titel — Ebenen-übergreifend.
  static bool _pausiert(Stueck s, DateTime tag, List<Pause> pausen) {
    for (final p in pausen) {
      if (p.routineUid != null) {
        if (p.routineUid != s.uid) continue;
      } else if (p.label != s.label) {
        continue;
      }
      if (!tag.isBefore(p.von) && !tag.isAfter(p.bis)) return true;
    }
    return false;
  }

  Vorkommen _bauen(String ebene, Stueck s, DateTime tag, Map<String, Object?> d,
      {String? zeit, String? ende, String? label, String? ort, bool versteckt = false,
      bool wartet = false, bool serie = false, bool switchedOff = false, DateTime? occurrenceDay}) {
    final deadline = d['typ'] == 'deadline';
    String? sollZeit;
    final soll = d['soll_abstand'];
    final z = _minuten(zeit);
    if (deadline && soll is int && soll <= 0 && soll >= -sollHoechstens && z != null) {
      final t = tag.add(Duration(minutes: z + soll));
      sollZeit = '${isoTag(t)}T${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    }
    final ueberNacht = ebene == ebeneRhythmus && zeit != null && ende != null &&
        zeit.length == 5 && ende.length == 5 && ende.compareTo(zeit) < 0;
    final shownLabel = label ?? (d['label'] as String?) ?? '';
    final bis = d['bis'] as String?;
    final span = s.art == 'termin' && bis != null && bis != d['tag'];
    final colour = ResolvedColour.resolve(
        s.colour.style, entryKey(shownLabel, s.colour.sourceId), colourTable, span: span);
    return Vorkommen(
      tag: tag, ebene: ebene, kennung: s.uid, label: shownLabel,
      zeit: zeit, ende: ende, ort: ort ?? d['ort'] as String?, versteckt: versteckt,
      deadline: deadline, vorwarnung: d['vorwarnung'] as int?, sollZeit: sollZeit,
      ueberNacht: ueberNacht, motiv: d['motiv'] as String?,
      absageNoetig: d['absage_noetig'] == true, erinnerungen: s.erinnerungen,
      wartet: wartet, serie: serie, switchedOff: switchedOff, occurrenceDay: occurrenceDay,
      colour: colour, groupColourKey: s.colour.groupKey,
    );
  }
}
