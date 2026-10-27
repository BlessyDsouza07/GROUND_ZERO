import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/auth_controller.dart';
import 'gz_passport_banner.dart';
import 'explore_map_screen.dart';
import '../../core/explore_api_client.dart';
import '../../core/gz_consent.dart';
import '../../core/gz_location.dart';
import '../../core/gz_maps.dart';
import '../../design/gz_ink.dart';
import '../../widgets/tiara/gz_frame_card.dart';
import '../../widgets/tiara/gz_scene.dart';
import '../../core/locale_controller.dart';
import '../../core/theme_controller.dart';
import '../../widgets/groundzero/gz_section_heading.dart';
import 'explore_search_screen.dart';
import 'place_card_tile.dart';
import 'place_detail_screen.dart';
import 'experience_screen.dart';
import '../../widgets/tiara/gz_place_art.dart';

/// Chunk 3 — Explore. Structure follows the spec's 6-layer page:
/// (1) immersive hero + mood CTA, (2) mood selector, (3) GroundZero's
/// live/contextual picks ("Right Now" + "GroundZero Picks"),
/// (4) Explore by Experience, (5) Beyond the Obvious, (6) search +
/// "Happening Today" as the map/complete-discovery layer (an actual
/// in-app map view, same as itinerary_screen.dart's flutter_map, is
/// deferred here — see README_EXPLORE.md's frontend notes; the spec's
/// map is explicitly secondary, reached via a CTA, and the data each
/// place already carries lat/lng for one is in place).
///
/// Reachable both signed-in (StartScreen's sidebar) and signed-out (a
/// "Explore" entry point can be wired from the public landing page) —
/// this screen itself makes no auth-gated calls; only
/// [PlaceDetailScreen]'s Add/Save actions do.
class ExploreScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;

  const ExploreScreen({super.key, required this.auth, required this.locale, required this.theme});

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  final _api = ExploreApiClient();

  late Future<List<GZMood>> _moodsFuture;
  late Future<GZRightNow> _contextFuture;
  late Future<List<GZExperienceCategory>> _experiencesFuture;
  late Future<List<GZEvent>> _happeningFuture;
  late Future<GZSituation?> _situationFuture;

  String? _selectedMood;
  Future<List<GZPlaceCard>>? _picksFuture;
  Future<List<GZPlaceCard>>? _beyondFuture;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Every request waits briefly for the traveller's real location so the
  /// lists are near them and match the time, instead of always starting at
  /// the city centre.
  Future<T> _after<T>(Future<T> Function() f) async {
    try {
      await GZLocation.ensure().timeout(const Duration(seconds: 8));
    } on Object {/* fall back to the city centre */}
    return f();
  }

  Future<void> _enableLocation() async {
    if (!GZConsent.location) {
      final ok = await GZConsent.ask(context, widget.auth.accessToken!, 'location');
      if (!ok || !mounted) return;
    }
    await GZLocation.refresh();
    if (!mounted) return;
    if (!GZLocation.known) {
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Location is blocked'),
          content: const Text(
              'Your browser is not sharing your location. Click the location or lock icon next to the web address, choose Allow, then press Enable again. Until then GroundZero shows places around central Mangaluru.'),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
        ),
      );
    }
    if (mounted) setState(_load);
  }

  void _load() {
    _moodsFuture = _api.moods();
    _contextFuture = _after(() => _api.rightNow());
    _situationFuture = _after(() => _api.situation()).then<GZSituation?>((v) => v).catchError((_) => null);
    _experiencesFuture = _after(() => _api.experienceCategories());
    _happeningFuture = _api.happeningToday();
    _beyondFuture = _after(() => _api.beyondTheObvious());
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  void _selectMood(String slug) {
    setState(() {
      _selectedMood = slug;
      _picksFuture = _after(() => _api.picks(slug));
    });
  }

  Future<void> _openTreasureMap() async {
    final cards = <GZPlaceCard>[];
    try {
      for (final cat in await _experiencesFuture) {
        cards.addAll(cat.preview);
      }
      cards.addAll(await _beyondFuture!);
    } on Object {/* show whatever loaded */}
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => ExploreMapScreen(cards: cards, onOpenPlace: _openPlace)));
  }

  void _openPlace(GZPlaceCard card) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlaceDetailScreen(
        placeId: card.placeId,
        auth: widget.auth,
        locale: widget.locale,
        theme: widget.theme,
      ),
    ));
  }

  void _openSearch() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ExploreSearchScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: 220,
            backgroundColor: scheme.primary,
            automaticallyImplyLeading: false,
            leading: const GZBackButton(color: Colors.white),
            actions: [
              IconButton(tooltip: 'Search', icon: const Icon(Icons.search, color: Colors.white), onPressed: _openSearch),
              const GZHomeAction(color: Colors.white),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: GZScene(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 60, 20, 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      const Text(
                        'EXPLORE',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 30, letterSpacing: 1),
                      ),
                      const Text(
                        'MANGALURU, DIFFERENTLY',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16, letterSpacing: 1.2),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(child: _SituationPanel(future: _situationFuture, onTapCard: _openPlace, onEnable: _enableLocation)),
          const SliverToBoxAdapter(child: GZPassportBanner()),
          SliverToBoxAdapter(child: _TreasureMapEntry(onOpen: _openTreasureMap)),
          SliverToBoxAdapter(child: _RightNowPanel(future: _contextFuture)),
          SliverToBoxAdapter(child: _MoodSelector(moodsFuture: _moodsFuture, selected: _selectedMood, onSelect: _selectMood)),
          if (_selectedMood != null)
            SliverToBoxAdapter(
              child: _PicksSection(mood: _selectedMood!, future: _picksFuture!, onTapCard: _openPlace),
            ),
          SliverToBoxAdapter(child: _HappeningTodaySection(future: _happeningFuture)),
          SliverToBoxAdapter(
            child: _InterstitialStatement(text: 'NOT EVERYTHING WORTH SEEING IS OBVIOUS.'),
          ),
          SliverToBoxAdapter(
            child: _BeyondTheObviousSection(future: _beyondFuture!, onTapCard: _openPlace),
          ),
          SliverToBoxAdapter(
            child: _ExperiencesSection(future: _experiencesFuture, onTapCard: _openPlace, auth: widget.auth, locale: widget.locale, theme: widget.theme),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 32)),
        ],
      ),
    );
  }
}

// DESIGN SYSTEM PASS (6th audit response follow-up, Oct 2026): this
// screen's own `_SectionHeader` is replaced by the shared
// `GZSectionHeading` (widgets/groundzero/gz_section_heading.dart) —
// same look (a small bold wide-tracked label, optional caption-style
// subtitle), now using the `section`/`caption` typography tokens from
// `design/gz_typography.dart` instead of ad hoc `titleLarge`/`bodySmall`
// overrides, and shared with the rest of the app rather than redefined
// per screen.

class _InterstitialStatement extends StatelessWidget {
  final String text;
  const _InterstitialStatement({required this.text});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 36),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: scheme.primary, height: 1.3),
      ),
    );
  }
}

/// "RIGHT NOW IN MANGALURU" — weather/tide/sunset/events, with
/// weather/tide actively explaining a recommendation rather than just
/// displaying a number (per spec: "don't merely show weather, use
/// weather to explain the recommendation").
class _RightNowPanel extends StatelessWidget {
  final Future<GZRightNow> future;
  const _RightNowPanel({required this.future});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return FutureBuilder<GZRightNow>(
      future: future,
      builder: (context, snap) {
        if (!snap.hasData) {
          return const Padding(padding: EdgeInsets.all(20), child: LinearProgressIndicator());
        }
        final rn = snap.data!;
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
          child: Card(
            color: scheme.primaryContainer.withOpacity(0.4),
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(rn.headline, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 18,
                    runSpacing: 8,
                    children: [
                      _StatChip(
                        icon: Icons.thermostat,
                        text: rn.weatherAvailable
                            ? '${rn.temperatureCelsius?.round()}°C · ${rn.condition}'
                            : 'Weather unavailable right now',
                      ),
                      _StatChip(
                        icon: Icons.waves,
                        text: rn.tideAvailable ? 'Tide ${rn.tideState}' : 'Tide data unavailable right now',
                      ),
                      _StatChip(
                        icon: Icons.wb_twilight,
                        text: rn.minutesToSunset > 0 ? 'Sunset in ${rn.minutesToSunset} min' : 'Past sunset',
                      ),
                      if (rn.eventsTodayCount != null)
                        _StatChip(icon: Icons.event, text: '${rn.eventsTodayCount} events today'),
                    ],
                  ),
                  if (rn.weatherNote != null) ...[
                    const SizedBox(height: 10),
                    Text(rn.weatherNote!, style: Theme.of(context).textTheme.bodySmall),
                  ],
                  if (rn.tideNote != null) ...[
                    const SizedBox(height: 4),
                    Text(rn.tideNote!, style: Theme.of(context).textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String text;
  const _StatChip({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: scheme.primary),
        const SizedBox(width: 4),
        Text(text, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

/// "WHAT ARE YOU IN THE MOOD FOR?" — large interactive choices, not tiny
/// category chips (per spec). Selecting one changes the page's own
/// content (the GroundZero Picks section below), not just a filter.
class _MoodSelector extends StatelessWidget {
  final Future<List<GZMood>> moodsFuture;
  final String? selected;
  final ValueChanged<String> onSelect;
  const _MoodSelector({required this.moodsFuture, required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const GZSectionHeading('WHAT ARE YOU IN THE MOOD FOR?'),
        FutureBuilder<List<GZMood>>(
          future: moodsFuture,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: LinearProgressIndicator());
            }
            return SizedBox(
              height: 64,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                itemCount: snap.data!.length,
                separatorBuilder: (_, __) => const SizedBox(width: 10),
                itemBuilder: (context, i) {
                  final mood = snap.data![i];
                  final isSelected = selected == mood.slug;
                  return ChoiceChip(
                    label: Text(mood.label.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.w700)),
                    selected: isSelected,
                    selectedColor: scheme.primary,
                    labelStyle: TextStyle(color: isSelected ? Colors.white : null),
                    onSelected: (_) => onSelect(mood.slug),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  );
                },
              ),
            );
          },
        ),
      ],
    );
  }
}

/// "GROUNDZERO PICKS" — never labeled "Recommended places" per spec.
class _PicksSection extends StatelessWidget {
  final String mood;
  final Future<List<GZPlaceCard>> future;
  final void Function(GZPlaceCard) onTapCard;
  const _PicksSection({required this.mood, required this.future, required this.onTapCard});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GZSectionHeading('GROUNDZERO PICKS', subtitle: 'For your "${mood.replaceAll('_', ' ')}" mood, right now'),
        FutureBuilder<List<GZPlaceCard>>(
          future: future,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: LinearProgressIndicator());
            }
            if (snap.data!.isEmpty) {
              return const Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: Text('Nothing matched this mood nearby yet.'));
            }
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: AsymmetricCardGrid(cards: snap.data!, onTapCard: onTapCard),
            );
          },
        ),
      ],
    );
  }
}

class _BeyondTheObviousSection extends StatelessWidget {
  final Future<List<GZPlaceCard>> future;
  final void Function(GZPlaceCard) onTapCard;
  const _BeyondTheObviousSection({required this.future, required this.onTapCard});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const GZSectionHeading('BEYOND THE OBVIOUS', subtitle: 'Verified places almost nobody writes about'),
        FutureBuilder<List<GZPlaceCard>>(
          future: future,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: LinearProgressIndicator());
            }
            return GZCardRow(cards: snap.data!, featured: true, minCardWidth: 270, onTapCard: onTapCard);
          },
        ),
      ],
    );
  }
}

class _ExperiencesSection extends StatelessWidget {
  final Future<List<GZExperienceCategory>> future;
  final void Function(GZPlaceCard) onTapCard;
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const _ExperiencesSection({required this.future, required this.onTapCard, required this.auth, required this.locale, required this.theme});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const GZSectionHeading('EXPLORE BY EXPERIENCE'),
        FutureBuilder<List<GZExperienceCategory>>(
          future: future,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: LinearProgressIndicator());
            }
            return Column(
              children: snap.data!.where((c) => c.preview.isNotEmpty).map((cat) {
                final ink = GZInk.of(context);
                final kind = switch (cat.slug) {
                  'coast' => GZArtKind.coast,
                  'food_flavours' => GZArtKind.food,
                  'culture_heritage' || 'faith_architecture' => GZArtKind.heritage,
                  'nature' || 'quiet_places' => GZArtKind.nature,
                  'local_life' => GZArtKind.market,
                  _ => GZArtKind.generic,
                };
                return Padding(
                  padding: const EdgeInsets.only(bottom: 26),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        child: Row(children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: ink.accent, width: 1.6)),
                            child: Icon(gzArtIcon(kind), color: ink.accent, size: 20),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(cat.label, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                              Text('${cat.totalCount} places', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: ink.muted)),
                            ]),
                          ),
                          TextButton(
                            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) => ExperienceScreen(category: cat, auth: auth, locale: locale, theme: theme),
                            )),
                            child: const Text('See all'),
                          ),
                        ]),
                      ),
                      GZCardRow(cards: cat.preview, onTapCard: onTapCard),
                    ],
                  ),
                );
              }).toList(),
            );
          },
        ),
      ],
    );
  }
}

class _HappeningTodaySection extends StatelessWidget {
  final Future<List<GZEvent>> future;
  const _HappeningTodaySection({required this.future});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<GZEvent>>(
      future: future,
      builder: (context, snap) {
        if (!snap.hasData || snap.data!.isEmpty) return const SizedBox.shrink();
        final scheme = Theme.of(context).colorScheme;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const GZSectionHeading('HAPPENING TODAY'),
            ...snap.data!.take(5).map((e) => ListTile(
                  leading: Icon(Icons.event_available, color: scheme.primary),
                  title: Text(e.title),
                  subtitle: Text([
                    if (e.startAt != null) '${e.startAt!.hour.toString().padLeft(2, '0')}:${e.startAt!.minute.toString().padLeft(2, '0')}',
                    if (e.venue != null) e.venue!,
                  ].join(' · ')),
                )),
          ],
        );
      },
    );
  }
}


/// "Where you are, what you need" — reads the traveller's real position and
/// the clock. At a bus stand late at night: rooms that are open. Already at
/// a stay: no rest-stop noise. Closed places never appear.
class _SituationPanel extends StatelessWidget {
  final Future<GZSituation?> future;
  final void Function(GZPlaceCard) onTapCard;
  final Future<void> Function() onEnable;
  const _SituationPanel({required this.future, required this.onTapCard, required this.onEnable});

  IconData _icon(String kind) => switch (kind) {
        'stay' => Icons.bed_outlined,
        'rest' => Icons.event_seat_outlined,
        'food' => Icons.restaurant_outlined,
        _ => Icons.explore_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return FutureBuilder<GZSituation?>(
      future: future,
      builder: (context, snap) {
        final sit = snap.data;
        if (sit == null) {
          if (snap.connectionState != ConnectionState.done) return const SizedBox(height: 4);
          return Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
            child: GZFrameCard(
              radius: 18,
              shadowOffset: 0,
              padding: const EdgeInsets.all(16),
              child: Row(children: [
                Icon(Icons.location_off_outlined, color: ink.muted),
                const SizedBox(width: 12),
                Expanded(
                  child: Text('Turn on location to see what is open near you right now.', style: text.bodyMedium?.copyWith(color: ink.muted)),
                ),
                TextButton(onPressed: onEnable, child: const Text('Enable')),
              ]),
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
          child: GZFrameCard(
            radius: 20,
            shadowOffset: 0,
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Icon(_icon(sit.kind), color: ink.accent),
                  const SizedBox(width: 10),
                  Expanded(child: Text(sit.headline, style: text.titleMedium?.copyWith(fontWeight: FontWeight.w800))),
                ]),
                const SizedBox(height: 4),
                Text(sit.detail, style: text.bodyMedium?.copyWith(color: ink.muted)),
                if (!sit.approx && GZLocation.known)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      'Your position: ${GZLocation.lat!.toStringAsFixed(5)}, ${GZLocation.lng!.toStringAsFixed(5)}'
                      '${GZLocation.accuracy != null ? ' (±${GZLocation.accuracy!.round()} m)' : ''}',
                      style: text.bodySmall?.copyWith(color: ink.muted, fontSize: 11.5),
                    ),
                  ),
                if (sit.approx)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(children: [
                      Icon(Icons.location_searching, size: 16, color: ink.muted),
                      const SizedBox(width: 6),
                      Expanded(child: Text('Showing central Mangaluru. Share your location for places near you.', style: text.bodySmall?.copyWith(color: ink.muted))),
                      TextButton(onPressed: onEnable, child: const Text('Enable')),
                    ]),
                  ),
                if (sit.suggestions.isNotEmpty) const SizedBox(height: 12),
                for (final c in sit.suggestions)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(14),
                      onTap: () => onTapCard(c),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: ink.border.withOpacity(0.35)),
                        ),
                        child: Row(children: [
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(c.name, style: text.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                              const SizedBox(height: 2),
                              Text(
                                '${c.distanceKm != null ? '${c.distanceKm!.toStringAsFixed(1)} km · ' : ''}${c.openLabel ?? ''}',
                                style: text.bodySmall?.copyWith(color: ink.muted),
                              ),
                            ]),
                          ),
                          IconButton(
                            tooltip: 'Take me there',
                            icon: Icon(Icons.directions_outlined, color: ink.accent),
                            onPressed: () => GZMaps.directions(context, c.latitude, c.longitude, name: c.name),
                          ),
                        ]),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}


class _TreasureMapEntry extends StatelessWidget {
  final VoidCallback onOpen;
  const _TreasureMapEntry({required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onOpen,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            gradient: const LinearGradient(colors: [Color(0xFF06384F), Color(0xFF0699BA)]),
          ),
          child: Row(children: [
            const Icon(Icons.map_outlined, color: Color(0xFFFBF3E2), size: 30),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Open the treasure map', style: TextStyle(color: Color(0xFFFBF3E2), fontWeight: FontWeight.w900, fontSize: 17)),
                const SizedBox(height: 2),
                Text('See everything on one chart. Stamp places to clear the fog.', style: TextStyle(color: const Color(0xFFFBF3E2).withOpacity(0.85), fontSize: 13)),
              ]),
            ),
            Icon(Icons.arrow_forward_rounded, color: ink.dark ? const Color(0xFFFFC136) : const Color(0xFFFBF3E2)),
          ]),
        ),
      ),
    );
  }
}
