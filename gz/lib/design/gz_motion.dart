import 'package:flutter/material.dart';

/// Named motion tokens. Per the production-candidate brief's own
/// staging (Phase 29: "add motion only after the design is right" —
/// explicitly deferred past this pass), this file only *names* the
/// durations/curves the app already uses (`main.dart`'s 900ms theme
/// cross-fade) plus a couple of standard tiers for components built in
/// this pass to reference consistently. It does not add any new
/// animation to a screen that didn't already have one.
class GZMotion {
  const GZMotion._();

  static const fast = Duration(milliseconds: 150);
  static const medium = Duration(milliseconds: 300);
  static const slow = Duration(milliseconds: 900); // matches main.dart's theme cross-fade

  static const standardCurve = Curves.easeInOut;
}
