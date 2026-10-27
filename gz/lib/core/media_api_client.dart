import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// Photo upload (POST /media/upload) and the shareable story video
/// (POST /trips/{id}/story-video).
class MediaApiClient {
  final http.Client _http;
  MediaApiClient({http.Client? client}) : _http = client ?? http.Client();

  Map<String, String> _h(String token) => {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'};

  Future<String> uploadPhoto(String token, Uint8List bytes) async {
    http.Response r;
    try {
      r = await _http
          .post(Uri.parse('$gzApiBaseUrl/media/upload'), headers: _h(token), body: jsonEncode({'data_base64': base64Encode(bytes)}))
          .timeout(const Duration(seconds: 60));
    } on Object {
      throw GZApiException("Couldn't upload the photo. Check your connection and try again.");
    }
    final j = _json(r);
    if (r.statusCode >= 200 && r.statusCode < 300 && j is Map && j['url'] is String) return j['url'] as String;
    throw GZApiException(_detail(j, 'Couldn\'t upload the photo.'), r.statusCode);
  }

  /// Renders the day's photos into one vertical video and returns its URL.
  Future<String> makeStoryVideo(String token, String tripId) async {
    http.Response r;
    try {
      r = await _http
          .post(Uri.parse('$gzApiBaseUrl/trips/$tripId/story-video'), headers: _h(token))
          .timeout(const Duration(seconds: 180));
    } on Object {
      throw GZApiException('Making the video took too long or lost connection. Please try again.');
    }
    final j = _json(r);
    if (r.statusCode >= 200 && r.statusCode < 300 && j is Map && j['url'] is String) return j['url'] as String;
    throw GZApiException(_detail(j, 'Couldn\'t make the video.'), r.statusCode);
  }

  dynamic _json(http.Response r) {
    try {
      return jsonDecode(utf8.decode(r.bodyBytes));
    } on Object {
      return null;
    }
  }

  String _detail(dynamic j, String fallback) => (j is Map && j['detail'] is String) ? j['detail'] as String : fallback;

  void close() => _http.close();
}
