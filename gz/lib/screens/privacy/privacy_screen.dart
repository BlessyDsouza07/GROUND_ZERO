import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/gz_consent.dart';
import '../../core/hive_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_nav.dart';
import '../../widgets/gz_nudge_watcher.dart';
import '../../widgets/tiara/gz_frame_card.dart';
import '../hive/memory_screen.dart';
import 'legal_screen.dart';

/// One place for every choice that touches the person's data: consent
/// switches, what's remembered, export, delete, legal text, and the
/// emergency numbers.
class PrivacyScreen extends StatefulWidget {
  final AuthController auth;
  const PrivacyScreen({super.key, required this.auth});

  @override
  State<PrivacyScreen> createState() => _PrivacyScreenState();
}

class _PrivacyScreenState extends State<PrivacyScreen> {
  final _api = HiveApiClient();
  List<({String label, String number})> _emergency = const [
    (label: 'All emergencies', number: '112'),
    (label: 'Ambulance', number: '108'),
    (label: 'Police', number: '100'),
    (label: 'Tourist helpline', number: '1363'),
  ];

  String get _token => widget.auth.accessToken!;

  @override
  void initState() {
    super.initState();
    GZConsent.load(_token).then((_) {
      if (mounted) setState(() {});
    });
    _api.emergency().then((e) {
      if (mounted) setState(() => _emergency = e);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _toggle(String kind, bool v) async {
    if (v) {
      final ok = await GZConsent.ask(context, _token, kind);
      if (!ok) return;
    } else {
      await GZConsent.set(_token, kind, false);
      if (kind == 'personalization') _toast('Turned off. What HIVE learned has been deleted.');
      if (kind == 'location') _toast('Location is off. Saved nudge history was deleted.');
    }
    if (mounted) setState(() {});
  }

  Future<void> _export() async {
    try {
      final json = await _api.exportJson(_token);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Your data'),
          content: SizedBox(width: 520, height: 360, child: SingleChildScrollView(child: SelectableText(json, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)))),
          actions: [
            TextButton(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: json));
                if (ctx.mounted) Navigator.pop(ctx);
                _toast('Copied. Paste it into a file to keep it.');
              },
              child: const Text('Copy'),
            ),
            FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
          ],
        ),
      );
    } on GZApiException catch (e) {
      _toast(e.message);
    }
  }

  Future<void> _deleteAccount() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete your account?'),
        content: const Text('This permanently deletes your account, trips, journal, contributions, preferences and consent records. It cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete everything')),
        ],
      ),
    );
    if (yes != true) return;
    try {
      await _api.deleteAccount(_token);
      GZConsent.clear();
      await widget.auth.signOut();
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on GZApiException catch (e) {
      _toast(e.message);
    }
  }

  Future<void> _call(String n) async {
    final ok = await launchUrl(Uri(scheme: 'tel', path: n));
    if (!ok) _toast('Dial $n on your phone.');
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    Widget section(String t) => Padding(padding: const EdgeInsets.fromLTRB(2, 22, 2, 8), child: Text(t, style: text.titleMedium));
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: const Text('Privacy & safety'), actions: const [GZHomeAction()]),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 48), children: [
            Text('You are in control. Everything below is off until you turn it on, and you can change it any time.', style: text.bodyMedium?.copyWith(color: ink.muted)),
            section('Your choices'),
            GZFrameCard(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Column(children: [
                SwitchListTile(
                  value: GZConsent.location,
                  onChanged: (v) => _toggle('location', v),
                  title: const Text('Location'),
                  subtitle: const Text('Show what\'s open and near you. No location history is saved.'),
                ),
                SwitchListTile(
                  value: GZConsent.personalization,
                  onChanged: (v) => _toggle('personalization', v),
                  title: const Text('Learn what I like'),
                  subtitle: const Text('Remembers saves, skips, visits. Turning off deletes it.'),
                ),
                SwitchListTile(
                  value: GZConsent.photos,
                  onChanged: (v) => _toggle('photos', v),
                  title: const Text('Camera and photos'),
                  subtitle: const Text('For journal and contributions. Hidden location data is stripped.'),
                ),
                SwitchListTile(
                  value: !GZNudges.paused,
                  onChanged: GZConsent.location ? (v) => setState(() => GZNudges.paused = !v) : null,
                  title: const Text('"You\'re near…" alerts'),
                  subtitle: const Text('Only while the app is open. Pause any time.'),
                ),
              ]),
            ),
            section('Your data'),
            GZFrameCard(
              padding: EdgeInsets.zero,
              child: Column(children: [
                ListTile(
                  leading: const Icon(Icons.psychology_alt_outlined),
                  title: const Text('See and edit what HIVE remembers'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MemoryScreen(auth: widget.auth))),
                ),
                ListTile(leading: const Icon(Icons.download_outlined), title: const Text('Download my data'), trailing: const Icon(Icons.chevron_right), onTap: _export),
                ListTile(
                  leading: Icon(Icons.delete_forever_outlined, color: Theme.of(context).colorScheme.error),
                  title: const Text('Delete my account and data'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _deleteAccount,
                ),
              ]),
            ),
            section('Read the rules'),
            GZFrameCard(
              padding: EdgeInsets.zero,
              child: Column(children: [
                for (final d in const [('privacy', 'Privacy Policy', Icons.lock_outline), ('terms', 'Terms of Use', Icons.gavel_outlined), ('safety', 'Staying safe', Icons.health_and_safety_outlined)])
                  ListTile(
                    leading: Icon(d.$3),
                    title: Text(d.$2),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => LegalScreen(doc: d.$1, title: d.$2))),
                  ),
              ]),
            ),
            section('In an emergency'),
            Wrap(spacing: 10, runSpacing: 10, children: [
              for (final e in _emergency)
                ActionChip(avatar: const Icon(Icons.call, size: 16), label: Text('${e.label}  ${e.number}'), onPressed: () => _call(e.number)),
            ]),
            const SizedBox(height: 8),
            Text('GroundZero is not an emergency service. Spot something wrong or unsafe in community content? Use "Report" on it.', style: text.bodySmall?.copyWith(color: ink.muted)),
          ]),
        ),
      ),
    );
  }
}
