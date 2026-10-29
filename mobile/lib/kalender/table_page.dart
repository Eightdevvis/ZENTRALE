// The calendar seen through the peephole ("Guckloch"): the next weeks lie as
// one big spread on the table, the phone is the window. Opened from the
// calendar page's app bar. Draws only; data from KalenderSteuerung.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n/app_localizations.dart';
import '../peephole/motion.dart';
import '../peephole/peephole_controller.dart';
import '../peephole/peephole_surface.dart';
import '../peephole/peephole_view.dart';
import 'kalender_seite.dart' show ebenenFarbe;
import 'kalender_steuerung.dart';
import 'regel.dart';
import 'table_surface.dart';

class CalendarTablePage extends StatefulWidget {
  const CalendarTablePage({super.key, required this.controller, this.motion});

  final KalenderSteuerung controller;

  /// Null = the real sensors (tests pass a fake source).
  final MotionSource? motion;

  @override
  State<CalendarTablePage> createState() => _CalendarTablePageState();
}

class _CalendarTablePageState extends State<CalendarTablePage> {
  late final MotionSource _motion = widget.motion ?? SensorMotionSource();
  PeepholeController? _window;

  @override
  void initState() {
    super.initState();
    // The motion mapping uses the phone's own axes: keep the screen upright
    // so turning the phone doesn't also flip the picture.
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  }

  void _show(PeepholeHit hit) {
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(hit.title, style: Theme.of(context).textTheme.titleMedium),
            if (hit.detail != null) ...[const SizedBox(height: 6), Text(hit.detail!)],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    return Scaffold(
      appBar: AppBar(title: Text(t.calendarTableTitle)),
      body: ListenableBuilder(
        listenable: widget.controller,
        builder: (context, _) {
          final s = widget.controller;
          final surface = CalendarTableSurface(
            calendar: s.kalender,
            today: tagVon(s.jetzt),
            layerColor: (layer) => ebenenFarbe(context, s.kalender, layer),
            strings: t,
            locale: locale,
          );
          _window ??= PeepholeController(
            surfaceSize: surface.size,
            home: surface.home,
            comfortableViewWidth: surface.comfortableViewWidth,
          );
          return PeepholeView(surface: surface, motion: _motion, controller: _window, onHit: _show);
        },
      ),
    );
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(const []); // back to the app's default
    _window?.dispose();
    super.dispose();
  }
}
