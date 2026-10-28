import 'package:groundzero/core/api_client.dart';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// Chunk 4 — My Trips / Journey Story / Contributions / Notifications.
/// Same style as TripsApiClient/ExploreApiClient: same base URL, same
/// exception mapping. Every call here needs a bearer token.

class GZTripSummary {
  final String tripId;
  final String status;
  final int placeCount;
  final int visitedCount;
  final String? nextPlaceName;
  final String? nextPlaceId;
  final String? coverPlaceName;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final DateTime? scheduledStartAt;
  final int? overallRating;
  final double budgetTotal;
  final double budgetRemaining;

  GZTripSummary({
    required this.tripId,
    required this.status,
    required this.placeCount,
    required this.visitedCount,
    this.nextPlaceName,
    this.nextPlaceId,
    this.coverPlaceName,
    this.startedAt,
    this.endedAt,
    this.scheduledStartAt,
    this.overallRating,
    required this.budgetTotal,
    required this.budgetRemaining,
  });

  factory GZTripSummary.fromJson(Map<String, dynamic> j) => GZTripSummary(
        tripId: j['trip_id'] as String,
        status: j['status'] as String,
        placeCount: j['place_count'] as int,
        visitedCount: j['visited_count'] as int,
        nextPlaceName: j['next_place_name'] as String?,
        nextPlaceId: j['next_place_id'] as String?,
        coverPlaceName: j['cover_place_name'] as String?,
        startedAt: j['started_at'] == null ? null : DateTime.parse(j['started_at'] as String),
        endedAt: j['ended_at'] == null ? null : DateTime.parse(j['ended_at'] as String),
        scheduledStartAt: j['scheduled_start_at'] == null ? null : DateTime.parse(j['scheduled_start_at'] as String),
        overallRating: j['overall_rating'] as int?,
        budgetTotal: (j['budget_total'] as num).toDouble(),
        budgetRemaining: (j['budget_remaining'] as num).toDouble(),
      );
}

class GZMyTrips {
  final List<GZTripSummary> upcoming;
  final List<GZTripSummary> completed;
  GZMyTrips({required this.upcoming, required this.completed});

  factory GZMyTrips.fromJson(Map<String, dynamic> j) => GZMyTrips(
        upcoming: (j['upcoming'] as List).map((e) => GZTripSummary.fromJson(e as Map<String, dynamic>)).toList(),
        completed: (j['completed'] as List).map((e) => GZTripSummary.fromJson(e as Map<String, dynamic>)).toList(),
      );
}

class GZTripStory {
  final String tripId;
  final String title;
  final int placeCount;
  final List<String> visitedPlaceNames;
  final double distanceKm;
  final int? durationMinutes;
  final int photoCount;
  final int videoCount;
  final List<String> highlights;
  final String? coverPlaceName;

  GZTripStory({
    required this.tripId,
    required this.title,
    required this.placeCount,
    required this.visitedPlaceNames,
    required this.distanceKm,
    this.durationMinutes,
    required this.photoCount,
    required this.videoCount,
    required this.highlights,
    this.coverPlaceName,
  });

  factory GZTripStory.fromJson(Map<String, dynamic> j) => GZTripStory(
        tripId: j['trip_id'] as String,
        title: j['title'] as String,
        placeCount: j['place_count'] as int,
        visitedPlaceNames: (j['visited_place_names'] as List).cast<String>(),
        distanceKm: (j['distance_km'] as num).toDouble(),
        durationMinutes: j['duration_minutes'] as int?,
        photoCount: j['photo_count'] as int,
        videoCount: j['video_count'] as int,
        highlights: (j['highlights'] as List).cast<String>(),
        coverPlaceName: j['cover_place_name'] as String?,
      );
}

class GZContribution {
  final String contributionId;
  // BUG FIX (4th audit response, Oct 2026): the backend's ContributionOut
  // schema only sets submission_id for kind=="add_place" -- the other
  // four kinds (suggest_update, local_tip, report_incorrect, add_media)
  // genuinely return submission_id: null, since they never go through
  // the layer0 CommunitySubmission pipeline. `j['submission_id'] as
  // String` used to throw a type-cast error (null is not a String) the
  // moment any of those four showed up in the list -- this screen would
  // have crashed as soon as the backend's other 4 contribution kinds
  // (shipped in the previous pass) were actually used. Made nullable,
  // and `kind`/`placeId` added so the UI can tell the five kinds apart
  // without guessing from submissionId's presence.
  final String? submissionId;
  final String? placeId;
  final String kind; // add_place | suggest_update | local_tip | report_incorrect | add_media
  final String placeName;
  final String status; // pending | approved | rejected
  final DateTime submittedAt;
  final DateTime? reviewedAt;
  final String impactMessage;
  final int? explorerPoints;

  GZContribution({
    required this.contributionId,
    this.submissionId,
    this.placeId,
    required this.kind,
    required this.placeName,
    required this.status,
    required this.submittedAt,
    this.reviewedAt,
    required this.impactMessage,
    this.explorerPoints,
  });

  factory GZContribution.fromJson(Map<String, dynamic> j) => GZContribution(
        contributionId: j['contribution_id'] as String,
        submissionId: j['submission_id'] as String?,
        placeId: j['place_id'] as String?,
        kind: j['kind'] as String? ?? 'add_place',
        placeName: j['place_name'] as String,
        status: j['status'] as String,
        submittedAt: DateTime.parse(j['submitted_at'] as String),
        reviewedAt: j['reviewed_at'] == null ? null : DateTime.parse(j['reviewed_at'] as String),
        impactMessage: j['impact_message'] as String,
        explorerPoints: j['explorer_points'] as int?,
      );
}

class GZMyContributions {
  final List<GZContribution> contributions;
  final int totalApproved;
  final String explorerLevel;
  GZMyContributions({required this.contributions, required this.totalApproved, required this.explorerLevel});

  factory GZMyContributions.fromJson(Map<String, dynamic> j) => GZMyContributions(
        contributions:
            (j['contributions'] as List).map((e) => GZContribution.fromJson(e as Map<String, dynamic>)).toList(),
        totalApproved: j['total_approved'] as int,
        explorerLevel: j['explorer_level'] as String,
      );
}

class GZNotification {
  final String id;
  final String category; // NOW | YOUR_JOURNEY | AROUND_YOU | GROUNDZERO
  final String headline;
  final String body;
  GZNotification({required this.id, required this.category, required this.headline, required this.body});

  factory GZNotification.fromJson(Map<String, dynamic> j) => GZNotification(
        id: j['id'] as String,
        category: j['category'] as String,
        headline: j['headline'] as String,
        body: j['body'] as String,
      );
}

class PersonalApiClient {
  final http.Client _http;
  PersonalApiClient({http.Client? client}) : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$gzApiBaseUrl$path');

  Map<String, String> _headers(String token) => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  Future<dynamic> _send(String method, String path, String token, {Map<String, dynamic>? body}) async {
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
              .timeout(const Duration(seconds: 30));
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

  Future<GZMyTrips> myTrips(String token) async {
    final j = await _send('GET', '/trips', token) as Map<String, dynamic>;
    return GZMyTrips.fromJson(j);
  }

  Future<GZTripStory> tripStory(String token, String tripId) async {
    final j = await _send('GET', '/trips/$tripId/story', token) as Map<String, dynamic>;
    return GZTripStory.fromJson(j);
  }

  Future<GZMyContributions> myContributions(String token) async {
    final j = await _send('GET', '/personal/contributions', token) as Map<String, dynamic>;
    return GZMyContributions.fromJson(j);
  }

  Future<GZContribution> addPlace(
    String token, {
    required String name,
    required String category,
    required double latitude,
    required double longitude,
    double estimatedCost = 0.0,
    String priceBand = 'budget',
    String? description,
    String? note,
    String? mediaUrl,
  }) async {
    final j = await _send('POST', '/personal/contributions', token, body: {
      'name': name,
      'category': category,
      'latitude': latitude,
      'longitude': longitude,
      'estimated_cost': estimatedCost,
      'price_band': priceBand,
      'description': description,
      'note': note,
      if (mediaUrl != null) 'media_url': mediaUrl,
    }) as Map<String, dynamic>;
    return GZContribution.fromJson(j);
  }

  Future<GZContribution> suggestUpdate(
    String token, {
    required String placeId,
    required String field,
    String? currentValue,
    required String suggestedValue,
    String? reason,
  }) async {
    final j = await _send('POST', '/personal/contributions/suggest-update', token, body: {
      'place_id': placeId,
      'field': field,
      'current_value': currentValue,
      'suggested_value': suggestedValue,
      'reason': reason,
    }) as Map<String, dynamic>;
    return GZContribution.fromJson(j);
  }

  Future<GZContribution> localTip(
    String token, {
    required String placeId,
    required String tip,
    String? bestTime,
    String? context,
  }) async {
    final j = await _send('POST', '/personal/contributions/local-tip', token, body: {
      'place_id': placeId,
      'tip': tip,
      'best_time': bestTime,
      'context': context,
    }) as Map<String, dynamic>;
    return GZContribution.fromJson(j);
  }

  Future<GZContribution> reportIncorrect(
    String token, {
    required String placeId,
    required String issueType,
    required String description,
    String? evidence,
  }) async {
    final j = await _send('POST', '/personal/contributions/report-incorrect', token, body: {
      'place_id': placeId,
      'issue_type': issueType,
      'description': description,
      'evidence': evidence,
    }) as Map<String, dynamic>;
    return GZContribution.fromJson(j);
  }

  Future<GZContribution> addMedia(
    String token, {
    required String placeId,
    required String mediaUrl,
    String? caption,
    String? source,
  }) async {
    final j = await _send('POST', '/personal/contributions/add-media', token, body: {
      'place_id': placeId,
      'media_url': mediaUrl,
      'caption': caption,
      'source': source,
    }) as Map<String, dynamic>;
    return GZContribution.fromJson(j);
  }

  Future<List<GZNotification>> notifications(String token) async {
    final j = await _send('GET', '/personal/notifications', token) as Map<String, dynamic>;
    return (j['notifications'] as List).map((e) => GZNotification.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> deleteAccount(String token) async {
    await _send('DELETE', '/auth/me', token);
  }

  void close() => _http.close();
}
