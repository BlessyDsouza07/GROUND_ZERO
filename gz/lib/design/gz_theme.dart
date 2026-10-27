import 'package:flutter/material.dart';

import 'package:google_fonts/google_fonts.dart';

import 'gz_colors.dart';
import 'gz_radii.dart';
import 'gz_typography.dart';

/// Builds GroundZero's two `ThemeData` objects from the design tokens in
/// this folder (`gz_colors.dart`, `gz_typography.dart`, `gz_radii.dart`).
/// This is the one place that assembles tokens into a Flutter `Theme` —
/// everything else (screens, `gz_*` widgets) should read colors/type/
/// radii from the tokens or from `Theme.of(context)`, never redefine
/// them.
///
/// `lib/core/theme.dart` keeps its original `buildGZLightTheme()`/
/// `buildGZDarkTheme()` function names (so `theme_controller.dart` and
/// everything downstream of it is untouched) but now just calls
/// `GZTheme.light()`/`GZTheme.dark()` here.
class GZTheme {
  const GZTheme._();

  static ThemeData light() {
    final typography = const GZTypography(onSurface: GZLightColors.onSurface, onSurfaceMuted: GZLightColors.onSurfaceMuted);
    final scheme = ColorScheme.fromSeed(
      seedColor: GZLightColors.primary,
      brightness: Brightness.light,
      primary: GZLightColors.primary,
      secondary: GZLightColors.secondary,
      tertiary: GZLightColors.tertiary,
      surface: GZLightColors.background,
      onSurface: GZLightColors.onSurface,
      onSurfaceVariant: GZLightColors.onSurfaceMuted,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: scheme,
      scaffoldBackgroundColor: GZLightColors.background,
      pageTransitionsTheme: const PageTransitionsTheme(builders: {
        TargetPlatform.android: ZoomPageTransitionsBuilder(),
        TargetPlatform.iOS: FadeUpwardsPageTransitionsBuilder(),
        TargetPlatform.macOS: FadeUpwardsPageTransitionsBuilder(),
        TargetPlatform.windows: ZoomPageTransitionsBuilder(),
        TargetPlatform.linux: ZoomPageTransitionsBuilder(),
      }),
      textTheme: typography.toTextTheme(),
      appBarTheme: AppBarTheme(
        backgroundColor: GZLightColors.background,
        foregroundColor: GZLightColors.primary,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: typography.cardTitle,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: GZLightColors.primary,
          foregroundColor: GZLightColors.onPrimary,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: GZRadii.mdRadius),
          textStyle: GoogleFonts.dmSans(fontWeight: FontWeight.w600, fontSize: 15),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: GZLightColors.primary,
          side: BorderSide(color: GZLightColors.ink.withOpacity(0.7), width: 1.2),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: GZRadii.mdRadius),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: GZLightColors.surface,
        border: OutlineInputBorder(
          borderRadius: GZRadii.smRadius,
          borderSide: BorderSide(color: GZLightColors.ink.withOpacity(0.3), width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: GZRadii.smRadius,
          borderSide: BorderSide(color: GZLightColors.primary, width: 2),
        ),
      ),
      cardTheme: CardThemeData(
        color: GZLightColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: BorderSide(color: GZLightColors.ink.withOpacity(0.34), width: 1)),
      ),
      dividerColor: GZLightColors.outline.withOpacity(0.4),
    );
  }

  static ThemeData dark() {
    final typography = const GZTypography(onSurface: GZDarkColors.onSurface, onSurfaceMuted: GZDarkColors.onSurfaceMuted);
    final scheme = ColorScheme.fromSeed(
      seedColor: GZDarkColors.primary,
      brightness: Brightness.dark,
      primary: GZDarkColors.primary,
      secondary: GZDarkColors.secondary,
      tertiary: GZDarkColors.tertiary,
      surface: GZDarkColors.background,
      onSurface: GZDarkColors.onSurface,
      onSurfaceVariant: GZDarkColors.onSurfaceMuted,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: GZDarkColors.background,
      textTheme: typography.toTextTheme(),
      appBarTheme: AppBarTheme(
        backgroundColor: GZDarkColors.background,
        foregroundColor: GZDarkColors.primary,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: typography.cardTitle,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: GZDarkColors.primary,
          foregroundColor: GZDarkColors.onPrimary,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: GZRadii.mdRadius),
          textStyle: GoogleFonts.dmSans(fontWeight: FontWeight.w600, fontSize: 15),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: GZDarkColors.primary,
          side: BorderSide(color: GZDarkColors.goldenAmber.withOpacity(0.7), width: 1.2),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: GZRadii.mdRadius),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: GZDarkColors.surface,
        border: OutlineInputBorder(
          borderRadius: GZRadii.smRadius,
          borderSide: BorderSide(color: GZDarkColors.goldenAmber.withOpacity(0.4), width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: GZRadii.smRadius,
          borderSide: BorderSide(color: GZDarkColors.primary, width: 2),
        ),
      ),
      cardTheme: CardThemeData(
        color: GZDarkColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: BorderSide(color: GZDarkColors.goldenAmber.withOpacity(0.5), width: 1)),
      ),
      dividerColor: GZDarkColors.outline.withOpacity(0.5),
    );
  }
}
