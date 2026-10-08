// Eine Nachricht, gezeichnet wie in der Claude-App: Sasha rechts in einer
// Blase, die KI als freier Text über die ganze Breite, Denken zum Aufklappen.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../auge/auge.dart';
import '../thema/farben.dart';

class SashaBlase extends StatelessWidget {
  const SashaBlase(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(left: 48, top: 8, bottom: 8),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: flaeche(context),
            borderRadius: BorderRadius.circular(18),
          ),
          child: SelectableText(text, style: Theme.of(context).textTheme.bodyLarge),
        ),
      );
}

class KiAntwort extends StatelessWidget {
  const KiAntwort({
    super.key,
    required this.text,
    this.denken,
    this.denktNoch = false,
    this.abgebrochen = false,
    this.zuletzt = false,
    this.wiederholen,
  });

  final String text;
  final String? denken;
  final bool denktNoch;
  final bool abgebrochen;
  final bool zuletzt;
  final VoidCallback? wiederholen;

  @override
  Widget build(BuildContext context) {
    final thema = Theme.of(context);
    final leise = thema.colorScheme.onSurface.withValues(alpha: .55);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (denktNoch && text.isEmpty)
          const SizedBox(width: 56, height: 40, child: Auge(denkt: true, oeffnenIn: Duration.zero)),
        if (denken != null && denken!.isNotEmpty) _Denken(denken!, offen: denktNoch && text.isEmpty),
        if (text.isNotEmpty)
          MarkdownBody(
            data: text,
            selectable: true,
            styleSheet: MarkdownStyleSheet.fromTheme(thema).copyWith(
              p: thema.textTheme.bodyLarge,
              code: thema.textTheme.bodyMedium?.copyWith(
                fontFamily: 'monospace', backgroundColor: flaeche(context)),
              codeblockDecoration: BoxDecoration(
                color: flaeche(context), borderRadius: BorderRadius.circular(8)),
            ),
          ),
        if (abgebrochen)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('abgebrochen', style: thema.textTheme.bodySmall?.copyWith(color: leise)),
          ),
        if (!denktNoch && text.isNotEmpty)
          Row(children: [
            IconButton(
              tooltip: 'Kopieren',
              visualDensity: VisualDensity.compact,
              iconSize: 18,
              color: leise,
              icon: const Icon(Icons.copy_rounded),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: text));
                ScaffoldMessenger.of(context)
                    .showSnackBar(const SnackBar(content: Text('Kopiert')));
              },
            ),
            if (zuletzt && wiederholen != null)
              IconButton(
                tooltip: 'Neu antworten',
                visualDensity: VisualDensity.compact,
                iconSize: 18,
                color: leise,
                icon: const Icon(Icons.refresh_rounded),
                onPressed: wiederholen,
              ),
          ]),
      ]),
    );
  }
}

class _Denken extends StatelessWidget {
  const _Denken(this.text, {this.offen = false});
  final String text;
  final bool offen;

  @override
  Widget build(BuildContext context) {
    final thema = Theme.of(context);
    final leise = thema.colorScheme.onSurface.withValues(alpha: .6);
    return Theme(
      data: thema.copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        key: ValueKey(offen),
        initiallyExpanded: offen,
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        dense: true,
        title: Text(offen ? 'Denkt nach …' : 'Gedanken',
            style: thema.textTheme.bodyMedium?.copyWith(color: leise)),
        expandedAlignment: Alignment.topLeft,
        children: [
          Text(text, style: thema.textTheme.bodySmall?.copyWith(color: leise, height: 1.4)),
        ],
      ),
    );
  }
}
