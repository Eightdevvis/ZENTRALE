// Die KI-Seite — schlicht wie die Claude-App: oben Menü und Titel, in der
// Mitte der Verlauf, unten das Eingabefeld. Die Logik steckt in ChatSteuerung.

import 'package:flutter/material.dart';

import '../auge/auge.dart';
import '../einstellungen/einstellungen_seite.dart';
import '../thema/farben.dart';
import 'chat_steuerung.dart';
import 'nachricht_ansicht.dart';

class ChatSeite extends StatefulWidget {
  const ChatSeite({super.key, required this.steuerung, required this.einstellungen});

  final ChatSteuerung steuerung;
  final EinstellungenSeite Function() einstellungen;

  @override
  State<ChatSeite> createState() => _ChatSeiteState();
}

class _ChatSeiteState extends State<ChatSeite> {
  final _eingabe = TextEditingController();
  final _rollen = ScrollController();

  ChatSteuerung get s => widget.steuerung;

  @override
  void initState() {
    super.initState();
    s.addListener(_nachUnten);
  }

  @override
  void dispose() {
    s.removeListener(_nachUnten);
    _eingabe.dispose();
    _rollen.dispose();
    super.dispose();
  }

  void _nachUnten() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_rollen.hasClients) _rollen.jumpTo(_rollen.position.maxScrollExtent);
    });
  }

  void _senden() {
    final t = _eingabe.text;
    if (t.trim().isEmpty) return;
    _eingabe.clear();
    s.senden(t);
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: s,
        builder: (context, _) => Scaffold(
          appBar: AppBar(
            title: Text(s.titel.isEmpty ? 'ZENTRALE' : s.titel,
                style: Theme.of(context).textTheme.titleMedium, overflow: TextOverflow.ellipsis),
            actions: [
              IconButton(
                tooltip: 'Neuer Chat',
                icon: const Icon(Icons.edit_square),
                onPressed: s.neu,
              ),
            ],
          ),
          drawer: _Leiste(steuerung: s, einstellungen: widget.einstellungen),
          body: SafeArea(
            child: Column(children: [
              if (s.fehler != null) _Fehler(s.fehler!, () => setState(() => s.fehler = null)),
              Expanded(child: s.nachrichten.isEmpty && !s.denkt ? const _Leer() : _verlauf()),
              _Eingabe(controller: _eingabe, denkt: s.denkt, senden: _senden, stoppen: s.stoppen),
            ]),
          ),
        ),
      );

  Widget _verlauf() {
    final ns = s.nachrichten;
    final e = s.entstehend;
    return ListView.builder(
      controller: _rollen,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: ns.length + (e != null ? 1 : 0),
      itemBuilder: (context, i) {
        if (i == ns.length) {
          return KiAntwort(text: e!.text, denken: e.denken, denktNoch: true);
        }
        final n = ns[i];
        if (n.vonSasha) return SashaBlase(n.text);
        return KiAntwort(
          text: n.text,
          denken: n.denken,
          abgebrochen: n.abgebrochen,
          zuletzt: i == ns.length - 1 && e == null,
          wiederholen: s.wiederholen,
        );
      },
    );
  }
}

class _Leer extends StatelessWidget {
  const _Leer();
  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const SizedBox(width: 120, height: 90, child: Auge(oeffnenIn: Duration(milliseconds: 600))),
          const SizedBox(height: 12),
          Text('Wie kann ich helfen?', style: Theme.of(context).textTheme.titleLarge),
        ]),
      );
}

class _Fehler extends StatelessWidget {
  const _Fehler(this.text, this.weg);
  final String text;
  final VoidCallback weg;
  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.errorContainer,
        child: ListTile(
          dense: true,
          title: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
          trailing: IconButton(icon: const Icon(Icons.close), onPressed: weg),
        ),
      );
}

class _Eingabe extends StatelessWidget {
  const _Eingabe({
    required this.controller,
    required this.denkt,
    required this.senden,
    required this.stoppen,
  });

  final TextEditingController controller;
  final bool denkt;
  final VoidCallback senden;
  final VoidCallback stoppen;

  @override
  Widget build(BuildContext context) {
    final a = AugeFarben.von(context);
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      padding: const EdgeInsets.fromLTRB(16, 4, 6, 4),
      decoration: BoxDecoration(
        color: flaeche(context),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Expanded(
          child: TextField(
            controller: controller,
            minLines: 1,
            maxLines: 6,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
              hintText: 'Schreib ZENTRALE …',
              border: InputBorder.none,
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: denkt
              ? IconButton.filled(
                  tooltip: 'Stopp',
                  onPressed: stoppen,
                  icon: const Icon(Icons.stop_rounded),
                )
              : ListenableBuilder(
                  listenable: controller,
                  builder: (context, _) => IconButton.filled(
                    tooltip: 'Senden',
                    style: IconButton.styleFrom(backgroundColor: a.iris, foregroundColor: a.pupille),
                    onPressed: controller.text.trim().isEmpty ? null : senden,
                    icon: const Icon(Icons.arrow_upward_rounded),
                  ),
                ),
        ),
      ]),
    );
  }
}

class _Leiste extends StatelessWidget {
  const _Leiste({required this.steuerung, required this.einstellungen});
  final ChatSteuerung steuerung;
  final EinstellungenSeite Function() einstellungen;

  @override
  Widget build(BuildContext context) {
    final s = steuerung;
    return Drawer(
      child: SafeArea(
        child: Column(children: [
          ListTile(
            leading: const Icon(Icons.edit_square),
            title: const Text('Neuer Chat'),
            onTap: () {
              Navigator.pop(context);
              s.neu();
            },
          ),
          const Divider(height: 1),
          Expanded(
            child: RefreshIndicator(
              onRefresh: s.abgleichen,
              child: ListView(children: [
                for (final g in s.liste)
                  ListTile(
                    title: Text(g.titel, maxLines: 1, overflow: TextOverflow.ellipsis),
                    selected: g.id == s.gespraech,
                    onTap: () {
                      Navigator.pop(context);
                      s.oeffnen(g.id);
                    },
                  ),
              ]),
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: s.gleichtAb
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.settings_outlined),
            title: const Text('Einstellungen'),
            onTap: () {
              Navigator.pop(context);
              Navigator.of(context).push(MaterialPageRoute(builder: (_) => einstellungen()));
            },
          ),
        ]),
      ),
    );
  }
}
