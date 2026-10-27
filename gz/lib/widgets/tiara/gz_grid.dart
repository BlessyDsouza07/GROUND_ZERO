import 'package:flutter/material.dart';

/// Equal-width, equal-height grid: every card in a row is stretched to the
/// tallest card of that row, and a short last row keeps the same column
/// width (no giant orphan card). Use instead of Wrap when cards must align.
class GZEqualGrid extends StatelessWidget {
  final List<Widget> children;
  final int columns;
  final double gap;

  const GZEqualGrid({super.key, required this.children, required this.columns, this.gap = 20});

  @override
  Widget build(BuildContext context) {
    final cols = columns < 1 ? 1 : columns;
    final rows = <Widget>[];
    for (var start = 0; start < children.length; start += cols) {
      final cells = <Widget>[];
      for (var i = 0; i < cols; i++) {
        if (i > 0) cells.add(SizedBox(width: gap));
        final idx = start + i;
        cells.add(Expanded(child: idx < children.length ? children[idx] : const SizedBox.shrink()));
      }
      rows.add(Padding(
        padding: EdgeInsets.only(bottom: start + cols < children.length ? gap : 0),
        child: IntrinsicHeight(child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: cells)),
      ));
    }
    return Column(children: rows);
  }
}
