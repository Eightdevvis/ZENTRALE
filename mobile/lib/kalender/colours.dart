// The colour of a calendar event — port of core/calendar_colours.py.
//
// Every front shows an event in the same colour: the course in its title
// ("Analysis I" and "Ana Tutorium" are both "analysis"), the list it takes its
// title from ("quelle:<id>") or its group ("gruppe:<key>") is its *key*; the
// synced table data/calendar_colours.json gives the key its fixed *slot*
// 0..11 (palette colours t0..t11); a key the table does not know falls back to
// crc32(key) % 12. The phone never assigns slots — computers do that and the
// table comes over the sync (mitte/regeln.dart).
//
// Precedence: X-ZENTRALE-STIL (CSS) > COLOR (RFC 7986) > span colour > course
// slot > layer colour. A style overrides only what it sets.
//
// The palette (hex, day + night) is the core's file core/calendar_palette.json,
// bundled byte-identical as assets/calendar_palette.json.
//
// Pinned to the core by test/daten/calendar_colour_vectors.json
// (scripts/calendar_colour_vectors.py). Docs: memory/werkzeuge/calendar_colours.md.

import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/services.dart' show AssetBundle, rootBundle;

import 'ics.dart';

const tableFormat = 'zentrale-calendar-colours/1';
const tableFile = 'calendar_colours.json';
const slotCount = 12;

/// core/calendar_colours.SHORT_FORMS
const shortForms = {
  'exphy': 'experimentalphysik',
  'tp': 'theoretische',
  'ana': 'analysis',
};

/// core/kalender_kategorie.KATEGORIEN (key → display name).
const groupCatalog = {'uni': 'Uni', 'arbeit': 'Arbeit'};

const sourcePrefix = 'quelle:';
const groupPrefix = 'gruppe:';

// ── Keys ─────────────────────────────────────────────────────────────────────

final _separators = RegExp(r'[\s\-–:/,.()]+');

/// First word of the title without the place, lower case, short forms resolved.
String courseKey(String? title) {
  final name = (title ?? '').split(' @ ').first.trim().toLowerCase();
  final word = name.isEmpty ? '' : name.split(_separators).first;
  return shortForms[word] ?? word;
}

/// Python's str.casefold for what titles contain (lower case + ß → ss).
String casefold(String s) => s.toLowerCase().replaceAll('ß', 'ss');

String? groupKey(String? category, [String? categoryName]) {
  if (category == null || category.isEmpty || category == 'keine') return null;
  if (category == 'custom') {
    final n = (categoryName ?? '').trim();
    return n.isEmpty ? null : '${groupPrefix}custom:${casefold(n)}';
  }
  return '$groupPrefix$category';
}

/// CATEGORIES values → group key (core/kalender_kategorie.aus_namen): the
/// first value; a catalog key or name becomes that key, anything else a
/// custom group with that name.
String? groupKeyFromCategories(List<String> names) {
  final n = names.where((x) => x.isNotEmpty).toList();
  if (n.isEmpty) return null;
  final t = casefold(n.first.trim());
  for (final e in groupCatalog.entries) {
    if (t == e.key || t == casefold(e.value)) return groupKey(e.key);
  }
  return groupKey('custom', n.first);
}

final _listId = RegExp(r'^[A-Za-z0-9_\-]{1,80}$');
final _projectId = RegExp(r'^[A-Za-z0-9_\-]{1,80}(/[0-9]{1,9})?$');

String? _sourceId(String art, String id) {
  art = art.trim().toLowerCase();
  id = id.trim();
  if (art == 'liste' && _listId.hasMatch(id)) return id;
  if (art == 'projekt' && _projectId.hasMatch(id)) return id;
  return null;
}

/// Source id from X-ZENTRALE-QUELLE ("liste:l_todo"), else from the URL
/// (`zentrale://fokus/<list>[/<item>]`) — core/kalender_quelle.aus_text/aus_adresse.
String? sourceIdFromIcs(String? xSource, String? url) {
  if (xSource != null) {
    final i = xSource.indexOf(':');
    return i < 0 ? _sourceId(xSource, '') : _sourceId(xSource.substring(0, i), xSource.substring(i + 1));
  }
  if (url == null) return null;
  final u = Uri.tryParse(url.trim());
  if (u == null || u.scheme != 'zentrale' || u.host != 'fokus' || u.hasQuery) return null;
  final parts = u.pathSegments.where((p) => p.isNotEmpty).toList();
  if (parts.length != 1 && parts.length != 2) return null;
  return _sourceId(parts.length == 1 ? 'liste' : 'projekt', parts.join('/'));
}

/// The colour key of an occurrence: its source, else the course in its title.
String? entryKey(String? label, String? sourceId) {
  if (sourceId != null && sourceId.isNotEmpty) return '$sourcePrefix$sourceId';
  final k = courseKey(label);
  return k.isEmpty ? null : k;
}

// ── Slots ────────────────────────────────────────────────────────────────────

final Uint32List _crcTable = () {
  final t = Uint32List(256);
  for (var n = 0; n < 256; n++) {
    var c = n;
    for (var k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
    }
    t[n] = c;
  }
  return t;
}();

/// zlib.crc32 of the UTF-8 bytes.
int crc32(String s) {
  var c = 0xFFFFFFFF;
  for (final b in utf8.encode(s)) {
    c = _crcTable[(c ^ b) & 0xFF] ^ (c >> 8);
  }
  return (c ^ 0xFFFFFFFF) & 0xFFFFFFFF;
}

int fallbackSlot(String key) => crc32(key) % slotCount;

int? slotFor(String? key, Map<String, int> table) {
  if (key == null || key.isEmpty) return null;
  final s = table[key];
  return s != null && s >= 0 && s < slotCount ? s : fallbackSlot(key);
}

/// File content → {key: slot}; tolerant (broken → {}), also the old flat form.
Map<String, int> parseTable(String? raw) {
  if (raw == null) return {};
  Object? d;
  try {
    d = jsonDecode(raw);
  } catch (_) {
    return {};
  }
  if (d is! Map) return {};
  final Object? slots = d['format'] == tableFormat ? d['slots'] : (d.containsKey('format') ? null : d);
  if (slots is! Map) return {};
  return {
    for (final e in slots.entries)
      if (e.key is String && (e.key as String).isNotEmpty && e.value is int && e.value >= 0 && e.value < slotCount)
        e.key as String: e.value as int,
  };
}

// ── Style (X-ZENTRALE-STIL / COLOR) ──────────────────────────────────────────

const _styleOffer = ['border-style', 'border-color', 'background-color', 'color', '--zentrale-muster', 'background-image'];
const _colourProps = {'border-color', 'background-color', 'color'};
const _choices = {
  'border-style': ['solid', 'dashed', 'dotted', 'double'],
  '--zentrale-muster': ['punkte', 'raster', 'dicht', 'streifen', 'schraeg', 'karo'],
};
final _hex = RegExp(r'^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$');
final _image = RegExp(r'^(none|url\(.+\))$');

/// '#FF8800', 'ff8800', '#f80' → '#ff8800'; else null (core/stil.hex_lesen).
String? hexRead(String? text) {
  final m = _hex.firstMatch((text ?? '').trim());
  if (m == null) return null;
  var d = m.group(1)!.toLowerCase();
  if (d.length == 3) d = d.split('').map((c) => '$c$c').join();
  return '#$d';
}

/// CSS3 name or hex → '#rrggbb' (core/stil.hex_aus_name).
String? hexFromName(String? name) {
  final s = (name ?? '').trim().toLowerCase();
  return css3Colours[s] ?? (s.startsWith('#') ? hexRead(s) : null);
}

/// "name: value; …" → map (core/stil.aus_css); null = broken.
Map<String, String>? _cssRead(String text) {
  final parts = <String>[];
  final now = StringBuffer();
  var depth = 0;
  String? quote;
  for (final ch in text.split('')) {
    if (quote != null) {
      if (ch == quote) quote = null;
    } else if (ch == '"' || ch == "'") {
      quote = ch;
    } else if (ch == '(') {
      depth++;
    } else if (ch == ')') {
      depth = depth > 0 ? depth - 1 : 0;
    } else if (ch == ';' && depth == 0) {
      parts.add(now.toString());
      now.clear();
      continue;
    }
    now.write(ch);
  }
  parts.add(now.toString());
  final out = <String, String>{};
  for (final p in parts) {
    if (p.trim().isEmpty) continue;
    final i = p.indexOf(':');
    if (i < 0 || p.substring(0, i).trim().isEmpty) return null;
    out[p.substring(0, i).trim().toLowerCase()] = p.substring(i + 1).trim();
  }
  return out;
}

/// The checked style (core/stil.pruefen with the box offer); null = invalid.
Map<String, String>? _styleCheck(Map<String, String> raw) {
  final out = <String, String>{};
  for (final e in raw.entries) {
    final name = e.key, value = e.value;
    if (!_styleOffer.contains(name)) return null;
    if (_choices.containsKey(name) && value.trim().toLowerCase() == 'none') {
      continue; // an old "none" = not set
    }
    if (_colourProps.contains(name)) {
      final h = value.trim().startsWith('#') ? hexRead(value) : null;
      if (h == null) return null;
      out[name] = h;
    } else if (_choices.containsKey(name)) {
      final w = value.trim().toLowerCase();
      if (!_choices[name]!.contains(w)) return null;
      out[name] = w;
    } else {
      if (!_image.hasMatch(value.trim())) return null;
      out[name] = value.trim();
    }
  }
  return out;
}

/// iCalendar TEXT unescaping exactly as the core (\\ \; \, \n only).
String unescapeText(String raw) =>
    raw.replaceAllMapped(RegExp(r'\\([\\;,nN])'), (m) => (m[1] == 'n' || m[1] == 'N') ? '\n' : m[1]!);

/// core/calendar_colours.style_from_ics: STIL wins, else COLOR as the fill;
/// a broken STIL means no style (COLOR not consulted).
Map<String, String>? styleFromIcs(String? styleText, String? colorName) {
  if (styleText != null) {
    final raw = _cssRead(styleText);
    if (raw == null) return null;
    final s = _styleCheck(raw);
    return s == null || s.isEmpty ? null : s;
  }
  if (colorName != null) {
    final h = hexFromName(colorName);
    return h == null ? null : {'background-color': h};
  }
  return null;
}

/// Comma-separated values of one CATEGORIES line (escaped commas stay).
List<String> categoriesValues(String raw) {
  final out = <String>[];
  final b = StringBuffer();
  for (var i = 0; i < raw.length; i++) {
    final c = raw[i];
    if (c == r'\' && i + 1 < raw.length) {
      b.write(c);
      b.write(raw[++i]);
    } else if (c == ',') {
      out.add(textLesen(b.toString()));
      b.clear();
    } else {
      b.write(c);
    }
  }
  out.add(textLesen(b.toString()));
  return out;
}

/// What the .ics says about an event's colour (read once per VEVENT).
class EventColourInput {
  const EventColourInput({this.sourceId, this.groupKey, this.style});
  final String? sourceId, groupKey;
  final Map<String, String>? style;

  static EventColourInput fromIcs(IcsKomponente ev) {
    final x = ev.prop('X-ZENTRALE-STIL');
    final c = ev.prop('COLOR');
    final names = <String>[for (final p in ev.alle('CATEGORIES')) ...categoriesValues(p.wert)];
    return EventColourInput(
      sourceId: sourceIdFromIcs(ev.prop('X-ZENTRALE-QUELLE')?.text, ev.prop('URL')?.text),
      groupKey: groupKeyFromCategories(names),
      style: styleFromIcs(x == null ? null : unescapeText(x.wert), c?.text),
    );
  }
}

// ── Precedence ───────────────────────────────────────────────────────────────

/// Where an event's colour comes from (core/calendar_colours.resolve).
class ResolvedColour {
  const ResolvedColour({required this.source, this.role, this.slot, this.key, this.style});

  /// 'style' | 'span' | 'course' | 'layer'
  final String source;

  /// Palette role for what the style leaves open ('t3', 'sp1'); null = layer colour.
  final String? role;
  final int? slot;
  final String? key;
  final Map<String, String>? style;

  static ResolvedColour resolve(Map<String, String>? style, String? key, Map<String, int> table, {bool span = false}) {
    final st = style == null || style.isEmpty ? null : style;
    final slot = span ? null : slotFor(key, table);
    final role = span ? 'sp1' : (slot == null ? null : 't$slot');
    final source = st != null ? 'style' : (span ? 'span' : (slot != null ? 'course' : 'layer'));
    return ResolvedColour(source: source, role: role, slot: slot, key: key, style: st);
  }
}

/// Final block colours as '#rrggbb' (core/calendar_colours.block_colours).
class BlockColours {
  const BlockColours(this.fill, this.text, this.border);
  final String? fill, text, border;
}

/// Black or white on [background] (luminance threshold 0.179, as the core).
String readableHexOn(String background) {
  final h = hexRead(background)!;
  double k(int v) {
    final x = v / 255;
    return x <= 0.03928 ? x / 12.92 : math.pow((x + 0.055) / 1.055, 2.4).toDouble();
  }

  final r = k(int.parse(h.substring(1, 3), radix: 16)),
      g = k(int.parse(h.substring(3, 5), radix: 16)),
      b = k(int.parse(h.substring(5, 7), radix: 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? '#000000' : '#ffffff';
}

BlockColours blockColours(ResolvedColour r, PaletteTheme theme, {String? layerDefault}) {
  final role = r.role == null ? null : theme.roles[r.role];
  var fill = role?.fill ?? layerDefault;
  var text = role?.onFill ?? (layerDefault == null ? null : readableHexOn(layerDefault));
  final st = r.style ?? const {};
  if (st['background-color'] != null) {
    fill = st['background-color'];
    text = st['color'] ?? readableHexOn(fill!);
  } else if (st['color'] != null) {
    text = st['color'];
  }
  return BlockColours(fill, text, st['border-color'] ?? text);
}

// ── Palette (assets/calendar_palette.json) ───────────────────────────────────

class PaletteRole {
  const PaletteRole(this.text, this.fill, this.onFill);
  final String text, fill, onFill;
}

class PaletteTheme {
  const PaletteTheme({required this.background, required this.roles, required this.opacity});
  final String background;
  final Map<String, PaletteRole> roles;

  /// fill / text / glass: how much of a colour stays when drawn see-through.
  final Map<String, double> opacity;
}

class CalendarColourPalette {
  const CalendarColourPalette(this.day, this.night);
  final PaletteTheme day, night;

  static const asset = 'assets/calendar_palette.json';

  /// Loaded once (main(), KalenderSteuerung, tests); null until then — the
  /// views then fall back to the layer colours.
  static CalendarColourPalette? current;

  PaletteTheme of({required bool night}) => night ? this.night : day;

  static CalendarColourPalette fromJson(String text) {
    final d = jsonDecode(text) as Map<String, dynamic>;
    PaletteTheme theme(String n) {
      final t = (d['themes'] as Map<String, dynamic>)[n] as Map<String, dynamic>;
      return PaletteTheme(
        background: (t['background'] as Map)['hex'] as String,
        roles: {
          for (final e in (t['roles'] as Map<String, dynamic>).entries)
            e.key: PaletteRole(e.value['text'] as String, e.value['fill'] as String, e.value['on_fill'] as String),
        },
        opacity: {for (final e in (t['opacity'] as Map<String, dynamic>).entries) e.key: (e.value as num).toDouble()},
      );
    }

    return CalendarColourPalette(theme('day'), theme('night'));
  }

  static Future<CalendarColourPalette> ensureLoaded([AssetBundle? bundle]) async {
    return current ??= fromJson(await (bundle ?? rootBundle).loadString(asset));
  }
}

// ── CSS3 colour names (core/stil.CSS3_FARBEN, RFC 7986 COLOR) ────────────────
const css3Colours = <String, String>{
  'aliceblue': '#f0f8ff', 'antiquewhite': '#faebd7', 'aqua': '#00ffff', 'aquamarine': '#7fffd4',
  'azure': '#f0ffff', 'beige': '#f5f5dc', 'bisque': '#ffe4c4', 'black': '#000000',
  'blanchedalmond': '#ffebcd', 'blue': '#0000ff', 'blueviolet': '#8a2be2', 'brown': '#a52a2a',
  'burlywood': '#deb887', 'cadetblue': '#5f9ea0', 'chartreuse': '#7fff00', 'chocolate': '#d2691e',
  'coral': '#ff7f50', 'cornflowerblue': '#6495ed', 'cornsilk': '#fff8dc', 'crimson': '#dc143c',
  'cyan': '#00ffff', 'darkblue': '#00008b', 'darkcyan': '#008b8b', 'darkgoldenrod': '#b8860b',
  'darkgray': '#a9a9a9', 'darkgreen': '#006400', 'darkgrey': '#a9a9a9', 'darkkhaki': '#bdb76b',
  'darkmagenta': '#8b008b', 'darkolivegreen': '#556b2f', 'darkorange': '#ff8c00', 'darkorchid': '#9932cc',
  'darkred': '#8b0000', 'darksalmon': '#e9967a', 'darkseagreen': '#8fbc8f', 'darkslateblue': '#483d8b',
  'darkslategray': '#2f4f4f', 'darkslategrey': '#2f4f4f', 'darkturquoise': '#00ced1', 'darkviolet': '#9400d3',
  'deeppink': '#ff1493', 'deepskyblue': '#00bfff', 'dimgray': '#696969', 'dimgrey': '#696969',
  'dodgerblue': '#1e90ff', 'firebrick': '#b22222', 'floralwhite': '#fffaf0', 'forestgreen': '#228b22',
  'fuchsia': '#ff00ff', 'gainsboro': '#dcdcdc', 'ghostwhite': '#f8f8ff', 'gold': '#ffd700',
  'goldenrod': '#daa520', 'gray': '#808080', 'green': '#008000', 'greenyellow': '#adff2f',
  'grey': '#808080', 'honeydew': '#f0fff0', 'hotpink': '#ff69b4', 'indianred': '#cd5c5c',
  'indigo': '#4b0082', 'ivory': '#fffff0', 'khaki': '#f0e68c', 'lavender': '#e6e6fa',
  'lavenderblush': '#fff0f5', 'lawngreen': '#7cfc00', 'lemonchiffon': '#fffacd', 'lightblue': '#add8e6',
  'lightcoral': '#f08080', 'lightcyan': '#e0ffff', 'lightgoldenrodyellow': '#fafad2', 'lightgray': '#d3d3d3',
  'lightgreen': '#90ee90', 'lightgrey': '#d3d3d3', 'lightpink': '#ffb6c1', 'lightsalmon': '#ffa07a',
  'lightseagreen': '#20b2aa', 'lightskyblue': '#87cefa', 'lightslategray': '#778899', 'lightslategrey': '#778899',
  'lightsteelblue': '#b0c4de', 'lightyellow': '#ffffe0', 'lime': '#00ff00', 'limegreen': '#32cd32',
  'linen': '#faf0e6', 'magenta': '#ff00ff', 'maroon': '#800000', 'mediumaquamarine': '#66cdaa',
  'mediumblue': '#0000cd', 'mediumorchid': '#ba55d3', 'mediumpurple': '#9370db', 'mediumseagreen': '#3cb371',
  'mediumslateblue': '#7b68ee', 'mediumspringgreen': '#00fa9a', 'mediumturquoise': '#48d1cc',
  'mediumvioletred': '#c71585', 'midnightblue': '#191970', 'mintcream': '#f5fffa', 'mistyrose': '#ffe4e1',
  'moccasin': '#ffe4b5', 'navajowhite': '#ffdead', 'navy': '#000080', 'oldlace': '#fdf5e6',
  'olive': '#808000', 'olivedrab': '#6b8e23', 'orange': '#ffa500', 'orangered': '#ff4500',
  'orchid': '#da70d6', 'palegoldenrod': '#eee8aa', 'palegreen': '#98fb98', 'paleturquoise': '#afeeee',
  'palevioletred': '#db7093', 'papayawhip': '#ffefd5', 'peachpuff': '#ffdab9', 'peru': '#cd853f',
  'pink': '#ffc0cb', 'plum': '#dda0dd', 'powderblue': '#b0e0e6', 'purple': '#800080',
  'red': '#ff0000', 'rosybrown': '#bc8f8f', 'royalblue': '#4169e1', 'saddlebrown': '#8b4513',
  'salmon': '#fa8072', 'sandybrown': '#f4a460', 'seagreen': '#2e8b57', 'seashell': '#fff5ee',
  'sienna': '#a0522d', 'silver': '#c0c0c0', 'skyblue': '#87ceeb', 'slateblue': '#6a5acd',
  'slategray': '#708090', 'slategrey': '#708090', 'snow': '#fffafa', 'springgreen': '#00ff7f',
  'steelblue': '#4682b4', 'tan': '#d2b48c', 'teal': '#008080', 'thistle': '#d8bfd8',
  'tomato': '#ff6347', 'turquoise': '#40e0d0', 'violet': '#ee82ee', 'wheat': '#f5deb3',
  'white': '#ffffff', 'whitesmoke': '#f5f5f5', 'yellow': '#ffff00', 'yellowgreen': '#9acd32',
};
