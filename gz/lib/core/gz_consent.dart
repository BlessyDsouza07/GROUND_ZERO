import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'gz_location.dart';
import 'hive_api_client.dart';

/// The person's privacy choices, mirrored from the server. Nothing that
/// uses location, memory or the camera starts until the matching switch is
/// on; every switch can be turned off again in Privacy.
class GZConsent {
  static bool location = false;
  static bool personalization = false;
  static bool photos = false;
  static String? token;
  static String? lastError;
  static final HiveApiClient _api = HiveApiClient();

  static void _apply(Map<String, bool> c) {
    location = c['location'] ?? false;
    personalization = c['personalization'] ?? false;
    photos = c['photos'] ?? false;
    GZLocation.consented = location;
    if (location && !GZLocation.known) GZLocation.refresh();
    if (!location) {
      GZLocation.lat = null;
      GZLocation.lng = null;
    }
  }

  static Future<void> load(String t) async {
    token = t;
    try {
      _apply(await _api.consents(t));
    } on Object {/* offline: everything stays off, which is the safe default */}
  }

  static void clear() {
    token = null;
    _apply(const {});
  }

  static Future<bool> set(String token, String kind, bool granted) async {
    lastError = null;
    try {
      _apply(await _api.setConsent(token, kind, granted));
      return granted;
    } on Object catch (e) {
      lastError = e.toString().isEmpty ? 'Could not save your choice.' : e.toString();
      return false;
    }
  }

  static const _copy = {
    'location': (
      'Use your location?',
      'GroundZero uses where you are right now to show what is open and near you. It is not saved as a history; you can switch it off any time in Privacy. Your browser or phone will ask too.',
    ),
    'personalization': (
      'Let GroundZero learn what you like?',
      'It remembers what you save, skip and visit so suggestions get more like you. You can see, edit and delete this memory whenever you want. Turning it off deletes it.',
    ),
    'photos': (
      'Use your camera and photos?',
      'Photos you take or choose go to your journal, your trip story, or a place you contribute. Hidden location data is stripped from the file. Nothing is taken without you pressing the button.',
    ),
  };

  /// Explains, then asks. Returns true only if the person agreed.
  static Future<bool> ask(BuildContext context, String token, String kind) async {
    final c = _copy[kind]!;
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(c.$1),
        content: Text(c.$2),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Allow')),
        ],
      ),
    );
    if (yes != true) return false;
    final ok = await set(token, kind, true);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Could not save that choice: ${lastError ?? 'unknown error'}. Is the backend running and up to date (alembic upgrade head)?'),
        duration: const Duration(seconds: 8),
      ));
    }
    return ok;
  }

  static const _seenKey = 'gz.consent_intro_seen';

  /// One-time "your choices" sheet shown after the first sign-in.
  static Future<void> showIntroOnce(BuildContext context, String token) async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(_seenKey) == true) return;
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      builder: (ctx) => _Intro(token: token),
    );
    await prefs.setBool(_seenKey, true);
  }
}

class _Intro extends StatefulWidget {
  final String token;
  const _Intro({required this.token});

  @override
  State<_Intro> createState() => _IntroState();
}

class _IntroState extends State<_Intro> {
  bool _loc = false, _pers = false, _photo = false, _busy = false;

  Future<void> _save() async {
    setState(() => _busy = true);
    if (_loc) await GZConsent.set(widget.token, 'location', true);
    if (_pers) await GZConsent.set(widget.token, 'personalization', true);
    if (_photo) await GZConsent.set(widget.token, 'photos', true);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(22, 22, 22, 22 + MediaQuery.of(context).viewInsets.bottom),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('You decide what GroundZero can use', style: t.titleLarge),
              const SizedBox(height: 6),
              Text('Everything is off until you switch it on. You can change any of this later in Privacy.', style: t.bodyMedium),
              const SizedBox(height: 10),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _loc,
                onChanged: (v) => setState(() => _loc = v),
                title: const Text('Location'),
                subtitle: const Text('Show what is open and near you right now. No location history is kept.'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _pers,
                onChanged: (v) => setState(() => _pers = v),
                title: const Text('Learn what I like'),
                subtitle: const Text('Remember saves and skips to improve suggestions. You can see, edit, delete it.'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _photo,
                onChanged: (v) => setState(() => _photo = v),
                title: const Text('Camera and photos'),
                subtitle: const Text('For your journal and contributions. Hidden location data is removed from photos.'),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save my choices')),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
