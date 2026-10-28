import 'package:groundzero/core/api_client.dart';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api_client.dart';
import 'gz_location.dart';

/// Talk to Guide — POST /guide/chat. Answers come from GroundZero's own
/// place records (and Groq when the backend has a key); `mode` says which.
class GZGuidePlace {
  final String? placeId;
  final String name;
  final String category;
  GZGuidePlace({this.placeId, required this.name, required this.category});

  factory GZGuidePlace.fromJson(Map<String, dynamic> j) =>
      GZGuidePlace(placeId: j['place_id'] as String?, name: j['name'] as String, category: j['category'] as String);
}

class GZGuideReply {
  final String reply;
  final String mode; // "llm" | "extractive"
  final List<GZGuidePlace> places;
  final String? note;
  GZGuideReply({required this.reply, required this.mode, required this.places, this.note});

  factory GZGuideReply.fromJson(Map<String, dynamic> j) => GZGuideReply(
        reply: j['reply'] as String,
        mode: j['mode'] as String,
        places: (j['places'] as List).map((e) => GZGuidePlace.fromJson(e as Map<String, dynamic>)).toList(),
        note: j['note'] as String?,
      );
}

class GuideApiClient {
  final http.Client _http;
  GuideApiClient({http.Client? client}) : _http = client ?? http.Client();

  Future<GZGuideReply> chat(
    String token, {
    required String message,
    required String language,
    required List<({String role, String content})> history,
    bool spoken = false,
  }) async {
    http.Response response;
    try {
      response = await _http
          .post(
            Uri.parse('$gzApiBaseUrl/guide/chat'),
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
            body: jsonEncode({
              'message': message,
              'language': language,
              'spoken': spoken,
              if (GZLocation.known) 'lat': GZLocation.lat,
              if (GZLocation.known) 'lng': GZLocation.lng,
              'history': [for (final h in history) {'role': h.role, 'content': h.content}],
            }),
          )
          .timeout(const Duration(seconds: 45));
    } on Object {
      throw GZApiException("Can't reach the GroundZero server. Check your connection and try again.");
    }
    dynamic body;
    try {
      body = jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      body = null;
    }
    if (response.statusCode >= 200 && response.statusCode < 300 && body is Map<String, dynamic>) {
      return GZGuideReply.fromJson(body);
    }
    final detail = (body is Map) ? body['detail'] : null;
    throw GZApiException(detail is String ? detail : 'The guide could not answer just now. Please try again.', response.statusCode);
  }

  /// Natural human voice for a reply (MP3 bytes), or null if unavailable.
  Future<Uint8List?> speak(String token, String text, String language) async {
    try {
      final r = await _http
          .post(
            Uri.parse('$gzApiBaseUrl/guide/speak'),
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
            body: jsonEncode({'text': text, 'language': language}),
          )
          .timeout(const Duration(seconds: 40));
      if (r.statusCode == 200 && r.bodyBytes.length > 500) return r.bodyBytes;
    } on Object {/* fall back to the browser voice */}
    return null;
  }

  /// Verify and save a Groq key from inside the app (local development).
  Future<(bool, String)> setKey(String token, String key) async {
    try {
      final r = await _http
          .post(
            Uri.parse('$gzApiBaseUrl/guide/key'),
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
            body: jsonEncode({'key': key.trim()}),
          )
          .timeout(const Duration(seconds: 30));
      final j = jsonDecode(utf8.decode(r.bodyBytes));
      if (j is Map) return (j['ok'] == true, '${j['detail'] ?? ''}');
    } on Object {/* fall through */}
    return (false, "Couldn't reach the server.");
  }

  void close() => _http.close();
}
