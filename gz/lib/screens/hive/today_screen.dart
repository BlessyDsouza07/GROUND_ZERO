import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/gz_consent.dart';
import '../../core/gz_location.dart';
import '../../core/gz_maps.dart';
import '../../core/hive_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_nav.dart';
import '../../widgets/tiara/gz_frame_card.dart';
import '../../widgets/tiara/gz_reveal.dart';
import '../privacy/privacy_screen.dart';
import 'memory_screen.dart';

const _expNames = {
  'coastal': 'Coastal life',
  'food': 'Everyday food',
  'heritage': 'Living heritage',
  'nature': 'Nature & quiet',
  'neighbourhood': 'Neighbourhood',
};

const _roleNames = {
  'anchor': 'Main stop',
  'food': 'Food break',
  'quiet': 'Quiet moment',
  'wildcard': 'Wildcard',
  'utility': 'Practical',
};

/// "Your Mangaluru, today" — HIVE's living plan. Everything on a card is
/// backed by data the server sent, and the card says plainly what it does
/// not know (typical hours, unconfirmed access, unknown crowd).
class TodayScreen extends StatefulWidget {
  final AuthController auth;
  const TodayScreen({super.key, required this.auth});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  final _api = HiveApiClient();
  final _text = TextEditingController();
  HivePlan? _plan;
  bool _loading = true;
  String? _error;
  String? _mode; // surprise | slow | less_touristy
  int? _minutes;
  final Set<String> _gone = {};

  @override
  void initState() {
    super.initState();
    _run();
  }

  @override
  void dispose() {
    _api.close();
    _text.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (GZConsent.location) {
        try {
          await GZLocation.ensure().timeout(const Duration(seconds: 8));
        } on Object {/* city centre fallback */}
      }
      final plan = await _api.plan(
        widget.auth.accessToken!,
        text: _text.text.trim(),
        lat: GZConsent.location ? GZLocation.lat : null,
        lng: GZConsent.location ? GZLocation.lng : null,
        mode: _mode,
        minutes: _minutes,
      );
      if (!mounted) return;
      setState(() {
        _plan = plan;
        _gone.clear();
        _loading = false;
      });
    } on GZApiException catch (e) {
      if (mounted) setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _send(HiveCard c, String kind, {String? reason, String? done}) async {
    try {
      final stored = await _api.feedback(widget.auth.accessToken!, c.placeId, kind, reason: reason);
      if (!mounted) return;
      if (stored) {
        _toast(done ?? 'Noted.');
      } else {
        _toast('Memory is off, so this was not saved. Turn it on in Privacy if you want suggestions to learn from it.');
      }
    } on GZApiException catch (e) {
      if (mounted) _toast(e.message);
    }
  }

  Future<void> _notForMe(HiveCard c) async {
    final reasons = const [
      ('not_interested', 'Not my kind of place', Icons.thumb_down_alt_outlined),
      ('seen_it', 'I\'ve already been', Icons.check_circle_outline),
      ('closed', 'It was closed', Icons.lock_clock_outlined),
      ('too_far', 'Too far', Icons.directions_walk_outlined),
      ('no_time', 'No time right now', Icons.hourglass_empty),
    ];
    final picked = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 4),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text('Why skip ${c.name}?', style: Theme.of(ctx).textTheme.titleMedium),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text('Only "not my kind of place" changes what I learn about you.', style: Theme.of(ctx).textTheme.bodySmall),
            ),
          ),
          for (final r in reasons)
            ListTile(leading: Icon(r.$3), title: Text(r.$2), onTap: () => Navigator.pop(ctx, r.$1)),
        ]),
      ),
    );
    if (picked == null) return;
    setState(() => _gone.add(c.placeId));
    await _send(c, 'dismissed', reason: picked, done: 'Got it. I won\'t show this again.');
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final cards = (_plan?.cards ?? const <HiveCard>[]).where((c) => !_gone.contains(c.placeId)).toList();
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        title: const Text('Your Mangaluru, today'),
        actions: [
          IconButton(
            tooltip: 'What HIVE remembers',
            icon: const Icon(Icons.psychology_alt_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MemoryScreen(auth: widget.auth))),
          ),
          const GZHomeAction(),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _run,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 48),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const _DayDial(),
                  const SizedBox(height: 14),
                  _AskBox(
                    controller: _text,
                    onSubmit: _run,
                    mode: _mode,
                    minutes: _minutes,
                    onMode: (m) {
                      setState(() => _mode = _mode == m ? null : m);
                      _run();
                    },
                    onMinutes: (m) {
                      setState(() => _minutes = _minutes == m ? null : m);
                      _run();
                    },
                  ),
                  if (!GZConsent.personalization || !GZConsent.location) ...[
                    const SizedBox(height: 12),
                    _ConsentNudge(
                      location: GZConsent.location,
                      memory: GZConsent.personalization,
                      onOpen: () async {
                        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PrivacyScreen(auth: widget.auth)));
                        if (mounted) {
                          setState(() {});
                          _run();
                        }
                      },
                    ),
                  ],
                  const SizedBox(height: 14),
                  if (_plan != null && _plan!.understood.isNotEmpty)
                    Wrap(spacing: 6, runSpacing: 6, children: [
                      Text('I understood:', style: text.labelMedium?.copyWith(color: ink.muted)),
                      for (final u in _plan!.understood) GZTag(u),
                    ]),
                  const SizedBox(height: 10),
                  if (_loading)
                    const Padding(padding: EdgeInsets.symmetric(vertical: 60), child: Center(child: CircularProgressIndicator()))
                  else if (_error != null)
                    _Notice(icon: Icons.cloud_off_outlined, text: _error!, action: 'Try again', onAction: _run)
                  else ...[
                    if (_plan?.message != null) _Notice(icon: Icons.info_outline, text: _plan!.message!),
                    if (_plan != null && !_plan!.located)
                      const _Notice(icon: Icons.near_me_disabled_outlined, text: 'Showing places around central Mangaluru. Turn location on in Privacy to see what is near you.'),
                    for (var i = 0; i < cards.length; i++)
                      GZReveal(
                        delay: Duration(milliseconds: 60 * i),
                        child: _StopCard(
                          card: cards[i],
                          index: i + 1,
                          last: i == cards.length - 1,
                          onGo: () {
                            GZMaps.directions(context, cards[i].lat, cards[i].lng, name: cards[i].name);
                            _send(cards[i], 'navigated');
                          },
                          onSave: () => _send(cards[i], 'saved', done: 'Saved to what you like.'),
                          onVisited: () {
                            setState(() => _gone.add(cards[i].placeId));
                            _send(cards[i], 'visited', done: 'Marked as visited.');
                          },
                          onSkip: () => _notForMe(cards[i]),
                          onOpened: () => _send(cards[i], 'opened'),
                        ),
                      ),
                    if (_plan != null && _plan!.note.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 14),
                        child: Text(_plan!.note, style: text.bodySmall?.copyWith(color: ink.muted)),
                      ),
                  ],
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A half-circle "day arc": the sun sits where the day is right now.
class _DayDial extends StatelessWidget {
  const _DayDial();

  String _greet(int h) {
    if (h < 5) return 'Late night in Mangaluru';
    if (h < 11) return 'Morning in Mangaluru';
    if (h < 15) return 'Midday in Mangaluru';
    if (h < 18) return 'Afternoon in Mangaluru';
    if (h < 21) return 'Evening in Mangaluru';
    return 'Night in Mangaluru';
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final now = DateTime.now();
    final frac = ((now.hour + now.minute / 60) - 5) / 15; // 5am..8pm
    return GZFrameCard(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
      radius: 24,
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(_greet(now.hour), style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text('A plan that fits the hour, the weather and you. Tell it what you feel like.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: ink.muted)),
          ]),
        ),
        const SizedBox(width: 12),
        SizedBox(
          width: 110,
          height: 62,
          child: CustomPaint(painter: _ArcPainter(frac.clamp(0.0, 1.0).toDouble(), ink.accent, ink.hairline)),
        ),
      ]),
    );
  }
}

class _ArcPainter extends CustomPainter {
  final double frac;
  final Color accent;
  final Color line;
  _ArcPainter(this.frac, this.accent, this.line);

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height - 4);
    final r = size.width / 2 - 6;
    final rect = Rect.fromCircle(center: c, radius: r);
    canvas.drawArc(rect, math.pi, math.pi, false, Paint()..style = PaintingStyle.stroke..strokeWidth = 2..color = line);
    canvas.drawArc(rect, math.pi, math.pi * frac, false, Paint()..style = PaintingStyle.stroke..strokeWidth = 3..strokeCap = StrokeCap.round..color = accent);
    final a = math.pi + math.pi * frac;
    final sun = Offset(c.dx + r * math.cos(a), c.dy + r * math.sin(a));
    canvas.drawCircle(sun, 7, Paint()..color = accent);
    canvas.drawCircle(sun, 11, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.5..color = accent.withOpacity(0.4));
    canvas.drawLine(Offset(c.dx - r - 4, c.dy), Offset(c.dx + r + 4, c.dy), Paint()..strokeWidth = 1.5..color = line);
  }

  @override
  bool shouldRepaint(covariant _ArcPainter old) => old.frac != frac || old.accent != accent;
}

class _AskBox extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSubmit;
  final String? mode;
  final int? minutes;
  final ValueChanged<String> onMode;
  final ValueChanged<int> onMinutes;
  const _AskBox({required this.controller, required this.onSubmit, required this.mode, required this.minutes, required this.onMode, required this.onMinutes});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      TextField(
        controller: controller,
        textInputAction: TextInputAction.search,
        onSubmitted: (_) => onSubmit(),
        maxLength: 200,
        decoration: InputDecoration(
          counterText: '',
          hintText: 'e.g. 2 hours, with kids, vegetarian, away from crowds',
          prefixIcon: const Icon(Icons.auto_awesome_outlined),
          suffixIcon: IconButton(tooltip: 'Plan', icon: const Icon(Icons.arrow_forward_rounded), onPressed: onSubmit),
        ),
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final m in const [
          ('surprise', 'Surprise me', Icons.casino_outlined),
          ('slow', 'Slow down', Icons.spa_outlined),
          ('less_touristy', 'Less touristy', Icons.alt_route_outlined),
        ])
          FilterChip(
            avatar: Icon(m.$3, size: 16),
            label: Text(m.$2),
            selected: mode == m.$1,
            onSelected: (_) => onMode(m.$1),
          ),
      ]),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final m in const [(30, '30 min'), (60, '1 hour'), (120, '2 hours'), (240, 'Half day')])
          ChoiceChip(label: Text(m.$2), selected: minutes == m.$1, onSelected: (_) => onMinutes(m.$1)),
      ]),
    ]);
  }
}

class _ConsentNudge extends StatelessWidget {
  final bool location;
  final bool memory;
  final VoidCallback onOpen;
  const _ConsentNudge({required this.location, required this.memory, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final parts = [if (!location) 'location', if (!memory) 'memory'];
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onOpen,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: ink.paperAlt.withOpacity(0.45), borderRadius: BorderRadius.circular(14), border: Border.all(color: ink.hairline)),
        child: Row(children: [
          Icon(Icons.shield_outlined, color: ink.accent),
          const SizedBox(width: 10),
          Expanded(
            child: Text('${parts.join(' and ')} ${parts.length > 1 ? 'are' : 'is'} off. Turn on only what you want. You stay in control.',
                style: Theme.of(context).textTheme.bodySmall),
          ),
          const Icon(Icons.chevron_right),
        ]),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  final IconData icon;
  final String text;
  final String? action;
  final VoidCallback? onAction;
  const _Notice({required this.icon, required this.text, this.action, this.onAction});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GZFrameCard(
        padding: const EdgeInsets.all(14),
        radius: 14,
        shadowOffset: 0,
        child: Row(children: [
          Icon(icon, color: ink.accent),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
          if (action != null) TextButton(onPressed: onAction, child: Text(action!)),
        ]),
      ),
    );
  }
}

class _StopCard extends StatefulWidget {
  final HiveCard card;
  final int index;
  final bool last;
  final VoidCallback onGo, onSave, onVisited, onSkip, onOpened;
  const _StopCard({
    required this.card,
    required this.index,
    required this.last,
    required this.onGo,
    required this.onSave,
    required this.onVisited,
    required this.onSkip,
    required this.onOpened,
  });

  @override
  State<_StopCard> createState() => _StopCardState();
}

class _StopCardState extends State<_StopCard> {
  bool _open = false;

  Color _stateColor(HiveCard c, GZInk ink) {
    if (c.openState == 'open' && c.openSource == 'listed') return const Color(0xFF2E7D4F);
    if (c.openState == 'open') return ink.accent;
    return ink.muted;
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.card;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(
          width: 40,
          child: Column(children: [
            CircleAvatar(
              radius: 15,
              backgroundColor: ink.accent,
              child: Text('${widget.index}', style: TextStyle(color: ink.dark ? const Color(0xFF240002) : Colors.white, fontWeight: FontWeight.w800)),
            ),
            if (!widget.last) Expanded(child: Container(width: 2, margin: const EdgeInsets.symmetric(vertical: 4), color: ink.hairline)),
          ]),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: GZFrameCard(
              radius: 20,
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: 6, runSpacing: 6, children: [
                  GZTag(_roleNames[c.role] ?? c.role, filled: true),
                  if (c.hiddenGem) const GZTag('Local pick', icon: Icons.star_outline),
                ]),
                const SizedBox(height: 8),
                Text(c.name, style: text.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(
                  '${c.category.replaceAll('_', ' ')} · ${c.distanceKm.toStringAsFixed(1)} km · ~${c.travelMin} min',
                  style: text.bodySmall?.copyWith(color: ink.muted),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Icon(c.openSource == 'listed' ? Icons.verified_outlined : Icons.schedule, size: 16, color: _stateColor(c, ink)),
                  const SizedBox(width: 6),
                  Expanded(child: Text(c.openLabel, style: text.bodySmall?.copyWith(color: _stateColor(c, ink), fontWeight: FontWeight.w700))),
                ]),
                if (c.experiences.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final e in c.experiences.where((e) => e.strength >= 0.5).take(3)) GZTag(_expNames[e.key] ?? e.key),
                  ]),
                ],
                const SizedBox(height: 6),
                InkWell(
                  onTap: () {
                    setState(() => _open = !_open);
                    if (_open) widget.onOpened();
                  },
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(children: [
                      Icon(_open ? Icons.expand_less : Icons.expand_more, size: 20, color: ink.accent),
                      const SizedBox(width: 4),
                      Text('Why this, why now?', style: text.labelLarge?.copyWith(color: ink.accent, fontWeight: FontWeight.w800)),
                    ]),
                  ),
                ),
                AnimatedCrossFade(
                  duration: const Duration(milliseconds: 200),
                  crossFadeState: _open ? CrossFadeState.showSecond : CrossFadeState.showFirst,
                  firstChild: const SizedBox(width: double.infinity),
                  secondChild: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    for (final w in c.why) _Line(Icons.check_circle_outline, w),
                    if (c.lessTouristyEvidence != null) _Line(Icons.alt_route_outlined, c.lessTouristyEvidence!),
                    for (final w in c.caveats) _Line(Icons.info_outline, w, muted: true),
                    const SizedBox(height: 6),
                    Text(
                      'Evidence: ${c.confidence} confidence · ${c.verificationNote}${c.sources.isEmpty ? '' : ' (${c.sources.join(', ')})'}',
                      style: text.bodySmall?.copyWith(color: ink.muted, fontSize: 11.5),
                    ),
                  ]),
                ),
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  FilledButton.icon(onPressed: widget.onGo, icon: const Icon(Icons.near_me, size: 16), label: const Text('Take me there')),
                  OutlinedButton.icon(onPressed: widget.onSave, icon: const Icon(Icons.favorite_border, size: 16), label: const Text('Like')),
                  OutlinedButton.icon(onPressed: widget.onVisited, icon: const Icon(Icons.check, size: 16), label: const Text('Been here')),
                  TextButton(onPressed: widget.onSkip, child: const Text('Not for me')),
                ]),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

class _Line extends StatelessWidget {
  final IconData icon;
  final String text;
  final bool muted;
  const _Line(this.icon, this.text, {this.muted = false});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 15, color: muted ? ink.muted : ink.accent),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: muted ? ink.muted : null, height: 1.35))),
      ]),
    );
  }
}
