import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'theme.dart';

const String _prefsKey = 'groundzero.theme_mode';

/// Drives GroundZero's light/dark/automatic theme.
///
/// In automatic mode it checks the clock every minute and flips between
/// the light and dark ThemeData; wrapping the app in an [AnimatedTheme]
/// (done in main.dart) turns that flip into the slow fade the brief
/// asked for, instead of a hard cut.
class ThemeController extends ChangeNotifier {
  GZThemeMode _mode = GZThemeMode.automatic;
  Timer? _clockTimer;

  GZThemeMode get mode => _mode;

  /// The theme to actually render right now, resolving `automatic`
  /// against the current time of day.
  ThemeData get activeTheme {
    switch (_mode) {
      case GZThemeMode.light:
        return buildGZLightTheme();
      case GZThemeMode.dark:
        return buildGZDarkTheme();
      case GZThemeMode.automatic:
        return isDaytimeNow() ? buildGZLightTheme() : buildGZDarkTheme();
    }
  }

  bool get isDarkRightNow => switch (_mode) {
        GZThemeMode.dark => true,
        GZThemeMode.light => false,
        GZThemeMode.automatic => !isDaytimeNow(),
      };

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null) {
      _mode = GZThemeMode.values.firstWhere(
        (m) => m.name == saved,
        orElse: () => GZThemeMode.automatic,
      );
    }
    _restartClockWatchIfNeeded();
    notifyListeners();
  }

  Future<void> setMode(GZThemeMode mode) async {
    if (mode == _mode) return;
    _mode = mode;
    _restartClockWatchIfNeeded();
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, mode.name);
  }

  void _restartClockWatchIfNeeded() {
    _clockTimer?.cancel();
    _clockTimer = null;
    if (_mode == GZThemeMode.automatic) {
      // A minute is frequent enough to catch the 6 AM / 7 PM boundary
      // promptly without doing any real work most of the time.
      _clockTimer = Timer.periodic(const Duration(minutes: 1), (_) => notifyListeners());
    }
  }

  @override
  void dispose() {
    _clockTimer?.cancel();
    super.dispose();
  }
}
