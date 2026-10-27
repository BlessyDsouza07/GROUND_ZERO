import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/gz_maps.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart' as ll;

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/trips_api_client.dart';
import '../../design/gz_ink.dart';
import '../../widgets/tiara/gz_place_art.dart';
import '../../widgets/tiara/gz_sticker_button.dart';
import 'active_trip_screen.dart';

/// The draft itinerary: an editable list on the left, a live map on the
/// right (flutter_map + OpenStreetMap tiles — free, no API key, in the
/// same spirit as the backend's own free-tooling choices for
/// routing/weather). On phones the two stack as tabs instead of a
/// side-by-side split, since there's no room for both at once.
class ItineraryScreen extends StatefulWidget {
  final AuthController auth;
  final GZTrip trip;
  const ItineraryScreen({super.key, required this.auth, required this.trip});

  @override
  State<ItineraryScreen> createState() => _ItineraryScreenState();
}

class _ItineraryScreenState extends State<ItineraryScreen> {
  final _api = TripsApiClient();
  late GZTrip _trip;
  bool _busy = false;
  String? _error;
  int _showingMap = 0; // phones only: 0 = list, 1 = map

  String get _token => widget.auth.accessToken!;

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

  Future<void> _reload() async {
    final trip = await _api.getTrip(_token, _trip.tripId);
    if (mounted) setState(() => _trip = trip);
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      await _reload();
    } on GZApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _removePlace(GZTripPlace p) => _run(() => _api.removePlace(_token, _trip.tripId, p.tripPlaceId));

  Future<void> _reorder(int oldIndex, int newIndex) async {
    final places = List<GZTripPlace>.from(_trip.places);
    if (newIndex > oldIndex) newIndex -= 1;
    final moved = places.removeAt(oldIndex);
    places.insert(newIndex, moved);
    setState(() => _trip = GZTrip(
          tripId: _trip.tripId, status: _trip.status, profileId: _trip.profileId,
          budgetTotal: _trip.budgetTotal, budgetRemaining: _trip.budgetRemaining, energyBand: _trip.energyBand,
          notificationsEnabled: _trip.notificationsEnabled, voiceGuideEnabled: _trip.voiceGuideEnabled,
          geofenceRadiusKm: _trip.geofenceRadiusKm, originLatitude: _trip.originLatitude, originLongitude: _trip.originLongitude,
          scheduledStartAt: _trip.scheduledStartAt, startedAt: _trip.startedAt, layer3SessionId: _trip.layer3SessionId,
          places: places,
        ));
    await _run(() => _api.reorderPlaces(_token, _trip.tripId, places.map((p) => p.tripPlaceId).toList()));
  }

  Future<void> _openAddPlaceSheet() async {
    await showModalBottomSheet(
      context: context, isScrollControlled: true,
      builder: (_) => _AddPlaceSheet(
        onAddExisting: (placeId) => _run(() => _api.addPlace(_token, _trip.tripId, placeId: placeId)),
        onAddNew: (name, lat, lon) => _run(() => _api.addPlace(_token, _trip.tripId, name: name, latitude: lat, longitude: lon)),
        searchPlaces: (q) => _api.searchPlaces(_token, q),
      ),
    );
  }

  Future<void> _rate() async {
    int rating = 4;
    final result = await showDialog<int>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setDialogState) {
        return AlertDialog(
          title: const Text('Rate this itinerary'),
          content: Row(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(5, (i) {
              final star = i + 1;
              return IconButton(
                icon: Icon(star <= rating ? Icons.star : Icons.star_border, color: Colors.amber),
                onPressed: () => setDialogState(() => rating = star),
              );
            }),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, rating), child: const Text('Submit')),
          ],
        );
      }),
    );
    if (result != null) {
      await _run(() => _api.rateTrip(_token, _trip.tripId, result, null));
    }
  }

  Future<void> _confirm() async {
    final decision = await showDialog<_ConfirmDecision>(
      context: context,
      builder: (_) => _ConfirmDialog(),
    );
    if (decision == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final confirmed = await _api.confirmTrip(
        _token, _trip.tripId,
        notificationsEnabled: decision.notifications, voiceGuideEnabled: decision.voiceGuide,
        startNow: decision.startNow, scheduledStartAt: decision.scheduledAt,
      );
      if (!mounted) return;
      if (confirmed.status == 'active') {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => ActiveTripScreen(auth: widget.auth, trip: confirmed)),
        );
      } else {
        Navigator.of(context).pop(); // scheduled for later — back to the dashboard
      }
    } on GZApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.of(context).size.width >= 900;
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        title: const Text('Your itinerary'),
        actions: [
          const GZHomeAction(),
          if (!wide)
            IconButton(
              icon: Icon(_showingMap == 0 ? Icons.map_outlined : Icons.list),
              onPressed: () => setState(() => _showingMap = _showingMap == 0 ? 1 : 0),
            ),
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
          Expanded(
            child: wide
                ? Row(
                    children: [
                      Expanded(flex: 5, child: _list()),
                      const VerticalDivider(width: 1),
                      Expanded(flex: 6, child: _map()),
                    ],
                  )
                : (_showingMap == 0 ? _list() : _map()),
          ),
        ],
      ),
    );
  }

  static String _humanReason(String role, String? raw) {
    final r = (raw ?? '').trim();
    if (r.isNotEmpty && !r.startsWith('Selected as') && !r.contains('personal_fit')) return r;
    switch (role) {
      case 'grounding':
        return 'A calm, easy first stop to settle into the city.';
      case 'signature':
        return 'One of the places that makes Mangaluru what it is.';
      case 'anchor':
        return 'A proper stop to eat or rest, so the day has a rhythm.';
      case 'local_secret':
        return 'A local favourite most visitors never hear about.';
      case 'tourist_pick':
        return 'Added by you, so it stays in the plan.';
      default:
        return 'Chosen to match your interests, energy and the time of day.';
    }
  }

  Widget _summary(GZInk ink) {
    final places = _trip.places;
    final travel = places.fold<int>(0, (a, p) => a + (p.travelTimeMinutes ?? 0));
    final secrets = places.where((p) => p.role == 'local_secret').length;
    final spent = (_trip.budgetTotal - _trip.budgetRemaining).clamp(0, _trip.budgetTotal <= 0 ? 1 : _trip.budgetTotal).toDouble();
    final frac = _trip.budgetTotal <= 0 ? 0.0 : (spent / _trip.budgetTotal).clamp(0.0, 1.0);
    final text = Theme.of(context).textTheme;
    final badges = <(IconData, String)>[
      if (_trip.budgetRemaining >= 0 && places.isNotEmpty) (Icons.savings_outlined, '₹${_trip.budgetRemaining.toStringAsFixed(0)} to spare'),
      if (secrets > 0) (Icons.auto_awesome, '$secrets local ${secrets == 1 ? 'secret' : 'secrets'}'),
      if (places.isNotEmpty && travel <= 90) (Icons.compress_rounded, 'Compact route'),
      if (places.any((p) => p.role == 'grounding')) (Icons.spa_outlined, 'Gentle start'),
    ];
    Widget stat(String v, String l) => Expanded(
          child: Column(children: [
            Text(v, style: text.headlineSmall?.copyWith(fontWeight: FontWeight.w900, color: Colors.white)),
            Text(l, style: const TextStyle(color: Color(0xCCFFFFFF), fontSize: 12)),
          ]),
        );
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF06384F), Color(0xFF006996), Color(0xFF0699BA)]),
        boxShadow: ink.softShadow,
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('YOUR DAY AT A GLANCE', style: TextStyle(color: Color(0xFFFBF3E2), fontWeight: FontWeight.w900, letterSpacing: 1.6, fontSize: 11.5)),
        const SizedBox(height: 14),
        // Route strip: numbered dots joined by a dashed line.
        SizedBox(
          height: 34,
          child: Row(children: [
            for (var i = 0; i < places.length; i++) ...[
              Container(
                width: 30,
                height: 30,
                alignment: Alignment.center,
                decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFFFBF3E2), border: Border.all(color: _roleTint(places[i].role, ink), width: 3)),
                child: Text('${i + 1}', style: const TextStyle(color: Color(0xFF06384F), fontWeight: FontWeight.w900, fontSize: 12)),
              ),
              if (i != places.length - 1)
                Expanded(child: LayoutBuilder(builder: (context, box) => Row(children: [
                      for (var d = 0; d < (box.maxWidth / 8).floor(); d++) Expanded(child: Container(height: 2, margin: const EdgeInsets.symmetric(horizontal: 1.5), color: Colors.white.withOpacity(0.55))),
                    ]))),
            ],
          ]),
        ),
        const SizedBox(height: 16),
        Row(children: [
          stat('${places.length}', 'stops'),
          stat(travel == 0 ? '-' : '$travel min', 'travelling'),
          stat('₹${_trip.budgetTotal.toStringAsFixed(0)}', 'budget'),
        ]),
        const SizedBox(height: 14),
        ClipRRect(borderRadius: BorderRadius.circular(99), child: LinearProgressIndicator(value: frac, minHeight: 7, backgroundColor: Colors.white.withOpacity(0.25), color: const Color(0xFFFFC136))),
        const SizedBox(height: 6),
        Text('₹${_trip.budgetRemaining.toStringAsFixed(0)} left of ₹${_trip.budgetTotal.toStringAsFixed(0)}', style: const TextStyle(color: Color(0xCCFFFFFF), fontSize: 12)),
        if (badges.isNotEmpty) ...[
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final b in badges)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(color: Colors.white.withOpacity(0.16), borderRadius: BorderRadius.circular(99), border: Border.all(color: Colors.white.withOpacity(0.35))),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(b.$1, size: 14, color: const Color(0xFFFFE08A)),
                  const SizedBox(width: 6),
                  Text(b.$2, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
                ]),
              ),
          ]),
        ],
        const SizedBox(height: 8),
        Row(children: [
          const Spacer(),
          TextButton.icon(style: TextButton.styleFrom(foregroundColor: Colors.white), onPressed: _rate, icon: const Icon(Icons.star_outline, size: 18), label: const Text('Rate')),
          TextButton.icon(style: TextButton.styleFrom(foregroundColor: Colors.white), onPressed: _openAddPlaceSheet, icon: const Icon(Icons.add_location_alt_outlined, size: 18), label: const Text('Add a place')),
        ]),
      ]),
    );
  }

  String _clock(DateTime? t) {
    if (t == null) return '';
    return MaterialLocalizations.of(context).formatTimeOfDay(TimeOfDay.fromDateTime(t.toLocal()), alwaysUse24HourFormat: false);
  }

  Widget _stopRow(GZInk ink, GZTripPlace p, int index, bool last) {
    final text = Theme.of(context).textTheme;
    final color = _roleTint(p.role, ink);
    final sub = gzArtSub('', const [], p.placeName);
    final kind = switch (p.role) {
      'signature' => GZArtKind.heritage,
      'grounding' => GZArtKind.nature,
      'anchor' => GZArtKind.food,
      'local_secret' => GZArtKind.market,
      _ => GZArtKind.generic,
    };
    final card = Container(
      margin: const EdgeInsets.only(bottom: 4),
      decoration: BoxDecoration(color: ink.paper, borderRadius: BorderRadius.circular(20), border: Border.all(color: ink.hairline), boxShadow: ink.softShadow),
      clipBehavior: Clip.antiAlias,
      child: IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(width: 92, child: GZPlaceArt(kind: kind, seed: p.placeName, sub: sub)),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 4, 12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: color.withOpacity(0.14), borderRadius: BorderRadius.circular(99)),
                  child: Text(_roleLabel(p.role).toUpperCase(), style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 10, letterSpacing: 0.8)),
                ),
                const SizedBox(height: 6),
                Text(p.placeName, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.titleSmall?.copyWith(fontWeight: FontWeight.w900, fontSize: 16, height: 1.2)),
                const SizedBox(height: 4),
                Text(_humanReason(p.role, p.reasonSelected), maxLines: 3, overflow: TextOverflow.ellipsis, style: text.bodySmall?.copyWith(color: ink.muted, height: 1.35)),
                const SizedBox(height: 8),
                Row(children: [
                  Icon(Icons.sell_outlined, size: 14, color: ink.muted),
                  const SizedBox(width: 4),
                  Text(p.estimatedCost <= 0 ? 'Free' : '₹${p.estimatedCost.toStringAsFixed(0)}', style: text.bodySmall?.copyWith(fontWeight: FontWeight.w800)),
                ]),
              ]),
            ),
          ),
          Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            if (p.latitude != null && p.longitude != null)
              IconButton(
                icon: Icon(Icons.near_me_outlined, color: ink.accent),
                tooltip: 'Take me there',
                onPressed: () => GZMaps.directions(context, p.latitude!, p.longitude!, name: p.placeName, mode: GZMaps.modeFor(p.travelMode)),
              ),
            ReorderableDragStartListener(index: index, child: const Padding(padding: EdgeInsets.all(8), child: Icon(Icons.drag_indicator))),
          ]),
        ]),
      ),
    );
    final travelChip = (index > 0 && p.travelMode != null)
        ? Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(color: ink.accent.withOpacity(0.1), borderRadius: BorderRadius.circular(99)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(_modeIcon(p.travelMode!), size: 14, color: ink.accent),
                const SizedBox(width: 6),
                Text('${p.travelTimeMinutes ?? 0} min by ${p.travelMode}', style: TextStyle(color: ink.accent, fontWeight: FontWeight.w800, fontSize: 12)),
              ]),
            ),
          )
        : const SizedBox.shrink();
    final time = _clock(p.scheduledTime);
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(
          width: 64,
          child: Column(children: [
            SizedBox(height: 18, child: Text(time, style: TextStyle(color: ink.muted, fontSize: 11, fontWeight: FontWeight.w800))),
            Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: BoxDecoration(shape: BoxShape.circle, color: color, border: Border.all(color: ink.paper, width: 3), boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 6)]),
              child: Text('${index + 1}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 14)),
            ),
            if (!last) Expanded(child: Container(width: 3, margin: const EdgeInsets.symmetric(vertical: 4), decoration: BoxDecoration(color: ink.accent.withOpacity(0.3), borderRadius: BorderRadius.circular(2)))),
          ]),
        ),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [travelChip, card, const SizedBox(height: 10)])),
      ]),
    );
  }

  IconData _modeIcon(String m) {
    final x = m.toLowerCase();
    if (x.contains('walk')) return Icons.directions_walk;
    if (x.contains('bus')) return Icons.directions_bus_outlined;
    if (x.contains('auto')) return Icons.electric_rickshaw_outlined;
    if (x.contains('bike') || x.contains('cycle')) return Icons.pedal_bike;
    return Icons.local_taxi_outlined;
  }

  Widget _list() {
    final ink = GZInk.of(context);
    return Column(
      children: [
        Expanded(
          child: ReorderableListView.builder(
            buildDefaultDragHandles: false,
            header: _summary(ink),
            padding: const EdgeInsets.fromLTRB(12, 0, 16, 100),
            itemCount: _trip.places.length,
            onReorder: _reorder,
            itemBuilder: (context, index) {
              final p = _trip.places[index];
              return Dismissible(
                key: ValueKey(p.tripPlaceId),
                direction: DismissDirection.endToStart,
                onDismissed: (_) => _removePlace(p),
                background: Container(
                  margin: const EdgeInsets.only(left: 64, bottom: 14),
                  decoration: BoxDecoration(color: Theme.of(context).colorScheme.errorContainer, borderRadius: BorderRadius.circular(20)),
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20),
                  child: const Icon(Icons.delete_outline),
                ),
                child: _stopRow(ink, p, index, index == _trip.places.length - 1),
              );
            },
          ),
        ),
        Container(
          decoration: BoxDecoration(color: ink.paper, border: Border(top: BorderSide(color: ink.hairline))),
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: SizedBox(
                width: double.infinity,
                child: GZStickerButton(label: 'Confirm and start my day', icon: Icons.flag_rounded, expand: true, onPressed: _trip.places.isEmpty ? null : _confirm),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _map() {
    final origin = (_trip.originLatitude != null && _trip.originLongitude != null)
        ? ll.LatLng(_trip.originLatitude!, _trip.originLongitude!)
        : const ll.LatLng(12.9141, 74.8560);
    return FlutterMap(
      options: MapOptions(initialCenter: origin, initialZoom: 13),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.groundzero.app',
        ),
        PolylineLayer(polylines: [
          Polyline(
            points: [
              origin,
              for (final p in _trip.places)
                if (p.latitude != null && p.longitude != null) ll.LatLng(p.latitude!, p.longitude!),
            ],
            strokeWidth: 4,
            color: const Color(0xAA006996),
          ),
        ]),
        MarkerLayer(markers: [
          Marker(point: origin, width: 36, height: 36, child: const Icon(Icons.my_location, color: Colors.blue, size: 30)),
          for (var i = 0; i < _trip.places.length; i++)
            if (_trip.places[i].latitude != null && _trip.places[i].longitude != null)
              Marker(
                point: ll.LatLng(_trip.places[i].latitude!, _trip.places[i].longitude!),
                width: 40,
                height: 40,
                child: Container(
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _roleTint(_trip.places[i].role, GZInk.of(context)),
                    border: Border.all(color: Colors.white, width: 3),
                    boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 6, offset: Offset(0, 2))],
                  ),
                  child: Text('${i + 1}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 14)),
                ),
              ),
        ]),
      ],
    );
  }
}

Color _roleTint(String role, GZInk ink) {
  switch (role) {
    case 'grounding':
      return const Color(0xFF2E8F72);
    case 'signature':
      return const Color(0xFFD97E0C);
    case 'anchor':
      return const Color(0xFFC8481F);
    case 'local_secret':
      return const Color(0xFF6B4BA8);
    case 'tourist_pick':
      return const Color(0xFFB3261E);
    default:
      return ink.accent;
  }
}

Color _roleColor(String role, BuildContext context) {
  final scheme = Theme.of(context).colorScheme;
  switch (role) {
    case 'grounding':
      return scheme.primary;
    case 'signature':
      return scheme.secondary;
    case 'anchor':
      return scheme.tertiary;
    case 'tourist_pick':
      return scheme.error;
    default:
      return scheme.outline;
  }
}

String _roleLabel(String role) {
  switch (role) {
    case 'grounding':
      return 'Grounding';
    case 'signature':
      return 'Signature';
    case 'anchor':
      return 'Anchor';
    case 'tourist_pick':
      return 'Your pick';
    case 'local_secret':
      return 'Local secret';
    default:
      return 'Personal';
  }
}

class _AddPlaceSheet extends StatefulWidget {
  final Future<void> Function(String placeId) onAddExisting;
  final Future<void> Function(String name, double lat, double lon) onAddNew;
  final Future<List<GZSearchPlace>> Function(String query) searchPlaces;

  const _AddPlaceSheet({required this.onAddExisting, required this.onAddNew, required this.searchPlaces});

  @override
  State<_AddPlaceSheet> createState() => _AddPlaceSheetState();
}

class _AddPlaceSheetState extends State<_AddPlaceSheet> {
  final _query = TextEditingController();
  List<GZSearchPlace> _results = [];
  bool _searching = false;

  Future<void> _search(String q) async {
    setState(() => _searching = true);
    final results = await widget.searchPlaces(q);
    if (mounted) setState(() {
      _results = results;
      _searching = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: DraggableScrollableSheet(
        initialChildSize: 0.7, minChildSize: 0.4, maxChildSize: 0.95, expand: false,
        builder: (context, scrollController) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Add a place', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                TextField(
                  controller: _query,
                  decoration: const InputDecoration(border: OutlineInputBorder(), hintText: 'Search by name', prefixIcon: Icon(Icons.search)),
                  onChanged: _search,
                ),
                const SizedBox(height: 12),
                Expanded(
                  child: _searching
                      ? const Center(child: CircularProgressIndicator())
                      : ListView.builder(
                          controller: scrollController,
                          itemCount: _results.length + 1,
                          itemBuilder: (context, i) {
                            if (i == _results.length) {
                              return ListTile(
                                leading: const Icon(Icons.add_circle_outline),
                                title: Text(_query.text.trim().isEmpty ? "Can't find it? Add your own" : 'Add "${_query.text.trim()}" as a new place'),
                                subtitle: const Text("We'll drop a pin at your current location — you can fine-tune it later."),
                                onTap: _query.text.trim().isEmpty
                                    ? null
                                    : () async {
                                        Navigator.of(context).pop();
                                        // No map-pin picker in this pass — uses the
                                        // trip's own origin as a stand-in location;
                                        // see trips/README_TRIPS.md for the deferred
                                        // "drop a pin" gesture.
                                        await widget.onAddNew(_query.text.trim(), 12.9141, 74.8560);
                                      },
                              );
                            }
                            final r = _results[i];
                            return ListTile(
                              leading: const Icon(Icons.place_outlined),
                              title: Text(r.name),
                              subtitle: Text('${r.category} · ₹${r.estimatedCost.toStringAsFixed(0)}'),
                              onTap: () async {
                                Navigator.of(context).pop();
                                await widget.onAddExisting(r.placeId);
                              },
                            );
                          },
                        ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ConfirmDecision {
  final bool notifications;
  final bool voiceGuide;
  final bool startNow;
  final DateTime? scheduledAt;
  _ConfirmDecision({required this.notifications, required this.voiceGuide, required this.startNow, this.scheduledAt});
}

class _ConfirmDialog extends StatefulWidget {
  @override
  State<_ConfirmDialog> createState() => _ConfirmDialogState();
}

class _ConfirmDialogState extends State<_ConfirmDialog> {
  bool _notifications = true;
  bool _voiceGuide = true;

  // BUG FIX (6th audit response, Oct 2026): "Schedule for later" set
  // trip.status to "scheduled" and stored scheduled_start_at (see
  // trips/service.py's confirm_trip), but nothing in the backend ever
  // promotes a scheduled trip to "active" at that time -- confirmed by
  // reading main.py's scheduler jobs (only the events-cache refresh job
  // exists) and every trip.status = "active" assignment in
  // trips/service.py (only confirm's start-now branch and resume_trip,
  // neither of which anything calls automatically for a scheduled
  // trip). A tourist who picked "Schedule for later" would have their
  // trip sit in "scheduled" forever with no way to actually start it
  // from this screen. Rather than ship a UI option that leads to a
  // dead end, this always confirms with startNow: true until a real
  // scheduler/activation path exists -- see trips/README_TRIPS.md for
  // the staged roadmap item.

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Ready to go?'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Independent toggles, exactly as specified — notifications and
            // the voice guide are two separate decisions, not one bundled
            // "on/off" switch.
            SwitchListTile(
              contentPadding: EdgeInsets.zero, title: const Text('Notifications'), value: _notifications,
              onChanged: (v) => setState(() => _notifications = v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero, title: const Text('Tour-guide voice'), value: _voiceGuide,
              onChanged: (v) => setState(() => _voiceGuide = v),
            ),
            const Divider(),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text("You'll start this trip now — scheduling a trip for later is coming in a future update."),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () => Navigator.pop(
            context,
            _ConfirmDecision(notifications: _notifications, voiceGuide: _voiceGuide, startNow: true, scheduledAt: null),
          ),
          child: const Text('Confirm'),
        ),
      ],
    );
  }
}
