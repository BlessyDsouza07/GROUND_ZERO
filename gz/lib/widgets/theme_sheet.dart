import 'package:flutter/material.dart';

import '../core/locale_controller.dart';
import '../core/theme.dart';
import '../core/theme_controller.dart';

/// Bottom sheet used by the top bar's Theme action and by Settings.
/// Offers Automatic (follows the clock), Light and Dark, using only the
/// approved brand palettes for each preview swatch.
Future<void> showThemePicker({
  required BuildContext context,
  required ThemeController theme,
  required LocaleController locale,
}) {
  return showModalBottomSheet<void>(
    context: context,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) => AnimatedBuilder(
      animation: theme,
      builder: (context, _) => _ThemeSheetBody(theme: theme, locale: locale),
    ),
  );
}

class _ThemeSheetBody extends StatelessWidget {
  final ThemeController theme;
  final LocaleController locale;
  const _ThemeSheetBody({required this.theme, required this.locale});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
            Text(t('theme_choose'), style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            _ThemeOption(
              label: t('theme_auto'),
              hint: t('theme_auto_hint'),
              swatches: const [GZLightPalette.deepOceanBlue, GZDarkPalette.deepBurgundy],
              selected: theme.mode == GZThemeMode.automatic,
              onTap: () => theme.setMode(GZThemeMode.automatic),
            ),
            _ThemeOption(
              label: t('theme_light'),
              swatches: const [
                GZLightPalette.deepOceanBlue,
                GZLightPalette.tealBlue,
                GZLightPalette.warmIvory,
              ],
              selected: theme.mode == GZThemeMode.light,
              onTap: () => theme.setMode(GZThemeMode.light),
            ),
            _ThemeOption(
              label: t('theme_dark'),
              swatches: const [
                GZDarkPalette.goldenAmber,
                GZDarkPalette.rustSienna,
                GZDarkPalette.deepBurgundy,
              ],
              selected: theme.mode == GZThemeMode.dark,
              onTap: () => theme.setMode(GZThemeMode.dark),
            ),
          ],
        ),
      ),
    );
  }
}

class _ThemeOption extends StatelessWidget {
  final String label;
  final String? hint;
  final List<Color> swatches;
  final bool selected;
  final VoidCallback onTap;

  const _ThemeOption({
    required this.label,
    required this.swatches,
    required this.selected,
    required this.onTap,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: Row(
        mainAxisSize: MainAxisSize.min,
        children: swatches
            .map(
              (c) => Container(
                width: 18,
                height: 18,
                margin: const EdgeInsets.only(right: 4),
                decoration: BoxDecoration(color: c, shape: BoxShape.circle),
              ),
            )
            .toList(),
      ),
      title: Text(label),
      subtitle: hint != null ? Text(hint!) : null,
      trailing: selected ? Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary) : null,
    );
  }
}
