import 'package:flutter/material.dart';

import 'gz_colors.dart';

/// The "retro print" look shared by every Tiara-style surface: a hard
/// ink border plus a hard (un-blurred) offset shadow, like a sticker or a
/// risograph card. One place so light and dark stay in step.
class GZInk {
  final Color border;
  final Color shadow;
  final Color paper;
  final Color paperAlt;
  final Color accent;
  final Color accent2;
  final Color text;
  final Color muted;
  final bool dark;

  const GZInk({
    required this.border,
    required this.shadow,
    required this.paper,
    required this.paperAlt,
    required this.accent,
    required this.accent2,
    required this.text,
    required this.muted,
    required this.dark,
  });

  static const _light = GZInk(
    border: GZLightColors.ink,
    shadow: GZLightColors.ink,
    paper: GZLightColors.paper,
    paperAlt: GZLightColors.seafoam,
    accent: GZLightColors.deepOcean,
    accent2: GZLightColors.teal,
    text: GZLightColors.ink,
    muted: GZLightColors.onSurfaceMuted,
    dark: false,
  );

  static const _dark = GZInk(
    border: GZDarkColors.goldenAmber,
    shadow: GZDarkColors.rust,
    paper: GZDarkColors.paper,
    paperAlt: GZDarkColors.deepCrimson,
    accent: GZDarkColors.goldenAmber,
    accent2: GZDarkColors.burntOrange,
    text: GZDarkColors.cream,
    muted: GZDarkColors.onSurfaceMuted,
    dark: true,
  );

  /// Thin, quiet outline used for cards and inputs.
  Color get hairline => border.withOpacity(dark ? 0.5 : 0.34);

  /// Soft, diffuse elevation (replaces the old hard offset shadow).
  List<BoxShadow> get softShadow => [
        BoxShadow(
          color: (dark ? Colors.black : border).withOpacity(dark ? 0.40 : 0.13),
          blurRadius: 26,
          offset: const Offset(0, 10),
        ),
      ];

  static GZInk of(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? _dark : _light;
}
