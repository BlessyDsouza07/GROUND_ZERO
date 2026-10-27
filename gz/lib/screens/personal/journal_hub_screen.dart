import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/auth_controller.dart';
import '../../core/locale_controller.dart';
import '../../core/personal_api_client.dart';
import '../../core/theme_controller.dart';
import '../new_trip/journal_screen.dart';

/// Top-level JOURNAL entry in the sidebar — "your journeys, as memory."
/// Lists every trip that has at least one place visited (so there's
/// something real to show), newest first. Tapping one opens that trip's
/// own enhanced journal (Timeline/Scrapbook/Map + stats). Kept as its
/// own screen rather than merged into My Trips because the spec treats
/// Journal as its own top-level destination with its own visual
/// language (editorial, memory-first) — My Trips is about managing
/// journeys, Journal is about what's left of them.
class JournalHubScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const JournalHubScreen({super.key, required this.auth, required this.locale, required this.theme});

  @override
  State<JournalHubScreen> createState() => _JournalHubScreenState();
}

class _JournalHubScreenState extends State<JournalHubScreen> {
  final _api = PersonalApiClient();
  late Future<GZMyTrips> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.myTrips(widget.auth.accessToken!);
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
      appBar: AppBar(leading: const GZBackButton(), title: const Text('Journal'), actions: const [GZHomeAction()]),
      body: FutureBuilder<GZMyTrips>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) return Center(child: Text('Could not load your journal.\n${snap.error}'));
          final withMemories = [...snap.data!.upcoming, ...snap.data!.completed].where((t) => t.visitedCount > 0 || const {'active', 'paused', 'scheduled', 'confirmed'}.contains(t.status)).toList();
          if (withMemories.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'Nothing here yet. Start a trip, then capture moments as you go. Only photos you choose to add ever appear here.',
                  textAlign: TextAlign.center, style: TextStyle(color: scheme.onSurfaceVariant),
                ),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(20),
            itemCount: withMemories.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (context, i) {
              final t = withMemories[i];
              return Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.all(16),
                  leading: CircleAvatar(backgroundColor: scheme.primaryContainer, child: Icon(Icons.menu_book_outlined, color: scheme.primary)),
                  title: Text(t.coverPlaceName ?? 'Your journey', style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text('${t.visitedCount} of ${t.placeCount} places captured'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => JournalScreen(auth: widget.auth, tripId: t.tripId, locale: widget.locale, theme: widget.theme),
                  )),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
