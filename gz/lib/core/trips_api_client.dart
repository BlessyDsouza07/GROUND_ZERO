import 'package:groundzero/core/api_client.dart';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// One itinerary stop, mirroring trips/schemas.py's ItineraryItemOut.
class GZTripPlace {
  final String tripPlaceId;
  final String placeId;
  final String placeName;
  final String role;
  final int orderIndex;
  final DateTime? scheduledTime;
  final String? travelMode;
  final int? travelTimeMinutes;
  final double estimatedCost;
  final String? reasonSelected;
  final double? latitude;
  final double? longitude;
  final bool isTouristAdded;
  final String status; // pending | visited | skipped

  GZTripPlace({
    required this.tripPlaceId,
    required this.placeId,
    required this.placeName,
    required this.role,
    required this.orderIndex,
    this.scheduledTime,
    this.travelMode,
    this.travelTimeMinutes,
    required this.estimatedCost,
    this.reasonSelected,
    this.latitude,
    this.longitude,
    required this.isTouristAdded,
    required this.status,
  });

  factory GZTripPlace.fromJson(Map<String, dynamic> j) => GZTripPlace(
        tripPlaceId: j['trip_place_id'] as String,
        placeId: j['place_id'] as String,
        placeName: j['place_name'] as String,
        role: j['role'] as String,
        orderIndex: j['order_index'] as int,
        scheduledTime: j['scheduled_time'] == null ? null : DateTime.parse(j['scheduled_time'] as String),
        travelMode: j['travel_mode'] as String?,
        travelTimeMinutes: j['travel_time_minutes'] as int?,
        estimatedCost: (j['estimated_cost'] as num).toDouble(),
        reasonSelected: j['reason_selected'] as String?,
        latitude: (j['latitude'] as num?)?.toDouble(),
        longitude: (j['longitude'] as num?)?.toDouble(),
        isTouristAdded: j['is_tourist_added'] as bool,
        status: j['status'] as String,
      );
}

/// A Trip, mirroring trips/schemas.py's TripOut.
class GZTrip {
  final String tripId;
  final String status; // draft | scheduled | active | paused | ended_early | completed
  final String profileId;
  final double budgetTotal;
  final double budgetRemaining;
  final String energyBand;
  final bool notificationsEnabled;
  final bool voiceGuideEnabled;
  final double? geofenceRadiusKm;
  final double? originLatitude;
  final double? originLongitude;
  final DateTime? scheduledStartAt;
  final DateTime? startedAt;
  final String? layer3SessionId;
  final List<GZTripPlace> places;

  GZTrip({
    required this.tripId,
    required this.status,
    required this.profileId,
    required this.budgetTotal,
    required this.budgetRemaining,
    required this.energyBand,
    required this.notificationsEnabled,
    required this.voiceGuideEnabled,
    this.geofenceRadiusKm,
    this.originLatitude,
    this.originLongitude,
    this.scheduledStartAt,
    this.startedAt,
    this.layer3SessionId,
    required this.places,
  });

  factory GZTrip.fromJson(Map<String, dynamic> j) => GZTrip(
        tripId: j['trip_id'] as String,
        status: j['status'] as String,
        profileId: j['profile_id'] as String,
        budgetTotal: (j['budget_total'] as num).toDouble(),
        budgetRemaining: (j['budget_remaining'] as num).toDouble(),
        energyBand: j['energy_band'] as String,
        notificationsEnabled: j['notifications_enabled'] as bool,
        voiceGuideEnabled: j['voice_guide_enabled'] as bool,
        geofenceRadiusKm: (j['geofence_radius_km'] as num?)?.toDouble(),
        originLatitude: (j['origin_latitude'] as num?)?.toDouble(),
        originLongitude: (j['origin_longitude'] as num?)?.toDouble(),
        scheduledStartAt: j['scheduled_start_at'] == null ? null : DateTime.parse(j['scheduled_start_at'] as String),
        startedAt: j['started_at'] == null ? null : DateTime.parse(j['started_at'] as String),
        layer3SessionId: j['layer3_session_id'] as String?,
        places: (j['places'] as List).map((p) => GZTripPlace.fromJson(p as Map<String, dynamic>)).toList(),
      );
}

class GZSearchPlace {
  final String placeId;
  final String name;
  final String category;
  final double latitude;
  final double longitude;
  final double estimatedCost;

  GZSearchPlace({
    required this.placeId,
    required this.name,
    required this.category,
    required this.latitude,
    required this.longitude,
    required this.estimatedCost,
  });

  factory GZSearchPlace.fromJson(Map<String, dynamic> j) => GZSearchPlace(
        placeId: j['place_id'] as String,
        name: j['name'] as String,
        category: j['category'] as String,
        latitude: (j['latitude'] as num).toDouble(),
        longitude: (j['longitude'] as num).toDouble(),
        estimatedCost: (j['estimated_cost'] as num).toDouble(),
      );
}

class GZSurveyState {
  final String sessionId;
  final String? nextStep; // null once done
  final double progressFraction;
  final bool done;

  GZSurveyState({required this.sessionId, this.nextStep, required this.progressFraction, required this.done});

  factory GZSurveyState.fromJson(Map<String, dynamic> j) => GZSurveyState(
        sessionId: j['session_id'] as String,
        nextStep: j['next_step'] as String?,
        progressFraction: (j['progress_fraction'] as num).toDouble(),
        done: j['done'] as bool,
      );
}

class GZJournalEntry {
  final String id;
  final String? tripPlaceId;
  final String mediaType;
  final String mediaUrl;
  final String? caption;
  final DateTime createdAt;

  GZJournalEntry({
    required this.id,
    this.tripPlaceId,
    required this.mediaType,
    required this.mediaUrl,
    this.caption,
    required this.createdAt,
  });

  factory GZJournalEntry.fromJson(Map<String, dynamic> j) => GZJournalEntry(
        id: j['id'] as String,
        tripPlaceId: j['trip_place_id'] as String?,
        mediaType: j['media_type'] as String,
        mediaUrl: j['media_url'] as String,
        caption: j['caption'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}

/// Every non-price-of-admission field the checkout endpoint hands back,
/// beyond the bare {"status":"ok"} (see trips/routes.py's checkout()).
class GZCheckoutResult {
  final double budgetRemaining;
  final double remainingItineraryCost;
  final bool budgetCoversRestOfTrip;
  final bool suggestRestStop;

  GZCheckoutResult({
    required this.budgetRemaining,
    required this.remainingItineraryCost,
    required this.budgetCoversRestOfTrip,
    required this.suggestRestStop,
  });

  factory GZCheckoutResult.fromJson(Map<String, dynamic> j) => GZCheckoutResult(
        budgetRemaining: (j['budget_remaining'] as num).toDouble(),
        remainingItineraryCost: (j['remaining_itinerary_cost'] as num).toDouble(),
        budgetCoversRestOfTrip: j['budget_covers_rest_of_trip'] as bool,
        suggestRestStop: j['suggest_rest_stop'] as bool,
      );
}

/// Thin wrapper around every /trips/* endpoint (trips/routes.py). Mirrors
/// GZApiClient's style exactly (same base URL, same exception mapping) —
/// kept as its own file rather than folded into api_client.dart because
/// almost every call here needs a bearer token and a couple need
/// PUT/DELETE, which the auth-only client never needed.
class TripsApiClient {
  final http.Client _http;
  TripsApiClient({http.Client? client}) : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$gzApiBaseUrl$path');

  Map<String, String> _headers(String? token) => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<dynamic> _send(String method, String path, {String? token, Map<String, dynamic>? body, int postTimeoutS = 30}) async {
    http.Response response;
    try {
      final uri = _uri(path);
      final headers = _headers(token);
      switch (method) {
        case 'GET':
          response = await _http.get(uri, headers: headers).timeout(const Duration(seconds: 20));
          break;
        case 'POST':
          response = await _http
              .post(uri, headers: headers, body: body == null ? null : jsonEncode(body))
              .timeout(Duration(seconds: postTimeoutS));
          break;
        case 'PUT':
          response = await _http
              .put(uri, headers: headers, body: body == null ? null : jsonEncode(body))
              .timeout(const Duration(seconds: 20));
          break;
        case 'DELETE':
          response = await _http.delete(uri, headers: headers).timeout(const Duration(seconds: 20));
          break;
        default:
          throw StateError('Unsupported method $method');
      }
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
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body ?? const {};
    }
    final detail = (body is Map) ? body['detail'] : null;
    final message = detail is String ? detail : 'Something went wrong. Please try again.';
    throw GZApiException(message, response.statusCode);
  }

  // -- survey --------------------------------------------------------------
  // BUG FIX (6th audit response, Oct 2026): start/answer never took a
  // token and so never sent Authorization at all, even though the
  // backend's own 3rd-audit fix (trips/routes.py) made all three survey
  // endpoints require auth. Confirmed live: POST /trips/survey/start
  // with no Authorization header returns 401. Only finalizeSurvey()
  // was passing a token. Now threaded through from SurveyScreen's
  // AuthController the same way finalizeSurvey() already does.
  Future<GZSurveyState> startSurvey(String token) async {
    final j = await _send('POST', '/trips/survey/start', token: token) as Map<String, dynamic>;
    return GZSurveyState(sessionId: j['session_id'] as String, nextStep: j['next_step'] as String, progressFraction: 0, done: false);
  }

  Future<GZSurveyState> answerSurvey(String sessionId, String step, dynamic value, String token) async {
    final j = await _send('POST', '/trips/survey/$sessionId/answer', token: token, body: {'step': step, 'value': value}) as Map<String, dynamic>;
    return GZSurveyState.fromJson(j);
  }

  Future<String> finalizeSurvey(String sessionId, String token) async {
    final j = await _send('POST', '/trips/survey/$sessionId/finalize', token: token) as Map<String, dynamic>;
    return j['profile_id'] as String;
  }

  // -- itinerary -------------------------------------------------------------
  Future<GZTrip> generateTrip({
    required String token,
    required String profileId,
    required double startLatitude,
    required double startLongitude,
    DateTime? startTime,
    List<String> pinnedPlaceIds = const [],
  }) async {
    final j = await _send('POST', '/trips/generate', token: token, postTimeoutS: 150, body: {
      'profile_id': profileId,
      'start_latitude': startLatitude,
      'start_longitude': startLongitude,
      if (startTime != null) 'start_time': startTime.toUtc().toIso8601String(),
      'pinned_place_ids': pinnedPlaceIds,
    }) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  /// If the generate call outlived the browser's patience the trip is still
  /// saved server-side — fetch the newest draft instead of failing.
  Future<GZTrip?> latestDraft(String token) async {
    try {
      final j = await _send('GET', '/trips', token: token) as Map<String, dynamic>;
      final up = (j['upcoming'] as List? ?? const []).cast<Map<String, dynamic>>();
      final drafts = up.where((t) => t['status'] == 'draft').toList()
        ..sort((a, b) => ('${b['scheduled_start_at']}').compareTo('${a['scheduled_start_at']}'));
      if (drafts.isEmpty) return null;
      return await getTrip(token, drafts.first['trip_id'] as String);
    } on Object {
      return null;
    }
  }

  Future<GZTrip> getTrip(String token, String tripId) async {
    final j = await _send('GET', '/trips/$tripId', token: token) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<List<GZSearchPlace>> searchPlaces(String token, String query) async {
    final j = await _send('GET', '/trips/places/search?query=${Uri.encodeQueryComponent(query)}', token: token) as List;
    return j.map((e) => GZSearchPlace.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<GZTripPlace> addPlace(
    String token, String tripId, {
    String? placeId, String? name, double? latitude, double? longitude, String? category, String? note, double estimatedCost = 0,
  }) async {
    final j = await _send('POST', '/trips/$tripId/places', token: token, body: {
      if (placeId != null) 'place_id': placeId,
      if (name != null) 'name': name,
      if (latitude != null) 'latitude': latitude,
      if (longitude != null) 'longitude': longitude,
      if (category != null) 'category': category,
      if (note != null) 'note': note,
      'estimated_cost': estimatedCost,
    }) as Map<String, dynamic>;
    return GZTripPlace.fromJson(j);
  }

  Future<void> removePlace(String token, String tripId, String tripPlaceId) async {
    await _send('DELETE', '/trips/$tripId/places/$tripPlaceId', token: token);
  }

  Future<GZTrip> reorderPlaces(String token, String tripId, List<String> orderedTripPlaceIds) async {
    final j = await _send('PUT', '/trips/$tripId/reorder', token: token, body: {'trip_place_ids': orderedTripPlaceIds}) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<void> rateTrip(String token, String tripId, int rating, String? feedback) async {
    await _send('POST', '/trips/$tripId/rate', token: token, body: {'rating': rating, if (feedback != null) 'feedback': feedback});
  }

  Future<GZTrip> confirmTrip(
    String token, String tripId, {
    required bool notificationsEnabled,
    required bool voiceGuideEnabled,
    required bool startNow,
    DateTime? scheduledStartAt,
    String? accommodationPlaceId,
    String? accommodationName,
  }) async {
    final j = await _send('POST', '/trips/$tripId/confirm', token: token, body: {
      'notifications_enabled': notificationsEnabled,
      'voice_guide_enabled': voiceGuideEnabled,
      'start_now': startNow,
      if (scheduledStartAt != null) 'scheduled_start_at': scheduledStartAt.toUtc().toIso8601String(),
      if (accommodationPlaceId != null) 'accommodation_place_id': accommodationPlaceId,
      if (accommodationName != null) 'accommodation_name': accommodationName,
    }) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  // -- live trip ------------------------------------------------------------
  Future<GZTripPlace> arrive(String token, String tripId, String tripPlaceId, {bool? listenedToGuide}) async {
    final j = await _send('POST', '/trips/$tripId/arrive', token: token, body: {
      'trip_place_id': tripPlaceId,
      if (listenedToGuide != null) 'listened_to_guide': listenedToGuide,
    }) as Map<String, dynamic>;
    return GZTripPlace.fromJson(j);
  }

  Future<GZCheckoutResult> checkout(
    String token, String tripId, String tripPlaceId, {
    required double amountSpent, required String energyAfter, required int rating, String? experienceNote,
  }) async {
    final j = await _send('POST', '/trips/$tripId/checkout', token: token, body: {
      'trip_place_id': tripPlaceId,
      'amount_spent': amountSpent,
      'energy_after': energyAfter,
      'rating': rating,
      if (experienceNote != null) 'experience_note': experienceNote,
    }) as Map<String, dynamic>;
    return GZCheckoutResult.fromJson(j);
  }

  Future<GZTripPlace> skipPlace(String token, String tripId, String tripPlaceId, {String? reason}) async {
    final j = await _send('POST', '/trips/$tripId/skip', token: token, body: {
      'trip_place_id': tripPlaceId,
      if (reason != null) 'reason': reason,
    }) as Map<String, dynamic>;
    return GZTripPlace.fromJson(j);
  }

  Future<GZTrip> topUpBudget(String token, String tripId, double additionalAmount) async {
    final j = await _send('POST', '/trips/$tripId/budget/top-up', token: token, body: {'additional_amount': additionalAmount}) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<GZTrip> pauseTrip(String token, String tripId) async {
    final j = await _send('POST', '/trips/$tripId/pause', token: token) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<GZTrip> resumeTrip(String token, String tripId, {required bool upgrade, double? latitude, double? longitude}) async {
    final j = await _send('POST', '/trips/$tripId/resume', token: token, body: {
      'upgrade': upgrade,
      if (latitude != null) 'latitude': latitude,
      if (longitude != null) 'longitude': longitude,
    }) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<GZTrip> exitTrip(String token, String tripId, String reason) async {
    final j = await _send('POST', '/trips/$tripId/exit', token: token, body: {'reason': reason}) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  Future<GZTrip> completeTrip(String token, String tripId) async {
    final j = await _send('POST', '/trips/$tripId/complete', token: token) as Map<String, dynamic>;
    return GZTrip.fromJson(j);
  }

  // -- journal ----------------------------------------------------------------
  Future<GZJournalEntry> addJournalEntry(
    String token, String tripId, {String? tripPlaceId, required String mediaType, required String mediaUrl, String? caption,
  }) async {
    final j = await _send('POST', '/trips/$tripId/journal', token: token, body: {
      if (tripPlaceId != null) 'trip_place_id': tripPlaceId,
      'media_type': mediaType,
      'media_url': mediaUrl,
      if (caption != null) 'caption': caption,
    }) as Map<String, dynamic>;
    return GZJournalEntry.fromJson(j);
  }

  Future<List<GZJournalEntry>> journalTimeline(String token, String tripId) async {
    final j = await _send('GET', '/trips/$tripId/journal', token: token) as Map<String, dynamic>;
    return (j['entries'] as List).map((e) => GZJournalEntry.fromJson(e as Map<String, dynamic>)).toList();
  }

  void close() => _http.close();
}
