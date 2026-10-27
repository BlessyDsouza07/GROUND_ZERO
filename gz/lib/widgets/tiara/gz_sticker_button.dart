import 'package:flutter/material.dart';

import '../../design/gz_ink.dart';

/// Chunky "sticker" button: ink border, hard shadow that squashes when
/// pressed. [outlined] gives the paper-coloured variant.
class GZStickerButton extends StatefulWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool outlined;
  final bool busy;
  final bool expand;
  final bool compact;

  const GZStickerButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.outlined = false,
    this.busy = false,
    this.expand = false,
    this.compact = false,
  });

  @override
  State<GZStickerButton> createState() => _GZStickerButtonState();
}

class _GZStickerButtonState extends State<GZStickerButton> {
  bool _down = false;
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final enabled = widget.onPressed != null && !widget.busy;
    final fill = widget.outlined ? ink.paper : ink.accent;
    final fg = widget.outlined ? ink.text : (ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE));
    final move = _down ? 1.0 : (_hover ? -1.0 : 0.0);

    final content = Row(
      mainAxisSize: widget.expand ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (widget.busy)
          SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.4, color: fg))
        else ...[
          if (widget.icon != null) ...[Icon(widget.icon, size: 18, color: fg), const SizedBox(width: 9)],
          Flexible(
            child: Text(
              widget.label,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(color: fg, fontSize: widget.compact ? 11.5 : 13, letterSpacing: 0.6, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ],
    );

    return Opacity(
      opacity: enabled || widget.busy ? 1 : 0.55,
      child: MouseRegion(
        cursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() {
          _hover = false;
          _down = false;
        }),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: enabled ? (_) => setState(() => _down = true) : null,
          onTapCancel: () => setState(() => _down = false),
          onTapUp: (_) => setState(() => _down = false),
          onTap: enabled ? widget.onPressed : null,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 110),
            transform: Matrix4.translationValues(0, move, 0),
            padding: widget.compact ? const EdgeInsets.symmetric(horizontal: 16, vertical: 10) : const EdgeInsets.symmetric(horizontal: 22, vertical: 15),
            decoration: BoxDecoration(
              color: fill,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: widget.outlined ? ink.border.withOpacity(0.7) : Colors.transparent, width: 1.2),
              boxShadow: widget.outlined || _down ? const [] : ink.softShadow,
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}
