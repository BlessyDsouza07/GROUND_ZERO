import 'dart:async';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/media_api_client.dart';
import '../../core/trips_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/media_image.dart';

/// Your day as a story: the traveller's own photos and words, played as a
/// full-screen slideshow with a slow zoom, then exported as a real vertical
/// video that can be shared.
class StoryScreen extends StatefulWidget {
  final AuthController auth;
  final String tripId;
  final List<GZJournalEntry> entries;
  final List<String> places;
  const StoryScreen({super.key, required this.auth, required this.tripId, required this.entries, this.places = const []});

  @override
  State<StoryScreen> createState() => _StoryScreenState();
}

class _StoryScreenState extends State<StoryScreen> with SingleTickerProviderStateMixin {
  static const _slide = Duration(seconds: 4);
  late final List<GZJournalEntry> _photos = widget.entries.where((e) => e.mediaType == 'photo').toList();
  late final AnimationController _c = AnimationController(vsync: this, duration: _slide)..addStatusListener(_onDone);
  final _media = MediaApiClient();
  int _i = 0;
  bool _making = false;

  @override
  void initState() {
    super.initState();
    if (_photos.isNotEmpty) _c.forward();
  }

  @override
  void dispose() {
    _c.dispose();
    _media.close();
    super.dispose();
  }

  void _onDone(AnimationStatus s) {
    if (s != AnimationStatus.completed) return;
    if (_i < _photos.length - 1) {
      setState(() => _i++);
      _c.forward(from: 0);
    }
  }

  void _go(int delta) {
    final n = (_i + delta).clamp(0, _photos.length - 1);
    setState(() => _i = n);
    _c.forward(from: 0);
  }

  Future<void> _makeVideo() async {
    final token = widget.auth.accessToken;
    if (token == null || _making) return;
    setState(() => _making = true);
    _c.stop();
    try {
      final url = await _media.makeStoryVideo(token, widget.tripId);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Your story video is ready'),
          content: const Text('Open it to watch or download, or share the link with friends.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
            TextButton(
              onPressed: () => Share.share('My day in Mangaluru, made with GroundZero: $url'),
              child: const Text('Share'),
            ),
            FilledButton(
              onPressed: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
              child: const Text('Open video'),
            ),
          ],
        ),
      );
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) {
        setState(() => _making = false);
        _c.forward();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    if (_photos.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Your story')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(28),
            child: Text('Capture a few moments first. Your story is made from the photos you take on the trip.', textAlign: TextAlign.center),
          ),
        ),
      );
    }
    final e = _photos[_i];
    final caption = (e.caption ?? '').trim();
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapUp: (d) => _go(d.localPosition.dx < MediaQuery.of(context).size.width / 3 ? -1 : 1),
        child: Stack(fit: StackFit.expand, children: [
          AnimatedBuilder(
            animation: _c,
            builder: (_, child) => Transform.scale(scale: 1.0 + 0.10 * _c.value, child: child),
            child: mediaImage(e.mediaUrl, fit: BoxFit.cover),
          ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0x99000000), Color(0x00000000), Color(0x00000000), Color(0xCC000000)], stops: [0, 0.25, 0.55, 1]),
            ),
          ),
          SafeArea(
            child: Column(children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                child: Row(children: [
                  for (var k = 0; k < _photos.length; k++)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 2),
                        child: AnimatedBuilder(
                          animation: _c,
                          builder: (_, __) => LinearProgressIndicator(
                            value: k < _i ? 1 : (k == _i ? _c.value : 0),
                            minHeight: 3,
                            color: ink.accent,
                            backgroundColor: Colors.white24,
                          ),
                        ),
                      ),
                    ),
                ]),
              ),
              Row(children: [
                IconButton(icon: const Icon(Icons.close, color: Colors.white), onPressed: () => Navigator.pop(context)),
                const Spacer(),
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilledButton.icon(
                    onPressed: _making ? null : _makeVideo,
                    icon: _making
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.movie_creation_outlined, size: 18),
                    label: Text(_making ? 'Making video…' : 'Make video'),
                  ),
                ),
              ]),
              const Spacer(),
              if (caption.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 36),
                  child: Text(
                    caption,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Colors.white, height: 1.3, shadows: const [Shadow(blurRadius: 10, color: Colors.black54)]),
                  ),
                ),
            ]),
          ),
        ]),
      ),
    );
  }
}
