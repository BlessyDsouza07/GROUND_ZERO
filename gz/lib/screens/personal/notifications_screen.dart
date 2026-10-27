import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/auth_controller.dart';
import '../../core/personal_api_client.dart';

/// NOTIFICATIONS — explicitly not a dump. Four categories, grouped, each
/// one already bundled server-side (personal/service.py) from real data
/// (next-stop distance + sunset proximity + budget, not three separate
/// pings). An empty category is simply not shown — never padded with
/// filler to look busy.
class NotificationsScreen extends StatefulWidget {
  final AuthController auth;
  const NotificationsScreen({super.key, required this.auth});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

const _kCategoryOrder = ['NOW', 'YOUR_JOURNEY', 'AROUND_YOU', 'GROUNDZERO'];
const _kCategoryLabels = {
  'NOW': 'NOW', 'YOUR_JOURNEY': 'YOUR JOURNEY', 'AROUND_YOU': 'AROUND YOU', 'GROUNDZERO': 'GROUNDZERO',
};
const _kCategoryIcons = {
  'NOW': Icons.bolt, 'YOUR_JOURNEY': Icons.route_outlined, 'AROUND_YOU': Icons.near_me_outlined, 'GROUNDZERO': Icons.volunteer_activism_outlined,
};

class _NotificationsScreenState extends State<NotificationsScreen> {
  final _api = PersonalApiClient();
  late Future<List<GZNotification>> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.notifications(widget.auth.accessToken!);
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
      appBar: AppBar(leading: const GZBackButton(), title: const Text('Notifications'), actions: const [GZHomeAction()]),
      body: FutureBuilder<List<GZNotification>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) return Center(child: Text('Could not load notifications.\n${snap.error}'));
          final items = snap.data!;
          if (items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text('Nothing worth telling you right now — we\'ll only reach out when it genuinely helps.',
                    textAlign: TextAlign.center, style: TextStyle(color: scheme.onSurfaceVariant)),
              ),
            );
          }
          final byCategory = <String, List<GZNotification>>{};
          for (final n in items) {
            byCategory.putIfAbsent(n.category, () => []).add(n);
          }
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              for (final cat in _kCategoryOrder)
                if (byCategory[cat]?.isNotEmpty ?? false) ...[
                  Row(children: [
                    Icon(_kCategoryIcons[cat], size: 16, color: scheme.primary),
                    const SizedBox(width: 6),
                    Text(_kCategoryLabels[cat]!, style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12, color: scheme.onSurfaceVariant)),
                  ]),
                  const SizedBox(height: 10),
                  for (final n in byCategory[cat]!) ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(n.headline, style: const TextStyle(fontWeight: FontWeight.w800)),
                            const SizedBox(height: 4),
                            Text(n.body, style: TextStyle(color: scheme.onSurfaceVariant)),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],
                  const SizedBox(height: 14),
                ],
            ],
          );
        },
      ),
    );
  }
}
