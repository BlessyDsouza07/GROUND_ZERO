import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'gz_consent.dart';
import 'hive_api_client.dart';

/// A tiny on-device "Mangaluru passport": places the traveller chose to stamp.
/// Stored only in this browser/device (SharedPreferences) — nothing is sent
/// anywhere from here.
class GZPassport {
  static const _key = 'gz.passport.stamps';
  static final ValueNotifier<Set<String>> stamps = ValueNotifier<Set<String>>({});
  static bool _loaded = false;

  static const levels = [
    (0, 'Newcomer'),
    (1, 'Wanderer'),
    (5, 'Explorer'),
    (15, 'Regular'),
    (30, 'Local'),
  ];

  static Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      final p = await SharedPreferences.getInstance();
      stamps.value = (p.getStringList(_key) ?? const <String>[]).toSet();
    } on Object {
      // Storage unavailable: passport just works for this session.
    }
  }

  static bool has(String id) => stamps.value.contains(id);

  /// Toggles a stamp; returns true when the place is now stamped.
  static Future<bool> toggle(String id) async {
    final next = Set<String>.of(stamps.value);
    final added = next.add(id);
    if (!added) next.remove(id);
    stamps.value = next;
    try {
      final p = await SharedPreferences.getInstance();
      await p.setStringList(_key, next.toList());
    } on Object {
      // ignore
    }
    return added;
  }

  static String levelName([int? n]) {
    final c = n ?? stamps.value.length;
    var name = levels.first.$2;
    for (final l in levels) {
      if (c >= l.$1) name = l.$2;
    }
    return name;
  }

  /// (nextLevelName, stampsNeeded) or null at top level.
  static ({String name, int need, double progress})? next([int? n]) {
    final c = n ?? stamps.value.length;
    for (var i = 0; i < levels.length; i++) {
      if (c < levels[i].$1) {
        final prev = levels[i - 1].$1;
        return (name: levels[i].$2, need: levels[i].$1 - c, progress: (c - prev) / (levels[i].$1 - prev));
      }
    }
    return null;
  }

  /// Toggle a stamp from any screen: saves it, sends the optional (consented)
  /// "visited" signal, and tells the traveller what it did for their level.
  static Future<bool> stamp(BuildContext context, String id, String name) async {
    final before = levelName();
    final added = await toggle(id);
    final tok = GZConsent.token;
    if (added && GZConsent.personalization && tok != null) {
      try {
        await HiveApiClient().feedback(tok, id, 'visited');
      } on Object {
        // Best-effort personalisation signal.
      }
    }
    if (!context.mounted) return added;
    final after = levelName();
    final nx = next();
    final msg = !added
        ? 'Stamp removed.'
        : after != before
            ? 'New level: $after! $name is in your passport.'
            : nx == null
                ? 'Stamped $name.'
                : 'Stamped $name. ${nx.need} more to become a ${nx.name}.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 3)));
    return added;
  }
}
