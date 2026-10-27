import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Voice for Talk to Guide: speech-to-text for asking, text-to-speech for
/// answers. Every call is guarded — if the browser/device has no speech
/// support the guide simply stays typed, never crashes.
class GuideVoice {
  final SpeechToText _stt = SpeechToText();
  final FlutterTts _tts = FlutterTts();
  final AudioPlayer _player = AudioPlayer();
  /// Set by the screen: fetches natural-voice MP3 bytes from the server.
  Future<Uint8List?> Function(String text, String code)? fetchAudio;
  bool sttReady = false;
  bool speaking = false;

  static String localeFor(String code) => switch (code) {
        'kn' => 'kn-IN',
        'hi' => 'hi-IN',
        'ta' => 'ta-IN',
        'te' => 'te-IN',
        _ => 'en-IN',
      };

  Future<bool> initListen({void Function(String)? onError}) async {
    try {
      sttReady = await _stt.initialize(onError: (e) => onError?.call(e.errorMsg), onStatus: (_) {});
    } on Object {
      sttReady = false;
    }
    return sttReady;
  }

  bool get isListening => _stt.isListening;

  Future<void> listen(String code, {required void Function(String text, bool done) onText}) async {
    if (!sttReady) return;
    try {
      await _stt.listen(
        localeId: localeFor(code).replaceAll('-', '_'),
        listenFor: const Duration(seconds: 40),
        pauseFor: const Duration(seconds: 3),
        onResult: (r) => onText(r.recognizedWords, r.finalResult),
      );
    } on Object {
      // Unsupported locale/permission — caller shows a hint.
    }
  }

  Future<void> stopListening() async {
    try {
      await _stt.stop();
    } on Object {/* ignore */}
  }

  bool _cancel = false;
  String? _voiceFor;

  /// Make written text sound like a person talking: no symbols, no bullets,
  /// units spoken out, and short sentence-sized pieces so the browser voice
  /// keeps a natural rhythm (and never cuts off mid-answer).
  static List<String> prepare(String raw) {
    var t = raw
        .replaceAll(RegExp(r'https?://\S+'), '')
        .replaceAll(RegExp(r'[*_#`>~|]'), '')
        .replaceAll(RegExp(r'^\s*[-•·]\s+', multiLine: true), '')
        .replaceAll('₹', 'rupees ')
        .replaceAll('&', ' and ')
        .replaceAllMapped(RegExp(r'(\d)\s?km\b'), (m) => '${m[1]} kilometres')
        .replaceAllMapped(RegExp(r'(\d)\s?min\b'), (m) => '${m[1]} minutes')
        .replaceAll(RegExp(r'[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]', unicode: true), '')
        .replaceAll(RegExp(r'\s*\n+\s*'), '. ')
        .replaceAll(RegExp(r'\.\s*\.'), '.')
        .replaceAll(RegExp(r'\s{2,}'), ' ')
        .trim();
    final parts = <String>[];
    for (final m in RegExp(r'[^.!?।]+[.!?।]?').allMatches(t)) {
      final piece = m.group(0)!.trim();
      if (piece.isEmpty) continue;
      if (piece.length <= 220) {
        parts.add(piece);
      } else {
        for (final c in piece.split(RegExp(r'(?<=,)\s+'))) {
          if (c.trim().isNotEmpty) parts.add(c.trim());
        }
      }
    }
    return parts;
  }

  Future<void> _pickVoice(String code) async {
    final locale = localeFor(code);
    if (_voiceFor == locale) return;
    _voiceFor = locale;
    try {
      await _tts.setLanguage(locale);
      final voices = await _tts.getVoices;
      if (voices is! List) return;
      final lang = locale.split('-').first.toLowerCase();
      int score(Map v) {
        final name = '${v['name']}'.toLowerCase();
        final loc = '${v['locale']}'.toLowerCase().replaceAll('_', '-');
        if (!loc.startsWith(lang)) return -1;
        var sc = loc == locale.toLowerCase() ? 5 : 1;
        if (name.contains('natural') || name.contains('neural')) sc += 8;
        if (name.contains('online')) sc += 4;
        if (name.contains('google')) sc += 3;
        for (final n in ['neerja', 'heera', 'veena', 'swara', 'sapna', 'pallavi', 'kalpana']) {
          if (name.contains(n)) sc += 2;
        }
        if (name.contains('espeak') || name.contains('compact')) sc -= 4;
        return sc;
      }

      Map? best;
      var bestScore = 0;
      for (final v in voices) {
        if (v is! Map) continue;
        final sc = score(v);
        if (sc > bestScore) {
          bestScore = sc;
          best = v;
        }
      }
      if (best != null) {
        await _tts.setVoice({'name': '${best['name']}', 'locale': '${best['locale']}'});
      }
    } on Object {/* default voice */}
  }

  Future<void> speak(String text, String code, {void Function()? onDone}) async {
    _cancel = false;
    // 1) natural neural voice from the server
    final fetch = fetchAudio;
    if (fetch != null) {
      try {
        speaking = true;
        final bytes = await fetch(text, code);
        if (bytes != null && !_cancel) {
          await _tts.stop();
          await _player.stop();
          final done = Completer<void>();
          final sub = _player.onPlayerComplete.listen((_) {
            if (!done.isCompleted) done.complete();
          });
          await _player.play(BytesSource(bytes, mimeType: 'audio/mpeg'));
          await done.future.timeout(const Duration(minutes: 3), onTimeout: () {});
          await sub.cancel();
          speaking = false;
          onDone?.call();
          return;
        }
      } on Object {
        // fall through to the browser voice
      }
    }
    if (_cancel) {
      speaking = false;
      onDone?.call();
      return;
    }
    // 2) browser/device voice as a fallback
    try {
      await _tts.stop();
      await _pickVoice(code);
      await _tts.awaitSpeakCompletion(true);
      await _tts.setSpeechRate(kIsWeb ? 1.0 : 0.5);
      await _tts.setPitch(1.0);
      await _tts.setVolume(1.0);
      speaking = true;
      for (final piece in prepare(text)) {
        if (_cancel) break;
        await _tts.speak(piece);
      }
    } on Object {/* ignore */}
    speaking = false;
    onDone?.call();
  }

  Future<void> stopSpeaking() async {
    speaking = false;
    _cancel = true;
    try {
      await _player.stop();
    } on Object {/* ignore */}
    try {
      await _tts.stop();
    } on Object {/* ignore */}
  }

  void dispose() {
    stopSpeaking();
    stopListening();
  }
}
