// Einstellungen: API-Schlüssel und was die App gerade weiß.

import 'package:flutter/material.dart';

import '../ablage/ablage.dart';
import '../ki/kontext.dart';
import 'einstellungen.dart';

class EinstellungenSeite extends StatefulWidget {
  const EinstellungenSeite({super.key, required this.einstellungen, required this.ablage});

  final Einstellungen einstellungen;
  final Ablage ablage;

  @override
  State<EinstellungenSeite> createState() => _EinstellungenSeiteState();
}

class _EinstellungenSeiteState extends State<EinstellungenSeite> {
  final _key = TextEditingController();
  bool _hatKey = false;
  Kontext? _kontext;

  @override
  void initState() {
    super.initState();
    _laden();
  }

  Future<void> _laden() async {
    final k = await widget.einstellungen.anthropicSchluessel();
    final kontext = await Kontext.laden(widget.ablage);
    if (!mounted) return;
    setState(() {
      _hatKey = k != null && k.isNotEmpty;
      _kontext = kontext;
    });
  }

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final k = _kontext;
    return Scaffold(
      appBar: AppBar(title: const Text('Einstellungen')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Claude-API-Schlüssel', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        TextField(
          controller: _key,
          obscureText: true,
          decoration: InputDecoration(
            border: const OutlineInputBorder(),
            hintText: _hatKey ? 'gespeichert — neu eintragen zum Ersetzen' : 'sk-ant-…',
          ),
        ),
        const SizedBox(height: 8),
        Row(children: [
          FilledButton(
            onPressed: () async {
              await widget.einstellungen.anthropicSetzen(_key.text);
              _key.clear();
              await _laden();
            },
            child: const Text('Speichern'),
          ),
          const SizedBox(width: 8),
          if (_hatKey)
            TextButton(
              onPressed: () async {
                await widget.einstellungen.anthropicSetzen(null);
                await _laden();
              },
              child: const Text('Entfernen'),
            ),
        ]),
        const SizedBox(height: 24),
        Text('KI', style: Theme.of(context).textTheme.titleSmall),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(k == null ? '…' : '${k.modell} · effort ${k.effort}'),
          subtitle: Text(k == null
              ? ''
              : k.ausDemKern
                  ? 'Gedächtnis und Regeln aus ZENTRALE, Stand ${k.stand}'
                  : 'Notbetrieb: noch kein Kontext aus ZENTRALE abgeglichen'),
        ),
        const SizedBox(height: 8),
        Text('Mitte', style: Theme.of(context).textTheme.titleSmall),
        const ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('noch nicht eingerichtet'),
          subtitle: Text('Gespräche bleiben auf dem Handy, bis der Abgleich steht — '
              'dann wandern sie automatisch hoch.'),
        ),
      ]),
    );
  }
}
