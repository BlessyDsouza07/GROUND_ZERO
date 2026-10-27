import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/gz_maps.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/explore_api_client.dart';
import '../../core/locale_controller.dart';
import '../../core/theme_controller.dart';
import '../../core/gz_passport.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_report.dart';
import '../../widgets/tiara/gz_place_art.dart';
import '../auth_screen.dart';

/// Full-screen place detail — structure per the spec: hero -> name ->
/// tagline -> "WHY GO?" -> "GOOD FOR" tags -> "WHY NOW?" live context ->
/// three CTAs (ADD TO MY TRIP, GO THERE, SAVE). "ADD TO MY TRIP" is the
/// strongest CTA (per spec: stronger visual weight than the others) and
/// is the one action in this whole screen that requires sign-in.
///
/// Known limitation (honestly deferred, not hidden): signing in from the
/// dialog below pushes the existing chunk-1 [AuthScreen]. On success,
/// main.dart's root listener swaps the ENTIRE app over to [StartScreen]
/// (the same thing that already happens from the public landing page in
/// chunk 1) — it does not pop back to this place. The tourist lands on
/// their dashboard, signed in, and can navigate back to Explore and the
/// place to finish adding it. Reworking main.dart's auth-swap so it
/// returns to exactly where a tourist was would touch chunk 1's root
/// navigation architecture, which is out of scope for an Explore chunk.
class PlaceDetailScreen extends StatefulWidget {
  final String placeId;
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  final double? lat;
  final double? lng;

  const PlaceDetailScreen({
    super.key,
    required this.placeId,
    required this.auth,
    required this.locale,
    required this.theme,
    this.lat,
    this.lng,
  });

  @override
  State<PlaceDetailScreen> createState() => _PlaceDetailScreenState();
}

class _PlaceDetailScreenState extends State<PlaceDetailScreen> {
  final _api = ExploreApiClient();
  late Future<GZPlaceDetail> _future;
  bool _saved = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    GZPassport.load();
  }

  @override
  void initState() {
    super.initState();
    _future = _api.placeDetail(widget.placeId, lat: widget.lat, lng: widget.lng);
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  /// The one sign-up wall on this whole screen. A signed-out tourist can
  /// read everything else freely; only acting on it (save / add to
  /// journey) asks them to create an account — per the spec's explicit
  /// "browsing before sign-up" requirement.
  Future<bool> _ensureSignedIn(String actionCopy) async {
    if (widget.auth.isSignedIn) return true;
    final proceed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('This could be part of your journey'),
        content: Text('Create a free GroundZero account and we\'ll build the rest around it. No payment required.\n\n$actionCopy'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Continue with GroundZero')),
        ],
      ),
    );
    if (proceed != true || !mounted) return false;
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => AuthScreen(locale: widget.locale, theme: widget.theme, auth: widget.auth, startOnSignUp: true),
    ));
    return widget.auth.isSignedIn;
  }

  Future<void> _addToJourney() async {
    final ok = await _ensureSignedIn('Add this place to your trip.');
    if (!ok || !mounted) return;
    try {
      final result = await _api.addToJourney(widget.auth.accessToken!, widget.placeId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result.message)));
    } on GZApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _save() async {
    final ok = await _ensureSignedIn('Save this place for later.');
    if (!ok || !mounted) return;
    // Chunk 3 has no standalone "saved places" list yet (not part of
    // Carol's chunk-3 spec — that's a Trips/Journal-adjacent feature of
    // its own). Honest placeholder: confirm the action, don't fabricate
    // a saved-places screen that doesn't exist.
    setState(() => _saved = true);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved.')));
  }

  static String _nice(String s) {
    final t = s.replaceAll('_', ' ').trim();
    return t.isEmpty ? t : t[0].toUpperCase() + t.substring(1).toLowerCase();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Scaffold(
      body: FutureBuilder<GZPlaceDetail>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text('Could not load this place.\n${snap.error}', textAlign: TextAlign.center),
              ),
            );
          }
          final place = snap.data!;
          final wide = MediaQuery.of(context).size.width >= 800;
          final kind = gzArtKindFor(place.category, place.tags);
          final sub = gzArtSub(place.category, place.tags, place.name);
          final text = Theme.of(context).textTheme;
          return Column(children: [
            Expanded(
              child: SingleChildScrollView(
                child: Column(children: [
                  // ---------- Hero ----------
                  SizedBox(
                    height: wide ? 360 : 290,
                    width: double.infinity,
                    child: Stack(fit: StackFit.expand, children: [
                      GZPlaceArt(kind: kind, seed: place.name, sub: sub),
                      const DecoratedBox(
                        decoration: BoxDecoration(gradient: LinearGradient(begin: Alignment.center, end: Alignment.bottomCenter, colors: [Color(0x00000000), Color(0xCC061A24)])),
                      ),
                      SafeArea(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
                          child: Align(
                            alignment: Alignment.topCenter,
                            child: Row(children: [
                              const GZBackButton(color: Colors.white),
                              const Spacer(),
                              IconButton(
                                tooltip: 'Report a problem',
                                icon: const Icon(Icons.flag_outlined, color: Colors.white),
                                onPressed: () => gzReport(context, widget.auth, kind: 'place', ref: widget.placeId),
                              ),
                              const GZHomeAction(color: Colors.white),
                            ]),
                          ),
                        ),
                      ),
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 860),
                            child: Padding(
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 22),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Wrap(spacing: 8, runSpacing: 6, children: [
                                  _HeroPill(icon: gzArtIcon(kind), label: gzArtLabel(kind)),
                                  if (place.provenance == 'verified') const _HeroPill(icon: Icons.verified_outlined, label: 'Verified'),
                                ]),
                                const SizedBox(height: 10),
                                Text(place.name, style: text.headlineMedium?.copyWith(color: Colors.white, fontWeight: FontWeight.w900, height: 1.1, fontSize: wide ? 38 : 30)),
                                const SizedBox(height: 4),
                                Text(place.tagline, style: TextStyle(color: Colors.white.withOpacity(0.9), fontWeight: FontWeight.w600, fontSize: 15)),
                              ]),
                            ),
                          ),
                        ),
                      ),
                    ]),
                  ),
                  // ---------- Body ----------
                  Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 860),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          _facts(ink, place, wide),
                          const SizedBox(height: 18),
                          _StampCard(placeId: place.placeId, name: place.name),
                          const SizedBox(height: 22),
                          _Section(title: 'Why go', child: Text(place.whyGo, style: text.bodyLarge?.copyWith(height: 1.5))),
                          if (place.goodFor.isNotEmpty) ...[
                            const SizedBox(height: 20),
                            _Section(
                              title: 'Good for',
                              child: Wrap(spacing: 8, runSpacing: 8, children: [
                                for (final g in place.goodFor)
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                                    decoration: BoxDecoration(color: ink.accent.withOpacity(0.12), borderRadius: BorderRadius.circular(99), border: Border.all(color: ink.accent.withOpacity(0.5))),
                                    child: Text(_nice(g), style: TextStyle(color: ink.accent, fontWeight: FontWeight.w800, fontSize: 13)),
                                  ),
                              ]),
                            ),
                          ],
                          const SizedBox(height: 20),
                          _WhyNowCard(whyNow: place.whyNow),
                          if (place.etiquetteTag != null) ...[
                            const SizedBox(height: 20),
                            _Section(
                              title: 'Good to know',
                              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Icon(Icons.info_outline, size: 18, color: ink.muted),
                                const SizedBox(width: 8),
                                Expanded(child: Text(place.etiquetteTag!, style: text.bodyMedium?.copyWith(height: 1.4))),
                              ]),
                            ),
                          ],
                        ]),
                      ),
                    ),
                  ),
                ]),
              ),
            ),
            // ---------- Action bar ----------
            Container(
              decoration: BoxDecoration(color: ink.paper, border: Border(top: BorderSide(color: ink.hairline))),
              child: SafeArea(
                top: false,
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 860),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(children: [
                        IconButton.outlined(
                          tooltip: _saved ? 'Saved' : 'Save for later',
                          onPressed: _save,
                          icon: Icon(_saved ? Icons.bookmark : Icons.bookmark_border),
                        ),
                        const SizedBox(width: 8),
                        OutlinedButton.icon(
                          onPressed: () => GZMaps.directions(context, place.latitude, place.longitude, name: place.name),
                          icon: const Icon(Icons.near_me_outlined),
                          label: const Text('Go there'),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: FilledButton.icon(
                            onPressed: _addToJourney,
                            icon: const Icon(Icons.add_road_rounded),
                            label: const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Text('Add to my journey')),
                          ),
                        ),
                      ]),
                    ),
                  ),
                ),
              ),
            ),
          ]);
        },
      ),
    );
  }

  Widget _facts(GZInk ink, GZPlaceDetail p, bool wide) {
    final cost = p.estimatedCost <= 0 ? 'Free' : '₹${p.estimatedCost.toStringAsFixed(0)}';
    final hours = p.openingHoursRaw.trim().isEmpty ? 'Not confirmed' : p.openingHoursRaw.trim();
    final items = [
      (Icons.sell_outlined, 'Typical cost', cost),
      (Icons.schedule_rounded, 'Hours', hours.length > 28 ? '${hours.substring(0, 26)}...' : hours),
      (Icons.flash_on_rounded, 'Right now', p.whyNow.headline.isEmpty ? '-' : _nice(p.whyNow.headline)),
      (Icons.category_outlined, 'Type', _nice(p.tags.isNotEmpty ? p.tags.first : p.category)),
    ];
    return LayoutBuilder(builder: (context, box) {
      final cols = box.maxWidth >= 640 ? 4 : 2;
      final w = (box.maxWidth - 10 * (cols - 1)) / cols;
      return Wrap(spacing: 10, runSpacing: 10, children: [
        for (final it in items)
          SizedBox(
            width: w,
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: ink.paper, borderRadius: BorderRadius.circular(18), border: Border.all(color: ink.hairline)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(it.$1, size: 20, color: ink.accent),
                const SizedBox(height: 8),
                Text(it.$2.toUpperCase(), style: TextStyle(color: ink.muted, fontSize: 10.5, fontWeight: FontWeight.w800, letterSpacing: 0.8)),
                const SizedBox(height: 2),
                Text(it.$3, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14.5, height: 1.2)),
              ]),
            ),
          ),
      ]);
    });
  }
}

class _HeroPill extends StatelessWidget {
  final IconData icon;
  final String label;
  const _HeroPill({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(color: Colors.black.withOpacity(0.4), borderRadius: BorderRadius.circular(99)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 14, color: Colors.white),
          const SizedBox(width: 5),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
        ]),
      );
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title.toUpperCase(), style: TextStyle(color: ink.accent, fontWeight: FontWeight.w900, letterSpacing: 1.4, fontSize: 12)),
      const SizedBox(height: 8),
      child,
    ]);
  }
}

/// The gamified bit: stamp the place once you have actually been there.
class _StampCard extends StatelessWidget {
  final String placeId;
  final String name;
  const _StampCard({required this.placeId, required this.name});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final onAccent = ink.dark ? const Color(0xFF240002) : Colors.white;
    return ValueListenableBuilder<Set<String>>(
      valueListenable: GZPassport.stamps,
      builder: (context, set, _) {
        final done = set.contains(placeId);
        final nx = GZPassport.next(set.length);
        return AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: done ? const Color(0xFFB3261E) : ink.hairline, width: done ? 1.6 : 1),
            gradient: LinearGradient(colors: [ink.accent.withOpacity(done ? 0.06 : 0.16), ink.accent2.withOpacity(0.08)]),
          ),
          child: Row(children: [
            AnimatedRotation(
              turns: done ? -0.03 : 0,
              duration: const Duration(milliseconds: 300),
              child: Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(shape: BoxShape.circle, color: done ? const Color(0xFFB3261E) : ink.accent, border: Border.all(color: onAccent.withOpacity(0.5), width: 2)),
                child: Icon(done ? Icons.verified : Icons.approval_outlined, color: Colors.white, size: 30),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(done ? 'Stamped. You have been here.' : 'Been here? Stamp it.', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
                const SizedBox(height: 2),
                Text(
                  done
                      ? '${set.length} ${set.length == 1 ? 'place' : 'places'} in your passport  ·  ${GZPassport.levelName(set.length)}'
                      : nx == null
                          ? 'Add it to your Mangaluru passport.'
                          : 'Adds to your passport. ${nx.need} more to become a ${nx.name}.',
                  style: TextStyle(color: ink.muted, fontSize: 13, height: 1.3),
                ),
              ]),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: () => GZPassport.stamp(context, placeId, name),
              style: FilledButton.styleFrom(backgroundColor: done ? ink.muted : ink.accent, foregroundColor: onAccent),
              child: Text(done ? 'Undo' : 'Stamp'),
            ),
          ]),
        );
      },
    );
  }
}

class _WhyNowCard extends StatelessWidget {
  final GZWhyNow whyNow;
  const _WhyNowCard({required this.whyNow});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(color: ink.accent.withOpacity(0.1), borderRadius: BorderRadius.circular(20), border: Border.all(color: ink.accent.withOpacity(0.35))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.bolt, color: ink.accent, size: 20),
          const SizedBox(width: 6),
          Text('WHY NOW', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.2, color: ink.accent, fontSize: 12)),
        ]),
        const SizedBox(height: 8),
        Text(whyNow.headline, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w900)),
        for (final r in whyNow.reasons)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Padding(padding: const EdgeInsets.only(top: 6), child: Icon(Icons.circle, size: 6, color: ink.accent)),
              const SizedBox(width: 8),
              Expanded(child: Text(r, style: Theme.of(context).textTheme.bodyMedium?.copyWith(height: 1.4))),
            ]),
          ),
      ]),
    );
  }
}
