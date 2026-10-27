import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../../design/gz_ink.dart';

/// Endless ticker strip (Tiara's category strip). Items repeat and slide
/// left forever; pure Flutter, no packages.
class GZMarquee extends StatefulWidget {
  final List<String> items;
  final double speed; // logical px per second
  final double height;

  const GZMarquee({super.key, required this.items, this.speed = 48, this.height = 54});

  @override
  State<GZMarquee> createState() => _GZMarqueeState();
}

class _GZMarqueeState extends State<GZMarquee> with SingleTickerProviderStateMixin {
  static const _repeat = 8;
  final ScrollController _controller = ScrollController();
  late final Ticker _ticker;
  Duration _last = Duration.zero;
  double _offset = 0;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_tick)..start();
  }

  void _tick(Duration elapsed) {
    final dt = (elapsed - _last).inMicroseconds / 1000000.0;
    _last = elapsed;
    if (!_controller.hasClients) return;
    final pos = _controller.position;
    final total = pos.maxScrollExtent + pos.viewportDimension;
    final segment = total / _repeat;
    if (segment <= 0) return;
    _offset += widget.speed * dt;
    if (_offset >= segment) _offset -= segment;
    final target = _offset > pos.maxScrollExtent ? pos.maxScrollExtent : _offset;
    _controller.jumpTo(target);
  }

  @override
  void dispose() {
    _ticker.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final style = Theme.of(context).textTheme.titleLarge?.copyWith(
          color: ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE),
          fontWeight: FontWeight.w500,
          fontStyle: FontStyle.italic,
          letterSpacing: -0.2,
        );
    return Container(
      height: widget.height,
      decoration: BoxDecoration(
        color: ink.accent,
        border: Border.symmetric(horizontal: BorderSide(color: ink.hairline, width: 1)),
      ),
      child: IgnorePointer(
        child: SingleChildScrollView(
          controller: _controller,
          scrollDirection: Axis.horizontal,
          physics: const NeverScrollableScrollPhysics(),
          child: Row(
            children: [
              for (var r = 0; r < _repeat; r++)
                for (final item in widget.items) ...[
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 22),
                    child: Text(item, style: style),
                  ),
                  Icon(Icons.circle, size: 6, color: style?.color),
                ],
            ],
          ),
        ),
      ),
    );
  }
}
