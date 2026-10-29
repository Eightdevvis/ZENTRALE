// Einstellungen: ZENTRALE-Konto (anmelden/abmelden), Stand der Mitte, KI,
// Kalender — und der Claude-Schlüssel von Hand als Notbehelf. Zeichnet nur;
// die Logik steht in AbgleichSteuerung, Konto und Einstellungen.

import 'package:flutter/material.dart';

import '../ablage/ablage.dart';
import '../ki/kontext.dart';
import '../l10n/app_localizations.dart';
import '../konto/geheim.dart';
import '../konto/konto.dart';
import '../mitte/abgleich_steuerung.dart';
import '../update/update_controller.dart';
import '../update/update_section.dart';
import 'einstellungen.dart';

class EinstellungenSeite extends StatefulWidget {
  const EinstellungenSeite({
    super.key,
    required this.einstellungen,
    required this.ablage,
    required this.abgleich,
    this.updates,
  });

  final Einstellungen einstellungen;
  final Ablage ablage;
  final AbgleichSteuerung abgleich;

  /// The self-update section (lib/update) — none in tests that do not need it.
  final UpdateController? updates;

  @override
  State<EinstellungenSeite> createState() => _EinstellungenSeiteState();
}

/// „2026-10-28T21:03:11.000Z“ → „28.10. 22:03“ (Ortszeit des Handys).
String zeitText(String? iso) {
  final d = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (d == null) return 'noch nie';
  return '${d.day}.${d.month}. ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}

class _EinstellungenSeiteState extends State<EinstellungenSeite> {
  final _key = TextEditingController();
  final _name = TextEditingController();
  final _passwort = TextEditingController();
  bool _hatKey = false;
  bool _kiAusMitte = false;
  bool _meldetAn = false;
  String? _anmeldeFehler;
  Kontext? _kontext;

  AbgleichSteuerung get _a => widget.abgleich;

  @override
  void initState() {
    super.initState();
    _a.addListener(_laden);
    _a.laden();
    _laden();
  }

  Future<void> _laden() async {
    final k = await widget.einstellungen.anthropicSchluessel();
    final kontext = await Kontext.laden(widget.ablage);
    final s = _a.sitzung;
    final ausMitte = s != null && await geheimLesen(widget.ablage, s.kontoSchluessel, kiAnthropic) != null;
    if (!mounted) return;
    setState(() {
      _hatKey = k != null && k.isNotEmpty;
      _kiAusMitte = ausMitte;
      _kontext = kontext;
    });
  }

  @override
  void dispose() {
    _a.removeListener(_laden);
    _key.dispose();
    _name.dispose();
    _passwort.dispose();
    super.dispose();
  }

  Future<void> _anmelden() async {
    setState(() {
      _meldetAn = true;
      _anmeldeFehler = null;
    });
    try {
      await _a.anmelden(_name.text, _passwort.text);
      _passwort.clear();
    } on KontoFehler catch (e) {
      _anmeldeFehler = e.meldung;
    } finally {
      _passwort.clear(); // nie länger als nötig im Speicher
      if (mounted) setState(() => _meldetAn = false);
    }
  }

  Widget _titel(String t) => Padding(
        padding: const EdgeInsets.only(top: 24, bottom: 4),
        child: Text(t, style: Theme.of(context).textTheme.titleSmall),
      );

  @override
  Widget build(BuildContext context) {
    final k = _kontext;
    final s = _a.sitzung;
    final z = _a.zustand;
    return Scaffold(
      appBar: AppBar(title: const Text('Einstellungen')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        _titel('ZENTRALE-Konto'),
        if (s != null) ...[
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.account_circle_outlined),
            title: Text(s.name),
            subtitle: const Text('Angemeldet — Gespräche, Kontext, Kalender und der '
                'Claude-Schlüssel kommen über die Mitte.'),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton(onPressed: _a.abmelden, child: const Text('Abmelden')),
          ),
        ] else ...[
          const Text('Einmal mit Benutzername und Passwort anmelden. Das Passwort wird '
              'nicht gespeichert — nur die Sitzung und der Kontoschlüssel, im Keystore.'),
          const SizedBox(height: 12),
          TextField(
            controller: _name,
            autocorrect: false,
            decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Benutzername'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _passwort,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Passwort'),
            onSubmitted: (_) => _anmelden(),
          ),
          const SizedBox(height: 8),
          Row(children: [
            FilledButton(onPressed: _meldetAn ? null : _anmelden, child: const Text('Anmelden')),
            if (_meldetAn) ...[
              const SizedBox(width: 12),
              const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
              const SizedBox(width: 8),
              const Text('Schlüssel wird berechnet …'),
            ],
          ]),
          if (_anmeldeFehler != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_anmeldeFehler!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
        ],
        _titel('Mitte'),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: _a.laeuft
              ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
              : Icon(z.fehler == null ? Icons.cloud_done_outlined : Icons.cloud_off_outlined),
          title: Text(s == null
              ? 'nicht angemeldet — alles bleibt auf dem Handy'
              : 'Letzter Abgleich: ${zeitText(z.letzterErfolg)}'),
          subtitle: Text([
            if (z.fehler != null) 'Fehler: ${z.fehler}',
            if (s != null && z.letzterVersuch != null) 'zuletzt versucht ${zeitText(z.letzterVersuch)}',
          ].join('\n')),
          trailing: s == null
              ? null
              : IconButton(tooltip: 'Jetzt abgleichen', icon: const Icon(Icons.sync), onPressed: _a.jetzt),
        ),
        if (widget.updates != null) ...[
          _titel(AppLocalizations.of(context).updateTitle),
          UpdateSection(controller: widget.updates!),
        ],
        _titel('Kalender'),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.calendar_month_outlined),
          title: Text(z.kalenderInMitte ? 'kommt über die Mitte' : 'noch nicht in der Mitte'),
          subtitle: Text(z.kalenderInMitte
              ? 'Neue Termine vom Handy gehen als Vorschlag an die Rechner.'
              : 'Sobald ein Rechner den Kalender in die Cloud gibt, ist er hier.'),
        ),
        _titel('KI'),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(k == null ? '…' : '${k.modell} · effort ${k.effort}'),
          subtitle: Text([
            if (k != null)
              k.ausDemKern
                  ? 'Gedächtnis und Regeln aus ZENTRALE, Stand ${k.stand}'
                  : 'Notbetrieb: noch kein Kontext aus ZENTRALE abgeglichen',
            _hatKey
                ? 'Claude-Schlüssel: von Hand eingetragen'
                : _kiAusMitte
                    ? 'Claude-Schlüssel: aus ZENTRALE (Adapter)'
                    : 'Claude-Schlüssel: fehlt',
          ].join('\n')),
        ),
        const SizedBox(height: 8),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('Claude-Schlüssel von Hand (Notbehelf)'),
          children: [
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
            const SizedBox(height: 8),
          ],
        ),
      ]),
    );
  }
}
