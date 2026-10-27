import 'package:flutter/material.dart';

import '../design/gz_colors.dart';
import '../design/gz_theme.dart';

/// GroundZero's two brand palettes.
///
/// DESIGN SYSTEM PASS (6th audit response follow-up, Oct 2026): the
/// actual color values now live in `lib/design/gz_colors.dart` — the
/// single source of truth the production-candidate brief asked for
/// ("Modify theme.dart, but don't keep everything inside that one
/// file"). `GZLightPalette`/`GZDarkPalette` stay here as thin aliases
/// so every existing call site (`theme_sheet.dart`, and any other file
/// that does `import 'core/theme.dart'` and reaches for
/// `GZLightPalette.deepOceanBlue`) keeps compiling unchanged — this is
/// a pure refactor, not a rename.
class GZLightPalette {
  static const deepOceanBlue = GZLightColors.deepOcean;
  static const ceruleanOceanBlue = GZLightColors.cerulean;
  static const tealBlue = GZLightColors.teal;
  static const seafoamGreen = GZLightColors.seafoam;
  static const warmIvory = GZLightColors.warmIvory;
}

class GZDarkPalette {
  static const goldenAmber = GZDarkColors.goldenAmber;
  static const burntOrange = GZDarkColors.burntOrange;
  static const rustSienna = GZDarkColors.rust;
  static const deepCrimsonRed = GZDarkColors.deepCrimson;
  static const deepBurgundy = GZDarkColors.deepBurgundy;
}

/// Which appearance the person picked. `automatic` follows the device
/// clock: light during the day, dark at night (see [isDaytimeNow]).
enum GZThemeMode { light, dark, automatic }

/// Simple, fixed day/night split used by automatic mode: 6:00 AM–6:59 PM
/// is daytime, everything else is night. No location or sunrise lookup
/// is involved — just the device clock, as requested.
bool isDaytimeNow([DateTime? at]) {
  final hour = (at ?? DateTime.now()).hour;
  return hour >= 6 && hour < 19;
}

/// Builds GroundZero's light theme. The actual `ThemeData` assembly now
/// lives in `lib/design/gz_theme.dart` (`GZTheme.light()`), built from
/// the design tokens in `lib/design/` — this function is kept as a thin
/// wrapper so `theme_controller.dart`'s existing `buildGZLightTheme()`
/// call site needs no change.
ThemeData buildGZLightTheme() => GZTheme.light();

/// Builds GroundZero's dark theme — see [buildGZLightTheme].
ThemeData buildGZDarkTheme() => GZTheme.dark();
