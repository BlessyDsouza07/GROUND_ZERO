import 'package:flutter/material.dart';

import '../../core/gz_consent.dart';
import '../../core/gz_passport.dart';
import '../../core/hive_api_client.dart';
import '../../core/explore_api_client.dart';
import '../../core/gz_maps.dart';
import '../../design/gz_ink.dart';
import '../../widgets/tiara/gz_place_art.dart';

/// A place, drawn as a small "travel ticket": illustrated cover on top, then
/// the name (up to two lines), one quiet meta line, and an honest open-status
/// line. Nothing is laid over the text, so it stays readable at any width.
///
/// [height] below ~130 switches to a compact horizontal row (used in lists).
/// The cover is an illustration of the *kind* of place, never a photo of it.
class PlaceCardTile extends StatefulWidget {
  final GZPlaceCard card;
  final VoidCallback onTap;
  final double height;
  final bool featured;

  const PlaceCardTile({super.key, required this.card, required this.onTap, this.height = 260, this.featured = false});

  @override
  State<PlaceCardTile> createState() => _PlaceCardTileState();
}

class _PlaceCardTileState extends State<PlaceCardTile> with SingleTickerProviderStateMixin {
  bool _hover = false;
  Offset _shift = Offset.zero;
  late final AnimationController _anim = AnimationController(vsync: this, duration: const Duration(seconds: 6));

  @override
  void initState() {
    super.initState();
    GZPassport.load();
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  void _setHover(bool v) {
    setState(() {
      _hover = v;
      if (!v) _shift = Offset.zero;
    });
    if (v) {
      _anim.repeat();
    } else {
      _anim.stop();
    }
  }

  Future<void> _stamp() => GZPassport.stamp(context, c.placeId, c.name);

  GZPlaceCard get c => widget.card;

  String get _meta {
    final parts = <String>[];
    final cat = c.category.replaceAll('_', ' ');
    parts.add(cat[0].toUpperCase() + cat.substring(1));
    if (c.distanceKm != null) parts.add('${c.distanceKm!.toStringAsFixed(1)} km');
    if (c.dwellMinutes > 0) parts.add('~${c.dwellMinutes} min');
    return parts.join('  ·  ');
  }

  ({Color color, String text, IconData icon}) _status(GZInk ink) {
    final label = (c.openLabel ?? '').trim();
    if (c.openState == 'open') {
      final listed = !label.toLowerCase().contains('usually');
      return (color: listed ? const Color(0xFF2E9E5B) : ink.accent, text: label.isEmpty ? 'Open now' : label, icon: listed ? Icons.circle : Icons.schedule);
    }
    if (c.openState == 'closed') return (color: ink.muted, text: label.isEmpty ? 'Closed now' : label, icon: Icons.lock_clock_outlined);
    return (color: ink.muted, text: label.isEmpty ? 'Hours not confirmed' : label, icon: Icons.help_outline);
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final kind = gzArtKindFor(c.category, c.tags);
    final compact = widget.height < 130;
    final st = _status(ink);
    final text = Theme.of(context).textTheme;

    final sub = gzArtSub(c.category, c.tags, c.name);
    final art = ClipRRect(
      borderRadius: compact ? BorderRadius.circular(14) : const BorderRadius.vertical(top: Radius.circular(20)),
      child: Stack(fit: StackFit.expand, children: [
        compact
            ? GZPlaceArt(kind: kind, seed: c.name, sub: sub)
            : MouseRegion(
                onHover: (e) {
                  final box = context.findRenderObject() as RenderBox?;
                  if (box == null) return;
                  final w = box.size.width;
                  setState(() => _shift = Offset((e.localPosition.dx / w - 0.5) * 2, 0));
                },
                child: AnimatedBuilder(
                  animation: _anim,
                  builder: (_, __) => GZPlaceArt(kind: kind, seed: c.name, sub: sub, t: _anim.value, shift: _shift),
                ),
              ),
        if (!compact)
          Positioned(
            right: 10,
            bottom: 10,
            child: ValueListenableBuilder<Set<String>>(
              valueListenable: GZPassport.stamps,
              builder: (_, set, __) => _StampButton(stamped: set.contains(c.placeId), onTap: _stamp),
            ),
          ),
        if (!compact)
          Positioned(
            left: 10,
            top: 10,
            child: _Pill(icon: gzArtIcon(kind), label: gzArtLabel(kind)),
          ),
        if (!compact && c.provenance == 'verified')
          const Positioned(right: 10, top: 10, child: _Pill(icon: Icons.verified_outlined, label: 'Verified')),
        if (compact) Center(child: Icon(gzArtIcon(kind), color: Colors.white.withOpacity(0.92), size: 26)),
      ]),
    );

    final body = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!compact) const SizedBox.shrink(),
        ConstrainedBox(
          constraints: BoxConstraints(minHeight: compact ? 0 : 38),
          child: Text(
          c.name,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: text.titleSmall?.copyWith(fontWeight: FontWeight.w800, height: 1.2, fontSize: 15),
        )),
        const SizedBox(height: 4),
        Text(_meta, maxLines: 1, overflow: TextOverflow.ellipsis, style: text.bodySmall?.copyWith(color: ink.muted, fontSize: 12)),
        const SizedBox(height: 6),
        Row(children: [
          Icon(st.icon, size: st.icon == Icons.circle ? 8 : 14, color: st.color),
          const SizedBox(width: 6),
          Expanded(
            child: Text(st.text, maxLines: 1, overflow: TextOverflow.ellipsis, style: text.bodySmall?.copyWith(color: st.color, fontWeight: FontWeight.w700, fontSize: 12)),
          ),
        ]),
      ],
    );

    final decoration = BoxDecoration(
      color: ink.paper,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: _hover ? ink.accent.withOpacity(0.9) : ink.hairline),
      boxShadow: _hover ? ink.softShadow : const [],
    );

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => _setHover(true),
      onExit: (_) => _setHover(false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          transform: Matrix4.translationValues(0, _hover ? -4 : 0, 0),
          decoration: decoration,
          child: compact
              ? Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(children: [
                    SizedBox(width: 78, height: 78, child: art),
                    const SizedBox(width: 12),
                    Expanded(child: body),
                    const Icon(Icons.chevron_right),
                  ]),
                )
              : Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  SizedBox(height: widget.featured ? 150 : 124, child: art),
                  Padding(padding: const EdgeInsets.fromLTRB(14, 12, 14, 4), child: body),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                    child: Row(children: [
                      TextButton.icon(
                        onPressed: () => GZMaps.directions(context, c.latitude, c.longitude, name: c.name),
                        icon: Icon(Icons.near_me_outlined, size: 16, color: ink.accent),
                        label: Text('Take me there', style: TextStyle(color: ink.accent, fontWeight: FontWeight.w800, fontSize: 12.5)),
                      ),
                      const Spacer(),
                      if (c.fitPercent != null)
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: Text('${c.fitPercent}% fit', style: text.labelSmall?.copyWith(color: ink.muted, fontWeight: FontWeight.w800)),
                        ),
                    ]),
                  ),
                ]),
        ),
      ),
    );
  }
}

class _StampButton extends StatelessWidget {
  final bool stamped;
  final VoidCallback onTap;
  const _StampButton({required this.stamped, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: stamped ? 'Remove stamp' : 'I have been here: stamp it',
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedScale(
          scale: stamped ? 1.0 : 0.92,
          duration: const Duration(milliseconds: 220),
          curve: Curves.elasticOut,
          child: Transform.rotate(
            angle: stamped ? -0.2 : 0,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: stamped ? const Color(0xFFB3261E).withOpacity(0.9) : Colors.black.withOpacity(0.42),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white.withOpacity(stamped ? 0.9 : 0.5), width: stamped ? 2 : 1),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(stamped ? Icons.verified : Icons.approval_outlined, size: 14, color: Colors.white),
                const SizedBox(width: 5),
                Text(stamped ? 'VISITED' : 'STAMP', style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w900, letterSpacing: 1)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final IconData icon;
  final String label;
  const _Pill({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(color: Colors.black.withOpacity(0.42), borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 13, color: Colors.white),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.3)),
      ]),
    );
  }
}

/// A tidy responsive grid: as many equal columns as fit (min ~250 px each),
/// replacing the old asymmetric layout that squeezed cards together.
class AsymmetricCardGrid extends StatelessWidget {
  final List<GZPlaceCard> cards;
  final void Function(GZPlaceCard) onTapCard;

  const AsymmetricCardGrid({super.key, required this.cards, required this.onTapCard});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      const gap = 14.0;
      final cols = (box.maxWidth / 260).floor().clamp(1, 4);
      final w = (box.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [for (final c in cards) SizedBox(width: w, child: PlaceCardTile(card: c, onTap: () => onTapCard(c)))],
      );
    });
  }
}


/// One full-width row of cards: as many equal cards as fit, stretched to the
/// whole row, so there is never a half-empty line. On narrow screens it
/// becomes a swipeable strip instead.
class GZCardRow extends StatelessWidget {
  final List<GZPlaceCard> cards;
  final void Function(GZPlaceCard) onTapCard;
  final bool featured;
  final double minCardWidth;
  const GZCardRow({super.key, required this.cards, required this.onTapCard, this.featured = false, this.minCardWidth = 240});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      const gap = 14.0, pad = 20.0;
      final inner = box.maxWidth - pad * 2;
      final cols = ((inner + gap) / (minCardWidth + gap)).floor();
      if (cols < 2) {
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(pad, 10, pad, 10),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final c in cards) Padding(padding: const EdgeInsets.only(right: gap), child: SizedBox(width: 250, child: PlaceCardTile(card: c, featured: featured, onTap: () => onTapCard(c)))),
          ]),
        );
      }
      final n = cols.clamp(2, 6);
      final shown = cards.take(n).toList();
      final w = (inner - gap * (n - 1)) / n;
      return Padding(
        padding: const EdgeInsets.fromLTRB(pad, 10, pad, 10),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (var i = 0; i < shown.length; i++) ...[
            SizedBox(width: w, child: PlaceCardTile(card: shown[i], featured: featured, onTap: () => onTapCard(shown[i]))),
            if (i != shown.length - 1) const SizedBox(width: gap),
          ],
        ]),
      );
    });
  }
}
