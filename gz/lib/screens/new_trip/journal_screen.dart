import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart' as ll;

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/locale_controller.dart';
import '../../core/personal_api_client.dart';
import '../../core/theme_controller.dart';
import '../../core/trips_api_client.dart';
import '../../widgets/media_image.dart';
import '../../widgets/gz_journal_capture.dart';
import '../explore/explore_screen.dart';
import 'story_screen.dart';

/// The post-trip journal — chunk 4 enhancement. Still the honest
/// version chunk 2 built (everything the tourist actually captured, in
/// order — no fabricated "AI-produced" montage, see the docstring that
/// used to live here, now in README.md), now with three ways to look at
/// it (Timeline / Scrapbook / Map) plus a real stats footer and a
/// "Memory Moments" treatment for entries that carry the tourist's own
/// caption. Nothing here is generated text — every caption, every
/// photo, is exactly what the tourist added during the trip. Per
/// Carol's explicit rule, GroundZero never reaches into the phone's
/// camera roll — only entries added through the trip's own camera
/// button (chunk 2's active_trip_screen.dart) ever land here.
class JournalScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController? locale;
  final ThemeController? theme;
  final String tripId;
  const JournalScreen({super.key, required this.auth, required this.tripId, this.locale, this.theme});

  @override
  State<JournalScreen> createState() => _JournalScreenState();
}

class _JournalScreenState extends State<JournalScreen> with SingleTickerProviderStateMixin {
  final _tripsApi = TripsApiClient();
  final _personalApi = PersonalApiClient();
  List<GZJournalEntry>? _entries;
  GZTrip? _trip;
  GZTripStory? _story;
  String? _error;
  late final TabController _tabs = TabController(length: 3, vsync: this);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _tripsApi.close();
    _personalApi.close();
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final token = widget.auth.accessToken!;
      final results = await Future.wait([
        _tripsApi.journalTimeline(token, widget.tripId),
        _tripsApi.getTrip(token, widget.tripId),
      ]);
      final entries = results[0] as List<GZJournalEntry>;
      final trip = results[1] as GZTrip;
      GZTripStory? story;
      try {
        story = await _personalApi.tripStory(token, widget.tripId);
      } on GZApiException {
        // Story is a nice-to-have footer, not required for the journal itself.
      }
      if (mounted) setState(() { _entries = entries; _trip = trip; _story = story; });
    } on GZApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  void _addToNextJourney() {
    if (widget.locale == null || widget.theme == null) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => ExploreScreen(auth: widget.auth, locale: widget.locale!, theme: widget.theme!),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        actions: [
          IconButton(
            tooltip: 'Play my story',
            icon: const Icon(Icons.play_circle_outline),
            onPressed: (_entries == null || _entries!.isEmpty)
                ? null
                : () => Navigator.of(context).push(MaterialPageRoute(
                      fullscreenDialog: true,
                      builder: (_) => StoryScreen(
                        auth: widget.auth,
                        tripId: widget.tripId,
                        entries: _entries!,
                        places: (_trip?.places ?? []).map((p) => p.placeName).toList(),
                      ),
                    )),
          ),
          const GZHomeAction(),
        ],
        title: const Text('Your journal'),
        bottom: TabBar(controller: _tabs, tabs: const [
          Tab(text: 'TIMELINE'), Tab(text: 'SCRAPBOOK'), Tab(text: 'MAP'),
        ]),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          if (await gzCaptureMoment(context, widget.auth, widget.tripId) && mounted) _load();
        },
        icon: const Icon(Icons.add_a_photo_outlined),
        label: const Text('Capture a moment'),
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _entries == null
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  children: [
                    Expanded(
                      child: TabBarView(controller: _tabs, children: [
                        _timeline(context),
                        _scrapbook(context),
                        _map(context),
                      ]),
                    ),
                    if (_story != null) _statsFooter(context, _story!),
                  ],
                ),
    );
  }

  Widget _timeline(BuildContext context) {
    if (_entries!.isEmpty) {
      return const Center(child: Text('Nothing captured yet. Tap Capture a moment to add your first photo.'));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _entries!.length,
      itemBuilder: (context, i) {
        final e = _entries![i];
        final isMemoryMoment = e.caption != null && e.caption!.trim().isNotEmpty;
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          shape: isMemoryMoment
              ? RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: Theme.of(context).colorScheme.primary.withOpacity(0.4), width: 1.5),
                )
              : null,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (e.mediaType == 'photo')
                ClipRRect(
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                  child: SizedBox(height: 220, width: double.infinity, child: mediaImage(e.mediaUrl)),
                )
              else
                Container(height: 100, alignment: Alignment.center, child: const Icon(Icons.movie_outlined, size: 40)),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (isMemoryMoment) ...[
                      Row(children: [
                        Icon(Icons.star, size: 14, color: Theme.of(context).colorScheme.primary),
                        const SizedBox(width: 4),
                        Text('MEMORY MOMENT', style: TextStyle(
                          fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.8,
                          color: Theme.of(context).colorScheme.primary,
                        )),
                      ]),
                      const SizedBox(height: 4),
                      Text(e.caption!, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                    ],
                    const SizedBox(height: 4),
                    Text(
                      '${e.createdAt.toLocal()}'.split('.').first,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _scrapbook(BuildContext context) {
    final photos = _entries!.where((e) => e.mediaType == 'photo').toList();
    if (photos.isEmpty) {
      return const Center(child: Text('No photos yet — your scrapbook fills in as you capture moments on a trip.'));
    }
    return GridView.builder(
      padding: const EdgeInsets.all(12),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 2, mainAxisSpacing: 10, crossAxisSpacing: 10),
      itemCount: photos.length,
      itemBuilder: (context, i) {
        final e = photos[i];
        return ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: Stack(
            fit: StackFit.expand,
            children: [
              mediaImage(e.mediaUrl),
              if (e.caption != null && e.caption!.trim().isNotEmpty)
                Positioned(
                  left: 0, right: 0, bottom: 0,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    color: Colors.black.withOpacity(0.45),
                    child: Text(e.caption!, maxLines: 2, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _map(BuildContext context) {
    final visited = (_trip?.places ?? []).where((p) => p.latitude != null && p.longitude != null).toList();
    if (visited.isEmpty) {
      return const Center(child: Text('Nothing to show on the map yet.'));
    }
    final center = ll.LatLng(visited.first.latitude!, visited.first.longitude!);
    return FlutterMap(
      options: MapOptions(initialCenter: center, initialZoom: 13),
      children: [
        TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.groundzero.app'),
        MarkerLayer(markers: [
          for (final p in visited)
            Marker(
              point: ll.LatLng(p.latitude!, p.longitude!), width: 36, height: 36,
              child: Icon(Icons.location_on, color: p.status == 'visited' ? Theme.of(context).colorScheme.primary : Colors.grey, size: 32),
            ),
        ]),
      ],
    );
  }

  Widget _statsFooter(BuildContext context, GZTripStory story) {
    final scheme = Theme.of(context).colorScheme;
    final stats = <(String, String)>[
      ('PLACES', '${story.placeCount}'),
      ('KM COVERED', story.distanceKm.toStringAsFixed(1)),
      if (story.durationMinutes != null) ('TIME', '${(story.durationMinutes! / 60).toStringAsFixed(1)}h'),
      ('PHOTOS', '${story.photoCount}'),
      if (story.videoCount > 0) ('VIDEOS', '${story.videoCount}'),
    ];
    return Container(
      decoration: BoxDecoration(color: scheme.surfaceVariant.withOpacity(0.4), border: Border(top: BorderSide(color: scheme.outlineVariant))),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('YOUR JOURNEY', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 10),
          Wrap(spacing: 20, runSpacing: 10, children: [
            for (final s in stats)
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(s.$2, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                Text(s.$1, style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant, letterSpacing: 0.5)),
              ]),
          ]),
          if (story.highlights.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text('WHAT STAYED WITH YOU', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 8, children: story.highlights.map((h) => Chip(label: Text(h))).toList()),
          ],
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _addToNextJourney,
              icon: const Icon(Icons.add_location_alt_outlined),
              label: const Text('ADD TO MY NEXT JOURNEY'),
            ),
          ),
        ],
      ),
    );
  }
}
