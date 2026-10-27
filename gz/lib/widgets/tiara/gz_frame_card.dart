import 'package:flutter/material.dart';

import '../../design/gz_ink.dart';

/// Tiara-style "framed" card: thick ink border, hard offset shadow and a
/// little lift on hover / press. Used for features, steps, places, forms.
class GZFrameCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? color;
  final double radius;
  final double shadowOffset;

  /// Lift on hover even without a tap action (purely decorative cards).
  final bool lift;

  const GZFrameCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(22),
    this.onTap,
    this.color,
    this.radius = 18,
    this.shadowOffset = 6,
    this.lift = false,
  });

  @override
  State<GZFrameCard> createState() => _GZFrameCardState();
}

class _GZFrameCardState extends State<GZFrameCard> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final active = widget.onTap != null || widget.lift;
    final raised = _hover && active;
    return MouseRegion(
      cursor: widget.onTap == null ? MouseCursor.defer : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          transform: Matrix4.translationValues(0, raised ? -3.0 : 0.0, 0),
          decoration: BoxDecoration(
            color: widget.color ?? ink.paper,
            borderRadius: BorderRadius.circular(widget.radius),
            border: Border.all(color: raised ? ink.accent.withOpacity(0.8) : ink.hairline, width: 1),
            boxShadow: widget.shadowOffset <= 0 && !raised ? const [] : ink.softShadow,
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(widget.radius - 1),
            child: Padding(padding: widget.padding, child: widget.child),
          ),
        ),
      ),
    );
  }
}

/// Small mono "tag" chip (e.g. 01, BEACH, LIVE).
class GZTag extends StatelessWidget {
  final String text;
  final IconData? icon;
  final bool filled;

  const GZTag(this.text, {super.key, this.icon, this.filled = false});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final fg = filled ? (ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE)) : ink.text;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
      decoration: BoxDecoration(
        color: filled ? ink.accent : Colors.transparent,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: ink.hairline, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 13, color: fg), const SizedBox(width: 6)],
          Text(
            text.toUpperCase(),
            style: Theme.of(context).textTheme.labelMedium?.copyWith(color: fg, letterSpacing: 1.4, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
