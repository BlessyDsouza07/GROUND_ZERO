import 'package:flutter/material.dart';

/// Soft, editorial drop shadows — used instead of Material's default
/// elevation (every `CardTheme` in `gz_theme.dart` keeps `elevation: 0`
/// deliberately, same as before this pass) so cards read as "designed"
/// rather than as stock Material surfaces with a default drop shadow.
///
/// Two levels only: `resting` for a card sitting in a list, `raised`
/// for one the person is actively interacting with (a dragged reorder
/// item, an open sheet). Kept intentionally subtle — see the brief:
/// "calm, intelligent, human... not flashy."
class GZShadows {
  const GZShadows._();

  static List<BoxShadow> resting(Brightness brightness) => [
        BoxShadow(
          color: (brightness == Brightness.dark ? Colors.black : const Color(0xFF14262C))
              .withOpacity(brightness == Brightness.dark ? 0.35 : 0.08),
          blurRadius: 18,
          offset: const Offset(0, 6),
        ),
      ];

  static List<BoxShadow> raised(Brightness brightness) => [
        BoxShadow(
          color: (brightness == Brightness.dark ? Colors.black : const Color(0xFF14262C))
              .withOpacity(brightness == Brightness.dark ? 0.45 : 0.14),
          blurRadius: 28,
          offset: const Offset(0, 10),
        ),
      ];
}
