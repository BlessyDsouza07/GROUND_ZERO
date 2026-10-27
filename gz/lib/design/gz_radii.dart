import 'package:flutter/material.dart';

/// GroundZero's corner-radius scale. The existing screens already used
/// 12/14/18 fairly consistently before this pass (inputs=12, buttons=14,
/// cards=18) — this file names those same three values plus a `full`
/// pill radius, so new components reach for `GZRadii.card` instead of a
/// bare `18` that means nothing on its own.
class GZRadii {
  const GZRadii._();

  static const double sm = 12.0; // inputs, chips
  static const double md = 14.0; // buttons
  static const double lg = 18.0; // cards, sheets
  static const double full = 999.0; // pills, avatars

  static BorderRadius get smRadius => BorderRadius.circular(sm);
  static BorderRadius get mdRadius => BorderRadius.circular(md);
  static BorderRadius get lgRadius => BorderRadius.circular(lg);
  static BorderRadius get fullRadius => BorderRadius.circular(full);
}
