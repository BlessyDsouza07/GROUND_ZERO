
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// GroundZero production API URL.
///
/// You can override this at build time with:
/// --dart-define=GZ_API_BASE_URL=https://your-backend.example.com
String get gzApiBaseUrl {
  const override = String.fromEnvironment('GZ_API_BASE_URL');

  final url = override.isNotEmpty
      ? override
      : 'https://ground-zero-iwcw.onrender.com';

  return url.replaceFirst(RegExp(r'/+$'), '');
}

/// Exception returned by GroundZero API operations.
class GZApiException implements Exception {
  final String message;
  final int? statusCode;

  GZApiException(this.message, [this.statusCode]);

  bool get isConnectionError => statusCode == null;

  @override
  String toString() => message;
}

/// Authenticated GroundZero user.
class GZUser {
  final String id;
  final String email;
  final String? displayName;

  const GZUser({
    required this.id,
    required this.email,
    this.displayName,
  });

  factory GZUser.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'] ?? json['user_id'] ?? json['sub'];

    if (rawId == null || json['email'] == null) {
      throw const FormatException(
        'The server returned an invalid user response.',
      );
    }

    return GZUser(
      id: rawId.toString(),
      email: json['email'].toString(),
      displayName: json['display_name']?.toString() ??
          json['displayName']?.toString() ??
          json['name']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        if (displayName != null) 'display_name': displayName,
      };
}

/// Result returned after registration or login.
class GZAuthResult {
  final String accessToken;
  final GZUser user;

  const GZAuthResult({
    required this.accessToken,
    required this.user,
  });

  factory GZAuthResult.fromJson(Map<String, dynamic> json) {
    // Support common FastAPI authentication response formats.
    final token = json['access_token'] ??
        json['token'];

    final rawUser = json['user'] ?? json['profile'];

    if (token == null || token.toString().isEmpty) {
      throw const FormatException(
        'The server response did not contain an access token.',
      );
    }

    if (rawUser is! Map<String, dynamic>) {
      throw const FormatException(
        'The server response did not contain valid user details.',
      );
    }

    return GZAuthResult(
      accessToken: token.toString(),
      user: GZUser.fromJson(rawUser),
    );
  }
}

/// HTTP client for the GroundZero FastAPI backend.
///
/// Routes used:
/// GET  /health
/// POST /auth/register
/// POST /auth/login
/// GET  /auth/me
class GZApiClient {
  final http.Client _http;
  final Duration requestTimeout;

  GZApiClient({
    http.Client? client,
    this.requestTimeout = const Duration(seconds: 20),
  }) : _http = client ?? http.Client();

  Uri _uri(String path) {
    return Uri.parse('$gzApiBaseUrl$path');
  }

  Map<String, String> get _jsonHeaders => const {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      };

  Map<String, String> _authHeaders(String accessToken) => {
        ..._jsonHeaders,
        'Authorization': 'Bearer $accessToken',
      };

  /// Checks whether the backend health endpoint returns HTTP 200.
  Future<bool> health() async {
    try {
      final response = await _http
          .get(
            _uri('/health'),
            headers: const {'Accept': 'application/json'},
          )
          .timeout(const Duration(seconds: 10));

      return response.statusCode == 200;
    } on Object {
      return false;
    }
  }

  /// Register a new GroundZero account.
  Future<GZAuthResult> register({
    required String email,
    required String password,
    String? displayName,
    bool acceptedTerms = false,
    bool adultConfirmed = false,
  }) async {
    final body = <String, dynamic>{
      'email': email.trim(),
      'password': password,
      'accepted_terms': acceptedTerms,
      'adult_confirmed': adultConfirmed,
      if (displayName != null && displayName.trim().isNotEmpty)
        'display_name': displayName.trim(),
    };

    final response = await _post('/auth/register', body);
    return GZAuthResult.fromJson(response);
  }

  /// Log in to an existing GroundZero account.
  Future<GZAuthResult> login({
    required String email,
    required String password,
  }) async {
    final response = await _post('/auth/login', {
      'email': email.trim(),
      'password': password,
    });

    return GZAuthResult.fromJson(response);
  }

  /// Get the currently authenticated user.
  Future<GZUser> me(String accessToken) async {
    final response = await _get('/auth/me', accessToken);
    return GZUser.fromJson(response);
  }

  /// Send a JSON POST request.
  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    http.Response response;

    try {
      response = await _http
          .post(
            _uri(path),
            headers: _jsonHeaders,
            body: jsonEncode(body),
          )
          .timeout(requestTimeout);
    } on TimeoutException {
      throw GZApiException(
        'GroundZero took too long to respond. Please try again.',
      );
    } on Object {
      throw GZApiException(
        'Cannot connect to GroundZero. Check your internet connection.',
      );
    }

    return _decode(response);
  }

  /// Send an authenticated JSON GET request.
  Future<Map<String, dynamic>> _get(
    String path,
    String accessToken,
  ) async {
    http.Response response;

    try {
      response = await _http
          .get(
            _uri(path),
            headers: _authHeaders(accessToken),
          )
          .timeout(requestTimeout);
    } on TimeoutException {
      throw GZApiException(
        'GroundZero took too long to respond. Please try again.',
      );
    } on Object {
      throw GZApiException(
        'Cannot connect to GroundZero. Check your internet connection.',
      );
    }

    return _decode(response);
  }

  /// Decode a response and convert HTTP errors to readable messages.
  Map<String, dynamic> _decode(http.Response response) {
    Map<String, dynamic> body = <String, dynamic>{};

    if (response.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(response.body);

        if (decoded is Map<String, dynamic>) {
          body = decoded;
        } else if (decoded is Map) {
          body = Map<String, dynamic>.from(decoded);
        }
      } on FormatException {
        // The response was not valid JSON.
      }
    }

    if (response.statusCode >= 200 &&
        response.statusCode < 300) {
      return body;
    }

    final detail = body['detail'] ??
        body['message'] ??
        body['error'];

    String message;

    if (detail is String && detail.isNotEmpty) {
      message = detail;
    } else if (response.statusCode == 400) {
      message = 'Please check the information you entered.';
    } else if (response.statusCode == 401) {
      message = 'Your login details are invalid or your session expired.';
    } else if (response.statusCode == 403) {
      message = 'You do not have permission to perform this action.';
    } else if (response.statusCode == 404) {
      message = 'The requested GroundZero endpoint was not found.';
    } else if (response.statusCode == 409) {
      message = 'This account already exists.';
    } else if (response.statusCode >= 500) {
      message = 'GroundZero server error. Please try again later.';
    } else {
      message = 'Something went wrong. Please try again.';
    }

    throw GZApiException(message, response.statusCode);
  }

  /// Close the underlying HTTP client when it is no longer needed.
  void close() {
    _http.close();
  }
}
