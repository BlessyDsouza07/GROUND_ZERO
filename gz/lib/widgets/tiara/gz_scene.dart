import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../design/gz_colors.dart';

/// The layered, drifting coastal illustration that plays the role of
/// Tiara's UFO / planets / clouds hero art: a retro striped sun, chunky
/// clouds drifting across, a Mangaluru lighthouse with a sweeping beam,
/// dhow boats, palms, birds and three rolling wave layers.
///
/// Everything is drawn in code (no image files), so it is crisp at any
/// size and re-colours itself for light ("sea by day") and dark ("dusk").
class GZScenePainter extends CustomPainter {
  /// Looping animation value 0..1 (seamless: every motion uses whole
  /// multiples of 2π or wraps around).
  final double t;

  /// Scroll progress 0..1 — layers shift at different speeds (parallax).
  final double parallax;
  final bool dark;

  GZScenePainter({required this.t, required this.parallax, required this.dark});

  static const _tau = math.pi * 2;

  // ---- palette (only the user's two palettes + tints) -----------------
  Color get _skyTop => dark ? GZDarkColors.deepBurgundy : GZLightColors.cerulean;
  Color get _skyMid => dark ? GZDarkColors.deepCrimson : GZLightColors.teal;
  Color get _skyLow => dark ? GZDarkColors.rust : GZLightColors.seafoam;
  Color get _skyHorizon => dark ? GZDarkColors.burntOrange : GZLightColors.warmIvory;
  Color get _sun => dark ? GZDarkColors.goldenAmber : const Color(0xFFF7F3EA);
  Color get _sunRing => dark ? GZDarkColors.goldenAmber : GZLightColors.warmIvory;
  Color get _cloud => dark ? const Color(0xFFFBE9C6) : const Color(0xFFF7F3EA);
  Color get _cloudShade => dark ? GZDarkColors.burntOrange : GZLightColors.seafoam;
  Color get _ridge => dark ? GZDarkColors.deepCrimson : GZLightColors.teal;
  Color get _sea1 => dark ? GZDarkColors.rust : GZLightColors.teal;
  Color get _sea2 => dark ? GZDarkColors.deepCrimson : GZLightColors.cerulean;
  Color get _sea3 => dark ? GZDarkColors.deepBurgundy : GZLightColors.deepOcean;
  Color get _foam => dark ? GZDarkColors.goldenAmber : const Color(0xFFF7F3EA);
  Color get _ink => dark ? GZDarkColors.deepBurgundy : const Color(0xFF00394F);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    if (w <= 0 || h <= 0) return;
    final horizon = h * 0.64;
    final p = parallax.clamp(0.0, 1.0).toDouble();

    // Sky
    final skyPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [_skyTop, _skyMid, _skyLow, _skyHorizon],
        stops: const [0.0, 0.38, 0.72, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, w, horizon + 2));
    canvas.drawRect(Rect.fromLTWH(0, 0, w, horizon + 2), skyPaint);

    if (dark) _stars(canvas, w, horizon);

    _sunDisc(canvas, w, h, horizon, p);

    // Far clouds (slow) then ridge, near clouds (faster)
    _cloudLayer(canvas, w, h, y: h * 0.22, scale: 0.8, speed: 1, seed: 1, p: p, par: 18, alpha: 0.75);
    _ridgeLine(canvas, w, horizon, p);
    _cloudLayer(canvas, w, h, y: h * 0.40, scale: 1.1, speed: 2, seed: 2, p: p, par: 34, alpha: 0.95);
    _birds(canvas, w, h);

    // Sea base
    final seaRect = Rect.fromLTWH(0, horizon, w, h - horizon);
    canvas.drawRect(
      seaRect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [_sea1, _sea2],
        ).createShader(seaRect),
    );
    _sunGlints(canvas, w, h, horizon);

    _lighthouse(canvas, w, h, horizon);
    _boats(canvas, w, h, horizon);

    // Waves, back to front
    _wave(canvas, w, h, base: horizon + (h - horizon) * 0.20, amp: 7, k: 2, phase: t * _tau, color: _sea2.withOpacity(0.92), foam: false);
    _wave(canvas, w, h, base: horizon + (h - horizon) * 0.46, amp: 10, k: 3, phase: -t * _tau * 2 + 1.2, color: _sea3.withOpacity(0.95), foam: true);
    _palms(canvas, w, h);
    _wave(canvas, w, h, base: horizon + (h - horizon) * 0.76, amp: 13, k: 2, phase: t * _tau * 3 + 2.4, color: _ink.withOpacity(dark ? 0.98 : 0.9), foam: true);
  }

  // ---------------------------------------------------------------------
  void _stars(Canvas canvas, double w, double horizon) {
    final rnd = math.Random(7);
    final paint = Paint()..color = const Color(0xFFFBE9C6);
    for (var i = 0; i < 70; i++) {
      final x = rnd.nextDouble() * w;
      final y = rnd.nextDouble() * horizon * 0.62;
      final tw = 0.5 + 0.5 * math.sin(t * _tau * 2 + i);
      paint.color = const Color(0xFFFBE9C6).withOpacity(0.25 + 0.6 * tw * (1 - y / horizon));
      canvas.drawCircle(Offset(x, y), rnd.nextDouble() * 1.4 + 0.4, paint);
    }
  }

  void _sunDisc(Canvas canvas, double w, double h, double horizon, double p) {
    final r = math.min(w * 0.22, h * 0.20).clamp(40.0, 220.0).toDouble();
    final c = Offset(w * 0.70, horizon - r * 0.55 - p * 26);

    // concentric retro rings (slowly pulsing)
    for (var i = 1; i <= 4; i++) {
      final pulse = 0.5 + 0.5 * math.sin(t * _tau - i * 0.7);
      canvas.drawCircle(
        c,
        r + i * r * 0.20,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6
          ..color = _sunRing.withOpacity((0.34 - i * 0.06) * (0.6 + 0.4 * pulse)),
      );
    }
    // glow
    canvas.drawCircle(
      c,
      r * 1.5,
      Paint()
        ..shader = RadialGradient(colors: [_sun.withOpacity(dark ? 0.35 : 0.30), _sun.withOpacity(0)])
            .createShader(Rect.fromCircle(center: c, radius: r * 1.5)),
    );
    // disc with retro horizontal cut-outs on its lower half
    final bounds = Rect.fromCircle(center: c, radius: r + 2);
    canvas.saveLayer(bounds, Paint());
    canvas.drawCircle(c, r, Paint()..color = _sun);
    final cut = Paint()..blendMode = BlendMode.clear;
    for (var i = 0; i < 5; i++) {
      final y = c.dy + r * (0.12 + i * 0.17);
      canvas.drawRect(Rect.fromLTWH(c.dx - r, y, r * 2, 1.2 + i * 1.7), cut);
    }
    canvas.restore();
  }

  void _cloudLayer(Canvas canvas, double w, double h,
      {required double y, required double scale, required int speed, required int seed, required double p, required double par, required double alpha}) {
    final rnd = math.Random(seed * 31);
    const count = 4;
    final span = w + 360 * scale;
    for (var i = 0; i < count; i++) {
      final baseX = (i / count) * span + rnd.nextDouble() * 80;
      final x = ((baseX + t * speed * span) % span) - 180 * scale;
      final cy = y + (rnd.nextDouble() - 0.5) * h * 0.10 - p * par;
      _cloud1(canvas, Offset(x, cy), scale * (0.8 + rnd.nextDouble() * 0.5), alpha);
    }
  }

  void _cloud1(Canvas canvas, Offset o, double s, double alpha) {
    final body = Paint()..color = _cloud.withOpacity(alpha);
    final shade = Paint()..color = _cloudShade.withOpacity(alpha * 0.55);
    final path = Path()
      ..addOval(Rect.fromCenter(center: o + Offset(-34 * s, 4 * s), width: 62 * s, height: 44 * s))
      ..addOval(Rect.fromCenter(center: o + Offset(0, -10 * s), width: 84 * s, height: 66 * s))
      ..addOval(Rect.fromCenter(center: o + Offset(40 * s, 2 * s), width: 70 * s, height: 50 * s))
      ..addRRect(RRect.fromRectAndRadius(
        Rect.fromCenter(center: o + Offset(2 * s, 14 * s), width: 140 * s, height: 28 * s),
        Radius.circular(14 * s),
      ));
    canvas.drawPath(path.shift(Offset(0, 5 * s)), shade);
    canvas.drawPath(path, body);
  }

  void _ridgeLine(Canvas canvas, double w, double horizon, double p) {
    // Distant Western Ghats ridge
    final path = Path()..moveTo(0, horizon);
    const steps = 48;
    for (var i = 0; i <= steps; i++) {
      final x = w * i / steps;
      final n = math.sin(i * 0.55) * 0.5 + math.sin(i * 1.3 + 1) * 0.3 + math.sin(i * 0.19) * 0.6;
      path.lineTo(x, horizon - 18 - (n + 1) * 14 - p * 6);
    }
    path
      ..lineTo(w, horizon)
      ..close();
    canvas.drawPath(path, Paint()..color = _ridge.withOpacity(dark ? 0.75 : 0.55));
  }

  void _birds(Canvas canvas, double w, double h) {
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..color = _ink.withOpacity(0.8);
    for (var i = 0; i < 4; i++) {
      final x = ((t * 1.0 + i * 0.09) % 1.0) * (w + 80) - 40;
      final y = h * (0.30 + 0.035 * i) + math.sin(t * _tau * 2 + i) * 6;
      final flap = math.sin(t * _tau * 40 + i * 2) * 3;
      final path = Path()
        ..moveTo(x - 9, y - 3 - flap)
        ..quadraticBezierTo(x - 4, y - 7 + flap, x, y)
        ..quadraticBezierTo(x + 4, y - 7 + flap, x + 9, y - 3 - flap);
      canvas.drawPath(path, paint);
    }
  }

  void _sunGlints(Canvas canvas, double w, double h, double horizon) {
    final cx = w * 0.70;
    final paint = Paint()..strokeCap = StrokeCap.round;
    for (var i = 0; i < 9; i++) {
      final y = horizon + 8 + i * (h - horizon) * 0.055;
      final len = (26 + i * 10) * (0.7 + 0.3 * math.sin(t * _tau * 2 + i));
      paint
        ..strokeWidth = 2.2
        ..color = _sun.withOpacity(0.55 - i * 0.045);
      canvas.drawLine(Offset(cx - len, y), Offset(cx + len, y), paint);
    }
  }

  void _lighthouse(Canvas canvas, double w, double h, double horizon) {
    final base = Offset(w * 0.16, horizon + (h - horizon) * 0.10);
    final s = (h / 640).clamp(0.6, 1.5).toDouble();
    final towerH = 150 * s;
    final bw = 34 * s;
    final tw = 20 * s;
    final top = base.dy - towerH;

    // rock
    canvas.drawPath(
      Path()
        ..moveTo(base.dx - 54 * s, base.dy + 8 * s)
        ..quadraticBezierTo(base.dx - 30 * s, base.dy - 16 * s, base.dx - 8 * s, base.dy - 12 * s)
        ..quadraticBezierTo(base.dx + 22 * s, base.dy - 20 * s, base.dx + 58 * s, base.dy + 8 * s)
        ..close(),
      Paint()..color = _ink,
    );
    // tower
    final tower = Path()
      ..moveTo(base.dx - bw / 2, base.dy - 8 * s)
      ..lineTo(base.dx - tw / 2, top)
      ..lineTo(base.dx + tw / 2, top)
      ..lineTo(base.dx + bw / 2, base.dy - 8 * s)
      ..close();
    canvas.drawPath(tower, Paint()..color = dark ? GZDarkColors.cream : const Color(0xFFF7F3EA));
    // stripes
    canvas.save();
    canvas.clipPath(tower);
    final stripe = Paint()..color = dark ? GZDarkColors.rust : GZLightColors.deepOcean;
    for (var i = 0; i < 3; i++) {
      final y = top + towerH * (0.16 + i * 0.30);
      canvas.drawRect(Rect.fromLTWH(base.dx - bw, y, bw * 2, towerH * 0.13), stripe);
    }
    canvas.restore();
    // gallery + lantern
    canvas.drawRect(Rect.fromCenter(center: Offset(base.dx, top - 2 * s), width: tw + 14 * s, height: 5 * s), Paint()..color = _ink);
    final lantern = Rect.fromCenter(center: Offset(base.dx, top - 14 * s), width: tw * 0.7, height: 18 * s);
    canvas.drawRect(lantern, Paint()..color = _sun);
    canvas.drawPath(
      Path()
        ..moveTo(base.dx - tw * 0.55, top - 23 * s)
        ..lineTo(base.dx, top - 36 * s)
        ..lineTo(base.dx + tw * 0.55, top - 23 * s)
        ..close(),
      Paint()..color = _ink,
    );
    // sweeping beam: width oscillates like the lamp rotating
    final sweep = math.cos(t * _tau * 2);
    final beamLen = w * 0.55;
    final beamH = 70 * s * (0.25 + 0.75 * sweep.abs());
    final dir = sweep >= 0 ? 1.0 : -1.0;
    final origin = Offset(base.dx, top - 14 * s);
    final beam = Path()
      ..moveTo(origin.dx, origin.dy)
      ..lineTo(origin.dx + dir * beamLen, origin.dy - beamH)
      ..lineTo(origin.dx + dir * beamLen, origin.dy + beamH)
      ..close();
    canvas.drawPath(
      beam,
      Paint()
        ..shader = LinearGradient(
          begin: dir > 0 ? Alignment.centerLeft : Alignment.centerRight,
          end: dir > 0 ? Alignment.centerRight : Alignment.centerLeft,
          colors: [_sun.withOpacity(dark ? 0.55 : 0.35), _sun.withOpacity(0)],
        ).createShader(Rect.fromLTWH(math.min(origin.dx, origin.dx + dir * beamLen), origin.dy - beamH, beamLen, beamH * 2)),
    );
  }

  void _boats(Canvas canvas, double w, double h, double horizon) {
    void dhow(double x, double y, double s, double bob) {
      canvas.save();
      canvas.translate(x, y + bob);
      canvas.rotate(math.sin(t * _tau * 2 + x) * 0.03);
      // hull
      canvas.drawPath(
        Path()
          ..moveTo(-26 * s, 0)
          ..lineTo(26 * s, 0)
          ..lineTo(18 * s, 9 * s)
          ..lineTo(-18 * s, 9 * s)
          ..close(),
        Paint()..color = _ink,
      );
      // sail
      canvas.drawPath(
        Path()
          ..moveTo(0, -4 * s)
          ..lineTo(0, -44 * s)
          ..lineTo(28 * s, -6 * s)
          ..close(),
        Paint()..color = dark ? GZDarkColors.goldenAmber : const Color(0xFFF7F3EA),
      );
      canvas.drawLine(Offset(0, 0), Offset(0, -46 * s), Paint()..color = _ink..strokeWidth = 2 * s);
      canvas.restore();
    }

    final s = (h / 640).clamp(0.6, 1.4).toDouble();
    final span = w + 120;
    final x1 = ((0.15 + t * 1) % 1.0) * span - 60;
    dhow(x1, horizon + (h - horizon) * 0.17, s * 0.8, math.sin(t * _tau * 3) * 2);
    final x2 = ((0.62 + t * 1) % 1.0) * span - 60;
    dhow(x2, horizon + (h - horizon) * 0.30, s * 1.1, math.sin(t * _tau * 3 + 2) * 2.5);
  }

  void _palms(Canvas canvas, double w, double h) {
    void palm(double x, double groundY, double hgt, double lean) {
      final trunk = Path()
        ..moveTo(x, groundY)
        ..quadraticBezierTo(x + lean * 0.5, groundY - hgt * 0.5, x + lean, groundY - hgt)
        ..lineTo(x + lean + 5, groundY - hgt)
        ..quadraticBezierTo(x + lean * 0.5 + 8, groundY - hgt * 0.5, x + 9, groundY)
        ..close();
      canvas.drawPath(trunk, Paint()..color = _ink);
      final c = Offset(x + lean + 2, groundY - hgt);
      final sway = math.sin(t * _tau * 2 + x) * 0.07;
      for (var i = 0; i < 7; i++) {
        final a = -math.pi * 0.95 + i * (math.pi * 0.95 / 3.0) * 0.5 + sway;
        final len = hgt * 0.5;
        final end = c + Offset(math.cos(a) * len, math.sin(a) * len * 0.55 + len * 0.35);
        final mid = c + Offset(math.cos(a) * len * 0.5, math.sin(a) * len * 0.5 - len * 0.18);
        final frond = Path()
          ..moveTo(c.dx, c.dy)
          ..quadraticBezierTo(mid.dx, mid.dy - 6, end.dx, end.dy)
          ..quadraticBezierTo(mid.dx, mid.dy + 8, c.dx, c.dy);
        canvas.drawPath(frond, Paint()..color = _ink);
      }
    }

    final s = (h / 640).clamp(0.7, 1.4).toDouble();
    palm(w * 0.93, h * 0.92, 210 * s, -26 * s);
    palm(w * 0.985, h * 0.94, 150 * s, -16 * s);
    palm(w * 0.03, h * 0.95, 130 * s, 18 * s);
  }

  void _wave(Canvas canvas, double w, double h,
      {required double base, required double amp, required int k, required double phase, required Color color, required bool foam}) {
    final path = Path()..moveTo(0, h);
    final top = <Offset>[];
    const steps = 64;
    for (var i = 0; i <= steps; i++) {
      final x = w * i / steps;
      final y = base + math.sin(x / w * _tau * k + phase) * amp + math.sin(x / w * _tau * (k + 2) - phase * 1.3) * amp * 0.35;
      top.add(Offset(x, y));
      path.lineTo(x, y);
    }
    path
      ..lineTo(w, h)
      ..close();
    canvas.drawPath(path, Paint()..color = color);
    if (foam) {
      final line = Path()..moveTo(top.first.dx, top.first.dy);
      for (final o in top.skip(1)) {
        line.lineTo(o.dx, o.dy);
      }
      canvas.drawPath(
        line,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.4
          ..strokeJoin = StrokeJoin.round
          ..color = _foam.withOpacity(dark ? 0.7 : 0.8),
      );
    }
  }

  @override
  bool shouldRepaint(covariant GZScenePainter old) => old.t != t || old.parallax != parallax || old.dark != dark;
}

/// Animated, parallax-aware scene with [child] laid on top. Fill any box;
/// the art scales to it.
class GZScene extends StatefulWidget {
  final Widget? child;
  final ScrollController? scroll;
  final Duration loop;

  const GZScene({super.key, this.child, this.scroll, this.loop = const Duration(seconds: 60)});

  @override
  State<GZScene> createState() => _GZSceneState();
}

class _GZSceneState extends State<GZScene> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: widget.loop)..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  double _parallax(double height) {
    final s = widget.scroll;
    if (s == null || !s.hasClients || height <= 0) return 0;
    return (s.offset / height).clamp(0.0, 1.0).toDouble();
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return LayoutBuilder(builder: (context, box) {
      final listenable = widget.scroll == null ? _c : Listenable.merge([_c, widget.scroll!]);
      return Stack(
        fit: StackFit.expand,
        children: [
          RepaintBoundary(
            child: AnimatedBuilder(
              animation: listenable,
              builder: (context, _) => CustomPaint(
                painter: GZScenePainter(t: _c.value, parallax: _parallax(box.maxHeight), dark: dark),
                size: Size.infinite,
              ),
            ),
          ),
          if (widget.child != null) widget.child!,
        ],
      );
    });
  }
}

/// Small painted "photo" for place tiles (Tiara's gallery / category tiles).
enum GZPlaceArt { beach, temple, heritage, fort, nature }

class GZPlaceArtPainter extends CustomPainter {
  final GZPlaceArt kind;
  final bool dark;
  const GZPlaceArtPainter({required this.kind, required this.dark});

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    if (w <= 0 || h <= 0) return;
    final top = dark ? GZDarkColors.deepCrimson : GZLightColors.cerulean;
    final bottom = dark ? GZDarkColors.burntOrange : GZLightColors.warmIvory;
    final sun = dark ? GZDarkColors.goldenAmber : const Color(0xFFF7F3EA);
    final land = dark ? GZDarkColors.deepBurgundy : GZLightColors.deepOcean;
    final land2 = dark ? GZDarkColors.rust : GZLightColors.teal;
    final r = Rect.fromLTWH(0, 0, w, h);
    canvas.drawRect(
      r,
      Paint()..shader = LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [top, bottom]).createShader(r),
    );
    canvas.drawCircle(Offset(w * 0.74, h * 0.34), h * 0.15, Paint()..color = sun);
    final ground = h * 0.74;
    final p1 = Paint()..color = land2;
    final p2 = Paint()..color = land;

    switch (kind) {
      case GZPlaceArt.beach:
        for (var i = 0; i < 3; i++) {
          final y = h * (0.62 + i * 0.1);
          final path = Path()..moveTo(0, h);
          for (var x = 0.0; x <= w; x += 6) {
            path.lineTo(x, y + math.sin(x / w * math.pi * 4 + i) * 4);
          }
          path
            ..lineTo(w, h)
            ..close();
          canvas.drawPath(path, Paint()..color = i == 2 ? land : (i == 1 ? land2 : land2.withOpacity(0.7)));
        }
        canvas.drawPath(
          Path()
            ..moveTo(w * 0.12, h)
            ..quadraticBezierTo(w * 0.16, h * 0.62, w * 0.24, h * 0.5)
            ..lineTo(w * 0.255, h * 0.5)
            ..quadraticBezierTo(w * 0.19, h * 0.64, w * 0.16, h)
            ..close(),
          p2,
        );
        break;
      case GZPlaceArt.temple:
        canvas.drawRect(Rect.fromLTWH(0, ground, w, h - ground), p2);
        final cx = w * 0.42;
        var y = ground;
        var half = w * 0.2;
        for (var i = 0; i < 5; i++) {
          final ph = h * 0.075;
          canvas.drawRect(Rect.fromLTWH(cx - half, y - ph, half * 2, ph), i.isEven ? p2 : p1);
          y -= ph;
          half *= 0.8;
        }
        canvas.drawPath(
          Path()
            ..moveTo(cx - half, y)
            ..lineTo(cx, y - h * 0.09)
            ..lineTo(cx + half, y)
            ..close(),
          p2,
        );
        break;
      case GZPlaceArt.heritage:
        canvas.drawRect(Rect.fromLTWH(0, ground, w, h - ground), p2);
        canvas.drawRect(Rect.fromLTWH(w * 0.28, h * 0.5, w * 0.34, ground - h * 0.5), p1);
        canvas.drawPath(
          Path()
            ..moveTo(w * 0.28, h * 0.5)
            ..lineTo(w * 0.45, h * 0.36)
            ..lineTo(w * 0.62, h * 0.5)
            ..close(),
          p2,
        );
        canvas.drawRect(Rect.fromLTWH(w * 0.435, h * 0.22, w * 0.03, h * 0.14), p2);
        canvas.drawRect(Rect.fromLTWH(w * 0.405, h * 0.255, w * 0.09, h * 0.025), p2);
        canvas.drawRRect(
          RRect.fromRectAndCorners(Rect.fromLTWH(w * 0.4, h * 0.56, w * 0.1, ground - h * 0.56), topLeft: Radius.circular(w * 0.05), topRight: Radius.circular(w * 0.05)),
          Paint()..color = bottom,
        );
        break;
      case GZPlaceArt.fort:
        canvas.drawRect(Rect.fromLTWH(0, ground, w, h - ground), p2);
        final wall = Rect.fromLTWH(w * 0.16, h * 0.5, w * 0.62, ground - h * 0.5);
        canvas.drawRect(wall, p1);
        for (var i = 0; i < 6; i++) {
          canvas.drawRect(Rect.fromLTWH(wall.left + i * wall.width / 6, h * 0.5 - h * 0.05, wall.width / 12, h * 0.05), p1);
        }
        canvas.drawRect(Rect.fromLTWH(w * 0.7, h * 0.36, w * 0.14, ground - h * 0.36), p2);
        break;
      case GZPlaceArt.nature:
        final ridge = Path()
          ..moveTo(0, ground)
          ..lineTo(0, h * 0.55)
          ..quadraticBezierTo(w * 0.25, h * 0.38, w * 0.5, h * 0.58)
          ..quadraticBezierTo(w * 0.75, h * 0.42, w, h * 0.56)
          ..lineTo(w, ground)
          ..close();
        canvas.drawPath(ridge, p1);
        canvas.drawRect(Rect.fromLTWH(0, ground, w, h - ground), p2);
        for (var i = 0; i < 5; i++) {
          final x = w * (0.1 + i * 0.2);
          final th = h * (0.14 + (i % 2) * 0.05);
          canvas.drawPath(
            Path()
              ..moveTo(x - w * 0.05, ground)
              ..lineTo(x, ground - th)
              ..lineTo(x + w * 0.05, ground)
              ..close(),
            p2,
          );
        }
        break;
    }
  }

  @override
  bool shouldRepaint(covariant GZPlaceArtPainter old) => old.kind != kind || old.dark != dark;
}
