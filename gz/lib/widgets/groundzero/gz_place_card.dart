import 'package:flutter/material.dart';

import '../../design/gz_radii.dart';
import '../../design/gz_shadows.dart';
import '../../design/gz_spacing.dart';
import '../../design/gz_typography.dart';

/// GroundZero's place card — the shared visual chrome (image area,
/// verified badge, fit%, title, tag line, soft shadow) used everywhere
/// a place is shown as a card.
///
/// Named `GZPlaceCardView` rather than `GZPlaceCard` because
/// `core/explore_api_client.dart` already defines a `GZPlaceCard` data
/// class (the place record itself) — this widget deliberately takes
/// plain parameters instead of that data object, so the design-system
/// layer doesn't import a specific screen's API client. Screens adapt
/// their own data into these parameters (see
/// `screens/explore/place_card_tile.dart`, which wraps this with the
/// explore-specific `GZPlaceCard` → icon-by-category mapping it already
/// had).
///
/// No real photography exists for the Master Data places yet (see
/// README_EXPLORE.md / the 6th-pass README changelog) — `imageBuilder`
/// is required precisely so a caller can't skip past that and must
/// supply *something* for the image area, honest branded fallback
/// included; this widget never fabricates a photo itself.
class GZPlaceCardView extends StatelessWidget {
  final WidgetBuilder imageBuilder;
  final String title;
  final String? tagLine;
  final int? fitPercent;
  final bool verified;
  final VoidCallback onTap;
  final double height;

  const GZPlaceCardView({
    super.key,
    required this.imageBuilder,
    required this.title,
    required this.onTap,
    this.tagLine,
    this.fitPercent,
    this.verified = false,
    this.height = 190,
  });

  @override
  Widget build(BuildContext context) {
    final type = GZTypography.of(context);
    final brightness = Theme.of(context).brightness;
    return InkWell(
      onTap: onTap,
      borderRadius: GZRadii.lgRadius,
      child: Container(
        decoration: BoxDecoration(borderRadius: GZRadii.lgRadius, boxShadow: GZShadows.resting(brightness)),
        child: ClipRRect(
          borderRadius: GZRadii.lgRadius,
          child: SizedBox(
            height: height,
            child: Stack(
              fit: StackFit.expand,
              children: [
                Builder(builder: imageBuilder),
                // Dark gradient so overlay text stays legible on any image.
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Colors.transparent, Colors.black.withOpacity(0.65)],
                        stops: const [0.4, 1.0],
                      ),
                    ),
                  ),
                ),
                if (fitPercent != null)
                  Positioned(
                    top: GZSpacing.xs,
                    right: GZSpacing.xs,
                    child: _Badge(text: '$fitPercent% FIT', color: Colors.black.withOpacity(0.55)),
                  ),
                if (verified)
                  Positioned(
                    top: GZSpacing.xs,
                    left: GZSpacing.xs,
                    child: _Badge(text: '✓ VERIFIED', color: Colors.black.withOpacity(0.45)),
                  ),
                Positioned(
                  left: GZSpacing.sm,
                  right: GZSpacing.sm,
                  bottom: GZSpacing.xs,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: type.cardTitle.copyWith(color: Colors.white),
                      ),
                      if (tagLine != null && tagLine!.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(tagLine!, style: type.metadata.copyWith(color: Colors.white.withOpacity(0.85))),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  const _Badge({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: color, borderRadius: GZRadii.smRadius),
      child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
    );
  }
}
