import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/gz_consent.dart';
import '../../core/hive_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_nav.dart';
import '../../widgets/tiara/gz_frame_card.dart';

const _labels = {
  'exp:coastal': 'Coastal life',
  'exp:food': 'Everyday food',
  'exp:heritage': 'Living heritage',
  'exp:nature': 'Nature & quiet',
  'exp:neighbourhood': 'Neighbourhood discovery',
};

String _labelFor(String key) {
  if (_labels.containsKey(key)) return _labels[key]!;
  if (key.startsWith('cat:')) return key.substring(4).replaceAll('_', ' ');
  return key;
}

String _sourceText(String s) => switch (s) {
      'stated' => 'You told me',
      'survey' => 'From your trip survey',
      _ => 'Learned from what you did',
    };

/// "What HIVE remembers about you" — every learned preference with where it
/// came from and how sure it is. You can change it, remove it, or erase all.
class MemoryScreen extends StatefulWidget {
  final AuthController auth;
  const MemoryScreen({super.key, required this.auth});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  final _api = HiveApiClient();
  HiveProfile? _profile;
  bool _loading = true;
  String? _error;

  String get _token => widget.auth.accessToken!;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final p = await _api.profile(_token);
      if (mounted) setState(() {
        _profile = p;
        _loading = false;
      });
    } on GZApiException catch (e) {
      if (mounted) setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _save({Map<String, dynamic>? constraints, Map<String, double>? stated, List<String>? remove}) async {
    try {
      final p = await _api.updateProfile(_token, constraints: constraints, stated: stated, remove: remove);
      if (mounted) setState(() => _profile = p);
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _turnOn() async {
    final ok = await GZConsent.ask(context, _token, 'personalization');
    if (ok && mounted) {
      setState(() {});
      _load();
    }
  }

  Future<void> _eraseAll() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Erase everything HIVE learned?'),
        content: const Text('This deletes your learned preferences, saves, skips and visited list. It cannot be undone. Your account and trips stay.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Erase')),
        ],
      ),
    );
    if (yes != true) return;
    try {
      await _api.deleteMemory(_token);
      await _load();
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  List<String> _list(String k) => List<String>.from((_profile!.constraints[k] as List?) ?? const []);

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: const Text('What HIVE remembers'), actions: const [GZHomeAction()]),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Text(_error!), const SizedBox(height: 10), OutlinedButton(onPressed: _load, child: const Text('Try again'))]))
              : Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 48), children: _body(context, ink, text)),
                  ),
                ),
    );
  }

  List<Widget> _body(BuildContext context, GZInk ink, TextTheme text) {
    final p = _profile!;
    final on = GZConsent.personalization;
    final diet = _list('dietary');
    final access = _list('accessibility');
    final spend = (p.constraints['max_spend_per_place'] as num?)?.toInt();
    return [
      if (!on)
        Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: GZFrameCard(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Icon(Icons.psychology_alt_outlined, color: ink.accent),
              const SizedBox(width: 12),
              Expanded(child: Text('Memory is off, so HIVE stores nothing about you and suggestions are the same for everyone.', style: text.bodyMedium)),
              const SizedBox(width: 8),
              FilledButton(onPressed: _turnOn, child: const Text('Turn on')),
            ]),
          ),
        ),
      Text('Your rules', style: text.titleMedium),
      const SizedBox(height: 4),
      Text('These are never relaxed quietly. If nothing fits, HIVE tells you instead.', style: text.bodySmall?.copyWith(color: ink.muted)),
      const SizedBox(height: 10),
      GZFrameCard(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Food', style: text.labelLarge),
          const SizedBox(height: 6),
          Wrap(spacing: 8, children: [
            for (final d in const [('veg', 'Vegetarian'), ('jain', 'Jain'), ('halal', 'Halal'), ('vegan', 'Vegan')])
              FilterChip(
                label: Text(d.$2),
                selected: diet.contains(d.$1),
                onSelected: !on
                    ? null
                    : (v) {
                        final next = [...diet]..remove(d.$1);
                        if (v) next.add(d.$1);
                        _save(constraints: {...p.constraints, 'dietary': next});
                      },
              ),
          ]),
          const SizedBox(height: 14),
          Text('Budget per place', style: text.labelLarge),
          const SizedBox(height: 6),
          Wrap(spacing: 8, children: [
            for (final b in const [(null, 'No limit'), (150, '₹150'), (300, '₹300'), (600, '₹600')])
              ChoiceChip(
                label: Text(b.$2),
                selected: spend == b.$1,
                onSelected: !on
                    ? null
                    : (_) {
                        final c = {...p.constraints};
                        if (b.$1 == null) {
                          c.remove('max_spend_per_place');
                        } else {
                          c['max_spend_per_place'] = b.$1;
                        }
                        _save(constraints: c);
                      },
              ),
          ]),
          const SizedBox(height: 10),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('I need wheelchair access'),
            subtitle: const Text('Places with access unknown are shown with a warning.'),
            value: access.contains('wheelchair'),
            onChanged: !on
                ? null
                : (v) => _save(constraints: {...p.constraints, 'accessibility': v ? ['wheelchair'] : <String>[]}),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Only places with confirmed access'),
            value: p.constraints['accessibility_strict'] == true,
            onChanged: !on || !access.contains('wheelchair') ? null : (v) => _save(constraints: {...p.constraints, 'accessibility_strict': v}),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('I\'m usually with children'),
            value: p.constraints['kids'] == true,
            onChanged: !on ? null : (v) => _save(constraints: {...p.constraints, 'kids': v}),
          ),
        ]),
      ),
      const SizedBox(height: 22),
      Text('What I\'ve picked up', style: text.titleMedium),
      const SizedBox(height: 4),
      Text('Drag to correct me. Remove anything that\'s wrong.', style: text.bodySmall?.copyWith(color: ink.muted)),
      const SizedBox(height: 10),
      if (p.affinities.isEmpty)
        Text('Nothing yet. Like, skip or visit a few places and it shows up here.', style: text.bodyMedium)
      else
        for (final a in p.affinities)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: GZFrameCard(
              padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
              radius: 16,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(_labelFor(a.key), style: text.titleSmall?.copyWith(fontWeight: FontWeight.w800))),
                  IconButton(tooltip: 'Forget this', icon: const Icon(Icons.close), onPressed: on ? () => _save(remove: [a.key]) : null),
                ]),
                Text('${_sourceText(a.source)} · ${(a.confidence * 100).round()}% sure', style: text.bodySmall?.copyWith(color: ink.muted)),
                Slider(
                  min: -1,
                  max: 1,
                  divisions: 20,
                  value: a.weight.clamp(-1.0, 1.0).toDouble(),
                  label: a.weight >= 0 ? 'Likes' : 'Avoids',
                  onChanged: null,
                  onChangeEnd: null,
                ),
                Wrap(spacing: 8, children: [
                  for (final v in const [(-0.8, 'Avoid'), (0.0, 'Neutral'), (0.8, 'Love')])
                    ActionChip(
                      label: Text(v.$2),
                      onPressed: on ? () => _save(stated: {a.key: v.$1}) : null,
                    ),
                ]),
              ]),
            ),
          ),
      const SizedBox(height: 10),
      Text('${p.visited} visited · ${p.dismissed} hidden', style: text.bodySmall?.copyWith(color: ink.muted)),
      const SizedBox(height: 16),
      OutlinedButton.icon(
        onPressed: _eraseAll,
        icon: const Icon(Icons.delete_outline),
        label: const Text('Erase everything HIVE learned'),
      ),
    ];
  }
}
