import 'package:flutter/material.dart';

/// Back + Home controls used on every inner screen so a visitor is never
/// stuck. Back goes one step; Home returns to the start page.
class GZBackButton extends StatelessWidget {
  final Color? color;
  const GZBackButton({super.key, this.color});

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).appBarTheme.foregroundColor ?? Theme.of(context).colorScheme.onSurface;
    return IconButton(
      tooltip: 'Back',
      icon: Icon(Icons.arrow_back_rounded, color: c),
      onPressed: () => Navigator.of(context).maybePop(),
    );
  }
}

class GZHomeAction extends StatelessWidget {
  final Color? color;
  const GZHomeAction({super.key, this.color});

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).appBarTheme.foregroundColor ?? Theme.of(context).colorScheme.onSurface;
    return IconButton(
      tooltip: 'Home',
      icon: Icon(Icons.home_outlined, color: c),
      onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
    );
  }
}
