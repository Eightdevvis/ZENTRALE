// Eine .ics-Datei → Stücke (je UID eins) mit derselben Bedeutung wie im Kern
// (core/kalender_ics_abbildung.lesen/_stueck_lesen). Ein Stück ist ein
// Einmal-Termin, eine Spanne über Tage oder eine Routine (RRULE) — die Art
// steht in X-ZENTRALE-ART, oder sie wird geraten wie im Kern (Google, khal).
//
// Nur Lesen: das Handy ändert keine vorhandenen Termine (nächster Schritt,
// memory/betrieb/abgleich_fremde_knoten.md, Termin-Vorschläge). Was ZENTRALE an einem
// Termin nicht verwaltet (DESCRIPTION, fremde VALARM), bleibt in der Datei.

import 'dart:convert';

import 'ics.dart';
import 'regel.dart';
import 'zeit.dart';

const artTermin = 'TERMIN', artSpanne = 'SPANNE', artRoutine = 'ROUTINE';
const alarmText = 'Deadline: ';

/// Eine Erinnerung aus einem VALARM: relativ zum Beginn (Minuten davor,
/// negativ = danach) oder ein fester Zeitpunkt (Ortszeit).
class Erinnerung {
  const Erinnerung({this.minutenVorher, this.absolut, this.text, this.vomEnde = false});
  final int? minutenVorher;

  /// TRIGGER;RELATED=END: [minutenVorher] zählt vom Ende statt vom Beginn.
  final bool vomEnde;
  final DateTime? absolut;
  final String? text;
}

class Abweichung {
  Abweichung({this.entfaellt = false, this.tag, this.zeit, this.ende, this.label, this.ort});
  final bool entfaellt;
  final String? tag, zeit, ende, label, ort;
}

class Pause {
  Pause(this.label, this.von, this.bis, this.grund, this.routineUid);
  final String? label, grund, routineUid;
  final DateTime von, bis;
}

class Stueck {
  Stueck({required this.uid, required this.art, required this.daten});
  final String uid;

  /// 'termin' (auch Spannen: dann mit [bis]) oder 'routine' — wie im Kern.
  final String art;

  /// label, ort, time, ende, typ, vorwarnung, soll_abstand, motiv,
  /// absage_noetig; Termin: tag (+ bis, times, enden); Routine: rrule, seit, aus.
  final Map<String, Object?> daten;
  final List<Erinnerung> erinnerungen = [];
  final Map<String, Abweichung> abweichungen = {};
  final List<Pause> pausen = [];

  String? get label => daten['label'] as String?;
}

Object? _xLesen(String? wert) {
  if (wert == null) return null;
  try {
    if (wert.startsWith('b64:')) {
      return jsonDecode(utf8.decode(base64Url.decode(_auffuellen(wert.substring(4)))));
    }
    return jsonDecode(wert);
  } catch (_) {
    return null;
  }
}

String _auffuellen(String s) => s + '=' * ((4 - s.length % 4) % 4);

IcsZeit? _zeit(IcsProperty? p) => p == null ? null : zeitLesen(p.wert, tzid: p.param('TZID'));

/// Alle Stücke einer Datei. Kaputte Stücke fallen weg (wie im Kern).
List<Stueck> stueckeLesen(String text) {
  final kal = icsLesen(text);
  final nachUid = <String, List<IcsKomponente>>{};
  for (final ev in kal.walk('VEVENT')) {
    nachUid.putIfAbsent(ev.prop('UID')?.text ?? '', () => []).add(ev);
  }
  final raus = <Stueck>[];
  for (final MapEntry(key: uid, value: evs) in nachUid.entries) {
    final master = evs.where((e) => e.prop('RECURRENCE-ID') == null).firstOrNull;
    if (master == null || master.prop('DTSTART') == null) continue;
    try {
      final s = _stueck(uid, master, [for (final e in evs) if (e.prop('RECURRENCE-ID') != null) e]);
      if (s != null) raus.add(s);
    } catch (_) {
      continue;
    }
  }
  return raus;
}

Stueck? _stueck(String uid, IcsKomponente master, List<IcsKomponente> abw) {
  var art = (master.prop('X-ZENTRALE-ART')?.text ?? '').toUpperCase();
  final extras = _xLesen(master.prop('X-ZENTRALE-EXTRAS')?.wert);
  final ex = extras is Map ? extras.cast<String, Object?>() : <String, Object?>{};
  final start = _zeit(master.prop('DTSTART'));
  if (start == null) return null;
  final ende = _endeLesen(master, start);
  final rr = master.prop('RRULE')?.wert;
  if (![artTermin, artSpanne, artRoutine].contains(art)) art = _artRaten(start, ende, rr);
  final daten = <String, Object?>{};
  _kopf(master, daten);
  final Stueck s;
  if (art == artRoutine) {
    s = Stueck(uid: uid, art: 'routine', daten: daten);
    _routine(s, master, abw, start, ende, rr ?? '', ex);
  } else {
    s = Stueck(uid: uid, art: 'termin', daten: daten);
    daten['tag'] = isoTag(start.tag);
    if (art == artSpanne) {
      _spanne(s, master, abw, start, ende, rr, ex);
    } else {
      if (!start.ganztags) {
        daten['time'] = hhmm(start.wert);
        final e = _endeText(start, ende);
        if (e != null && daten['typ'] != 'deadline') daten['ende'] = e;
      }
      _rohAnwenden(master, daten);
      _lueckenFuellen(daten, ex);
    }
  }
  s.erinnerungen.addAll(_erinnerungen(master));
  return s;
}

IcsZeit? _endeLesen(IcsKomponente ev, IcsZeit start) {
  final e = _zeit(ev.prop('DTEND'));
  if (e != null) return e;
  final d = ev.prop('DURATION');
  if (d != null) {
    final dauer = dauerLesen(d.wert);
    if (dauer != null) return IcsZeit(start.wert.add(dauer), ganztags: start.ganztags);
  }
  return null;
}

String _artRaten(IcsZeit start, IcsZeit? ende, String? rr) {
  if (rr != null) {
    final teile = <String, String>{
      for (final t in rr.split(';'))
        if (t.contains('=')) t.split('=').first.toUpperCase(): t.split('=').last
    };
    final einfach = teile.keys.every((k) => const {'FREQ', 'COUNT', 'UNTIL', 'INTERVAL', 'WKST'}.contains(k));
    final endlich = teile.containsKey('COUNT') || teile.containsKey('UNTIL');
    if ((teile['FREQ'] ?? '').toUpperCase() == 'DAILY' && einfach && endlich &&
        int.tryParse(teile['INTERVAL'] ?? '1') == 1) {
      return artSpanne;
    }
    return artRoutine;
  }
  if (!start.ganztags) {
    if (ende != null && !ende.ganztags && ende.tag.isAfter(start.tag)) {
      final mitternacht = start.tag.add(const Duration(days: 1));
      return ende.wert == mitternacht ? artTermin : artSpanne;
    }
    return artTermin;
  }
  if (ende != null && ende.wert.difference(start.wert).inDays > 1) return artSpanne;
  return artTermin;
}

void _kopf(IcsKomponente ev, Map<String, Object?> d) {
  final s = ev.prop('SUMMARY')?.text ?? '';
  if (s.isNotEmpty) d['label'] = s;
  final o = ev.prop('LOCATION')?.text ?? '';
  if (o.isNotEmpty) d['ort'] = o;
  if ((ev.prop('X-ZENTRALE-ABSAGE-NOETIG')?.text ?? '').toUpperCase() == 'TRUE') d['absage_noetig'] = true;
  final m = ev.prop('X-ZENTRALE-MOTIV')?.text ?? '';
  if (m.isNotEmpty) d['motiv'] = m;
  if ((ev.prop('X-ZENTRALE-TYP')?.text ?? '').toUpperCase() == 'DEADLINE') {
    d['typ'] = 'deadline';
    final v = _vorwarnungLesen(ev);
    if (v != null) d['vorwarnung'] = v;
    final soll = ev.prop('X-ZENTRALE-SOLL');
    if (soll != null) {
      final dd = dauerLesen(soll.text);
      if (dd != null && dd <= Duration.zero && dd.inSeconds % 60 == 0) d['soll_abstand'] = dd.inMinutes;
    }
  }
}

int? _alarmMinuten(IcsKomponente al) {
  final t = al.prop('TRIGGER');
  if (t == null || (t.param('VALUE') ?? '').toUpperCase() == 'DATE-TIME') return null;
  final d = dauerLesen(t.wert);
  if (d == null || d > Duration.zero) return null;
  if ((t.param('RELATED') ?? 'START').toUpperCase() != 'START') return null;
  return d.inSeconds % 60 == 0 ? -d.inMinutes : null;
}

/// Unsere Vorwarnung: erst die Marke, dann unsere DESCRIPTION, dann der
/// erste relative Alarm — Google wirft X-Felder aus VALARM weg.
int? _vorwarnungLesen(IcsKomponente ev) {
  final alarme = ev.kinder.where((k) => k.name == 'VALARM').toList();
  final wahlen = <bool Function(IcsKomponente)>[
    (a) => (a.prop('X-ZENTRALE-VORWARNUNG')?.text ?? '').toUpperCase() == 'TRUE',
    (a) => (a.prop('DESCRIPTION')?.text ?? '').startsWith(alarmText),
    (a) => true,
  ];
  for (final w in wahlen) {
    for (final a in alarme) {
      if (w(a) && _alarmMinuten(a) != null) return _alarmMinuten(a);
    }
  }
  return null;
}

/// Jeder VALARM wird eine Erinnerung am Handy (relativ zum Beginn, zum Ende
/// oder ein fester Zeitpunkt).
List<Erinnerung> _erinnerungen(IcsKomponente ev) {
  final raus = <Erinnerung>[];
  for (final a in ev.kinder.where((k) => k.name == 'VALARM')) {
    final t = a.prop('TRIGGER');
    if (t == null) continue;
    final text = a.prop('DESCRIPTION')?.text;
    if ((t.param('VALUE') ?? '').toUpperCase() == 'DATE-TIME') {
      final z = zeitLesen(t.wert, tzid: t.param('TZID'));
      if (z != null) raus.add(Erinnerung(absolut: z.wert, text: text));
      continue;
    }
    final d = dauerLesen(t.wert);
    if (d == null) continue;
    raus.add(Erinnerung(minutenVorher: -d.inMinutes, text: text,
        vomEnde: (t.param('RELATED') ?? 'START').toUpperCase() == 'END'));
  }
  return raus;
}

/// Gegenstück zu _ende_text: gleicher Tag, „24:00“ oder über Mitternacht.
String? _endeText(IcsZeit start, IcsZeit? ende) {
  if (start.ganztags || ende == null || ende.ganztags || !ende.wert.isAfter(start.wert)) return null;
  if (ende.tag == start.tag) return hhmm(ende.wert);
  final folgetag = start.tag.add(const Duration(days: 1));
  if (ende.wert == folgetag) return '24:00';
  final ue = ende.wert.hour * 60 + ende.wert.minute;
  final us = start.wert.hour * 60 + start.wert.minute;
  if (ende.tag == folgetag && ue > 0 && ue < us) return hhmm(ende.wert);
  return null;
}

void _rohAnwenden(IcsKomponente ev, Map<String, Object?> d) {
  final roh = _xLesen(ev.prop('X-ZENTRALE-ZEIT-ROH')?.wert);
  if (roh is! Map) return;
  for (final MapEntry(key: pfad, value: paar) in roh.entries) {
    if (paar is! List || paar.length != 2) continue;
    final teile = '$pfad'.split('/');
    if (teile.length == 1) {
      if (d[teile[0]] == paar[1]) d[teile[0]] = paar[0];
    } else {
      final feld = d[teile[0]];
      if (feld is Map && feld[teile[1]] == paar[1]) feld[teile[1]] = paar[0];
    }
  }
}

/// Extras füllen nur Lücken (bei times/enden je Tag).
void _lueckenFuellen(Map<String, Object?> d, Map<String, Object?> ex, [Set<String> tagesfelder = const {}]) {
  for (final MapEntry(key: k, value: v) in ex.entries) {
    if (tagesfelder.contains(k) && v is Map && d[k] is Map) {
      final m = d[k] as Map;
      for (final MapEntry(key: tk, value: tv) in v.entries) {
        m.putIfAbsent(tk, () => tv);
      }
    } else if (!d.containsKey(k)) {
      d[k] = v;
    }
  }
}

void _spanne(Stueck s, IcsKomponente ev, List<IcsKomponente> abw, IcsZeit start, IcsZeit? ende,
    String? rr, Map<String, Object?> ex) {
  final d = s.daten;
  final von = start.tag;
  final times = <String, Object?>{}, enden = <String, Object?>{};
  DateTime bis;
  if (rr != null) {
    final r = Regel.lesen(rr);
    if (r.anzahl != null) {
      bis = von.add(Duration(days: r.anzahl! - 1));
    } else {
      bis = tagVon(_untilLokal(rr) ?? von);
    }
    final basisT = start.ganztags ? null : hhmm(start.wert);
    final basisE = (!start.ganztags && ende != null && !ende.ganztags && ende.tag == start.tag &&
            ende.wert.isAfter(start.wert))
        ? hhmm(ende.wert)
        : null;
    final proTag = <DateTime, (IcsZeit?, IcsZeit?)>{};
    for (final a in abw) {
      final rid = _zeit(a.prop('RECURRENCE-ID'));
      if (rid == null) continue;
      final aS = _zeit(a.prop('DTSTART'));
      proTag[rid.tag] = (aS, aS == null ? null : _endeLesen(a, aS));
    }
    for (var cur = von; !cur.isAfter(bis); cur = cur.add(const Duration(days: 1))) {
      var t = basisT, e = basisE;
      final p = proTag[cur];
      if (p != null) {
        final (aS, aE) = p;
        t = aS != null && !aS.ganztags ? hhmm(aS.wert) : null;
        e = (aS != null && !aS.ganztags && aE != null && !aE.ganztags && aE.tag == aS.tag &&
                aE.wert.isAfter(aS.wert))
            ? hhmm(aE.wert)
            : null;
      }
      if (t != null) {
        times[isoTag(cur)] = t;
        if (e != null) enden[isoTag(cur)] = e;
      }
    }
  } else if (!start.ganztags) {
    times[isoTag(von)] = hhmm(start.wert);
    if (ende != null && !ende.ganztags && ende.wert.isAfter(start.wert)) {
      if (ende.wert.hour == 0 && ende.wert.minute == 0 && ende.wert.second == 0) {
        bis = ende.tag.subtract(const Duration(days: 1));
      } else {
        bis = ende.tag;
        enden[isoTag(bis)] = hhmm(ende.wert);
      }
    } else {
      bis = von;
    }
  } else {
    bis = (ende != null && ende.wert.isAfter(von)) ? ende.tag.subtract(const Duration(days: 1)) : von;
  }
  d['bis'] = isoTag(bis);
  if (times.isNotEmpty) d['times'] = times;
  if (enden.isNotEmpty) d['enden'] = enden;
  _rohAnwenden(ev, d);
  _lueckenFuellen(d, ex, {'times', 'enden'});
}

/// UNTIL einer Regel in Ortszeit (UTC-Wert umgerechnet), zonenlos.
DateTime? _untilLokal(String rr) {
  for (final t in rr.split(';')) {
    final g = t.indexOf('=');
    if (g > 0 && t.substring(0, g).toUpperCase() == 'UNTIL') {
      return zeitLesen(t.substring(g + 1))?.wert;
    }
  }
  return null;
}

/// Die Regel mit UNTIL in Ortszeit ohne Zone — wie _regel_text im Kern.
String _regelText(String rr) => rr.split(';').map((t) {
      final g = t.indexOf('=');
      if (g > 0 && t.substring(0, g).toUpperCase() == 'UNTIL' && t.endsWith('Z')) {
        final w = zeitLesen(t.substring(g + 1))!.wert;
        String z(int x, [int n = 2]) => x.toString().padLeft(n, '0');
        return 'UNTIL=${z(w.year, 4)}${z(w.month)}${z(w.day)}T${z(w.hour)}${z(w.minute)}${z(w.second)}';
      }
      return t;
    }).join(';');

void _routine(Stueck s, IcsKomponente ev, List<IcsKomponente> abw, IcsZeit start, IcsZeit? ende,
    String rr, Map<String, Object?> ex) {
  final d = s.daten;
  var regel = _regelText(rr);
  final roh = _xLesen(ev.prop('X-ZENTRALE-RRULE-ROH')?.wert);
  if (roh is Map && roh['roh'] is String && roh['geschrieben'] == regel) regel = roh['roh'] as String;
  d['rrule'] = regel;
  if (!start.ganztags) {
    d['time'] = hhmm(start.wert);
    final e = _endeText(start, ende);
    if (e != null && d['typ'] != 'deadline') d['ende'] = e;
  }
  _rohAnwenden(ev, d);
  if ((ev.prop('X-ZENTRALE-OHNE-ANFANG')?.text ?? '').toUpperCase() != 'TRUE') {
    d['seit'] = isoTag(_seitLesen(ev, regel, start.tag));
  }

  for (final p in ev.alle('X-ZENTRALE-PAUSE')) {
    final o = _xLesen(p.wert);
    if (o is! Map) continue;
    final von = isoTagLesen(o['von'] as String?), bis = isoTagLesen(o['bis'] as String?);
    if (von == null || bis == null) continue;
    s.pausen.add(Pause(o['label'] as String?, von, bis, o['grund'] as String?, o['routine_uid'] as String?));
  }

  // EXDATE: alles, was weder X-ZENTRALE-AUS noch eine Pause erklärt, ist
  // außerhalb gelöscht (Google, „nur diesen Termin“) und gilt als aus.
  final xAus = _xLesen(ev.prop('X-ZENTRALE-AUS')?.wert);
  final ausListe = xAus is List ? [for (final a in xAus) '$a'] : null;
  final exTage = <String>{};
  for (final p in ev.alle('EXDATE')) {
    for (final w in p.wert.split(',')) {
      final z = zeitLesen(w, tzid: p.param('TZID'));
      if (z != null) exTage.add(isoTag(z.tag));
    }
  }
  final erklaert = <String>{...?ausListe};
  for (final p in s.pausen) {
    try {
      for (final t in _vorkommenTage(d, p.von, p.bis)) {
        erklaert.add(isoTag(t));
      }
    } catch (_) {}
  }
  final extern = (exTage.difference(erklaert).toList()..sort());
  if (ausListe != null || extern.isNotEmpty) d['aus'] = [...?ausListe, ...extern];

  for (final a in abw) {
    final rid = _zeit(a.prop('RECURRENCE-ID'));
    if (rid == null) continue;
    final schluessel = isoTag(rid.tag);
    if ((a.prop('STATUS')?.text ?? '').toUpperCase() == 'CANCELLED') {
      s.abweichungen[schluessel] = Abweichung(entfaellt: true);
      continue;
    }
    final aS = _zeit(a.prop('DTSTART'));
    if (aS == null) continue;
    String? zeit, aEnde;
    if (!aS.ganztags) {
      zeit = hhmm(aS.wert);
      final e = _endeText(aS, _endeLesen(a, aS));
      if (e != null && e != '24:00') aEnde = e;
    }
    final sum = a.prop('SUMMARY')?.text ?? '';
    final ort = a.prop('LOCATION')?.text ?? '';
    s.abweichungen[schluessel] = Abweichung(
        tag: isoTag(aS.tag), zeit: zeit, ende: aEnde,
        label: sum.isNotEmpty && sum != d['label'] ? sum : null,
        ort: ort.isNotEmpty && ort != d['ort'] ? ort : null);
  }
  _lueckenFuellen(d, ex);
}

/// `seit`: X-ZENTRALE-SEIT, wenn er noch zu DTSTART passt (sein erstes
/// Vorkommen IST DTSTART) — sonst DTSTART.
DateTime _seitLesen(IcsKomponente ev, String regel, DateTime startTag) {
  final x = isoTagLesen(ev.prop('X-ZENTRALE-SEIT')?.text);
  if (x == null || x.isAfter(startTag)) return startTag;
  try {
    final erstes = Regel.lesen(regel).erster(x) ?? x;
    return erstes == startTag ? x : startTag;
  } catch (_) {
    return startTag;
  }
}

/// kalender_regel.vorkommen: Tage der Routine in [von, bis]; ohne `seit`
/// beginnt die Regel am Anfang des Zeitraums (alte Routinen „schon immer“).
List<DateTime> _vorkommenTage(Map<String, Object?> d, DateTime von, DateTime bis) {
  final regel = Regel.lesen(d['rrule'] as String);
  final seit = isoTagLesen(d['seit'] as String?);
  final anfang = seit ?? von;
  if (seit != null && seit.isAfter(bis)) return [];
  return [for (final t in regel.tage(anfang, bis)) if (!t.isBefore(von)) t];
}

/// Für kalender.dart: dieselbe Rechnung von außen.
List<DateTime> routinenTage(Stueck s, DateTime von, DateTime bis) => _vorkommenTage(s.daten, von, bis);
