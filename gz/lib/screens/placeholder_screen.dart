import 'package:flutter/material.dart';

import '../core/locale_controller.dart';

/// Content-only "coming soon" panel used for every sidebar destination
/// that hasn't been built yet (New Trip, Explore, Talk to Guide, Trips,
/// My Journal, Notifications, Contributions). Carol described the home
/// page and the sidebar in this chunk; each of these gets its own real
/// screen in a later chunk.
class ComingSoonPanel extends StatelessWidget {
  final LocaleController locale;
  final IconData icon;
  final String title;

  const ComingSoonPanel({super.key, required this.locale, required this.icon, required this.title});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(color: scheme.primary.withOpacity(0.10), shape: BoxShape.circle),
              child: Icon(icon, size: 40, color: scheme.primary),
            ),
            const SizedBox(height: 20),
            Text(title, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(t('soon_t'), style: Theme.of(context).textTheme.titleSmall?.copyWith(color: scheme.primary)),
            const SizedBox(height: 8),
            Text(
              t('soon_d'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
