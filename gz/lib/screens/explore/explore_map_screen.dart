import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../core/explore_api_client.dart';
import '../../core/gz_location.dart';
import '../../core/gz_passport.dart';
import '../../design/gz_ink.dart';
import '../../widgets/tiara/gz_place_art.dart';
import 'place_card_tile.dart';

/// Treasure map: every place we know near you, drawn on a clean illustrated
/// chart. Nearby places group into numbered clusters that split as you zoom.
/// The chart starts hazed ("unexplored"); stamping a place reveals the area
/// around it in full colour, and each kind of place is a quest with a badge.
///
/// It is an illustrated chart, not a navigation map: positions come from the
/// places' real coordinates, the sea edge is an approximation of the coast,
/// and every card has Take me there for real directions.
class ExploreMapScreen extends StatefulWidget {
  final List<GZPlaceCard> cards;
  final void Function(GZPlaceCard) onOpenPlace;
  const ExploreMapScreen({super.key, required this.cards, required this.onOpenPlace});

  @override
  State<ExploreMapScreen> createState() => _ExploreMapScreenState();
}

const double _kW = 2400, _kH = 1700;
const double _kReveal = 190;

class _Proj {
  final double lat0, lon0, scale;
  _Proj(this.lat0, this.lon0, this.scale);

  factory _Proj.fit(List<(double, double)> pts) {
    var minLat = pts.first.$1, maxLat = pts.first.$1, minLon = pts.first.$2, maxLon = pts.first.$2;
    for (final p in pts) {
      minLat = math.min(minLat, p.$1);
      maxLat = math.max(maxLat, p.$1);
      minLon = math.min(minLon, p.$2);
      maxLon = math.max(maxLon, p.$2);
    }
    final lat0 = (minLat + maxLat) / 2, lon0 = (minLon + maxLon) / 2;
    final kx = 111.32 * math.cos(lat0 * math.pi / 180), ky = 110.57;
    final spanX = math.max(3.0, (maxLon - minLon) * kx), spanY = math.max(3.0, (maxLat - minLat) * ky);
    final scale = math.min((_kW - 500) / spanX, (_kH - 500) / spanY);
    return _Proj(lat0, lon0, scale);
  }

  Offset xy(double lat, double lon) {
    final kx = 111.32 * math.cos(lat0 * math.pi / 180), ky = 110.57;
    return Offset(_kW / 2 + (lon - lon0) * kx * scale, _kH / 2 - (lat - lat0) * ky * scale);
  }

  double latAt(double y) => lat0 - (y - _kH / 2) / (110.57 * scale);
}

/// Rough shoreline of the Mangaluru coast (longitude by latitude).
double _coastLon(double lat) => 74.842 - (lat - 12.80) * 0.30;

Color _kindColor(GZArtKind k) => switch (k) {
      GZArtKind.coast => const Color(0xFF0699BA),
      GZArtKind.heritage => const Color(0xFFD97E0C),
      GZArtKind.nature => const Color(0xFF2E8F72),
      GZArtKind.food => const Color(0xFFC8481F),
      GZArtKind.market => const Color(0xFF9B3B8C),
      GZArtKind.stay => const Color(0xFF3C5A8C),
      GZArtKind.generic => const Color(0xFF5B6B73),
    };

String _questName(GZArtKind k) => switch (k) {
      GZArtKind.coast => 'Coast walker',
      GZArtKind.heritage => 'Heritage hunter',
      GZArtKind.nature => 'Green seeker',
      GZArtKind.food => 'Flavour finder',
      GZArtKind.market => 'Street local',
      GZArtKind.stay => 'Night owl',
      GZArtKind.generic => 'Wanderer',
    };

class _Cluster {
  final Offset at;
  final List<GZPlaceCard> items;
  _Cluster(this.at, this.items);
}

class _ExploreMapScreenState extends State<ExploreMapScreen> with TickerProviderStateMixin {
  final _tc = TransformationController();
  late final AnimationController _fly = AnimationController(vsync: this, duration: const Duration(milliseconds: 550));
  late final AnimationController _pulse = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
  GZArtKind? _filter;
  late final List<GZPlaceCard> _cards;
  late final _Proj _proj;
  late final Map<String, Offset> _pos;
  late final List<(Offset, Offset)> _edges;
  Size _vp = Size.zero;
  bool _fitted = false;
  Matrix4? _from, _to;

  @override
  void initState() {
    super.initState();
    GZPassport.load();
    final seen = <String>{};
    _cards = [
      for (final c in widget.cards)
        if (seen.add(c.placeId)) c
    ];
    final pts = <(double, double)>[for (final c in _cards) (c.latitude, c.longitude)];
    if (GZLocation.known) pts.add((GZLocation.lat!, GZLocation.lng!));
    if (pts.isEmpty) pts.add((12.9141, 74.8560));
    _proj = _Proj.fit(pts);
    _pos = {for (final c in _cards) c.placeId: _proj.xy(c.latitude, c.longitude)};
    // Faint "constellation" links: each place to its two nearest neighbours.
    final edges = <(Offset, Offset)>[];
    final list = _pos.values.toList();
    for (var i = 0; i < list.length; i++) {
      final d = [for (var j = 0; j < list.length; j++) if (j != i) (j, (list[i] - list[j]).distance)]..sort((a, b) => a.$2.compareTo(b.$2));
      for (final e in d.take(2)) {
        if (e.$1 > i) edges.add((list[i], list[e.$1]));
      }
    }
    _edges = edges;
    _fly.addListener(() {
      if (_from == null || _to == null) return;
      _tc.value = Matrix4Tween(begin: _from, end: _to).transform(Curves.easeInOutCubic.transform(_fly.value));
    });
  }

  @override
  void dispose() {
    _fly.dispose();
    _pulse.dispose();
    _tc.dispose();
    super.dispose();
  }

  Matrix4 _matrixFor(Offset world, double s) => Matrix4.identity()
    ..translate(_vp.width / 2 - world.dx * s, _vp.height / 2 - world.dy * s)
    ..scale(s);

  void _flyTo(Offset world, double s, {VoidCallback? then}) {
    _from = _tc.value.clone();
    _to = _matrixFor(world, s);
    _fly.forward(from: 0).then((_) => then?.call());
  }

  void _fitInitial(Size vp) {
    if (_fitted || vp.isEmpty) return;
    _fitted = true;
    final xs = [for (final o in _pos.values) o.dx]..sort();
    final ys = [for (final o in _pos.values) o.dy]..sort();
    if (xs.isEmpty) {
      _tc.value = _matrixFor(const Offset(_kW / 2, _kH / 2), 0.6);
      return;
    }
    double pct(List<double> v, double p) => v[((v.length - 1) * p).round()];
    var x0 = pct(xs, 0.05), x1 = pct(xs, 0.95), y0 = pct(ys, 0.05), y1 = pct(ys, 0.95);
    if (GZLocation.known) {
      final u = _proj.xy(GZLocation.lat!, GZLocation.lng!);
      x0 = math.min(x0, u.dx);
      x1 = math.max(x1, u.dx);
      y0 = math.min(y0, u.dy);
      y1 = math.max(y1, u.dy);
    }
    final w = math.max(300.0, x1 - x0 + 220), h = math.max(300.0, y1 - y0 + 220);
    final s = math.min(vp.width / w, vp.height / h).clamp(0.25, 2.5);
    _tc.value = _matrixFor(Offset((x0 + x1) / 2, (y0 + y1) / 2), s);
  }

  void _openCard(GZPlaceCard c) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Center(
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 340),
              child: PlaceCardTile(
                card: c,
                featured: true,
                onTap: () {
                  Navigator.pop(ctx);
                  widget.onOpenPlace(c);
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _openCluster(_Cluster cl) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.7),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.all(16),
            children: [
              Text('${cl.items.length} places here', style: Theme.of(ctx).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w900)),
              const SizedBox(height: 10),
              for (final c in cl.items)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: PlaceCardTile(
                    card: c,
                    height: 100,
                    onTap: () {
                      Navigator.pop(ctx);
                      _openCard(c);
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _visit(GZPlaceCard c) {
    final o = _pos[c.placeId]!;
    final s = math.max(_tc.value.getMaxScaleOnAxis(), 1.4);
    _flyTo(o, s, then: () {
      if (mounted) _openCard(c);
    });
  }

  List<_Cluster> _clusters(double scale) {
    final cell = 70 / scale;
    final groups = <String, List<GZPlaceCard>>{};
    for (final c in _cards) {
      if (_filter != null && gzArtKindFor(c.category, c.tags) != _filter) continue;
      final o = _pos[c.placeId]!;
      groups.putIfAbsent('${(o.dx / cell).floor()}_${(o.dy / cell).floor()}', () => []).add(c);
    }
    return [
      for (final g in groups.values)
        _Cluster(
          Offset(g.map((c) => _pos[c.placeId]!.dx).reduce((a, b) => a + b) / g.length, g.map((c) => _pos[c.placeId]!.dy).reduce((a, b) => a + b) / g.length),
          g,
        )
    ];
  }

  // ---------------------------------------------------------------- panels

  Widget _explorerCard(GZInk ink, Set<String> stamps, {bool compact = false}) {
    final got = _cards.where((c) => stamps.contains(c.placeId)).length;
    final nx = GZPassport.next(stamps.length);
    final lvl = GZPassport.levelName(stamps.length);
    final onAccent = ink.dark ? const Color(0xFF240002) : Colors.white;
    final ring = SizedBox(
      width: compact ? 46 : 74,
      height: compact ? 46 : 74,
      child: Stack(alignment: Alignment.center, children: [
        SizedBox.expand(
          child: CircularProgressIndicator(
            value: nx == null ? 1 : nx.progress.clamp(0.02, 1.0),
            strokeWidth: compact ? 5 : 7,
            backgroundColor: onAccent.withOpacity(0.0),
            color: const Color(0xFFFFC136),
          ),
        ),
        Text('${stamps.length}', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: compact ? 16 : 26)),
      ]),
    );
    return Container(
      padding: EdgeInsets.all(compact ? 12 : 18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF06384F), Color(0xFF006996), Color(0xFF0699BA)]),
      ),
      child: Row(children: [
        ring,
        SizedBox(width: compact ? 12 : 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(lvl.toUpperCase(), style: TextStyle(color: const Color(0xFFFFE08A), fontWeight: FontWeight.w900, letterSpacing: 1.4, fontSize: compact ? 11 : 12)),
            const SizedBox(height: 2),
            Text(
              nx == null ? 'Top level. You are a true local.' : '${nx.need} more ${nx.need == 1 ? 'stamp' : 'stamps'} to ${nx.name}',
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: compact ? 13 : 16, height: 1.2),
            ),
            if (!compact) ...[
              const SizedBox(height: 4),
              Text('$got of ${_cards.length} places on this map explored', style: const TextStyle(color: Color(0xCCFFFFFF), fontSize: 12.5)),
            ],
          ]),
        ),
      ]),
    );
  }

  List<GZArtKind> get _kinds => [
        for (final k in GZArtKind.values)
          if (k != GZArtKind.generic && _cards.any((c) => gzArtKindFor(c.category, c.tags) == k)) k
      ];

  (int, int) _progress(GZArtKind k, Set<String> stamps) {
    final all = _cards.where((c) => gzArtKindFor(c.category, c.tags) == k).toList();
    return (all.where((c) => stamps.contains(c.placeId)).length, all.length);
  }

  Widget _quests(GZInk ink, Set<String> stamps) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('QUESTS', style: TextStyle(color: ink.accent, fontWeight: FontWeight.w900, letterSpacing: 1.4, fontSize: 12)),
      const SizedBox(height: 8),
      for (final k in _kinds)
        Builder(builder: (context) {
          final (done, total) = _progress(k, stamps);
          final complete = total > 0 && done == total;
          final sel = _filter == k;
          final color = _kindColor(k);
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => setState(() => _filter = sel ? null : k),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: sel ? color.withOpacity(0.12) : ink.paper,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: sel ? color : ink.hairline, width: sel ? 1.8 : 1),
                ),
                child: Row(children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: complete ? const Color(0xFFFFC136) : color),
                    child: Icon(complete ? Icons.emoji_events_rounded : gzArtIcon(k), color: complete ? const Color(0xFF4A1202) : Colors.white, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Expanded(child: Text(_questName(k), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14))),
                        Text('$done/$total', style: TextStyle(color: ink.muted, fontWeight: FontWeight.w800, fontSize: 12.5)),
                      ]),
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(99),
                        child: LinearProgressIndicator(value: total == 0 ? 0 : done / total, minHeight: 6, backgroundColor: ink.hairline.withOpacity(0.4), color: color),
                      ),
                    ]),
                  ),
                ]),
              ),
            ),
          );
        }),
    ]);
  }

  List<GZPlaceCard> _nextUp(Set<String> stamps) {
    final l = _cards.where((c) => !stamps.contains(c.placeId) && (_filter == null || gzArtKindFor(c.category, c.tags) == _filter)).toList();
    l.sort((a, b) => (a.distanceKm ?? 99).compareTo(b.distanceKm ?? 99));
    return l.take(6).toList();
  }

  Widget _thumb(GZPlaceCard c, double size) => ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: SizedBox(width: size, height: size, child: GZPlaceArt(kind: gzArtKindFor(c.category, c.tags), seed: c.name, sub: gzArtSub(c.category, c.tags, c.name))),
      );

  Widget _nextUpList(GZInk ink, Set<String> stamps) {
    final list = _nextUp(stamps);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('NEXT UP, NEAREST FIRST', style: TextStyle(color: ink.accent, fontWeight: FontWeight.w900, letterSpacing: 1.4, fontSize: 12)),
      const SizedBox(height: 8),
      if (list.isEmpty) const Text('Everything here is stamped. Nicely done.'),
      for (final c in list)
        InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => _visit(c),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(children: [
              _thumb(c, 52),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(c.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                  Text(
                    '${gzArtLabel(gzArtKindFor(c.category, c.tags))}${c.distanceKm != null ? '  ·  ${c.distanceKm!.toStringAsFixed(1)} km' : ''}',
                    style: TextStyle(color: ink.muted, fontSize: 12),
                  ),
                ]),
              ),
              Icon(Icons.my_location, size: 18, color: ink.accent),
            ]),
          ),
        ),
    ]);
  }

  Widget _chipsBar(GZInk ink, Set<String> stamps) => SizedBox(
        height: 46,
        child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [
          Padding(padding: const EdgeInsets.only(right: 8), child: ChoiceChip(label: const Text('All'), selected: _filter == null, onSelected: (_) => setState(() => _filter = null))),
          for (final k in _kinds)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                avatar: Icon(gzArtIcon(k), size: 16, color: _kindColor(k)),
                label: Text('${gzArtLabel(k)} ${_progress(k, stamps).$1}/${_progress(k, stamps).$2}'),
                selected: _filter == k,
                onSelected: (_) => setState(() => _filter = _filter == k ? null : k),
              ),
            ),
        ]),
      );

  Widget _bottomStrip(GZInk ink, Set<String> stamps) {
    final list = _nextUp(stamps);
    if (list.isEmpty) return const SizedBox.shrink();
    return Container(
      height: 92,
      decoration: BoxDecoration(color: ink.paper, border: Border(top: BorderSide(color: ink.hairline))),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.all(10),
        itemCount: list.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (_, i) {
          final c = list[i];
          return InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: () => _visit(c),
            child: Container(
              width: 230,
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), border: Border.all(color: ink.hairline)),
              child: Row(children: [
                _thumb(c, 60),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(c.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13, height: 1.2)),
                    Text(c.distanceKm != null ? '${c.distanceKm!.toStringAsFixed(1)} km' : gzArtLabel(gzArtKindFor(c.category, c.tags)), style: TextStyle(color: ink.muted, fontSize: 12)),
                  ]),
                ),
              ]),
            ),
          );
        },
      ),
    );
  }

  // ------------------------------------------------------------------- map

  Widget _mapView(GZInk ink) {
    return LayoutBuilder(builder: (context, box) {
      _vp = Size(box.maxWidth, box.maxHeight);
      _fitInitial(_vp);
      return ClipRect(
        child: Stack(children: [
          InteractiveViewer(
            transformationController: _tc,
            constrained: false,
            minScale: 0.2,
            maxScale: 4,
            boundaryMargin: const EdgeInsets.all(300),
            child: SizedBox(
              width: _kW,
              height: _kH,
              child: Stack(children: [
                Positioned.fill(
                  child: ValueListenableBuilder<Set<String>>(
                    valueListenable: GZPassport.stamps,
                    builder: (context, stamps, _) {
                      final clear = <Offset>[
                        for (final c in _cards)
                          if (stamps.contains(c.placeId)) _pos[c.placeId]!,
                      ];
                      return CustomPaint(painter: _ChartPainter(_proj, clear, _edges, ink.dark));
                    },
                  ),
                ),
                if (GZLocation.known) _youMarker(_proj.xy(GZLocation.lat!, GZLocation.lng!)),
                // Pins and clusters stay a constant size on screen at any zoom.
                AnimatedBuilder(
                  animation: _tc,
                  builder: (context, _) {
                    final scale = _tc.value.getMaxScaleOnAxis();
                    final inv = (1 / scale).clamp(0.4, 2.2);
                    return ValueListenableBuilder<Set<String>>(
                      valueListenable: GZPassport.stamps,
                      builder: (context, stamps, _) => Stack(children: [
                        for (final cl in _clusters(scale))
                          Positioned(
                            left: cl.at.dx - 30,
                            top: cl.at.dy - 64,
                            width: 60,
                            height: 64,
                            child: Transform.scale(
                              scale: inv.toDouble(),
                              alignment: Alignment.bottomCenter,
                              child: cl.items.length == 1 ? _pin(cl.items.first, stamps) : _clusterPin(cl, stamps, scale),
                            ),
                          ),
                      ]),
                    );
                  },
                ),
              ]),
            ),
          ),
          Positioned(
            right: 12,
            top: 12,
            child: Column(children: [
              _roundBtn(Icons.add, () => _flyTo(_worldCenter(), math.min(_tc.value.getMaxScaleOnAxis() * 1.6, 4))),
              const SizedBox(height: 8),
              _roundBtn(Icons.remove, () => _flyTo(_worldCenter(), math.max(_tc.value.getMaxScaleOnAxis() / 1.6, 0.2))),
              const SizedBox(height: 8),
              _roundBtn(Icons.my_location, () {
                _fitted = false;
                _fitInitial(_vp);
                setState(() {});
              }),
            ]),
          ),
          Positioned(left: 12, bottom: 12, child: IgnorePointer(child: _Legend(ink: ink))),
          const Positioned(right: 12, bottom: 12, child: IgnorePointer(child: _Compass())),
        ]),
      );
    });
  }

  Offset _worldCenter() => MatrixUtils.transformPoint(Matrix4.inverted(_tc.value), Offset(_vp.width / 2, _vp.height / 2));

  Widget _roundBtn(IconData i, VoidCallback f) => Material(
        color: Colors.white,
        elevation: 3,
        shape: const CircleBorder(),
        child: InkWell(customBorder: const CircleBorder(), onTap: f, child: SizedBox(width: 40, height: 40, child: Icon(i, color: const Color(0xFF06384F)))),
      );

  Widget _youMarker(Offset o) => Positioned(
        left: o.dx - 40,
        top: o.dy - 40,
        child: IgnorePointer(
          child: AnimatedBuilder(
            animation: _pulse,
            builder: (_, __) => SizedBox(
              width: 80,
              height: 80,
              child: Stack(alignment: Alignment.center, children: [
                Container(
                  width: 24 + 56 * _pulse.value,
                  height: 24 + 56 * _pulse.value,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFF1A73E8).withOpacity(0.35 * (1 - _pulse.value))),
                ),
                Container(width: 22, height: 22, decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFF1A73E8), border: Border.all(color: Colors.white, width: 3))),
              ]),
            ),
          ),
        ),
      );

  Widget _pin(GZPlaceCard c, Set<String> stamps) {
    final kind = gzArtKindFor(c.category, c.tags);
    final color = _kindColor(kind);
    final done = stamps.contains(c.placeId);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _openCard(c),
      child: Tooltip(
        message: c.name,
        child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color,
              border: Border.all(color: done ? const Color(0xFFFFC136) : Colors.white, width: done ? 4 : 3),
              boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 6, offset: Offset(0, 3))],
            ),
            child: Icon(done ? Icons.check_rounded : gzArtIcon(kind), size: 20, color: Colors.white),
          ),
          Container(width: 4, height: 16, color: color),
        ]),
      ),
    );
  }

  Widget _clusterPin(_Cluster cl, Set<String> stamps, double scale) {
    final counts = <GZArtKind, int>{};
    for (final c in cl.items) {
      final k = gzArtKindFor(c.category, c.tags);
      counts[k] = (counts[k] ?? 0) + 1;
    }
    final top = counts.entries.reduce((a, b) => a.value >= b.value ? a : b).key;
    final done = cl.items.where((c) => stamps.contains(c.placeId)).length;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => scale < 2.6 ? _flyTo(cl.at, math.min(scale * 2.4, 4)) : _openCluster(cl),
      child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
        Container(
          width: 50,
          height: 50,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _kindColor(top),
            border: Border.all(color: Colors.white, width: 4),
            boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 8, offset: Offset(0, 3))],
          ),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('${cl.items.length}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 17, height: 1)),
            if (done > 0) Text('$done done', style: const TextStyle(color: Color(0xFFFFE08A), fontWeight: FontWeight.w800, fontSize: 8.5)),
          ]),
        ),
        Container(width: 4, height: 12, color: _kindColor(top)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final wide = MediaQuery.of(context).size.width >= 900;
    return Scaffold(
      appBar: AppBar(title: const Text('Treasure map')),
      body: ValueListenableBuilder<Set<String>>(
        valueListenable: GZPassport.stamps,
        builder: (context, stamps, _) {
          if (wide) {
            return Row(children: [
              Expanded(child: _mapView(ink)),
              Container(
                width: 350,
                decoration: BoxDecoration(color: ink.paperAlt.withOpacity(0.35), border: Border(left: BorderSide(color: ink.hairline))),
                child: ListView(padding: const EdgeInsets.all(16), children: [
                  _explorerCard(ink, stamps),
                  const SizedBox(height: 18),
                  _quests(ink, stamps),
                  const SizedBox(height: 12),
                  _nextUpList(ink, stamps),
                  const SizedBox(height: 12),
                  Text('Stamp a place from its card to reveal the map around it.', style: TextStyle(color: ink.muted, fontSize: 12, height: 1.4)),
                ]),
              ),
            ]);
          }
          return Column(children: [
            Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 8), child: _explorerCard(ink, stamps, compact: true)),
            _chipsBar(ink, stamps),
            const SizedBox(height: 6),
            Expanded(child: _mapView(ink)),
            _bottomStrip(ink, stamps),
          ]);
        },
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  final GZInk ink;
  const _Legend({required this.ink});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(color: Colors.white.withOpacity(0.92), borderRadius: BorderRadius.circular(12)),
        child: const Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.circle, size: 10, color: Color(0xFF1A73E8)),
          SizedBox(width: 6),
          Text('You', style: TextStyle(fontSize: 11, color: Color(0xFF06384F), fontWeight: FontWeight.w700)),
          SizedBox(width: 12),
          Icon(Icons.check_circle, size: 12, color: Color(0xFFD9A400)),
          SizedBox(width: 6),
          Text('Stamped', style: TextStyle(fontSize: 11, color: Color(0xFF06384F), fontWeight: FontWeight.w700)),
          SizedBox(width: 12),
          Text('Illustrated chart', style: TextStyle(fontSize: 11, color: Color(0xFF5B6B73))),
        ]),
      );
}

class _ChartPainter extends CustomPainter {
  final _Proj proj;
  final List<Offset> clear;
  final List<(Offset, Offset)> edges;
  final bool dark;
  _ChartPainter(this.proj, this.clear, this.edges, this.dark);

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    // Land
    canvas.drawRect(
      rect,
      Paint()..shader = ui.Gradient.linear(Offset.zero, Offset(size.width, size.height), dark ? [const Color(0xFF2E1B14), const Color(0xFF22130E)] : [const Color(0xFFF4EEDD), const Color(0xFFE9E0C8)]),
    );
    // Sea polygon
    final topLat = proj.latAt(0), botLat = proj.latAt(size.height);
    const n = 48;
    final shorePts = <Offset>[
      for (var i = 0; i <= n; i++)
        () {
          final lat = topLat + (botLat - topLat) * i / n;
          return proj.xy(lat, _coastLon(lat));
        }()
    ];
    final sea = Path()..moveTo(-400, shorePts.first.dy);
    for (final p in shorePts) {
      sea.lineTo(p.dx, p.dy);
    }
    sea
      ..lineTo(-400, shorePts.last.dy)
      ..close();
    final minX = shorePts.map((p) => p.dx).reduce(math.min);
    final maxX = shorePts.map((p) => p.dx).reduce(math.max);
    canvas.drawPath(
      sea,
      Paint()..shader = ui.Gradient.linear(Offset(minX - 500, 0), Offset(maxX, 0), [const Color(0xFF0B6A90), const Color(0xFF20A4B0), const Color(0xFF8FC2B9)], [0, 0.7, 1]),
    );
    // Wave lines parallel to the shore
    final shore = Path()..moveTo(shorePts.first.dx, shorePts.first.dy);
    for (final p in shorePts.skip(1)) {
      shore.lineTo(p.dx, p.dy);
    }
    for (var i = 1; i <= 6; i++) {
      canvas.drawPath(
        shore.shift(Offset(-26.0 * i, 0)),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.2
          ..color = Colors.white.withOpacity(0.32 - i * 0.04),
      );
    }
    canvas.drawPath(
      shore,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 7
        ..color = const Color(0xFFFBF3E2),
    );
    // Constellation links between neighbouring places
    final link = Paint()
      ..color = (dark ? const Color(0xFFFFC136) : const Color(0xFF006996)).withOpacity(0.22)
      ..strokeWidth = 2;
    for (final e in edges) {
      final d = e.$2 - e.$1;
      final len = d.distance;
      if (len < 1) continue;
      final u = d / len;
      for (var t = 0.0; t < len; t += 16) {
        canvas.drawLine(e.$1 + u * t, e.$1 + u * math.min(t + 7, len), link);
      }
    }
    // Sea label
    final tp = TextPainter(
      text: const TextSpan(text: 'ARABIAN SEA', style: TextStyle(color: Color(0xB3FFFFFF), fontSize: 46, letterSpacing: 14, fontWeight: FontWeight.w800)),
      textDirection: TextDirection.ltr,
    )..layout();
    canvas.save();
    final mid = proj.xy(proj.lat0, _coastLon(proj.lat0));
    canvas.translate(mid.dx - 170, size.height / 2 + tp.width / 2);
    canvas.rotate(-math.pi / 2);
    tp.paint(canvas, Offset.zero);
    canvas.restore();

    // Unexplored haze over the land only, cleared around stamped places.
    final landOnly = Path.combine(PathOperation.difference, Path()..addRect(rect), sea);
    canvas.save();
    canvas.clipPath(landOnly);
    canvas.saveLayer(rect, Paint());
    canvas.drawRect(rect, Paint()..color = (dark ? const Color(0xFF140805) : const Color(0xFFF8F4E8)).withOpacity(0.7));
    final hatch = Paint()
      ..color = (dark ? Colors.white : const Color(0xFF8C6B3A)).withOpacity(0.10)
      ..strokeWidth = 2;
    for (var x = -size.height; x < size.width; x += 22) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), hatch);
    }
    final hole = Paint()
      ..blendMode = BlendMode.clear
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 34);
    for (final o in clear) {
      canvas.drawCircle(o, _kReveal, hole);
    }
    canvas.restore();
    canvas.restore();
    // Golden dashed edge of explored areas
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..color = const Color(0xFFFFC136).withOpacity(0.9);
    for (final o in clear) {
      for (var a = 0.0; a < math.pi * 2; a += 0.12) {
        canvas.drawArc(Rect.fromCircle(center: o, radius: _kReveal), a, 0.06, false, ring);
      }
    }
  }

  @override
  bool shouldRepaint(_ChartPainter old) => old.clear.length != clear.length || old.dark != dark || old.proj != proj;
}

class _Compass extends StatelessWidget {
  const _Compass();

  @override
  Widget build(BuildContext context) => SizedBox(width: 60, height: 60, child: CustomPaint(painter: _CompassPainter()));
}

class _CompassPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final c = s.center(Offset.zero);
    canvas.drawCircle(c, 28, Paint()..color = const Color(0xFFFBF3E2).withOpacity(0.95));
    canvas.drawCircle(
      c,
      28,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = const Color(0xFF06384F),
    );
    final n = Path()
      ..moveTo(c.dx, c.dy - 22)
      ..lineTo(c.dx - 6, c.dy)
      ..lineTo(c.dx + 6, c.dy)
      ..close();
    final so = Path()
      ..moveTo(c.dx, c.dy + 22)
      ..lineTo(c.dx - 6, c.dy)
      ..lineTo(c.dx + 6, c.dy)
      ..close();
    canvas.drawPath(n, Paint()..color = const Color(0xFFC8481F));
    canvas.drawPath(so, Paint()..color = const Color(0xFF06384F));
  }

  @override
  bool shouldRepaint(_) => false;
}
