import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/auth_controller.dart';
import '../../core/locale_controller.dart';
import '../../core/personal_api_client.dart';
import '../../core/theme_controller.dart';
import '../explore/explore_screen.dart';
import '../new_trip/journal_screen.dart';

/// JOURNEY STORY — auto-generated entirely from data the trip already
/// produced (place count, distance, duration, photo/video counts,
/// highlights from the tourist's own ratings). No narrative text is
/// invented anywhere here — see trips/service.py::trip_story and
/// personal/README_PERSONAL.md.
class JourneyStoryScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  final String tripId;
  const JourneyStoryScreen({super.key, required this.auth, required this.locale, required this.theme, required this.tripId});

  @override
  State<JourneyStoryScreen> createState() => _JourneyStoryScreenState();
}

class _JourneyStoryScreenState extends State<JourneyStoryScreen> {
  final _api = PersonalApiClient();
  late Future<GZTripStory> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.tripStory(widget.auth.accessToken!, widget.tripId);
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: FutureBuilder<GZTripStory>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) return Center(child: Text('Could not load this journey.\n${snap.error}'));
          final story = snap.data!;
          final stats = <(String, String)>[
            ('PLACES', '${story.placeCount}'),
            ('DISTANCE', '${story.distanceKm.toStringAsFixed(1)} km'),
            if (story.durationMinutes != null) ('TIME', '${(story.durationMinutes! / 60).toStringAsFixed(1)} hrs'),
            ('PHOTOS', '${story.photoCount}'),
            if (story.videoCount > 0) ('VIDEOS', '${story.videoCount}'),
          ];
          return CustomScrollView(
            slivers: [
              SliverAppBar(
                expandedHeight: 240, pinned: true, backgroundColor: scheme.primary,
                automaticallyImplyLeading: false,
                leading: const GZBackButton(color: Colors.white),
                actions: const [GZHomeAction(color: Colors.white)],
                flexibleSpace: FlexibleSpaceBar(
                  background: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [scheme.primary, scheme.tertiary]),
                    ),
                    child: Center(child: Icon(Icons.auto_stories_outlined, size: 64, color: Colors.white.withOpacity(0.75))),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(story.title, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 20),
                      Wrap(spacing: 24, runSpacing: 14, children: [
                        for (final s in stats)
                          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(s.$2, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
                            Text(s.$1, style: TextStyle(fontSize: 11, letterSpacing: 0.8, color: scheme.onSurfaceVariant)),
                          ]),
                      ]),
                      if (story.visitedPlaceNames.isNotEmpty) ...[
                        const SizedBox(height: 24),
                        Text('WHERE YOU WENT', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12, color: scheme.onSurfaceVariant)),
                        const SizedBox(height: 10),
                        ...story.visitedPlaceNames.map((n) => Padding(
                              padding: const EdgeInsets.only(bottom: 6),
                              child: Row(children: [
                                Icon(Icons.place, size: 16, color: scheme.primary),
                                const SizedBox(width: 8),
                                Expanded(child: Text(n)),
                              ]),
                            )),
                      ],
                      if (story.highlights.isNotEmpty) ...[
                        const SizedBox(height: 20),
                        Text('WHAT STAYED WITH YOU', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12, color: scheme.onSurfaceVariant)),
                        const SizedBox(height: 10),
                        Wrap(spacing: 8, runSpacing: 8, children: story.highlights.map((h) => Chip(label: Text(h))).toList()),
                      ],
                      const SizedBox(height: 28),
                      Row(children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            icon: const Icon(Icons.menu_book_outlined),
                            label: const Text('VIEW JOURNAL'),
                            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) => JournalScreen(auth: widget.auth, tripId: widget.tripId, locale: widget.locale, theme: widget.theme),
                            )),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: ElevatedButton.icon(
                            icon: const Icon(Icons.add_location_alt_outlined),
                            label: const Text('NEXT JOURNEY'),
                            onPressed: () => Navigator.of(context).pushReplacement(MaterialPageRoute(
                              builder: (_) => ExploreScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
                            )),
                          ),
                        ),
                      ]),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
