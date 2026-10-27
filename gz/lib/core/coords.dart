/// Forgiving latitude/longitude parsing. Accepts:
///   12.8834            -74.5         12.8834° N      74.8983 E
///   N 12.8834          12°52'0.2"N   12 52 0.2 N     "12.8834, 74.8983"
/// Returns null when the text can't be read as a coordinate.
class GZCoords {
  static double? parse(String raw, {required bool isLat}) {
    var s = raw.trim();
    if (s.isEmpty) return null;
    s = s
        .replaceAll('°', ' ')
        .replaceAll('′', ' ')
        .replaceAll('″', ' ')
        .replaceAll("'", ' ')
        .replaceAll('"', ' ')
        .replaceAll(',', ' ')
        .replaceAll('−', '-');
    var sign = 1.0;
    final hemi = RegExp(r'[NSEWnsew]').allMatches(s).map((m) => m.group(0)!.toUpperCase()).toList();
    if (hemi.length > 1) return null;
    if (hemi.isNotEmpty) {
      final h = hemi.first;
      if (isLat && (h == 'E' || h == 'W')) return null;
      if (!isLat && (h == 'N' || h == 'S')) return null;
      if (h == 'S' || h == 'W') sign = -1;
      s = s.replaceAll(RegExp(r'[NSEWnsew]'), ' ');
    }
    final parts = s.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty || parts.length > 3) return null;
    final nums = <double>[];
    for (final p in parts) {
      final v = double.tryParse(p);
      if (v == null) return null;
      nums.add(v);
    }
    var value = nums[0].abs();
    if (nums.length > 1) value += nums[1].abs() / 60;
    if (nums.length > 2) value += nums[2].abs() / 3600;
    if (parts[0].startsWith('-')) sign = -1;
    final result = value * sign;
    final limit = isLat ? 90.0 : 180.0;
    if (result.abs() > limit) return null;
    return result;
  }

  /// Splits "12.8834, 74.8983" (or "12.8834° N, 74.8983° E") pasted into one box.
  static (double, double)? parsePair(String raw) {
    final m = RegExp(r'^\s*(.+?)\s*[,;]\s*(.+?)\s*$').firstMatch(raw);
    if (m == null) return null;
    final a = parse(m.group(1)!, isLat: true);
    final b = parse(m.group(2)!, isLat: false);
    if (a == null || b == null) return null;
    return (a, b);
  }
}
