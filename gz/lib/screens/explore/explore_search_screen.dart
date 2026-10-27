import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/explore_api_client.dart';
import '../../core/locale_controller.dart';
import '../../core/theme_controller.dart';
import 'place_card_tile.dart';
import 'place_detail_screen.dart';

/// Full search UI: recent searches (device-local, no account needed),
/// suggested searches, then results. Per spec: "Discovery first,
/// precision second" — filters (Distance, Category, Open now) live
/// behind a FILTER button rather than being forced before search.
class ExploreSearchScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const ExploreSearchScreen({super.key, required this.auth, required this.locale, required this.theme});

  @override
  State<ExploreSearchScreen> createState() => _ExploreSearchScreenState();
}

class _ExploreSearchScreenState extends State<ExploreSearchScreen> {
  final _api = ExploreApiClient();
  final _controller = TextEditingController();
  final List<String> _recent = [];
  List<GZPlaceCard>? _results;
  List<String> _suggested = [];
  bool _openNowOnly = false;
  bool _loading = false;

  @override
  void dispose() {
    _api.close();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _runSearch(String query) async {
    if (query.trim().isEmpty) return;
    setState(() => _loading = true);
    try {
      final (results, suggested) = await _api.search(query, openNow: _openNowOnly);
      setState(() {
        _results = results;
        _suggested = suggested;
        if (!_recent.contains(query)) _recent.insert(0, query);
        if (_recent.length > 6) _recent.removeLast();
      });
    } on GZApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openPlace(GZPlaceCard card) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlaceDetailScreen(placeId: card.placeId, auth: widget.auth, locale: widget.locale, theme: widget.theme),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        title: TextField(
          controller: _controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'Search places...', border: InputBorder.none),
          onSubmitted: _runSearch,
        ),
        actions: [
          const GZHomeAction(),
          IconButton(
            icon: Icon(_openNowOnly ? Icons.filter_alt : Icons.filter_alt_outlined),
            tooltip: 'Open now',
            onPressed: () {
              setState(() => _openNowOnly = !_openNowOnly);
              if (_controller.text.isNotEmpty) _runSearch(_controller.text);
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _results == null
              ? _buildPrompt(context)
              : _buildResults(context),
    );
  }

  Widget _buildPrompt(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (_recent.isNotEmpty) ...[
          Text('RECENT', style: Theme.of(context).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: _recent.map((r) => ActionChip(label: Text(r), onPressed: () => _runSearch(r))).toList()),
          const SizedBox(height: 24),
        ],
        Text('SUGGESTED', style: Theme.of(context).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: ['Quiet places', 'Sunset spots', 'Rain-friendly', 'Family', 'Local food', 'Beaches']
              .map((s) => ActionChip(label: Text(s), onPressed: () => _runSearch(s)))
              .toList(),
        ),
      ],
    );
  }

  Widget _buildResults(BuildContext context) {
    if (_results!.isEmpty) {
      return Center(child: Text('No places matched "${_controller.text}".'));
    }
    return ListView.separated(
      padding: const EdgeInsets.all(20),
      itemCount: _results!.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, i) => PlaceCardTile(card: _results![i], onTap: () => _openPlace(_results![i]), height: 100),
    );
  }
}
