import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Opens real turn-by-turn directions to an exact coordinate in the
/// device's maps (Google Maps on web/Android, Maps on iOS via the same
/// universal link). Never a stub: if it genuinely cannot launch, the user
/// is shown the coordinates so they can still find the spot.
class GZMaps {
  static Uri directionsUri(double lat, double lng, {String mode = 'driving'}) => Uri.https(
        'www.google.com',
        '/maps/dir/',
        {'api': '1', 'destination': '$lat,$lng', 'travelmode': mode},
      );

  static Uri pinUri(double lat, double lng) => Uri.https(
        'www.google.com',
        '/maps/search/',
        {'api': '1', 'query': '$lat,$lng'},
      );

  static Future<void> directions(BuildContext context, double lat, double lng,
      {String? name, String mode = 'driving'}) async {
    final messenger = ScaffoldMessenger.of(context);
    var ok = false;
    try {
      ok = await launchUrl(directionsUri(lat, lng, mode: mode), mode: LaunchMode.externalApplication);
    } on Object {
      ok = false;
    }
    if (!ok) {
      messenger.showSnackBar(SnackBar(
        content: Text('Couldn\'t open maps. ${name ?? 'Place'} is at ${lat.toStringAsFixed(5)}, ${lng.toStringAsFixed(5)}.'),
      ));
    }
  }

  /// OSM-mode name for a trip leg's travel mode.
  static String modeFor(String? m) => switch ((m ?? '').toLowerCase()) {
        'walk' || 'walking' => 'walking',
        'bike' || 'bicycle' => 'bicycling',
        _ => 'driving',
      };
}
