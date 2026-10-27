import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/hive_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_nav.dart';

/// Shows a legal document (privacy / terms / safety) fetched from the
/// backend, so the text the app shows is always the text the server holds.
class LegalScreen extends StatefulWidget {
  final String doc; // privacy | terms | safety
  final String title;
  const LegalScreen({super.key, required this.doc, required this.title});

  @override
  State<LegalScreen> createState() => _LegalScreenState();
}

class _LegalScreenState extends State<LegalScreen> {
  final _api = HiveApiClient();
  late Future<String> _future = _api.legal(widget.doc);

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: Text(widget.title), actions: const [GZHomeAction()]),
      body: FutureBuilder<String>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) {
            final msg = snap.error is GZApiException ? (snap.error as GZApiException).message : 'Could not load this page.';
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(msg, textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  OutlinedButton(onPressed: () => setState(() => _future = _api.legal(widget.doc)), child: const Text('Try again')),
                ]),
              ),
            );
          }
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: ListView(padding: const EdgeInsets.fromLTRB(20, 16, 20, 40), children: _render(context, snap.data!, ink)),
            ),
          );
        },
      ),
    );
  }

  List<Widget> _render(BuildContext context, String md, GZInk ink) {
    final t = Theme.of(context).textTheme;
    final out = <Widget>[];
    for (final raw in md.split('\n')) {
      final line = raw.trimRight();
      if (line.isEmpty || RegExp(r'^\|[-| ]+\|$').hasMatch(line)) continue;
      if (line.startsWith('# ')) {
        out.add(Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(line.substring(2), style: t.headlineSmall)));
      } else if (line.startsWith('## ')) {
        out.add(Padding(padding: const EdgeInsets.only(top: 18, bottom: 6), child: Text(line.substring(3), style: t.titleMedium)));
      } else if (line.startsWith('> ')) {
        out.add(Container(
          margin: const EdgeInsets.symmetric(vertical: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: ink.paperAlt.withOpacity(0.5), borderRadius: BorderRadius.circular(12), border: Border.all(color: ink.hairline)),
          child: Text(_plain(line.substring(2)), style: t.bodyMedium),
        ));
      } else if (line.startsWith('|')) {
        final cells = line.split('|').map((c) => c.trim()).where((c) => c.isNotEmpty).toList();
        out.add(Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Text(cells.join('  ·  '), style: t.bodySmall?.copyWith(color: ink.muted)),
        ));
      } else if (line.startsWith('* ') || RegExp(r'^\d+\. ').hasMatch(line)) {
        out.add(Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Text(line.startsWith('* ') ? '•  ${_plain(line.substring(2))}' : _plain(line), style: t.bodyMedium?.copyWith(height: 1.45)),
        ));
      } else {
        out.add(Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(_plain(line), style: t.bodyMedium?.copyWith(height: 1.45))));
      }
    }
    return out;
  }

  String _plain(String s) => s.replaceAll('**', '').replaceAll('`', '');
}
