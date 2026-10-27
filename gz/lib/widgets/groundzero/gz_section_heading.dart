import 'package:flutter/material.dart';

import '../../design/gz_spacing.dart';
import '../../design/gz_typography.dart';

/// GroundZero's section heading — the `section` typography tier
/// (`GZTypography.section`: small, bold, wide-tracked caps) applied
/// consistently, with an optional one-line subtitle in `caption`.
///
/// Replaces each screen's own ad hoc `_SectionHeader` private widget
/// (explore_screen.dart had one; other screens had their own close
/// variants) with a single shared component, per the production-
/// candidate brief: "the whole application should use GZSectionHeading…
/// that is how you make the entire application look like one product."
class GZSectionHeading extends StatelessWidget {
  final String title;
  final String? subtitle;
  final EdgeInsetsGeometry padding;

  const GZSectionHeading(
    this.title, {
    super.key,
    this.subtitle,
    this.padding = const EdgeInsets.fromLTRB(GZSpacing.md, GZSpacing.lg, GZSpacing.md, GZSpacing.sm),
  });

  @override
  Widget build(BuildContext context) {
    final type = GZTypography.of(context);
    return Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: type.section),
          if (subtitle != null)
            Padding(
              padding: const EdgeInsets.only(top: GZSpacing.xxs),
              child: Text(subtitle!, style: type.caption),
            ),
        ],
      ),
    );
  }
}
