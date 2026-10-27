import 'package:flutter/material.dart';

/// GroundZero palettes — exactly the two sets Carol specified.
///
/// Light ("sea by day"):  #006996 #0699BA #20A4B0 #8FC2B9 #E0DCD3
/// Dark  ("dusk sunset"): #FFC136 #D97E0C #A73006 #6F0100 #240002
///
/// Only tints/shades of these (for paper, ink and muted text) are derived.
class GZLightColors {
  const GZLightColors._();
  static const deepOcean = Color(0xFF006996);
  static const cerulean = Color(0xFF0699BA);
  static const teal = Color(0xFF20A4B0);
  static const seafoam = Color(0xFF8FC2B9);
  static const warmIvory = Color(0xFFE0DCD3);

  // derived
  static const ink = Color(0xFF00394F); // deepOcean, darkened — borders & text
  static const paper = Color(0xFFF1EEE7); // warmIvory, lightened — cards
  static const primary = deepOcean;
  static const secondary = cerulean;
  static const tertiary = teal;
  static const background = warmIvory;
  static const surface = paper;
  static const onPrimary = Color(0xFFF7F4EE);
  static const onSurface = ink;
  static const onSurfaceMuted = Color(0xFF3E6577);
  static const outline = seafoam;
}

class GZDarkColors {
  const GZDarkColors._();
  static const goldenAmber = Color(0xFFFFC136);
  static const burntOrange = Color(0xFFD97E0C);
  static const rust = Color(0xFFA73006);
  static const deepCrimson = Color(0xFF6F0100);
  static const deepBurgundy = Color(0xFF240002);

  // derived
  static const paper = Color(0xFF3A0508); // between burgundy and crimson
  static const cream = Color(0xFFFBE9C6); // goldenAmber, lightened — text
  static const primary = goldenAmber;
  static const secondary = burntOrange;
  static const tertiary = rust;
  static const background = deepBurgundy;
  static const surface = paper;
  static const onPrimary = deepBurgundy;
  static const onSurface = cream;
  static const onSurfaceMuted = Color(0xFFD9B98A);
  static const outline = rust;
}
