import 'package:flutter/material.dart';

import '../../design/gz_ink.dart';
import 'gz_scene.dart';

/// Page footer in the Tiara manner: a painted skyline/sea band, then
/// EXPLORE / CONNECT columns and the credit line.
class GZFooter extends StatelessWidget {
  final String credit;
  final List<(String, VoidCallback)> explore;

  const GZFooter({super.key, required this.credit, required this.explore});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final wide = MediaQuery.of(context).size.width >= 760;

    Widget column(String title, List<Widget> children) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: text.labelMedium?.copyWith(color: ink.accent, letterSpacing: 2.4, fontWeight: FontWeight.w700)),
            const SizedBox(height: 14),
            ...children,
          ],
        );

    Widget link(String label, VoidCallback onTap) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: InkWell(
            onTap: onTap,
            child: Text(label, style: text.bodyLarge?.copyWith(color: ink.text)),
          ),
        );

    final exploreCol = column('EXPLORE', [for (final e in explore) link(e.$1, e.$2)]);
    final connectCol = column('BUILT FOR', [
      Text('Mangaluru, Karnataka', style: text.bodyLarge?.copyWith(color: ink.text)),
      const SizedBox(height: 6),
      Text('12.87° N · 74.84° E', style: text.labelSmall?.copyWith(color: ink.muted)),
      const SizedBox(height: 6),
      Text('English · ಕನ್ನಡ · हिन्दी · தமிழ் · తెలుగు', style: text.bodyMedium?.copyWith(color: ink.muted)),
    ]);

    return Container(
      color: ink.paper,
      child: Column(
        children: [
          SizedBox(
            height: wide ? 220 : 160,
            width: double.infinity,
            child: const GZScene(loop: Duration(seconds: 90)),
          ),
          Container(
            width: double.infinity,
            decoration: BoxDecoration(color: ink.paper, border: Border(top: BorderSide(color: ink.hairline, width: 1))),
            padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 44 : 32),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('groundzero', style: text.displaySmall?.copyWith(color: ink.text, letterSpacing: -1.5)),
                    const SizedBox(height: 28),
                    if (wide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [Expanded(child: exploreCol), Expanded(child: connectCol)],
                      )
                    else ...[exploreCol, const SizedBox(height: 24), connectCol],
                    const SizedBox(height: 28),
                    Divider(color: ink.border.withOpacity(0.5), height: 1),
                    const SizedBox(height: 16),
                    Text(credit, style: text.labelSmall?.copyWith(color: ink.muted)),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
