import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'strings.dart';

/// The languages GroundZero currently ships with, in the order shown in
/// the language picker. Keep this list and [kStrings] (strings.dart) in
/// sync — every key must exist for every code here.
class AppLanguage {
  final String code;
  final String nativeName;
  final String englishName;

  const AppLanguage(this.code, this.nativeName, this.englishName);
}

const List<AppLanguage> kSupportedLanguages = [
  AppLanguage('en', 'English', 'English'),
  AppLanguage('kn', 'ಕನ್ನಡ', 'Kannada'),
  AppLanguage('hi', 'हिन्दी', 'Hindi'),
  AppLanguage('ta', 'தமிழ்', 'Tamil'),
  AppLanguage('te', 'తెలుగు', 'Telugu'),
];

const String _prefsKey = 'groundzero.language_code';

/// Holds the app's current language and exposes `t()` for looking up a
/// translated string by key. Every screen listens to this via
/// AnimatedBuilder/ListenableBuilder so switching languages updates the
/// whole app immediately, with no restart.
class LocaleController extends ChangeNotifier {
  String _code = 'en';

  String get code => _code;

  AppLanguage get current =>
      kSupportedLanguages.firstWhere((l) => l.code == _code, orElse: () => kSupportedLanguages.first);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null && kStrings.containsKey(saved)) {
      _code = saved;
      notifyListeners();
    }
  }

  Future<void> setLanguage(String code) async {
    if (!kStrings.containsKey(code) || code == _code) return;
    _code = code;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, code);
  }

  /// Translates [key], optionally substituting `{placeholder}` tokens
  /// from [args]. Falls back to English, then to the key itself, so a
  /// missing translation never crashes the UI.
  String t(String key, [Map<String, String>? args]) {
    final table = kStrings[_code] ?? kStrings['en']!;
    String text = table[key] ?? kStrings['en']?[key] ?? key;
    if (args != null) {
      args.forEach((name, value) {
        text = text.replaceAll('{$name}', value);
      });
    }
    return text;
  }
}
