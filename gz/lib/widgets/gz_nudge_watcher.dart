import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../core/auth_controller.dart';
import '../core/gz_consent.dart';
import '../core/hive_api_client.dart';
import '../screens/hive/today_screen.dart';

/// Foreground-only "you're near something" nudges.
///  * Runs only while the app is open AND the person switched location on.
///  * Asks the server once a minute; the server decides (accuracy, dwell,
///    cooldown, quiet mode, closed places) and at most one nudge appears.
///  * Coordinates are not stored. Pausing here stops all checks at once.
class GZNudges {
  static bool paused = false;
}

class NudgeWatcher extends StatefulWidget {
  final AuthController auth;
  final Widget child;
  const NudgeWatcher({super.key, required this.auth, required this.child});

  @override
  State<NudgeWatcher> createState() => _NudgeWatcherState();
}

class _NudgeWatcherState extends State<NudgeWatcher> with WidgetsBindingObserver {
  final _api = HiveApiClient();
  Timer? _timer;
  bool _foreground = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _tick());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => _foreground = state == AppLifecycleState.resumed;

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _api.close();
    super.dispose();
  }

  Future<void> _tick() async {
    if (_busy || !_foreground || GZNudges.paused || !GZConsent.location || !mounted) return;
    final token = widget.auth.accessToken;
    if (token == null) return;
    _busy = true;
    try {
      final perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) return;
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
      ).timeout(const Duration(seconds: 12));
      final nudge = await _api.checkIn(token, pos.latitude, pos.longitude, pos.accuracy);
      if (nudge != null && mounted) _show(nudge);
    } on Object {/* quiet: a missed check is harmless */} finally {
      _busy = false;
    }
  }

  void _show(HiveNudge n) {
    final m = ScaffoldMessenger.of(context);
    m.clearMaterialBanners();
    m.showMaterialBanner(MaterialBanner(
      leading: const Icon(Icons.near_me_outlined),
      content: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text(n.title, style: const TextStyle(fontWeight: FontWeight.w800)),
        Text(n.body + (n.caveat != null ? ' ${n.caveat}' : '')),
      ]),
      actions: [
        TextButton(onPressed: m.clearMaterialBanners, child: const Text('Dismiss')),
        TextButton(
          onPressed: () {
            m.clearMaterialBanners();
            Navigator.of(context).push(MaterialPageRoute(builder: (_) => TodayScreen(auth: widget.auth)));
          },
          child: const Text('See today'),
        ),
      ],
    ));
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
