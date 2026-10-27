import 'package:geolocator/geolocator.dart';

/// The traveller's real position, fetched once and shared by every screen so
/// recommendations are near them (and not always near the city centre).
/// If permission is denied or slow, [lat]/[lng] stay null and the backend
/// falls back to central Mangaluru.
class GZLocation {
  static double? lat;
  static double? lng;
  static double? accuracy; // metres, as reported by the device
  static bool denied = false;

  /// Set from the person's saved privacy choice (GZConsent). Nothing asks the
  /// browser or phone for location while this is false.
  static bool consented = false;
  static Future<void>? _inflight;

  static bool get known => lat != null && lng != null;

  static Future<void> ensure() => _inflight ??= _load();

  static Future<void> refresh() {
    _inflight = null;
    return ensure();
  }

  static Future<void> _load() async {
    if (!consented) return;
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        denied = true;
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.best),
      ).timeout(const Duration(seconds: 25));
      lat = pos.latitude;
      lng = pos.longitude;
      accuracy = pos.accuracy;
      denied = false;
    } on Object {
      // keep whatever we had; callers fall back gracefully
    }
  }
}
