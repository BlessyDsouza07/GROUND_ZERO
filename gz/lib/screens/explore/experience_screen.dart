import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/explore_api_client.dart';
import '../../core/locale_controller.dart';
import '../../core/theme_controller.dart';
import '../../design/gz_ink.dart';
import '../../widgets/gz_nav.dart';
import 'place_card_tile.dart';
import 'place_detail_screen.dart';

/// "See all" for one experience (Coast, Food, Heritage…), as a tidy grid.
class ExperienceScreen extends StatefulWidget {
  final GZExperienceCategory category;
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const ExperienceScreen({super.key, required this.category, required this.auth, required this.locale, required this.theme});

  @override
  State<ExperienceScreen> createState() => _ExperienceScreenState();
}

class _ExperienceScreenState extends State<ExperienceScreen> {
  final _api = ExploreApiClient();
  late Future<List<GZPlaceCard>> _future = _api.experienceCategory(widget.category.slug, limit: 60);
  bool _openOnly = false;

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  void _open(GZPlaceCard c) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlaceDetailScreen(placeId: c.placeId, auth: widget.auth, locale: widget.locale, theme: widget.theme),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: Text(widget.category.label), actions: const [GZHomeAction()]),
      body: FutureBuilder<List<GZPlaceCard>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) {
            final m = snap.error is GZApiException ? (snap.error as GZApiException).message : 'Could not load these places.';
            return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(m),
              const SizedBox(height: 10),
              OutlinedButton(onPressed: () => setState(() => _future = _api.experienceCategory(widget.category.slug, limit: 60)), child: const Text('Try again')),
            ]));
          }
          var cards = snap.data ?? const <GZPlaceCard>[];
          if (_openOnly) cards = cards.where((c) => c.openState == 'open').toList();
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1100),
              child: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 40), children: [
                Text('${widget.category.totalCount} places', style: text.bodyMedium?.copyWith(color: ink.muted)),
                const SizedBox(height: 10),
                Wrap(spacing: 8, children: [
                  FilterChip(label: const Text('Open now'), selected: _openOnly, onSelected: (v) => setState(() => _openOnly = v)),
                ]),
                const SizedBox(height: 16),
                if (cards.isEmpty)
                  Padding(padding: const EdgeInsets.symmetric(vertical: 40), child: Center(child: Text('Nothing open right now in this group.', style: text.bodyMedium)))
                else
                  AsymmetricCardGrid(cards: cards, onTapCard: _open),
              ]),
            ),
          );
        },
      ),
    );
  }
}
