import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/tiara/gz_art_data.dart';

/// Shown while the day plan is being built. Instead of a spinner it is a small
/// "arrival" story: five stages along a coast road, each one describing what
/// the planner is really doing, with a short Mangaluru fact underneath.
/// The bar advances on a timer and waits at the last stage until the plan is
/// ready, so it never claims to be finished before it is.
class GZJourneyLoader extends StatefulWidget {
  final String? error;
  final VoidCallback? onRetry;
  const GZJourneyLoader({super.key, this.error, this.onRetry});

  @override
  State<GZJourneyLoader> createState() => _GZJourneyLoaderState();
}

class _GZJourneyLoaderState extends State<GZJourneyLoader> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(seconds: 16))..forward();

  static const _stages = [
    (Icons.flight_land_rounded, 'Landing in Mangaluru', 'Reading your answers.'),
    (Icons.schedule_rounded, 'Checking what is open', 'Hours, closures and today\'s events.'),
    (Icons.explore_rounded, 'Skipping the obvious', 'Looking past what every list repeats.'),
    (Icons.tune_rounded, 'Matching your pace', 'Energy, crowds, budget and food.'),
    (Icons.route_rounded, 'Laying out your day', 'Ordering stops so the walking makes sense.'),
  ];

  static const _facts = [
    'Mangaluru sits where the Netravati and Gurupura rivers meet the Arabian Sea.',
    'Tulu, Konkani, Kannada and Beary are all spoken here, often in the same street.',
    'The red Mangalore tiles seen across the region were first made here in the 1860s.',
    'Neer dosa, kori rotti and ghee roast are all local kitchen classics.',
  ];

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final svg = kGZArtSvgs['coast']![0];
    return Scaffold(
      body: Stack(fit: StackFit.expand, children: [
        // The whole coast scene, undistorted: sky, sun, sea, boat and palms.
        SvgPicture.string(svg, fit: BoxFit.cover, alignment: Alignment.bottomCenter),
        // A soft shade at the top so the card always reads clearly.
        const DecoratedBox(
          decoration: BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.center, colors: [Color(0x66042A3C), Color(0x00042A3C)])),
        ),
        // Slow drifting clouds
        AnimatedBuilder(
          animation: _c,
          builder: (context, _) {
            final w = MediaQuery.of(context).size.width;
            final h = MediaQuery.of(context).size.height;
            Widget cloud(double y, double size, double speed, double phase, double op) {
              final x = ((_c.value * speed + phase) % 1.0) * (w + size * 2) - size;
              return Positioned(left: x, top: h * y, child: Opacity(opacity: op, child: _Cloud(size: size)));
            }
            return Stack(children: [cloud(0.08, 120, 1.6, 0.1, 0.85), cloud(0.2, 80, 2.4, 0.55, 0.7), cloud(0.34, 150, 1.1, 0.8, 0.6)]);
          },
        ),
        SafeArea(
          child: Align(
            alignment: const Alignment(0, -0.35),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: widget.error != null ? _errorCard(context) : AnimatedBuilder(animation: _c, builder: (_, __) => _card(context)),
              ),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _errorCard(BuildContext context) {
    return _panel(Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.error_outline, size: 36, color: Color(0xFFB3261E)),
      const SizedBox(height: 12),
      Text(widget.error!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 16, height: 1.4)),
      const SizedBox(height: 16),
      if (widget.onRetry != null) FilledButton(onPressed: widget.onRetry, child: const Text('Back to my answers')),
    ]));
  }

  Widget _panel(Widget child) => Container(
        padding: const EdgeInsets.all(26),
        decoration: BoxDecoration(color: const Color(0xFFFBF3E2), borderRadius: BorderRadius.circular(28), boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 30, offset: Offset(0, 14))]),
        child: DefaultTextStyle(style: const TextStyle(color: Color(0xFF06384F)), child: child),
      );

  Widget _card(BuildContext context) {
    // Progress eases toward 92% and holds there until the plan arrives.
    final p = (Curves.easeOutCubic.transform(_c.value) * 0.92).clamp(0.0, 0.92);
    final stage = math.min(_stages.length - 1, (p / 0.92 * _stages.length).floor());
    final fact = _facts[(_c.value * 40).floor() ~/ 10 % _facts.length];
    const teal = Color(0xFF006996);
    return _panel(Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('YOUR MANGALURU DAY', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 12, color: teal)),
      const SizedBox(height: 8),
      AnimatedSwitcher(
        duration: const Duration(milliseconds: 350),
        child: Text(_stages[stage].$2, key: ValueKey(stage), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w900, height: 1.1)),
      ),
      const SizedBox(height: 6),
      Text(_stages[stage].$3, style: TextStyle(fontSize: 15, color: const Color(0xFF06384F).withOpacity(0.75))),
      const SizedBox(height: 26),
      LayoutBuilder(builder: (context, box) {
        final w = box.maxWidth;
        return SizedBox(
          height: 56,
          child: Stack(clipBehavior: Clip.none, children: [
            Positioned(left: 0, right: 0, top: 36, child: Container(height: 6, decoration: BoxDecoration(color: const Color(0xFFE0DCD3), borderRadius: BorderRadius.circular(99)))),
            Positioned(left: 0, top: 36, child: Container(height: 6, width: w * p, decoration: BoxDecoration(color: teal, borderRadius: BorderRadius.circular(99)))),
            for (var i = 0; i < _stages.length; i++)
              Positioned(
                left: (w - 22) * (i / (_stages.length - 1)),
                top: 30,
                child: Container(
                  width: 22,
                  height: 18,
                  alignment: Alignment.center,
                  child: Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: i <= stage ? teal : const Color(0xFFE0DCD3), border: Border.all(color: const Color(0xFFFBF3E2), width: 2)),
                  ),
                ),
              ),
            Positioned(
              left: ((w - 34) * p).clamp(0.0, w - 34),
              top: 0,
              child: Transform.translate(
                offset: Offset(0, math.sin(_c.value * 40) * 2),
                child: Container(
                  width: 34,
                  height: 34,
                  decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFFE8833A)),
                  child: Icon(_stages[stage].$1, color: Colors.white, size: 19),
                ),
              ),
            ),
          ]),
        );
      }),
      const SizedBox(height: 18),
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(Icons.lightbulb_outline, size: 18, color: Color(0xFFE8833A)),
        const SizedBox(width: 8),
        Expanded(child: AnimatedSwitcher(duration: const Duration(milliseconds: 400), child: Text(fact, key: ValueKey(fact), style: const TextStyle(fontSize: 13.5, height: 1.4)))),
      ]),
    ]));
  }
}

class _Cloud extends StatelessWidget {
  final double size;
  const _Cloud({required this.size});

  @override
  Widget build(BuildContext context) {
    final c = Colors.white.withOpacity(0.9);
    return SizedBox(
      width: size,
      height: size * 0.45,
      child: Stack(children: [
        Positioned(left: 0, bottom: 0, child: Container(width: size, height: size * 0.22, decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(99)))),
        Positioned(left: size * 0.18, bottom: size * 0.1, child: Container(width: size * 0.38, height: size * 0.38, decoration: BoxDecoration(color: c, shape: BoxShape.circle))),
        Positioned(left: size * 0.45, bottom: size * 0.1, child: Container(width: size * 0.3, height: size * 0.3, decoration: BoxDecoration(color: c, shape: BoxShape.circle))),
      ]),
    );
  }
}
