import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// GroundZero type system (Tiara-inspired: wide retro-future display
/// face, friendly grotesk body, mono for counters and labels).
///
///   display / headline / title*  -> Fraunces (editorial serif)
///   body / caption               -> DM Sans
///   label / metadata / section   -> DM Sans (tags, counters)
///
/// Fonts load from Google Fonts at runtime and fall back to the system
/// font if the network blocks them, so the app never breaks without them.
class GZTypography {
  final Color onSurface;
  final Color onSurfaceMuted;

  const GZTypography({required this.onSurface, required this.onSurfaceMuted});

  static GZTypography of(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return GZTypography(onSurface: scheme.onSurface, onSurfaceMuted: scheme.onSurfaceVariant);
  }

  TextStyle get display => GoogleFonts.fraunces(
        fontSize: 44,
        height: 1.0,
        fontWeight: FontWeight.w600,
        letterSpacing: -1.4,
        color: onSurface,
      );

  TextStyle get hero => GoogleFonts.fraunces(
        fontSize: 30,
        height: 1.1,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.6,
        color: onSurface,
      );

  TextStyle get section => GoogleFonts.dmSans(
        fontSize: 12,
        height: 1.2,
        fontWeight: FontWeight.w700,
        letterSpacing: 2.0,
        color: onSurface,
      );

  TextStyle get cardTitle => GoogleFonts.fraunces(
        fontSize: 17,
        height: 1.2,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
        color: onSurface,
      );

  TextStyle get label => GoogleFonts.dmSans(
        fontSize: 11,
        height: 1.3,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.3,
        color: onSurfaceMuted,
      );

  TextStyle get body => GoogleFonts.dmSans(
        fontSize: 15.5,
        height: 1.5,
        fontWeight: FontWeight.w400,
        color: onSurface,
      );

  TextStyle get caption => GoogleFonts.dmSans(
        fontSize: 13.5,
        height: 1.4,
        fontWeight: FontWeight.w500,
        color: onSurfaceMuted,
      );

  TextStyle get metadata => GoogleFonts.dmSans(
        fontSize: 11,
        height: 1.3,
        fontWeight: FontWeight.w400,
        letterSpacing: 0.3,
        color: onSurfaceMuted,
      );

  /// A complete TextTheme (every slot) so no screen falls back to the
  /// default Roboto look.
  TextTheme toTextTheme() {
    TextStyle grotesk(double size, FontWeight w, {Color? color, double? height}) =>
        GoogleFonts.dmSans(fontSize: size, fontWeight: w, color: color ?? onSurface, height: height);
    TextStyle wide(double size, FontWeight w, {double ls = -0.5}) => GoogleFonts.fraunces(
          fontSize: size,
          fontWeight: w,
          letterSpacing: ls,
          height: 1.15,
          color: onSurface,
        );
    return TextTheme(
      displayLarge: display,
      displayMedium: wide(38, FontWeight.w600, ls: -1.0),
      displaySmall: wide(32, FontWeight.w600, ls: -0.8),
      headlineLarge: hero,
      headlineMedium: wide(26, FontWeight.w600),
      headlineSmall: wide(22, FontWeight.w600),
      titleLarge: wide(20, FontWeight.w600, ls: -0.2),
      titleMedium: grotesk(16, FontWeight.w700),
      titleSmall: grotesk(14.5, FontWeight.w700),
      bodyLarge: grotesk(16, FontWeight.w400, height: 1.5),
      bodyMedium: grotesk(14, FontWeight.w400, color: onSurfaceMuted, height: 1.45),
      bodySmall: grotesk(12.5, FontWeight.w400, color: onSurfaceMuted, height: 1.4),
      labelLarge: GoogleFonts.dmSans(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 1.3, color: onSurface),
      labelMedium: label,
      labelSmall: metadata,
    );
  }
}
