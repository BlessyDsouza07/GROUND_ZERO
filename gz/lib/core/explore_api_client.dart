import 'package:groundzero/core/api_client.dart';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';
import 'gz_location.dart';

/// Mirrors explore/schemas.py's WhyNowOut.
class GZWhyNow {
  final String headline;
  final List<String> reasons;
  GZWhyNow({required this.headline, required this.reasons});
  factory GZWhyNow.fromJson(Map<String, dynamic> j) => GZWhyNow(
        headline: j['headline'] as String,
        reasons: (j['reasons'] as List).map((e) => e as String).toList(),
      );
}

/// Mirrors explore/schemas.py's PlaceCardOut (and its subclasses
/// PickOut/BeyondTheObviousOut, which just add a couple of extra fields
/// on top — kept as nullable extras here rather than three separate
/// Dart classes, since every screen that renders a "place card" wants
/// the same shape).
class GZPlaceCard {
  final String placeId;
  final String name;
  final String category;
  final List<String> tags;
  final double latitude;
  final double longitude;
  final String priceBand;
  final double estimatedCost;
  final int dwellMinutes;
  final String crowdLevel;
  final String? bestTime;
  final String? grade;
  final int mediaMentions;
  final String provenance; // "verified" | "community"
  final String? imageUrl; // always null today — see README_EXPLORE.md
  final double? distanceKm;
  final GZWhyNow whyNow;
  final String? openState; // open | closed | unknown
  final String? openLabel;

  // GroundZero Picks only:
  final int? fitPercent;
  final Map<String, bool>? whyThisPick;
  // Beyond the Obvious only:
  final String? whyFoundThis;

  GZPlaceCard({
    required this.placeId,
    required this.name,
    required this.category,
    required this.tags,
    required this.latitude,
    required this.longitude,
    required this.priceBand,
    required this.estimatedCost,
    required this.dwellMinutes,
    required this.crowdLevel,
    this.bestTime,
    this.grade,
    required this.mediaMentions,
    required this.provenance,
    this.imageUrl,
    this.distanceKm,
    required this.whyNow,
    this.openState,
    this.openLabel,
    this.fitPercent,
    this.whyThisPick,
    this.whyFoundThis,
  });

  factory GZPlaceCard.fromJson(Map<String, dynamic> j) => GZPlaceCard(
        placeId: j['place_id'] as String,
        name: j['name'] as String,
        category: j['category'] as String,
        tags: (j['tags'] as List).map((e) => e as String).toList(),
        latitude: (j['latitude'] as num).toDouble(),
        longitude: (j['longitude'] as num).toDouble(),
        priceBand: j['price_band'] as String,
        estimatedCost: (j['estimated_cost'] as num).toDouble(),
        dwellMinutes: j['dwell_minutes'] as int,
        crowdLevel: j['crowd_level'] as String,
        bestTime: j['best_time'] as String?,
        grade: j['grade'] as String?,
        mediaMentions: j['media_mentions'] as int,
        provenance: j['provenance'] as String,
        imageUrl: j['image_url'] as String?,
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        whyNow: GZWhyNow.fromJson(j['why_now'] as Map<String, dynamic>),
        openState: j['open_state'] as String?,
        openLabel: j['open_label'] as String?,
        fitPercent: j['fit_percent'] as int?,
        whyThisPick: j['why_this_pick'] == null
            ? null
            : (j['why_this_pick'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as bool)),
        whyFoundThis: j['why_found_this'] as String?,
      );
}

class GZSituation {
  final String situation; // stay | transit | place | outdoors
  final String? nearName;
  final String headline;
  final String detail;
  final String kind; // food | stay | rest | explore
  final double? accuracyM;
  final List<GZPlaceCard> suggestions;
  bool approx = false; // true when we could not get the traveller's real position
  GZSituation({required this.situation, this.nearName, required this.headline, required this.detail, required this.kind, required this.suggestions, this.accuracyM});

  factory GZSituation.fromJson(Map<String, dynamic> j) => GZSituation(
        situation: j['situation'] as String,
        nearName: j['near_name'] as String?,
        headline: j['headline'] as String,
        detail: j['detail'] as String,
        kind: j['kind'] as String,
        accuracyM: (j['accuracy_m'] as num?)?.toDouble(),
        suggestions: (j['suggestions'] as List).map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList(),
      );
}

class GZMood {
  final String slug;
  final String label;
  final String tagline;
  GZMood({required this.slug, required this.label, required this.tagline});
  factory GZMood.fromJson(Map<String, dynamic> j) =>
      GZMood(slug: j['slug'] as String, label: j['label'] as String, tagline: j['tagline'] as String);
}

/// Mirrors explore/schemas.py's RightNowOut — the "RIGHT NOW IN
/// MANGALURU" live-context panel.
class GZRightNow {
  final String headline;
  final bool weatherAvailable;
  final double? temperatureCelsius;
  final String? condition;
  final bool? isRain;
  final bool tideAvailable;
  final String? tideState;
  final int minutesToSunset;
  final int? eventsTodayCount;
  final String? weatherNote;
  final String? tideNote;

  GZRightNow({
    required this.headline,
    required this.weatherAvailable,
    this.temperatureCelsius,
    this.condition,
    this.isRain,
    required this.tideAvailable,
    this.tideState,
    required this.minutesToSunset,
    this.eventsTodayCount,
    this.weatherNote,
    this.tideNote,
  });

  factory GZRightNow.fromJson(Map<String, dynamic> j) => GZRightNow(
        headline: j['headline'] as String,
        weatherAvailable: j['weather_available'] as bool,
        temperatureCelsius: (j['temperature_celsius'] as num?)?.toDouble(),
        condition: j['condition'] as String?,
        isRain: j['is_rain'] as bool?,
        tideAvailable: j['tide_available'] as bool,
        tideState: j['tide_state'] as String?,
        minutesToSunset: j['minutes_to_sunset'] as int,
        eventsTodayCount: j['events_today_count'] as int?,
        weatherNote: j['weather_note'] as String?,
        tideNote: j['tide_note'] as String?,
      );
}

class GZExperienceCategory {
  final String slug;
  final String label;
  final List<GZPlaceCard> preview;
  final int totalCount;
  GZExperienceCategory({required this.slug, required this.label, required this.preview, required this.totalCount});
  factory GZExperienceCategory.fromJson(Map<String, dynamic> j) => GZExperienceCategory(
        slug: j['slug'] as String,
        label: j['label'] as String,
        preview: (j['preview'] as List).map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList(),
        totalCount: j['total_count'] as int,
      );
}

class GZEvent {
  final int id;
  final String title;
  final DateTime? startAt;
  final String? venue;
  final String? address;
  final String sourceUrl;
  GZEvent({required this.id, required this.title, this.startAt, this.venue, this.address, required this.sourceUrl});
  factory GZEvent.fromJson(Map<String, dynamic> j) => GZEvent(
        id: j['id'] as int,
        title: j['title'] as String,
        startAt: j['start_at'] == null ? null : DateTime.tryParse(j['start_at'] as String),
        venue: j['venue'] as String?,
        address: j['address'] as String?,
        sourceUrl: j['source_url'] as String,
      );
}

class GZPlaceDetail {
  final String placeId;
  final String name;
  final String category;
  final List<String> tags;
  final String tagline;
  final double latitude;
  final double longitude;
  final String whyGo;
  final List<String> goodFor;
  final GZWhyNow whyNow;
  final String priceBand;
  final double estimatedCost;
  final String openingHoursRaw;
  final String? etiquetteTag;
  final String? grade;
  final String provenance;
  final String? imageUrl;

  GZPlaceDetail({
    required this.placeId,
    required this.name,
    required this.category,
    required this.tags,
    required this.tagline,
    required this.latitude,
    required this.longitude,
    required this.whyGo,
    required this.goodFor,
    required this.whyNow,
    required this.priceBand,
    required this.estimatedCost,
    required this.openingHoursRaw,
    this.etiquetteTag,
    this.grade,
    required this.provenance,
    this.imageUrl,
  });

  factory GZPlaceDetail.fromJson(Map<String, dynamic> j) => GZPlaceDetail(
        placeId: j['place_id'] as String,
        name: j['name'] as String,
        category: j['category'] as String,
        tags: (j['tags'] as List).map((e) => e as String).toList(),
        tagline: j['tagline'] as String,
        latitude: (j['latitude'] as num).toDouble(),
        longitude: (j['longitude'] as num).toDouble(),
        whyGo: j['why_go'] as String,
        goodFor: (j['good_for'] as List).map((e) => e as String).toList(),
        whyNow: GZWhyNow.fromJson(j['why_now'] as Map<String, dynamic>),
        priceBand: j['price_band'] as String,
        estimatedCost: (j['estimated_cost'] as num).toDouble(),
        openingHoursRaw: j['opening_hours_raw'] as String,
        etiquetteTag: j['etiquette_tag'] as String?,
        grade: j['grade'] as String?,
        provenance: j['provenance'] as String,
        imageUrl: j['image_url'] as String?,
      );
}

class GZAddToJourneyResult {
  final String status; // "added" | "no_active_trip"
  final String? tripId;
  final String message;
  GZAddToJourneyResult({required this.status, this.tripId, required this.message});
  factory GZAddToJourneyResult.fromJson(Map<String, dynamic> j) => GZAddToJourneyResult(
        status: j['status'] as String,
        tripId: j['trip_id'] as String?,
        message: j['message'] as String,
      );
}

/// Thin wrapper around every /explore/* endpoint. Same style as
/// TripsApiClient: every GET here works with NO token (Explore is
/// browsable before sign-in, per the spec) — only [addToJourney] takes one.
class ExploreApiClient {
  final http.Client _http;
  ExploreApiClient({http.Client? client}) : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$gzApiBaseUrl$path');

  Future<dynamic> _get(String path, {String? token}) async {
    http.Response response;
    try {
      response = await _http.get(
        _uri(path),
        headers: {if (token != null) 'Authorization': 'Bearer $token'},
      ).timeout(const Duration(seconds: 20));
    } on Object {
      throw GZApiException("Can't reach the GroundZero server. Check your connection and try again.");
    }
    return _decode(response);
  }

  Future<dynamic> _post(String path, {String? token, Map<String, dynamic>? body}) async {
    http.Response response;
    try {
      response = await _http.post(
        _uri(path),
        headers: {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'},
        body: body == null ? null : jsonEncode(body),
      ).timeout(const Duration(seconds: 30));
    } on Object {
      throw GZApiException("Can't reach the GroundZero server. Check your connection and try again.");
    }
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    dynamic body;
    if (response.body.isNotEmpty) {
      try {
        body = jsonDecode(response.body);
      } on FormatException {
        body = null;
      }
    }
    if (response.statusCode >= 200 && response.statusCode < 300) return body;
    final detail = (body is Map) ? body['detail'] : null;
    final message = detail is String ? detail : 'Something went wrong. Please try again.';
    throw GZApiException(message, response.statusCode);
  }

  Future<List<GZMood>> moods() async {
    final j = await _get('/explore/moods') as List;
    return j.map((e) => GZMood.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<GZSituation?> situation() async {
    await GZLocation.ensure();
    final known = GZLocation.known;
    final lat = known ? GZLocation.lat : 12.9141;
    final lng = known ? GZLocation.lng : 74.8560;
    final j = await _get('/explore/situation?lat=$lat&lng=$lng&approx=${!known}${known && GZLocation.accuracy != null ? '&accuracy=${GZLocation.accuracy}' : ''}') as Map<String, dynamic>;
    return GZSituation.fromJson(j)..approx = !known;
  }

  Future<GZRightNow> rightNow({double? lat, double? lng}) async {
    final qp = _latLngQuery(lat, lng);
    final j = await _get('/explore/context$qp') as Map<String, dynamic>;
    return GZRightNow.fromJson(j);
  }

  Future<List<GZEvent>> happeningToday() async {
    final j = await _get('/explore/happening-today') as List;
    return j.map((e) => GZEvent.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<GZPlaceCard>> picks(String mood, {double? lat, double? lng, int limit = 12}) async {
    final qp = _latLngQuery(lat, lng, extra: 'mood=${Uri.encodeQueryComponent(mood)}&limit=$limit');
    final j = await _get('/explore/picks$qp') as List;
    return j.map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<GZPlaceCard>> beyondTheObvious({double? lat, double? lng, int limit = 10}) async {
    final qp = _latLngQuery(lat, lng, extra: 'limit=$limit');
    final j = await _get('/explore/beyond-the-obvious$qp') as List;
    return j.map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<GZExperienceCategory>> experienceCategories({double? lat, double? lng}) async {
    final qp = _latLngQuery(lat, lng);
    final j = await _get('/explore/experiences$qp') as List;
    return j.map((e) => GZExperienceCategory.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<GZPlaceCard>> experienceCategory(String slug, {double? lat, double? lng, int limit = 40}) async {
    final qp = _latLngQuery(lat, lng, extra: 'limit=$limit');
    final j = await _get('/explore/experiences/$slug$qp') as List;
    return j.map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<(List<GZPlaceCard>, List<String>)> search(
    String query, {
    double? lat,
    double? lng,
    String? category,
    bool openNow = false,
  }) async {
    final extra = [
      'q=${Uri.encodeQueryComponent(query)}',
      if (category != null) 'category=${Uri.encodeQueryComponent(category)}',
      if (openNow) 'open_now=true',
    ].join('&');
    final qp = _latLngQuery(lat, lng, extra: extra);
    final j = await _get('/explore/search$qp') as Map<String, dynamic>;
    final results = (j['results'] as List).map((e) => GZPlaceCard.fromJson(e as Map<String, dynamic>)).toList();
    final suggested = (j['suggested_searches'] as List).map((e) => e as String).toList();
    return (results, suggested);
  }

  Future<GZPlaceDetail> placeDetail(String placeId, {double? lat, double? lng}) async {
    final qp = _latLngQuery(lat, lng);
    final j = await _get('/explore/place/$placeId$qp') as Map<String, dynamic>;
    return GZPlaceDetail.fromJson(j);
  }

  Future<GZAddToJourneyResult> addToJourney(String token, String placeId, {String? tripId}) async {
    final j = await _post('/explore/add-to-journey', token: token, body: {
      'place_id': placeId,
      if (tripId != null) 'trip_id': tripId,
    }) as Map<String, dynamic>;
    return GZAddToJourneyResult.fromJson(j);
  }

  String _latLngQuery(double? lat, double? lng, {String? extra}) {
    lat ??= GZLocation.lat;
    lng ??= GZLocation.lng;
    final parts = <String>[
      if (lat != null) 'lat=$lat',
      if (lng != null) 'lng=$lng',
      if (extra != null && extra.isNotEmpty) extra,
    ];
    return parts.isEmpty ? '' : '?${parts.join('&')}';
  }

  void close() => _http.close();
}
