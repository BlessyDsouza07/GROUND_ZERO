import 'package:flutter/material.dart';

import '../../core/gz_passport.dart';
import '../../design/gz_ink.dart';

/// Explore-page strip showing the traveller's stamp count, level and progress.
class GZPassportBanner extends StatefulWidget {
  const GZPassportBanner({super.key});

  @override
  State<GZPassportBanner> createState() => _GZPassportBannerState();
}

class _GZPassportBannerState extends State<GZPassportBanner> {
  @override
  void initState() {
    super.initState();
    GZPassport.load();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return ValueListenableBuilder<Set<String>>(
      valueListenable: GZPassport.stamps,
      builder: (context, set, _) {
        final n = set.length;
        final nx = GZPassport.next(n);
        final onAccent = ink.dark ? const Color(0xFF240002) : Colors.white;
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: ink.hairline),
              gradient: LinearGradient(colors: [ink.accent.withOpacity(0.16), ink.accent2.withOpacity(0.10)]),
            ),
            child: Row(children: [
              Transform.rotate(
                angle: -0.12,
                child: Container(
                  width: 58,
                  height: 58,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: ink.accent, border: Border.all(color: onAccent.withOpacity(0.5), width: 2)),
                  child: Text('$n', style: TextStyle(color: onAccent, fontWeight: FontWeight.w900, fontSize: 22)),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('MANGALURU PASSPORT  ·  ${GZPassport.levelName(n).toUpperCase()}',
                      style: text.labelMedium?.copyWith(fontWeight: FontWeight.w900, letterSpacing: 1.2, color: ink.accent)),
                  const SizedBox(height: 4),
                  Text(
                    n == 0
                        ? 'Tap the stamp on any place you have visited to start collecting.'
                        : nx == null
                            ? 'You have stamped $n places. You are a true local.'
                            : '${nx.need} more ${nx.need == 1 ? 'stamp' : 'stamps'} to become a ${nx.name}.',
                    style: text.bodyMedium?.copyWith(height: 1.3),
                  ),
                  if (nx != null) ...[
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(99),
                      child: LinearProgressIndicator(value: nx.progress.clamp(0.0, 1.0), minHeight: 6, backgroundColor: ink.hairline.withOpacity(0.4), color: ink.accent),
                    ),
                  ],
                ]),
              ),
            ]),
          ),
        );
      },
    );
  }
}
