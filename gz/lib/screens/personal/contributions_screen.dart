import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/auth_controller.dart';
import '../../core/personal_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/tiara/gz_frame_card.dart';
import 'add_place_screen.dart';
import 'contribute_screen.dart';

/// CONTRIBUTIONS — "HELP BUILD GROUNDZERO". Five real actions, each
/// posting to its own backend endpoint and then appearing under "Your
/// impact" as pending until reviewed. The level line is a quiet progress
/// marker, never a leaderboard.
class ContributionsScreen extends StatefulWidget {
  final AuthController auth;
  const ContributionsScreen({super.key, required this.auth});

  @override
  State<ContributionsScreen> createState() => _ContributionsScreenState();
}

const _levels = [(0, 'Explorer'), (3, 'Pathfinder'), (8, 'Local Guide'), (16, 'Insider'), (31, 'Pioneer')];

const _kindLabels = {
  'add_place': 'New place',
  'suggest_update': 'Update',
  'local_tip': 'Local tip',
  'report_incorrect': 'Report',
  'add_media': 'Media',
};

class _ContributionsScreenState extends State<ContributionsScreen> {
  final _api = PersonalApiClient();
  late Future<GZMyContributions> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<GZMyContributions> _load() => _api.myContributions(widget.auth.accessToken!);

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  void _reload() => setState(() => _future = _load());

  Future<void> _openAddPlace() async {
    final result = await Navigator.of(context).push(MaterialPageRoute(builder: (_) => AddPlaceScreen(auth: widget.auth)));
    if (result != null) _reload();
  }

  Future<void> _open(ContributeKind kind) async {
    final result = await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ContributeScreen(auth: widget.auth, kind: kind)));
    if (result != null) _reload();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final actions = <(IconData, String, String, VoidCallback, bool)>[
      (Icons.add_location_alt_outlined, 'Add a place', 'Missing somewhere? Submit it for review.', _openAddPlace, true),
      (ContributeKind.suggestUpdate.icon, 'Suggest an update', 'Correct a detail on a place.', () => _open(ContributeKind.suggestUpdate), false),
      (ContributeKind.localTip.icon, 'Share a local tip', 'The insider knowledge visitors miss.', () => _open(ContributeKind.localTip), false),
      (ContributeKind.reportIncorrect.icon, 'Report an issue', 'Flag wrong or outdated information.', () => _open(ContributeKind.reportIncorrect), false),
      (ContributeKind.addMedia.icon, 'Add media', 'Link a helpful photo or video.', () => _open(ContributeKind.addMedia), false),
    ];

    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: const Text('Contributions'), actions: const [GZHomeAction()]),
      body: FutureBuilder<GZMyContributions>(
        future: _future,
        builder: (context, snap) {
          final loading = snap.connectionState != ConnectionState.done;
          final data = snap.data;
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 980),
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Text('Help build GroundZero', style: text.headlineSmall?.copyWith(color: ink.text)),
                  const SizedBox(height: 6),
                  Text('Every real place GroundZero knows about started with someone like you pointing it out.', style: text.bodyLarge?.copyWith(color: ink.muted)),
                  const SizedBox(height: 22),
                  LayoutBuilder(builder: (context, box) {
                    const gap = 16.0;
                    final cols = box.maxWidth >= 760 ? 3 : (box.maxWidth >= 480 ? 2 : 1);
                    final w = (box.maxWidth - gap * (cols - 1)) / cols;
                    return Wrap(spacing: gap, runSpacing: gap, children: [
                      for (final a in actions)
                        SizedBox(
                          width: w,
                          height: 132,
                          child: GZFrameCard(
                            onTap: a.$4,
                            color: a.$5 ? ink.accent : null,
                            padding: const EdgeInsets.all(18),
                            child: _ActionBody(icon: a.$1, title: a.$2, sub: a.$3, onAccent: a.$5),
                          ),
                        ),
                    ]);
                  }),
                  const SizedBox(height: 32),
                  Text('Your impact', style: text.titleLarge?.copyWith(color: ink.text)),
                  const SizedBox(height: 14),
                  if (loading)
                    const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
                  else if (snap.hasError)
                    Text('Could not load your contributions. Pull back and try again.', style: text.bodyMedium)
                  else if (data != null) ...[
                    _LevelCard(data: data),
                    const SizedBox(height: 16),
                    if (data.contributions.isEmpty)
                      Text('Nothing submitted yet — pick an action above to get started.', style: text.bodyMedium)
                    else
                      for (final c in data.contributions) _ContributionCard(c: c),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ActionBody extends StatelessWidget {
  final IconData icon;
  final String title;
  final String sub;
  final bool onAccent;
  const _ActionBody({required this.icon, required this.title, required this.sub, required this.onAccent});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final fg = onAccent ? (ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE)) : ink.text;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: onAccent ? fg : ink.accent, size: 24),
        const Spacer(),
        Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: text.titleSmall?.copyWith(color: fg, fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text(sub, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.bodySmall?.copyWith(color: onAccent ? fg : ink.muted)),
      ],
    );
  }
}

class _LevelCard extends StatelessWidget {
  final GZMyContributions data;
  const _LevelCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final n = data.totalApproved;
    final nextIdx = _levels.indexWhere((l) => l.$1 > n);
    final hasNext = nextIdx != -1;
    final prevAt = hasNext ? _levels[nextIdx - 1].$1 : _levels.last.$1;
    final nextAt = hasNext ? _levels[nextIdx].$1 : n;
    final progress = hasNext ? ((n - prevAt) / (nextAt - prevAt)).clamp(0.0, 1.0).toDouble() : 1.0;
    return GZFrameCard(
      shadowOffset: 0,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.workspace_premium_outlined, color: ink.accent),
              const SizedBox(width: 10),
              Text(data.explorerLevel, style: text.titleMedium?.copyWith(color: ink.text)),
              const Spacer(),
              Text('$n verified', style: text.labelMedium),
            ],
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(value: progress, minHeight: 6, color: ink.accent, backgroundColor: ink.accent.withOpacity(0.18)),
          ),
          const SizedBox(height: 8),
          Text(
            hasNext ? '${nextAt - n} more verified contribution${nextAt - n == 1 ? '' : 's'} to ${_levels[nextIdx].$2}' : 'Top level reached — thank you.',
            style: text.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _ContributionCard extends StatelessWidget {
  final GZContribution c;
  const _ContributionCard({required this.c});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final approved = c.status == 'approved';
    final rejected = c.status == 'rejected';
    final color = approved ? const Color(0xFF2E9E5B) : (rejected ? scheme.error : ink.muted);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GZFrameCard(
        shadowOffset: 0,
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(approved ? Icons.check_circle : (rejected ? Icons.cancel_outlined : Icons.hourglass_top), size: 18, color: color),
              const SizedBox(width: 8),
              Expanded(child: Text(c.placeName, style: text.titleSmall?.copyWith(color: ink.text))),
              GZTag(_kindLabels[c.kind] ?? c.kind),
            ]),
            const SizedBox(height: 8),
            Text(c.impactMessage, style: text.bodyMedium?.copyWith(color: color)),
            if (c.explorerPoints != null) ...[
              const SizedBox(height: 6),
              Text('+${c.explorerPoints} Explorer Points', style: text.labelSmall),
            ],
          ],
        ),
      ),
    );
  }
}
