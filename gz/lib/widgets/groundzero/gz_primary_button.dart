import 'package:flutter/material.dart';

/// GroundZero's primary call-to-action button. A thin, explicitly-named
/// wrapper around `ElevatedButton` — the actual color/radius/padding
/// come from `gz_theme.dart`'s `elevatedButtonTheme`, which every
/// `ElevatedButton` already inherits, so this component's job is purely
/// to give call sites one consistent, readable name ("GZPrimaryButton"
/// instead of a bare `ElevatedButton` whose styling intent isn't
/// visible at the call site) and a consistent loading-state affordance.
class GZPrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;

  const GZPrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.loading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final child = loading
        ? const SizedBox(
            height: 20,
            width: 20,
            child: CircularProgressIndicator(strokeWidth: 2.4, valueColor: AlwaysStoppedAnimation(Colors.white)),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 8)],
              Text(label),
            ],
          );
    return ElevatedButton(onPressed: loading ? null : onPressed, child: child);
  }
}
