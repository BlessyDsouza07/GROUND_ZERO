import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../design/gz_ink.dart';

/// Real, computed sunset for Mangaluru (12.87°N, 74.84°E) using the NOAA
/// low-precision solar equations — good to a few minutes, which is all a
/// "golden hour" countdown needs. No network, no API key.
class GZSun {
  const GZSun._();
  static const double lat = 12.87;
  static const double lon = 74.84;
  static const Duration ist = Duration(hours: 5, minutes: 30);

  /// Sunset instant (UTC) for the Mangaluru calendar day containing [instant].
  static DateTime sunsetFor(DateTime instant, {int addDays = 0}) {
    final local = instant.toUtc().add(ist).add(Duration(days: addDays));
    final dayStart = DateTime.utc(local.year, local.month, local.day);
    final n = dayStart.difference(DateTime.utc(local.year, 1, 1)).inDays + 1;
    final g = 2 * math.pi / 365 * (n - 1);
    final eq = 229.18 *
        (0.000075 +
            0.001868 * math.cos(g) -
            0.032077 * math.sin(g) -
            0.014615 * math.cos(2 * g) -
            0.040849 * math.sin(2 * g));
    final decl = 0.006918 -
        0.399912 * math.cos(g) +
        0.070257 * math.sin(g) -
        0.006758 * math.cos(2 * g) +
        0.000907 * math.sin(2 * g) -
        0.002697 * math.cos(3 * g) +
        0.00148 * math.sin(3 * g);
    final latR = lat * math.pi / 180;
    var cosHa = math.cos(90.833 * math.pi / 180) / (math.cos(latR) * math.cos(decl)) - math.tan(latR) * math.tan(decl);
    cosHa = cosHa.clamp(-1.0, 1.0).toDouble();
    final ha = math.acos(cosHa) * 180 / math.pi;
    final minutesUtc = 720 - 4 * (lon - ha) - eq;
    // minutesUtc is measured from 00:00 UTC of the same calendar date.
    return dayStart.add(Duration(seconds: (minutesUtc * 60).round()));
  }

  static String clock(DateTime utc) {
    final l = utc.add(ist);
    final h12 = l.hour % 12 == 0 ? 12 : l.hour % 12;
    final m = l.minute.toString().padLeft(2, '0');
    return '$h12:$m ${l.hour >= 12 ? 'pm' : 'am'}';
  }
}

/// Tiara has a "registration closes in" countdown; GroundZero's is the
/// next golden hour on the Mangaluru coast.
class GZGoldenHourCountdown extends StatefulWidget {
  const GZGoldenHourCountdown({super.key});

  @override
  State<GZGoldenHourCountdown> createState() => _GZGoldenHourCountdownState();
}

class _GZGoldenHourCountdownState extends State<GZGoldenHourCountdown> {
  Timer? _timer;
  DateTime _now = DateTime.now().toUtc();

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _now = DateTime.now().toUtc());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  ({String label, Duration left, DateTime sunset}) _state() {
    var sunset = GZSun.sunsetFor(_now);
    final start = sunset.subtract(const Duration(hours: 1));
    if (_now.isBefore(start)) {
      return (label: 'golden hour starts in', left: start.difference(_now), sunset: sunset);
    }
    if (_now.isBefore(sunset)) {
      return (label: 'golden hour is on · sun sets in', left: sunset.difference(_now), sunset: sunset);
    }
    sunset = GZSun.sunsetFor(_now, addDays: 1);
    return (label: 'next golden hour in', left: sunset.subtract(const Duration(hours: 1)).difference(_now), sunset: sunset);
  }

  @override
  Widget build(BuildContext context) {
    final s = _state();
    final h = s.left.inHours;
    final m = s.left.inMinutes % 60;
    final sec = s.left.inSeconds % 60;
    final ink = GZInk.of(context);
    Widget block(String v, String unit) => Container(
          width: 74,
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: ink.paper,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: ink.hairline, width: 1),
            boxShadow: ink.softShadow,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(v, style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
              const SizedBox(height: 2),
              Text(unit.toUpperCase(), style: Theme.of(context).textTheme.labelSmall?.copyWith(color: ink.muted, letterSpacing: 1.6)),
            ],
          ),
        );
    String two(int v) => v.toString().padLeft(2, '0');
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          s.label.toUpperCase(),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: ink.text, letterSpacing: 2),
        ),
        const SizedBox(height: 14),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 14,
          runSpacing: 14,
          children: [block(two(h), 'hrs'), block(two(m), 'min'), block(two(sec), 'sec')],
        ),
        const SizedBox(height: 14),
        Text(
          'Sunset in Mangaluru: ${GZSun.clock(s.sunset)}',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(color: ink.muted),
        ),
      ],
    );
  }
}
