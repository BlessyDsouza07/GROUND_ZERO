import 'package:groundzero/core/api_client.dart';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// One card in "Your Mangaluru, today" — everything shown is backed by a
/// field the server sent. `why` are the reasons, `caveats` the honest gaps.
class HiveCard {
  final String placeId;
  final String name;
  final String category;
  final double lat;
  final double lng;
  final String role;
  final double distanceKm;
  final int travelMin;
  final String openState;
  final String openLabel;
  final String openSource;
  final List<String> why;
  final List<String> caveats;
  final String? lessTouristyEvidence;
  final bool hiddenGem;
  final String confidence;
  final String verificationNote;
  final List<String> sources;
  final List<({String key, double strength})> experiences;
  final int stop;

  HiveCard.fromJson(Map<String, dynamic> j)
      : placeId = j['place_id'] as String,
        name = j['name'] as String,
        category = j['category'] as String,
        lat = (j['lat'] as num).toDouble(),
        lng = (j['lng'] as num).toDouble(),
        role = j['role'] as String? ?? 'anchor',
        distanceKm = (j['distance_km'] as num).toDouble(),
        travelMin = (j['travel_min'] as num).toInt(),
        openState = j['open_state'] as String? ?? 'unknown',
        openLabel = j['open_label'] as String? ?? '',
        openSource = j['open_source'] as String? ?? 'none',
        why = List<String>.from(j['why'] as List? ?? const []),
        caveats = List<String>.from(j['caveats'] as List? ?? const []),
        lessTouristyEvidence = j['less_touristy_evidence'] as String?,
        hiddenGem = j['hidden_gem'] as bool? ?? false,
        confidence = (j['evidence'] as Map?)?['confidence'] as String? ?? 'low',
        verificationNote = (j['evidence'] as Map?)?['verification_note'] as String? ?? '',
        sources = List<String>.from((j['evidence'] as Map?)?['sources'] as List? ?? const []),
        experiences = [
          for (final e in (j['experiences'] as List? ?? const []))
            (key: (e as Map)['key'] as String, strength: (e['strength'] as num).toDouble()),
        ],
        stop = (j['stop'] as num?)?.toInt() ?? 0;
}

class HivePlan {
  final List<String> understood;
  final String? message;
  final List<HiveCard> cards;
  final bool personalised;
  final bool located;
  final String note;
  HivePlan.fromJson(Map<String, dynamic> j)
      : understood = List<String>.from(j['understood'] as List? ?? const []),
        message = j['message'] as String?,
        cards = [for (final c in (j['cards'] as List? ?? const [])) HiveCard.fromJson(c as Map<String, dynamic>)],
        personalised = j['personalised'] as bool? ?? false,
        located = j['located'] as bool? ?? false,
        note = j['note'] as String? ?? '';
}

class HiveAffinity {
  final String key;
  final double weight;
  final double confidence;
  final String source;
  HiveAffinity(this.key, this.weight, this.confidence, this.source);
}

class HiveProfile {
  final List<HiveAffinity> affinities;
  final Map<String, dynamic> constraints;
  final int visited;
  final int dismissed;
  HiveProfile.fromJson(Map<String, dynamic> j)
      : affinities = [
          for (final e in ((j['affinities'] as Map?) ?? const {}).entries)
            HiveAffinity(e.key as String, ((e.value as Map)['weight'] as num).toDouble(),
                (((e.value as Map)['confidence'] ?? 0) as num).toDouble(), ((e.value as Map)['source'] ?? 'behaviour') as String),
        ]..sort((a, b) => b.weight.abs().compareTo(a.weight.abs())),
        constraints = Map<String, dynamic>.from(j['constraints'] as Map? ?? const {}),
        visited = (j['visited_count'] as num?)?.toInt() ?? 0,
        dismissed = (j['dismissed_count'] as num?)?.toInt() ?? 0;
}

class HiveNudge {
  final String placeId;
  final String title;
  final String body;
  final String? caveat;
  HiveNudge(this.placeId, this.title, this.body, this.caveat);
}

class HiveEvent {
  final String title;
  final String? startAt;
  final String? venue;
  final String? sourceUrl;
  final bool confirmed;
  HiveEvent.fromJson(Map<String, dynamic> j)
      : title = j['title'] as String,
        startAt = j['start_at'] as String?,
        venue = j['venue'] as String?,
        sourceUrl = j['source_url'] as String?,
        confirmed = j['status'] == 'confirmed';
}

/// HIVE 2 + privacy endpoints. Every method throws [GZApiException].
class HiveApiClient {
  final http.Client _http;
  HiveApiClient({http.Client? client}) : _http = client ?? http.Client();

  Uri _u(String p) => Uri.parse('$gzApiBaseUrl$p');
  Map<String, String> _h(String? t) => {'Content-Type': 'application/json', if (t != null) 'Authorization': 'Bearer $t'};

  Future<dynamic> _send(String method, String path, {String? token, Map<String, dynamic>? body}) async {
    http.Response r;
    try {
      final req = http.Request(method, _u(path))..headers.addAll(_h(token));
      if (body != null) req.body = jsonEncode(body);
      r = await http.Response.fromStream(await _http.send(req).timeout(const Duration(seconds: 20)));
    } on Object {
      throw GZApiException('Can\'t reach GroundZero right now. Check your connection and try again.');
    }
    dynamic decoded;
    try {
      decoded = r.body.isEmpty ? <String, dynamic>{} : jsonDecode(utf8.decode(r.bodyBytes));
    } on FormatException {
      decoded = <String, dynamic>{};
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return decoded;
    final d = decoded is Map ? decoded['detail'] : null;
    throw GZApiException(d is String ? d : 'Something went wrong. Please try again.', r.statusCode);
  }

  Future<HivePlan> plan(String token, {String text = '', double? lat, double? lng, String? mode, int? minutes, int limit = 6}) async {
    final j = await _send('POST', '/hive/plan', token: token, body: {
      'text': text,
      if (lat != null) 'lat': lat,
      if (lng != null) 'lng': lng,
      if (mode != null) 'mode': mode,
      if (minutes != null) 'minutes': minutes,
      'limit': limit,
    });
    return HivePlan.fromJson(j as Map<String, dynamic>);
  }

  /// Returns false when personalisation is off (nothing was stored).
  Future<bool> feedback(String token, String placeId, String kind, {String? reason, int? rating}) async {
    final j = await _send('POST', '/hive/feedback', token: token, body: {
      'place_id': placeId,
      'kind': kind,
      if (reason != null) 'reason': reason,
      if (rating != null) 'rating': rating,
    });
    return (j as Map)['stored'] == true;
  }

  Future<HiveProfile> profile(String token) async =>
      HiveProfile.fromJson(await _send('GET', '/hive/profile', token: token) as Map<String, dynamic>);

  Future<HiveProfile> updateProfile(String token, {Map<String, dynamic>? constraints, Map<String, double>? stated, List<String>? remove}) async {
    final j = await _send('PUT', '/hive/profile', token: token, body: {
      if (constraints != null) 'constraints': constraints,
      if (stated != null) 'stated': stated,
      if (remove != null) 'remove': remove,
    });
    return HiveProfile.fromJson(j as Map<String, dynamic>);
  }

  Future<void> deleteMemory(String token) => _send('DELETE', '/hive/profile', token: token);

  /// Foreground check-in. Coordinates are used for this one decision and not stored.
  Future<HiveNudge?> checkIn(String token, double lat, double lng, double accuracyM, {bool quiet = false}) async {
    final j = await _send('POST', '/hive/location', token: token, body: {'lat': lat, 'lng': lng, 'accuracy_m': accuracyM, 'quiet': quiet}) as Map;
    final n = j['notify'];
    if (n is! Map) return null;
    return HiveNudge(n['place_id'] as String, n['title'] as String, n['body'] as String, n['caveat'] as String?);
  }

  Future<List<HiveEvent>> events(String token) async {
    final j = await _send('GET', '/hive/events', token: token) as Map;
    return [for (final e in (j['events'] as List? ?? const [])) HiveEvent.fromJson(e as Map<String, dynamic>)];
  }

  // ---- privacy ----
  Future<Map<String, bool>> consents(String token) async {
    final j = await _send('GET', '/privacy/consents', token: token) as Map;
    return {for (final e in (j['consents'] as Map).entries) e.key as String: (e.value as Map)['granted'] == true};
  }

  Future<Map<String, bool>> setConsent(String token, String kind, bool granted) async {
    final j = await _send('PUT', '/privacy/consents', token: token, body: {'kind': kind, 'granted': granted}) as Map;
    return {for (final e in (j['consents'] as Map).entries) e.key as String: (e.value as Map)['granted'] == true};
  }

  Future<String> exportJson(String token) async =>
      const JsonEncoder.withIndent('  ').convert(await _send('GET', '/privacy/export', token: token));

  Future<String> legal(String doc) async => ((await _send('GET', '/legal/$doc')) as Map)['markdown'] as String;

  Future<List<({String label, String number})>> emergency() async {
    final j = await _send('GET', '/safety') as Map;
    return [for (final e in (j['emergency'] as List)) (label: (e as Map)['label'] as String, number: e['number'] as String)];
  }

  Future<void> report(String token, {required String kind, required String ref, required String reason, String? detail}) =>
      _send('POST', '/privacy/report', token: token, body: {'target_kind': kind, 'target_ref': ref, 'reason': reason, if (detail != null) 'detail': detail});

  Future<void> deleteAccount(String token) => _send('DELETE', '/auth/me', token: token);

  void close() => _http.close();
}
