// Farben — dieselben wie das Auge der TUI (tui/pixel.py, AUGE_FARBEN), immer
// Tag UND Nacht (memory/system/pixelstil.md: Tag wird dunkler, nicht heller).

import 'package:flutter/material.dart';

class AugeFarben {
  const AugeFarben({
    required this.bg, required this.weiss, required this.schatten,
    required this.iris, required this.irishell, required this.irisrand,
    required this.pupille, required this.rand, required this.lid,
    required this.falte,
  });

  final Color bg, weiss, schatten, iris, irishell, irisrand, pupille, rand, lid, falte;

  static const nacht = AugeFarben(
    bg: Color(0xFF000000), weiss: Color(0xFFCFDDE6), schatten: Color(0xFF5D7385),
    iris: Color(0xFF1FB88C), irishell: Color(0xFF9DF5D6), irisrand: Color(0xFF0A3F31),
    pupille: Color(0xFF020A08), rand: Color(0xFF7FCFB8), lid: Color(0xFF2F5C52),
    falte: Color(0xFF5FAE98),
  );

  static const tag = AugeFarben(
    bg: Color(0xFFFFFFFF), weiss: Color(0xFFEEF4F7), schatten: Color(0xFF9FB2C4),
    iris: Color(0xFF14A37A), irishell: Color(0xFF6FE8BF), irisrand: Color(0xFF073B2D),
    pupille: Color(0xFF02100B), rand: Color(0xFF0B5C46), lid: Color(0xFFB9D6CD),
    falte: Color(0xFF4F8F7C),
  );

  static AugeFarben von(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? nacht : tag;
}

ThemeData zentraleThema(Brightness hell) {
  final a = hell == Brightness.dark ? AugeFarben.nacht : AugeFarben.tag;
  final nacht = hell == Brightness.dark;
  final schema = ColorScheme.fromSeed(
    seedColor: a.iris,
    brightness: hell,
    surface: a.bg,
    primary: nacht ? a.rand : a.rand,
  );
  return ThemeData(
    colorScheme: schema,
    scaffoldBackgroundColor: a.bg,
    useMaterial3: true,
    appBarTheme: AppBarTheme(
      backgroundColor: a.bg,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: true,
    ),
    drawerTheme: DrawerThemeData(backgroundColor: a.bg),
  );
}

/// Flächen im Chat (Sashas Blasen, Eingabe) — leicht abgehoben vom Grund.
Color flaeche(BuildContext context) {
  final a = AugeFarben.von(context);
  return Color.lerp(a.bg, a.lid, Theme.of(context).brightness == Brightness.dark ? .35 : .3)!;
}
