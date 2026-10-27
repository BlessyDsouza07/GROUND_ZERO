import 'package:flutter/material.dart';

import '../../design/gz_ink.dart';
import 'gz_footer.dart';
import 'gz_reveal.dart';
import 'gz_scene.dart';

/// Shared shell for public inner pages (About, How it works): a painted
/// header band with a big lowercase title, the body, then the footer.
class GZPageShell extends StatelessWidget {
  final String kicker;
  final String title;
  final String? subtitle;
  final List<Widget> children;
  final String footerCredit;
  final List<(String, VoidCallback)> footerLinks;

  const GZPageShell({
    super.key,
    required this.kicker,
    required this.title,
    this.subtitle,
    required this.children,
    required this.footerCredit,
    required this.footerLinks,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final wide = MediaQuery.of(context).size.width >= 760;
    return SingleChildScrollView(
      child: Column(
        children: [
          SizedBox(
            height: wide ? 380 : 330,
            width: double.infinity,
            child: GZScene(
              child: Padding(
                padding: EdgeInsets.fromLTRB(24, 96, 24, wide ? 80 : 64),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 980),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: ink.paper,
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(color: ink.hairline, width: 1),
                            ),
                            child: Text(kicker.toUpperCase(), style: text.labelMedium?.copyWith(color: ink.text, letterSpacing: 2)),
                          ),
                          const SizedBox(height: 14),
                          Text(
                            title,
                            style: (wide ? text.displayMedium : text.displaySmall)?.copyWith(
                              color: const Color(0xFFF7F4EE),
                              shadows: [Shadow(color: Color(0x55000000), blurRadius: 16, offset: Offset(0, 3))],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
          Container(
            width: double.infinity,
            padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 64 : 40),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 860),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (subtitle != null) ...[
                      GZReveal(child: Text(subtitle!, style: text.bodyLarge?.copyWith(fontSize: 18, color: ink.text))),
                      const SizedBox(height: 36),
                    ],
                    ...children,
                  ],
                ),
              ),
            ),
          ),
          GZFooter(credit: footerCredit, explore: footerLinks),
        ],
      ),
    );
  }
}
