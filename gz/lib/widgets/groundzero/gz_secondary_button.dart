import 'package:flutter/material.dart';

/// GroundZero's secondary action button — same role as
/// [GZPrimaryButton] but for a lower-emphasis action (e.g. "Cancel"
/// beside a primary "Confirm"). Wraps `OutlinedButton`, whose styling
/// comes entirely from `gz_theme.dart`'s `outlinedButtonTheme`.
class GZSecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  const GZSecondaryButton({super.key, required this.label, required this.onPressed, this.icon});

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onPressed,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 8)],
          Text(label),
        ],
      ),
    );
  }
}
