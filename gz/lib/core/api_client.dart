import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;

/// Base URL of the GroundZero FastAPI backend (see auth/routes.py for
/// the endpoints this calls). Override at build time with:
///   flutter run --dart-define=GZ_API_BASE_URL=https://your-host:8000
/// The defaults below only pick a sensible per-platform localhost so the
/// app is runnable out of the box against a backend running on the same
/// machine during development; they are not a real deployment target.
String get gzApiBaseUrl {
  const override = String.fromEnvironment('GZ_API_BASE_URL');
  if (override.isNotEmpty) return override;
  if (kIsWeb) {
    // Same host the page was opened from. `localhost` and `127.0.0.1` are
    // different browser origins, so a hard-coded `localhost` fails (CORS /
    // connection) whenever the app is opened via 127.0.0.1 or a LAN IP.
    final host = Uri.base.host;
    return 'http://${host.isEmpty ? 'localhost' : host}:8000';
  }
  if (defaultTargetPlatform == TargetPlatform.android) {
    // 10.0.2.2 is how the Android emulator reaches the host machine.
    return 'http://10.0.2.2:8000';
  }
  return 'http://localhost:8000';
}

class GZApiException implements Exception {
  final String message;
  final int? statusCode;
  GZApiException(this.message, [this.statusCode]);

  @override
  String toString() => message;
}

class GZUser {
  final String id;
  final String email;
  final String? displayName;

  GZUser({required this.id, required this.email, this.displayName});

  factory GZUser.fromJson(Map<String, dynamic> json) => GZUser(
        id: json['id'] as String,
        email: json['email'] as String,
        displayName: json['display_name'] as String?,
      );
}

class GZAuthResult {
  final String accessToken;
  final GZUser user;
  GZAuthResult({required this.accessToken, required this.user});

  factory GZAuthResult.fromJson(Map<String, dynamic> json) => GZAuthResult(
        accessToken: json['access_token'] as String,
        user: GZUser.fromJson(json['user'] as Map<String, dynamic>),
      );
}

/// Thin wrapper around the backend's /auth/* endpoints (auth/routes.py).
/// Every method throws [GZApiException] with a message ready to show
/// the person directly — no raw exception text ever reaches the UI.
class GZApiClient {
  final http.Client _http;
  GZApiClient({http.Client? client}) : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$gzApiBaseUrl$path');

  Future<GZAuthResult> register({
    required String email,
    required String password,
    String? displayName,
    bool acceptedTerms = false,
    bool adultConfirmed = false,
  }) async {
    final res = await _post('/auth/register', {
      'email': email,
      'password': password,
      'accepted_terms': acceptedTerms,
      'adult_confirmed': adultConfirmed,
      if (displayName != null && displayName.trim().isNotEmpty) 'display_name': displayName.trim(),
    });
    return GZAuthResult.fromJson(res);
  }

  Future<GZAuthResult> login({required String email, required String password}) async {
    final res = await _post('/auth/login', {'email': email, 'password': password});
    return GZAuthResult.fromJson(res);
  }

  /// Quick reachability probe used by the sign-in screen's status pill.
  /// True only when the backend answers GET /health with 200.
  Future<bool> health() async {
    try {
      final res = await _http.get(_uri('/health')).timeout(const Duration(seconds: 6));
      return res.statusCode == 200;
    } on Object {
      return false;
    }
  }

  Future<GZUser> me(String accessToken) async {
    final res = await _get('/auth/me', accessToken);
    return GZUser.fromJson(res);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    http.Response response;
    try {
      response = await _http
          .post(_uri(path), headers: const {'Content-Type': 'application/json'}, body: jsonEncode(body))
          .timeout(const Duration(seconds: 15));
    } on Object catch (error) {
      // statusCode stays null: the caller treats that as "no connection".
      throw GZApiException('Cannot connect to GroundZero at $gzApiBaseUrl (${error.runtimeType}).');
    }
    return _decode(response);
  }

  Future<Map<String, dynamic>> _get(String path, String accessToken) async {
    http.Response response;
    try {
      response = await _http
          .get(_uri(path), headers: {'Authorization': 'Bearer $accessToken'})
          .timeout(const Duration(seconds: 15));
    } on Object catch (error) {
      // statusCode stays null: the caller treats that as "no connection".
      throw GZApiException('Cannot connect to GroundZero at $gzApiBaseUrl (${error.runtimeType}).');
    }
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    Map<String, dynamic> body = const {};
    if (response.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) body = decoded;
      } on FormatException {
        // Fall through: body stays empty, status code alone drives the error below.
      }
    }
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body;
    }
    final detail = body['detail'];
    final message = detail is String ? detail : 'Something went wrong. Please try again.';
    throw GZApiException(message, response.statusCode);
  }

  void close() => _http.close();
}
