import '../../widgets/gz_journal_capture.dart';
import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/gz_maps.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart' as ll;

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/trips_api_client.dart';
import 'journal_screen.dart';

/// The live trip: current stop, arrive/listen, checkout (spend + energy +
/// rating), skip, journal capture, pause/resume, and exit-with-reason.
/// Everything here calls straight into trips/routes.py, which in turn
/// hands geofencing/silence-filter/voice-guide decisions to the real
/// layer3 session started at confirm time — this screen does not
/// reimplement any of that; see trips/README_TRIPS.md.
///
/// Honest limitation: real GPS-triggered arrival detection and the
/// silence-filter-gated voice narration both exist in the backend
/// (layer3's /l3/context/evaluate, /l3/location/ping, and layer5's
/// /companion/narrate) but this pass wires the tourist-facing manual
/// controls ("I'm here", "listen now") rather than a background
/// location stream — see the README for why, and what wiring a
/// continuous GPS stream in later would take.
class ActiveTripScreen extends StatefulWidget {
  final AuthController auth;
  final GZTrip trip;
  const ActiveTripScreen({super.key, required this.auth, required this.trip});

  @override
  State<ActiveTripScreen> createState() => _ActiveTripScreenState();
}

class _ActiveTripScreenState extends State<ActiveTripScreen> {
  final _api = TripsApiClient();
  final _picker = ImagePicker();
  late GZTrip _trip;
  bool _busy = false;
  String? _error;

  String get _token => widget.auth.accessToken!;

  GZTripPlace? get _current {
    final pending = _trip.places.where((p) => p.status == 'pending');
    return pending.isEmpty ? null : pending.first;
  }

  @override
  void initState() {
    super.initState();
    _trip = widget.trip;
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      final refreshed = await _api.getTrip(_token, _trip.tripId);
      if (mounted) setState(() => _trip = refreshed);
      if (mounted && _current == null && _trip.status == 'active') {
        await _finishTrip();
      }
    } on GZApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _finishTrip() async {
    await _api.completeTrip(_token, _trip.tripId);
    if (!mounted) return;
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text("That's the whole day!"),
        content: const Text('Nicely done. Want to see your journal from today?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Later')),
          FilledButton(
            onPressed: () {
              Navigator.pop(context);
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => JournalScreen(auth: widget.auth, tripId: _trip.tripId)),
              );
            },
            child: const Text('See journal'),
          ),
        ],
      ),
    );
    if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
  }

  Future<void> _arrive(GZTripPlace place) async {
    final listen = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text("You're at ${place.placeName}"),
        content: const Text('Want the guide to tell you about this place?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Yes, tell me')),
        ],
      ),
    );
    await _run(() => _api.arrive(_token, _trip.tripId, place.tripPlaceId, listenedToGuide: listen));
  }

  Future<void> _checkout(GZTripPlace place) async {
    final result = await showDialog<_CheckoutInput>(context: context, builder: (_) => _CheckoutDialog(placeName: place.placeName));
    if (result == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final outcome = await _api.checkout(
        _token, _trip.tripId, place.tripPlaceId,
        amountSpent: result.amountSpent, energyAfter: result.energyAfter, rating: result.rating, experienceNote: result.note,
      );
      final refreshed = await _api.getTrip(_token, _trip.tripId);
      if (mounted) setState(() => _trip = refreshed);

      if (!mounted) return;
      if (outcome.suggestRestStop) {
        await showDialog(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Feeling low on energy?'),
            content: const Text("We'll bias what's next toward something calmer — a place to sit, eat, or rest."),
            actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Got it'))],
          ),
        );
      }
      if (!outcome.budgetCoversRestOfTrip) {
        await _offerBudgetTopUp(outcome);
      }
      if (_current == null) await _finishTrip();
    } on GZApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _offerBudgetTopUp(GZCheckoutResult outcome) async {
    final decision = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Budget's getting tight"),
        content: Text(
          "What's left of your itinerary costs about ₹${outcome.remainingItineraryCost.toStringAsFixed(0)}, "
          "but you only have ₹${outcome.budgetRemaining.toStringAsFixed(0)} left.",
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, 'continue'), child: const Text('Continue as-is')),
          FilledButton(onPressed: () => Navigator.pop(ctx, 'topup'), child: const Text('Add more budget')),
        ],
      ),
    );
    if (decision == 'topup' && mounted) {
      final amount = await showDialog<double>(context: context, builder: (_) => const _TopUpDialog());
      if (amount != null) {
        await _run(() => _api.topUpBudget(_token, _trip.tripId, amount));
      }
    }
  }

  Future<void> _skip(GZTripPlace place) async {
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final controller = TextEditingController();
        return AlertDialog(
          title: Text('Skip ${place.placeName}?'),
          content: TextField(controller: controller, decoration: const InputDecoration(hintText: 'Why? (optional)')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Skip')),
          ],
        );
      },
    );
    if (reason == null) return;
    await _run(() => _api.skipPlace(_token, _trip.tripId, place.tripPlaceId, reason: reason.isEmpty ? null : reason));
  }

  Future<void> _addJournalPhoto(GZTripPlace? place) async {
    await gzCaptureMoment(context, widget.auth, _trip.tripId, tripPlaceId: place?.tripPlaceId);
  }

  Future<void> _pause() => _run(() => _api.pauseTrip(_token, _trip.tripId));
  Future<void> _resume() => _run(() => _api.resumeTrip(_token, _trip.tripId, upgrade: false));

  Future<void> _exit() async {
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final controller = TextEditingController();
        return AlertDialog(
          title: const Text('Leaving the trip?'),
          content: TextField(controller: controller, decoration: const InputDecoration(hintText: 'What made you want to stop?')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Stay on trip')),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, controller.text.trim().isEmpty ? 'no reason given' : controller.text.trim()),
              child: const Text('Exit'),
            ),
          ],
        );
      },
    );
    if (reason == null) return;
    setState(() => _busy = true);
    try {
      await _api.exitTrip(_token, _trip.tripId, reason);
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on GZApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final current = _current;
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        title: Text(_trip.status == 'paused' ? 'Trip paused' : "Today's trip"),
        actions: [
          const GZHomeAction(),
          IconButton(icon: const Icon(Icons.menu_book_outlined), tooltip: 'Journal', onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => JournalScreen(auth: widget.auth, tripId: _trip.tripId)),
              )),
          if (_trip.status == 'active')
            IconButton(icon: const Icon(Icons.pause), tooltip: 'Pause', onPressed: _pause)
          else if (_trip.status == 'paused')
            IconButton(icon: const Icon(Icons.play_arrow), tooltip: 'Resume', onPressed: _resume),
          IconButton(icon: const Icon(Icons.exit_to_app), tooltip: 'Exit trip', onPressed: _exit),
        ],
      ),
      body: Column(
        children: [
          if (_error != null)
            Container(
              width: double.infinity, color: Theme.of(context).colorScheme.errorContainer, padding: const EdgeInsets.all(12),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
            ),
          if (_busy) const LinearProgressIndicator(minHeight: 3),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text('Budget left: ₹${_trip.budgetRemaining.toStringAsFixed(0)} · Energy: ${_trip.energyBand}'),
          ),
          Expanded(
            child: MediaQuery.of(context).size.width >= 900
                ? Row(children: [
                    Expanded(flex: 5, child: _body(current)),
                    const VerticalDivider(width: 1),
                    Expanded(flex: 6, child: _map()),
                  ])
                : _body(current),
          ),
        ],
      ),
    );
  }

  Widget _body(GZTripPlace? current) {
    if (current == null) {
      return const Center(child: Text("You've been everywhere on today's list!"));
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Next up', style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: 4),
                  Text(current.placeName, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Text('${current.travelMode ?? ''} ${current.travelTimeMinutes ?? 0} min · ₹${current.estimatedCost.toStringAsFixed(0)}'),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12, runSpacing: 12,
                    children: [
                      if (current.latitude != null && current.longitude != null)
                        FilledButton.icon(
                          onPressed: () => GZMaps.directions(context, current.latitude!, current.longitude!, name: current.placeName, mode: GZMaps.modeFor(current.travelMode)),
                          icon: const Icon(Icons.directions),
                          label: const Text('Take me there'),
                        ),
                      FilledButton.icon(onPressed: () => _arrive(current), icon: const Icon(Icons.location_on), label: const Text("I'm here")),
                      OutlinedButton.icon(onPressed: () => _checkout(current), icon: const Icon(Icons.check_circle_outline), label: const Text('Check out')),
                      OutlinedButton.icon(onPressed: () => _skip(current), icon: const Icon(Icons.skip_next), label: const Text('Skip')),
                      OutlinedButton.icon(onPressed: () => _addJournalPhoto(current), icon: const Icon(Icons.camera_alt_outlined), label: const Text('Journal')),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Rest of the day', style: Theme.of(context).textTheme.titleMedium),
          ..._trip.places.where((p) => p.tripPlaceId != current.tripPlaceId).map(
                (p) => ListTile(
                  leading: Icon(
                    p.status == 'visited' ? Icons.check_circle : (p.status == 'skipped' ? Icons.cancel_outlined : Icons.circle_outlined),
                    color: p.status == 'visited' ? Colors.green : (p.status == 'skipped' ? Colors.grey : null),
                  ),
                  title: Text(p.placeName),
                  subtitle: Text(p.status),
                ),
              ),
        ],
      ),
    );
  }

  Widget _map() {
    final origin = (_trip.originLatitude != null && _trip.originLongitude != null)
        ? ll.LatLng(_trip.originLatitude!, _trip.originLongitude!)
        : const ll.LatLng(12.9141, 74.8560);
    return FlutterMap(
      options: MapOptions(initialCenter: origin, initialZoom: 13),
      children: [
        TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.groundzero.app'),
        MarkerLayer(markers: [
          Marker(point: origin, width: 36, height: 36, child: const Icon(Icons.my_location, color: Colors.blue, size: 30)),
          for (final p in _trip.places)
            if (p.latitude != null && p.longitude != null)
              Marker(
                point: ll.LatLng(p.latitude!, p.longitude!), width: 34, height: 34,
                child: Icon(
                  Icons.location_on,
                  color: p.status == 'visited' ? Colors.green : (p.status == 'skipped' ? Colors.grey : Theme.of(context).colorScheme.primary),
                  size: 30,
                ),
              ),
        ]),
      ],
    );
  }
}

class _CheckoutInput {
  final double amountSpent;
  final String energyAfter;
  final int rating;
  final String? note;
  _CheckoutInput({required this.amountSpent, required this.energyAfter, required this.rating, this.note});
}

class _CheckoutDialog extends StatefulWidget {
  final String placeName;
  const _CheckoutDialog({required this.placeName});

  @override
  State<_CheckoutDialog> createState() => _CheckoutDialogState();
}

class _CheckoutDialogState extends State<_CheckoutDialog> {
  final _amountController = TextEditingController(text: '0');
  String _energy = 'moderate';
  int _rating = 4;
  final _noteController = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Leaving ${widget.placeName}?'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _amountController, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'How much did you spend here? (₹)'),
            ),
            const SizedBox(height: 16),
            const Text('How is your energy now?'),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'low', label: Text('Low')),
                ButtonSegment(value: 'moderate', label: Text('Moderate')),
                ButtonSegment(value: 'high', label: Text('High')),
              ],
              selected: {_energy},
              onSelectionChanged: (s) => setState(() => _energy = s.first),
            ),
            const SizedBox(height: 16),
            const Text('How was it?'),
            Row(
              children: List.generate(5, (i) {
                final star = i + 1;
                return IconButton(
                  icon: Icon(star <= _rating ? Icons.star : Icons.star_border, color: Colors.amber),
                  onPressed: () => setState(() => _rating = star),
                );
              }),
            ),
            TextField(controller: _noteController, decoration: const InputDecoration(hintText: 'Anything you want to remember? (optional)')),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () => Navigator.pop(
            context,
            _CheckoutInput(
              amountSpent: double.tryParse(_amountController.text) ?? 0,
              energyAfter: _energy, rating: _rating,
              note: _noteController.text.trim().isEmpty ? null : _noteController.text.trim(),
            ),
          ),
          child: const Text('Done'),
        ),
      ],
    );
  }
}

class _TopUpDialog extends StatefulWidget {
  const _TopUpDialog();

  @override
  State<_TopUpDialog> createState() => _TopUpDialogState();
}

class _TopUpDialogState extends State<_TopUpDialog> {
  final _controller = TextEditingController(text: '500');

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add how much?'),
      content: TextField(controller: _controller, keyboardType: TextInputType.number, decoration: const InputDecoration(prefixText: '₹ ')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, double.tryParse(_controller.text) ?? 0), child: const Text('Add')),
      ],
    );
  }
}
