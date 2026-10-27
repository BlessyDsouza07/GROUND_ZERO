import 'dart:typed_data';
import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart' as ll;

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/coords.dart';
import '../../core/media_api_client.dart';
import '../../widgets/gz_photo_field.dart';
import '../../design/gz_ink.dart';
import '../../core/personal_api_client.dart';

/// "+ ADD A PLACE" — the one contribution action wired end to end. Goes
/// through PersonalApiClient.addPlace -> layer0's real community-
/// submission pipeline (User -> Submission -> Review -> Master Data).
/// Nothing here writes to Master Data directly — see
/// personal/README_PERSONAL.md.
class AddPlaceScreen extends StatefulWidget {
  final AuthController auth;
  const AddPlaceScreen({super.key, required this.auth});

  @override
  State<AddPlaceScreen> createState() => _AddPlaceScreenState();
}

const _kCategories = ['nature', 'food', 'heritage', 'viewpoint', 'market', 'faith', 'other'];
const _kMangaluru = ll.LatLng(12.9141, 74.8560);

class _AddPlaceScreenState extends State<AddPlaceScreen> {
  final _formKey = GlobalKey<FormState>();
  final _api = PersonalApiClient();
  final _map = MapController();
  final _nameCtrl = TextEditingController();
  final _latCtrl = TextEditingController();
  final _lngCtrl = TextEditingController();
  final _noteCtrl = TextEditingController();
  String _category = 'other';
  bool _submitting = false;
  bool _locating = false;
  ll.LatLng? _pin;
  Uint8List? _photo;

  @override
  void initState() {
    super.initState();
    _latCtrl.addListener(_syncPinFromText);
    _lngCtrl.addListener(_syncPinFromText);
  }

  @override
  void dispose() {
    _api.close();
    _nameCtrl.dispose();
    _latCtrl.dispose();
    _lngCtrl.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  void _syncPinFromText() {
    final la = GZCoords.parse(_latCtrl.text, isLat: true);
    final lo = GZCoords.parse(_lngCtrl.text, isLat: false);
    if (la != null && lo != null) {
      final p = ll.LatLng(la, lo);
      if (_pin == null || _pin!.latitude != la || _pin!.longitude != lo) {
        setState(() => _pin = p);
        try {
          _map.move(p, _map.camera.zoom);
        } on Object {/* map not ready yet */}
      }
    }
  }

  /// Fill both boxes from one pasted "12.8834, 74.8983" style value.
  void _setPin(ll.LatLng p, {bool fromMap = false}) {
    _latCtrl.removeListener(_syncPinFromText);
    _lngCtrl.removeListener(_syncPinFromText);
    _latCtrl.text = p.latitude.toStringAsFixed(6);
    _lngCtrl.text = p.longitude.toStringAsFixed(6);
    _latCtrl.addListener(_syncPinFromText);
    _lngCtrl.addListener(_syncPinFromText);
    setState(() => _pin = p);
    if (!fromMap) {
      try {
        _map.move(p, 16);
      } on Object {/* ignore */}
    }
  }

  String? _latValidator(String? v) {
    final t = (v ?? '').trim();
    if (t.isEmpty) return 'Enter a latitude';
    final pair = GZCoords.parsePair(t);
    if (pair != null) return null; // pasted both; handled on change
    if (GZCoords.parse(t, isLat: true) == null) return 'Try 12.8834 or 12.8834° N (−90 to 90)';
    return null;
  }

  String? _lngValidator(String? v) {
    final t = (v ?? '').trim();
    if (t.isEmpty) return 'Enter a longitude';
    if (GZCoords.parse(t, isLat: false) == null) return 'Try 74.8983 or 74.8983° E (−180 to 180)';
    return null;
  }

  void _onLatChanged(String v) {
    final pair = GZCoords.parsePair(v);
    if (pair != null) _setPin(ll.LatLng(pair.$1, pair.$2));
  }

  Future<void> _useMyLocation() async {
    setState(() => _locating = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        messenger.showSnackBar(const SnackBar(content: Text('Location permission is off. Tap the map or type the coordinates instead.')));
      } else {
        final pos = await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
        ).timeout(const Duration(seconds: 12));
        _setPin(ll.LatLng(pos.latitude, pos.longitude));
      }
    } on Object {
      messenger.showSnackBar(const SnackBar(content: Text('Couldn\'t get your location. Tap the map or type the coordinates.')));
    } finally {
      if (mounted) setState(() => _locating = false);
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final pair = GZCoords.parsePair(_latCtrl.text);
    final lat = pair?.$1 ?? GZCoords.parse(_latCtrl.text, isLat: true);
    final lng = pair?.$2 ?? GZCoords.parse(_lngCtrl.text, isLat: false);
    if (lat == null || lng == null) return;
    setState(() => _submitting = true);
    final media = MediaApiClient();
    try {
      String? photoUrl;
      if (_photo != null) photoUrl = await media.uploadPhoto(widget.auth.accessToken!, _photo!);
      final contribution = await _api.addPlace(
        widget.auth.accessToken!,
        name: _nameCtrl.text.trim(),
        category: _category,
        latitude: lat,
        longitude: lng,
        note: _noteCtrl.text.trim().isEmpty ? null : _noteCtrl.text.trim(),
        mediaUrl: photoUrl,
      );
      if (!mounted) return;
      Navigator.of(context).pop(contribution);
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      media.close();
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: const Text('Add a place'), actions: const [GZHomeAction()]),
      body: Form(
        key: _formKey,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 680),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Text(
                  'Know somewhere GroundZero is missing? Submit it and it goes through real review before it\'s added — never straight onto the map.',
                  style: text.bodyMedium?.copyWith(color: ink.muted),
                ),
                const SizedBox(height: 20),
                TextFormField(
                  controller: _nameCtrl,
                  decoration: const InputDecoration(labelText: 'Place name'),
                  validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  value: _category,
                  decoration: const InputDecoration(labelText: 'Category'),
                  items: _kCategories.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setState(() => _category = v ?? 'other'),
                ),
                const SizedBox(height: 24),
                Text('Where is it?', style: text.titleMedium),
                const SizedBox(height: 4),
                Text('Tap the map, use your location, or type coordinates like 12.8834° N and 74.8983° E.',
                    style: text.bodySmall?.copyWith(color: ink.muted)),
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: SizedBox(
                    height: 240,
                    child: FlutterMap(
                      mapController: _map,
                      options: MapOptions(
                        initialCenter: _pin ?? _kMangaluru,
                        initialZoom: 12,
                        onTap: (_, p) => _setPin(p, fromMap: true),
                      ),
                      children: [
                        TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.groundzero.app'),
                        if (_pin != null)
                          MarkerLayer(markers: [
                            Marker(point: _pin!, width: 40, height: 40, alignment: Alignment.topCenter,
                                child: Icon(Icons.location_on, color: ink.accent, size: 40)),
                          ]),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: _locating ? null : _useMyLocation,
                    icon: _locating
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.my_location, size: 18),
                    label: const Text('Use my current location'),
                  ),
                ),
                const SizedBox(height: 12),
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    child: TextFormField(
                      controller: _latCtrl,
                      decoration: const InputDecoration(labelText: 'Latitude', hintText: '12.8834° N'),
                      keyboardType: TextInputType.text,
                      onChanged: _onLatChanged,
                      validator: _latValidator,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _lngCtrl,
                      decoration: const InputDecoration(labelText: 'Longitude', hintText: '74.8983° E'),
                      keyboardType: TextInputType.text,
                      validator: _lngValidator,
                    ),
                  ),
                ]),
                const SizedBox(height: 16),
                GZPhotoField(bytes: _photo, onChanged: (b) => setState(() => _photo = b), label: 'Add a photo of the place (optional)'),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _noteCtrl,
                  decoration: const InputDecoration(labelText: 'Why does this place matter? (optional)'),
                  maxLines: 3,
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('SUBMIT FOR REVIEW'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
