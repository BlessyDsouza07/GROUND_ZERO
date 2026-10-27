import 'package:flutter/material.dart';

import '../../design/gz_spacing.dart';
import '../../design/gz_typography.dart';

/// GroundZero's empty-state — one consistent look for "nothing here
/// yet" across the app (My Trips with no journeys, Journal with no
/// photos, a search with no results), instead of each screen writing
/// its own centered `Text`. An icon, a short message, and an optional
/// action — nothing more; the brief's "calm, intelligent" tone applies
/// here too, so this deliberately doesn't try to be cute or playful.
class GZEmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  const GZEmptyState({
    super.key,
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    final type = GZTypography.of(context);
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(GZSpacing.xl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: scheme.onSurfaceVariant.withOpacity(0.6)),
          const SizedBox(height: GZSpacing.md),
          Text(message, textAlign: TextAlign.center, style: type.body.copyWith(color: scheme.onSurfaceVariant)),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: GZSpacing.md),
            OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}
