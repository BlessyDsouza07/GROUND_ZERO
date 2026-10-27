import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

const String _tokenKey = 'groundzero.access_token';

/// Holds the signed-in user (if any) for the whole app. main.dart creates
/// one instance and every screen that needs to know "is someone signed
/// in" listens to it, rather than each screen managing its own copy of
/// the token.
class AuthController extends ChangeNotifier {
  final GZApiClient _api;
  AuthController({GZApiClient? api}) : _api = api ?? GZApiClient();

  String? _token;
  GZUser? _user;
  bool _restoring = true;

  bool get isSignedIn => _token != null && _user != null;
  bool get isRestoring => _restoring;
  GZUser? get user => _user;

  /// The raw bearer token, for the trips/* endpoints (trips_api_client.dart)
  /// that need it directly rather than going through this controller's own
  /// higher-level methods. Null whenever `isSignedIn` is false.
  String? get accessToken => _token;

  /// Tries to restore a session from a previously saved token. Called
  /// once at startup; if the saved token has expired or the server
  /// rejects it, the person is simply left signed out — no error shown.
  Future<void> restore() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_tokenKey);
    if (saved != null) {
      try {
        final user = await _api.me(saved).timeout(const Duration(seconds: 6));
        _token = saved;
        _user = user;
      } on GZApiException catch (e) {
        // Only a real rejection (401) clears the saved login. A server that
        // is merely down or slow must not sign the person out.
        if (e.statusCode == 401) await prefs.remove(_tokenKey);
      } on Object {
        // Timeout / unreachable: keep the token, start signed out this time.
      }
    }
    _restoring = false;
    notifyListeners();
  }

  Future<void> register({
    required String email,
    required String password,
    String? displayName,
    required bool acceptedTerms,
    required bool adultConfirmed,
  }) async {
    final result = await _api.register(
        email: email, password: password, displayName: displayName, acceptedTerms: acceptedTerms, adultConfirmed: adultConfirmed);
    await _applySession(result);
  }

  Future<void> login({required String email, required String password}) async {
    final result = await _api.login(email: email, password: password);
    await _applySession(result);
  }

  Future<void> _applySession(GZAuthResult result) async {
    _token = result.accessToken;
    _user = result.user;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, result.accessToken);
  }

  Future<void> signOut() async {
    _token = null;
    _user = null;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
