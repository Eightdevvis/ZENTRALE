// The building kit's type system on the phone (contracts/ports/1, building
// kit step 9): the same JSON Schema 2020-12 file the core checks with, run
// with the pub package json_schema. Every built-in manifest validates, the
// item vectors agree, and every item of every vector sketch that the core
// accepts is valid here too. (The graph rules of the compiler are Python only
// for now — memory/hub/port_types.md; the sketch cases are here to port.)
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:json_schema/json_schema.dart';

import 'vectors.dart';

Map<String, dynamic> _read(String name) =>
    jsonDecode(File(vectorPath(name)).readAsStringSync()) as Map<String, dynamic>;

JsonSchema _schemaFor(Map<String, dynamic> root, String kind) {
  final s = Map<String, dynamic>.from(root)
    ..remove(r'$id')
    ..[r'$ref'] = '#/\$defs/$kind';
  return JsonSchema.create(s, schemaVersion: SchemaVersion.draft2020_12);
}

void main() {
  final root = _read('ports.schema.json');
  final vectors = _read('port_vectors.json');
  final kinds = <String, JsonSchema>{};
  bool valid(String kind, Object? item) =>
      kinds.putIfAbsent(kind, () => _schemaFor(root, kind)).validate(item).isValid;

  test('the registry validates', () {
    expect(valid('registry', _read('types.json')), isTrue);
  });

  test('every built-in manifest validates', () {
    final manifests = vectors['manifests'] as Map<String, dynamic>;
    expect(manifests, isNotEmpty);
    manifests.forEach((name, ports) {
      expect(valid('manifestPorts', ports), isTrue, reason: name);
    });
  });

  test('item vectors agree with the core', () {
    for (final i in (vectors['items'] as List).cast<Map<String, dynamic>>()) {
      expect(valid(i['kind'] as String, i['item']), i['valid'], reason: jsonEncode(i));
    }
  });

  test('items of the sketches: schema faults only where the core found them', () {
    for (final c in (vectors['cases'] as List).cast<Map<String, dynamic>>()) {
      final expect_ = c['expect'] as Map<String, dynamic>;
      final schemaFault = !(expect_['ok'] as bool) &&
          (expect_['errors'] as List).any((e) => (e as Map)['code'] == 'schema');
      final sketch = c['sketch'] as Map<String, dynamic>;
      final items = [
        for (final p in sketch['pieces'] as List) valid('piece', p),
        for (final w in sketch['wires'] as List) valid('wire', w),
      ];
      expect(valid('sketch', sketch), isTrue, reason: c['name'] as String);
      expect(items.contains(false), schemaFault, reason: c['name'] as String);
    }
  });
}
