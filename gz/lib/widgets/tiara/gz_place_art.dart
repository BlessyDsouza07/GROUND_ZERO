import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'gz_art_data.dart';

enum GZArtKind { coast, heritage, nature, food, market, stay, generic }

GZArtKind gzArtKindFor(String category, List<String> tags) {
  final all = {category, ...tags};
  bool has(List<String> k) => k.any(all.contains);
  if (has(['bus_stand', 'transit_point', 'railway'])) return GZArtKind.generic;
  if (has(['beach', 'coast', 'harbour'])) return GZArtKind.coast;
  if (has(['restaurant', 'cafe', 'coffee_shop', 'local_kitchen', 'street_food', 'bakery', 'dessert_shop', 'ice_cream', 'food_court'])) return GZArtKind.food;
  if (has(['heritage_site', 'temple', 'church', 'mosque', 'museum', 'art_gallery', 'library', 'theatre'])) return GZArtKind.heritage;
  if (has(['park', 'garden', 'lake', 'nature_spot', 'viewpoint'])) return GZArtKind.nature;
  if (has(['market', 'local_shop', 'shopping_mall'])) return GZArtKind.market;
  if (has(['lodging'])) return GZArtKind.stay;
  return GZArtKind.generic;
}

/// A finer subject inside a kind (a temple vs a church, a fish plate vs a
/// coffee cup), chosen from the place's own category, tags and name.
String gzArtSub(String category, List<String> tags, String name) {
  final all = {category, ...tags}.map((e) => e.toLowerCase()).toSet();
  final n = name.toLowerCase();
  bool has(List<String> k) => k.any(all.contains);
  bool nm(List<String> k) => k.any(n.contains);
  if (has(['bus_stand', 'transit_point', 'railway'])) return 'bus';
  if (has(['church', 'christian']) || nm(['church', 'chapel', 'cathedral', 'basilica'])) return 'church';
  if (has(['mosque', 'muslim']) || nm(['masjid', 'mosque', 'juma', 'dargah'])) return 'mosque';
  if (has(['temple', 'hindu']) || nm(['temple', 'devasthana', 'mutt', 'kshetra', 'mandir'])) return 'temple';
  if (has(['seafood']) || nm(['fish', 'seafood', 'kori', 'prawn', 'crab'])) return 'seafood';
  if (has(['cafe', 'coffee_shop']) || nm(['cafe', 'coffee', 'chai', 'tea '])) return 'coffee';
  if (has(['dessert_shop', 'ice_cream', 'bakery']) || nm(['ice cream', 'bakery', 'sweets', 'dessert'])) return 'dessert';
  if (has(['street_food'])) return 'street';
  if (has(['lake']) || nm(['lake', 'kere'])) return 'lake';
  if (has(['park', 'garden'])) return 'park';
  if (has(['lighthouse']) || nm(['light house', 'lighthouse'])) return 'lighthouse';
  return '';
}

IconData gzArtIcon(GZArtKind k) => switch (k) {
      GZArtKind.coast => Icons.waves_rounded,
      GZArtKind.heritage => Icons.account_balance_outlined,
      GZArtKind.nature => Icons.park_outlined,
      GZArtKind.food => Icons.ramen_dining_outlined,
      GZArtKind.market => Icons.storefront_outlined,
      GZArtKind.stay => Icons.bed_outlined,
      GZArtKind.generic => Icons.place_outlined,
    };

String gzArtLabel(GZArtKind k) => switch (k) {
      GZArtKind.coast => 'Coast',
      GZArtKind.heritage => 'Heritage',
      GZArtKind.nature => 'Nature',
      GZArtKind.food => 'Food',
      GZArtKind.market => 'Local life',
      GZArtKind.stay => 'Stay',
      GZArtKind.generic => 'Place',
    };

/// Illustrated cover art: hand-composed vector scenes (a gopuram for a
/// temple, a plate of fish for a seafood kitchen, a lighthouse...) in three
/// colourways, picked per place. It is an illustration of the *kind* of
/// place, never a photo of it. [t] (0..1, looping) breathes the scene while
/// hovered and [shift] (-1..1) slides it with the pointer for depth.
class GZPlaceArt extends StatelessWidget {
  final GZArtKind kind;
  final String sub;
  final String seed;
  final double t;
  final Offset shift;
  const GZPlaceArt({super.key, required this.kind, required this.seed, this.sub = '', this.t = 0, this.shift = Offset.zero});

  String get _scene {
    if (kGZArtSvgs.containsKey(sub)) return sub;
    return switch (kind) {
      GZArtKind.coast => 'coast',
      GZArtKind.heritage => 'heritage',
      GZArtKind.nature => seed.hashCode.abs() % 2 == 0 ? 'lake' : 'park',
      GZArtKind.food => 'thali',
      GZArtKind.market => 'market',
      GZArtKind.stay => 'stay',
      GZArtKind.generic => 'generic',
    };
  }

  @override
  Widget build(BuildContext context) {
    final variants = kGZArtSvgs[_scene]!;
    final svg = variants[seed.hashCode.abs() % variants.length];
    final breathe = 1.07 + 0.015 * math.sin(t * 2 * math.pi);
    return ClipRect(
      child: Transform.translate(
        offset: Offset(-shift.dx * 8, 0),
        child: Transform.scale(
          scale: breathe,
          child: SvgPicture.string(svg, fit: BoxFit.cover, alignment: Alignment.center, width: double.infinity, height: double.infinity),
        ),
      ),
    );
  }
}
