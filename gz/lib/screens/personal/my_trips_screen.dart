import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/locale_controller.dart';
import '../../core/personal_api_client.dart';
import '../../core/theme_controller.dart';
import '../../core/trips_api_client.dart';
import '../../widgets/groundzero/gz_empty_state.dart';
import '../new_trip/active_trip_screen.dart';
import '../new_trip/itinerary_screen.dart';
import 'journey_story_screen.dart';

/// MY TRIPS — "Your journeys". Per spec: UPCOMING (biggest card = most
/// important/active trip, with "CONTINUE JOURNEY") and COMPLETED (shown
/// as journey covers — photo-style placeholder + title + place count —
/// linking straight into the Journey Story). Everything here is a real
/// Trip row from trips/routes.py's GET /trips; nothing is invented.
class MyTripsScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const MyTripsScreen({super.key, required this.auth, required this.locale, required this.theme});

  @override
  State<MyTripsScreen> createState() => _MyTripsScreenState();
}

class _MyTripsScreenState extends State<MyTripsScreen> {
  final _api = PersonalApiClient();
  final _tripsApi = TripsApiClient();
  Future<GZMyTrips>? _future;

  @override
  void initState() {
    super.initState();
    _future = _api.myTrips(widget.auth.accessToken!);
  }

  @override
  void dispose() {
    _api.close();
    _tripsApi.close();
    super.dispose();
  }

  Future<void> _continue(GZTripSummary t) async {
    try {
      final trip = await _tripsApi.getTrip(widget.auth.accessToken!, t.tripId);
      if (!mounted) return;
      if (trip.status == 'draft') {
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => ItineraryScreen(auth: widget.auth, trip: trip)));
      } else {
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => ActiveTripScreen(auth: widget.auth, trip: trip)));
      }
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  void _openStory(GZTripSummary t) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => JourneyStoryScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme, tripId: t.tripId),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: const Text('My Trips'), actions: const [GZHomeAction()]),
      body: FutureBuilder<GZMyTrips>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) return Center(child: Text('Could not load your trips.\n${snap.error}', textAlign: TextAlign.center));
          final trips = snap.data!;
          if (trips.upcoming.isEmpty && trips.completed.isEmpty) {
            // DESIGN SYSTEM PASS (6th audit response follow-up, Oct
            // 2026): shared GZEmptyState instead of this screen's own
            // centered Text, same wording.
            return const Center(
              child: GZEmptyState(
                icon: Icons.map_outlined,
                message: 'No journeys yet. Start a new trip and it shows up here.',
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (trips.upcoming.isNotEmpty) ...[
                _Label('YOUR JOURNEYS'),
                const SizedBox(height: 12),
                for (int i = 0; i < trips.upcoming.length; i++) ...[
                  _UpcomingCard(trip: trips.upcoming[i], big: i == 0, onContinue: () => _continue(trips.upcoming[i])),
                  const SizedBox(height: 14),
                ],
                const SizedBox(height: 12),
              ],
              if (trips.completed.isNotEmpty) ...[
                _Label('COMPLETED'),
                const SizedBox(height: 12),
                GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2, mainAxisSpacing: 14, crossAxisSpacing: 14, childAspectRatio: 0.85,
                  ),
                  itemCount: trips.completed.length,
                  itemBuilder: (context, i) => _JourneyCover(trip: trips.completed[i], onTap: () => _openStory(trips.completed[i])),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Label extends StatelessWidget {
  final String text;
  const _Label(this.text);
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Text(text, style: TextStyle(color: scheme.onSurfaceVariant, fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12));
  }
}

class _UpcomingCard extends StatelessWidget {
  final GZTripSummary trip;
  final bool big;
  final VoidCallback onContinue;
  const _UpcomingCard({required this.trip, required this.big, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isActive = trip.status == 'active' || trip.status == 'paused';
    return Card(
      elevation: big ? 3 : 1,
      color: big ? scheme.primary : null,
      child: Padding(
        padding: EdgeInsets.all(big ? 24 : 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isActive ? 'ACTIVE NOW' : trip.status.toUpperCase(),
              style: TextStyle(
                fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 11,
                color: big ? scheme.onPrimary.withOpacity(0.85) : scheme.primary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              trip.nextPlaceName != null ? 'Next stop: ${trip.nextPlaceName}' : 'Ready whenever you are',
              style: (big ? Theme.of(context).textTheme.titleLarge : Theme.of(context).textTheme.titleMedium)
                  ?.copyWith(fontWeight: FontWeight.w800, color: big ? scheme.onPrimary : null),
            ),
            const SizedBox(height: 6),
            Text(
              '${trip.visitedCount} of ${trip.placeCount} places visited',
              style: TextStyle(color: big ? scheme.onPrimary.withOpacity(0.85) : scheme.onSurfaceVariant),
            ),
            SizedBox(height: big ? 20 : 12),
            ElevatedButton(
              onPressed: onContinue,
              style: big ? ElevatedButton.styleFrom(backgroundColor: scheme.onPrimary, foregroundColor: scheme.primary) : null,
              child: const Text('CONTINUE JOURNEY'),
            ),
          ],
        ),
      ),
    );
  }
}

class _JourneyCover extends StatelessWidget {
  final GZTripSummary trip;
  final VoidCallback onTap;
  const _JourneyCover({required this.trip, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [scheme.tertiary, scheme.primary]),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Icon(Icons.photo_library_outlined, color: Colors.white.withOpacity(0.85)),
              const Spacer(),
              Text(
                trip.coverPlaceName ?? 'Your journey',
                maxLines: 2, overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 15),
              ),
              const SizedBox(height: 4),
              Text('${trip.placeCount} places', style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }
}
