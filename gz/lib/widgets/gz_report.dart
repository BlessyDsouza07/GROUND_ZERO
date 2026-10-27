import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/hive_api_client.dart';

/// "Report a problem" for places, photos, tips and stories. Reports go to
/// the review queue; for danger the sheet points to 112.
Future<void> gzReport(BuildContext context, AuthController auth, {required String kind, required String ref}) async {
  if (!auth.isSignedIn) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sign in to report something.')));
    return;
  }
  const reasons = [
    ('privacy', 'Shows someone\'s private details or face'),
    ('unsafe', 'Unsafe or dangerous'),
    ('inaccurate', 'Wrong or out of date'),
    ('inappropriate', 'Offensive or inappropriate'),
    ('other', 'Something else'),
  ];
  final picked = await showModalBottomSheet<String>(
    context: context,
    builder: (ctx) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 18, 20, 4),
          child: Align(alignment: Alignment.centerLeft, child: Text('Report a problem', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
          child: Align(alignment: Alignment.centerLeft, child: Text('In immediate danger? Call 112.')),
        ),
        for (final r in reasons) ListTile(title: Text(r.$2), onTap: () => Navigator.pop(ctx, r.$1)),
      ]),
    ),
  );
  if (picked == null || !context.mounted) return;
  final api = HiveApiClient();
  try {
    await api.report(auth.accessToken!, kind: kind, ref: ref, reason: picked);
    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Thanks. We\'ll review it.')));
  } on GZApiException catch (e) {
    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
  } finally {
    api.close();
  }
}
