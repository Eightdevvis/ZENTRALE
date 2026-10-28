// Wann findet eine Routine statt? — die RRULE als Tage, gerechnet wie im
// Kern (core/kalender_regel.vorkommen: dateutil mit DTSTART um Mitternacht
// des Anfangstags). Die Uhrzeit steht nicht in der Regel, sondern in der
// Routine — darum rechnet diese Datei nur mit Kalendertagen, und die
// Sommerzeit spielt hier keine Rolle (sie gilt erst beim Uhrzeit-Anhängen).
//
// Gebaut nach dateutils Perioden-Verfahren: je Periode (Tag, Woche, Monat,
// Jahr im Abstand INTERVAL) alle Kandidaten-Tage bilden, nach BYMONTH,
// BYMONTHDAY, BYDAY filtern, BYSETPOS anwenden; vor dem Anfang Liegendes
// fällt weg, COUNT zählt ab dem Anfang, UNTIL gilt inklusive. Fehlen die
// BY-Teile, nimmt dateutil sie vom Anfang (Wochentag, Monatstag, Monat) —
// hier genauso. Was die Regel nicht kennt (BYWEEKNO, BYYEARDAY, BYHOUR …),
// wirft RegelFehler: lieber eine Routine nicht zeigen als falsch.
//
// Prüfstein: test/kalender_test.dart gegen kalender_testvektoren.json.

class RegelFehler implements Exception {
  RegelFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

/// Ein Kalendertag ohne Uhrzeit und ohne Zone (UTC-Mitternacht als Träger,
/// damit kein Sommerzeit-Sprung einen Tag verschiebt).
DateTime tag(int j, int m, int t) => DateTime.utc(j, m, t);
DateTime tagVon(DateTime d) => DateTime.utc(d.year, d.month, d.day);
String isoTag(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
DateTime? isoTagLesen(String? s) {
  if (s == null || !RegExp(r'^\d{4}-\d\d-\d\d$').hasMatch(s)) return null;
  final d = DateTime.utc(int.parse(s.substring(0, 4)), int.parse(s.substring(5, 7)),
      int.parse(s.substring(8, 10)));
  return isoTag(d) == s ? d : null;
}

const _wt = {'MO': 1, 'TU': 2, 'WE': 3, 'TH': 4, 'FR': 5, 'SA': 6, 'SU': 7};

class Wochentag {
  Wochentag(this.tag, this.n);
  final int tag; // 1 = Montag … 7 = Sonntag (DateTime.weekday)
  final int? n; // 2TU → 2, -1SU → -1, ohne Zahl null
}

class Regel {
  Regel._(this.freq, this.intervall, this.anzahl, this.bis, this.monate, this.monatstage,
      this.wochentage, this.setpos, this.wkst);

  final String freq;
  final int intervall;
  final int? anzahl;

  /// UNTIL als Tag+Uhrzeit (zonenlos, Ortszeit) — verglichen mit Mitternacht.
  final DateTime? bis;
  final List<int> monate;
  final List<int> monatstage;
  final List<Wochentag> wochentage;
  final List<int> setpos;
  final int wkst;

  /// "FREQ=WEEKLY;BYDAY=TU;UNTIL=20270301T235959" (ohne "RRULE:").
  factory Regel.lesen(String text) {
    String? freq;
    var intervall = 1;
    int? anzahl;
    DateTime? bis;
    var monate = <int>[], monatstage = <int>[], setpos = <int>[];
    var wochentage = <Wochentag>[];
    var wkst = 1;
    List<int> zahlen(String v) => [for (final x in v.split(',')) int.parse(x.trim())];
    for (final teil in text.split(';')) {
      if (teil.trim().isEmpty) continue;
      final g = teil.indexOf('=');
      if (g < 0) throw RegelFehler('Regel-Teil ohne „=“: $teil');
      final k = teil.substring(0, g).trim().toUpperCase();
      final v = teil.substring(g + 1).trim();
      try {
        switch (k) {
          case 'FREQ':
            freq = v.toUpperCase();
          case 'INTERVAL':
            intervall = int.parse(v);
          case 'COUNT':
            anzahl = int.parse(v);
          case 'UNTIL':
            bis = _bisLesen(v);
          case 'BYMONTH':
            monate = zahlen(v);
          case 'BYMONTHDAY':
            monatstage = zahlen(v);
          case 'BYSETPOS':
            setpos = zahlen(v);
          case 'WKST':
            wkst = _wt[v.toUpperCase()] ?? (throw RegelFehler('WKST $v'));
          case 'BYDAY':
            wochentage = [
              for (final x in v.split(','))
                () {
                  final m = RegExp(r'^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$')
                      .firstMatch(x.trim().toUpperCase());
                  if (m == null) throw RegelFehler('BYDAY $x');
                  return Wochentag(_wt[m.group(2)]!, m.group(1) == null ? null : int.parse(m.group(1)!));
                }()
            ];
          default:
            throw RegelFehler('Regel-Teil $k kennt das Handy nicht');
        }
      } on FormatException {
        throw RegelFehler('Regel-Teil $teil ist unlesbar');
      }
    }
    if (!const ['DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'].contains(freq)) {
      throw RegelFehler('FREQ=$freq kennt das Handy nicht');
    }
    if (intervall < 1) throw RegelFehler('INTERVAL < 1');
    return Regel._(freq!, intervall, anzahl, bis, monate, monatstage, wochentage, setpos, wkst);
  }

  static DateTime _bisLesen(String v) {
    final m = RegExp(r'^(\d{4})(\d\d)(\d\d)(?:T(\d\d)(\d\d)(\d\d)Z?)?$').firstMatch(v);
    if (m == null) throw RegelFehler('UNTIL $v');
    int g(int i) => int.parse(m.group(i) ?? '0');
    return DateTime.utc(g(1), g(2), g(3), g(4), g(5), g(6));
  }

  /// Alle Tage der Regel ab [anfang] (= DTSTART-Tag) bis einschließlich
  /// [ende], aufsteigend.
  List<DateTime> tage(DateTime anfang, DateTime ende) {
    anfang = tagVon(anfang);
    ende = tagVon(ende);
    // Wie dateutil: fehlende BY-Teile kommen vom Anfang.
    var mt = monatstage, wt = wochentage, mo = monate;
    if (wt.isEmpty && mt.isEmpty) {
      if (freq == 'WEEKLY') {
        wt = [Wochentag(anfang.weekday, null)];
      } else if (freq == 'MONTHLY') {
        mt = [anfang.day];
      } else if (freq == 'YEARLY') {
        if (mo.isEmpty) mo = [anfang.month];
        mt = [anfang.day];
      }
    }
    final raus = <DateTime>[];
    var gezaehlt = 0;
    for (var k = 0; k < 100000; k++) {
      final kandidaten = _periode(anfang, k);
      if (kandidaten == null) break;
      var treffer = [
        for (final d in kandidaten)
          if (_passt(d, mo, mt, wt)) d
      ];
      if (setpos.isNotEmpty) {
        final n = treffer.length;
        treffer = [
          for (final p in setpos)
            if (p > 0 && p <= n)
              treffer[p - 1]
            else if (p < 0 && -p <= n)
              treffer[n + p]
        ]..sort();
      }
      for (final d in treffer) {
        if (d.isBefore(anfang)) continue;
        if (bis != null && d.isAfter(bis!)) return raus;
        if (anzahl != null && gezaehlt >= anzahl!) return raus;
        gezaehlt++;
        if (d.isAfter(ende)) return raus;
        raus.add(d);
      }
      // Erste Periode schon hinter dem Ende? Dann kommt nichts mehr.
      if (kandidaten.isNotEmpty && kandidaten.first.isAfter(ende)) return raus;
    }
    return raus;
  }

  /// Die Kandidaten-Tage der k-ten Periode (null = über jede Grenze hinaus).
  List<DateTime>? _periode(DateTime a, int k) {
    switch (freq) {
      case 'DAILY':
        return [a.add(Duration(days: k * intervall))];
      case 'WEEKLY':
        final start = a.subtract(Duration(days: (a.weekday - wkst) % 7));
        final s = start.add(Duration(days: 7 * k * intervall));
        return [for (var i = 0; i < 7; i++) s.add(Duration(days: i))];
      case 'MONTHLY':
        final m0 = a.year * 12 + (a.month - 1) + k * intervall;
        final j = m0 ~/ 12, m = m0 % 12 + 1;
        if (j > 9999) return null;
        final n = DateTime.utc(j, m + 1, 0).day;
        return [for (var t = 1; t <= n; t++) DateTime.utc(j, m, t)];
      default: // YEARLY
        final j = a.year + k * intervall;
        if (j > 9999) return null;
        final raus = <DateTime>[];
        for (var d = DateTime.utc(j, 1, 1); d.year == j; d = d.add(const Duration(days: 1))) {
          raus.add(d);
        }
        return raus;
    }
  }

  bool _passt(DateTime d, List<int> mo, List<int> mt, List<Wochentag> wt) {
    if (mo.isNotEmpty && !mo.contains(d.month)) return false;
    if (mt.isNotEmpty) {
      final n = DateTime.utc(d.year, d.month + 1, 0).day;
      if (!mt.any((x) => x > 0 ? x == d.day : n + x + 1 == d.day)) return false;
    }
    if (wt.isNotEmpty && !wt.any((w) => _wochentagPasst(d, w, mo))) return false;
    return true;
  }

  /// BYDAY mit Zahl: n-ter Wochentag im Monat (MONTHLY, oder YEARLY mit
  /// BYMONTH) bzw. im Jahr (YEARLY ohne BYMONTH) — wie dateutil.
  bool _wochentagPasst(DateTime d, Wochentag w, List<int> mo) {
    if (d.weekday != w.tag) return false;
    final n = w.n;
    if (n == null || freq == 'DAILY' || freq == 'WEEKLY') return true;
    final imMonat = freq == 'MONTHLY' || mo.isNotEmpty;
    final erster = imMonat ? DateTime.utc(d.year, d.month, 1) : DateTime.utc(d.year, 1, 1);
    final letzter = imMonat ? DateTime.utc(d.year, d.month + 1, 0) : DateTime.utc(d.year, 12, 31);
    if (n > 0) return (d.difference(erster).inDays ~/ 7) + 1 == n;
    return -((letzter.difference(d).inDays ~/ 7) + 1) == n;
  }

  /// Der erste Tag ab [ab], an dem die Regel trifft (kalender_regel.erstes_vorkommen).
  DateTime? erster(DateTime ab, {int horizont = 3700}) {
    final t = tage(ab, ab.add(Duration(days: horizont)));
    return t.isEmpty ? null : t.first;
  }
}
