// Which calendar view is shown, remembered per device. A UI preference
// only — it lives in the app's own support folder, never in the synced
// Ablage.

import 'dart:io';

import 'package:path_provider/path_provider.dart';

enum CalendarViewMode { day, week, month, agenda }

abstract class ViewModeMemory {
  Future<CalendarViewMode?> load();
  Future<void> save(CalendarViewMode mode);
}

/// For tests and as fallback: forgets on restart.
class MemoryViewModeMemory implements ViewModeMemory {
  MemoryViewModeMemory([this.mode]);
  CalendarViewMode? mode;

  @override
  Future<CalendarViewMode?> load() async => mode;

  @override
  Future<void> save(CalendarViewMode m) async => mode = m;
}

/// One small file in the application support directory.
class FileViewModeMemory implements ViewModeMemory {
  FileViewModeMemory([this._file]);
  File? _file;

  Future<File> _f() async =>
      _file ??= File('${(await getApplicationSupportDirectory()).path}/ui/calendar_view_mode');

  @override
  Future<CalendarViewMode?> load() async {
    try {
      final f = await _f();
      if (!await f.exists()) return null;
      final name = (await f.readAsString()).trim();
      return CalendarViewMode.values.where((m) => m.name == name).firstOrNull;
    } catch (_) {
      return null; // unreadable: just use the default
    }
  }

  @override
  Future<void> save(CalendarViewMode mode) async {
    try {
      final f = await _f();
      await f.parent.create(recursive: true);
      await f.writeAsString(mode.name);
    } catch (_) {
      // A lost preference is not worth an error.
    }
  }
}
