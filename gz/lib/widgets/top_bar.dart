import 'package:flutter/material.dart';

import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import 'language_sheet.dart';
import 'theme_sheet.dart';
import 'tiara/gz_sticker_button.dart';

/// The top bar for GroundZero's public pages (home, about, how-it-works,
/// explore): a floating capsule nav in the Tiara manner — logo, text
/// links, translate + theme buttons and a "Sign Up for free" sticker.
///
/// Wide screens show every item inline; narrow screens collapse them
/// into a menu sheet so nothing is cramped or clipped. Pages that want
/// the painted hero behind the bar set `extendBodyBehindAppBar: true`.
class GZTopBar extends StatelessWidget implements PreferredSizeWidget {
  final LocaleController locale;
  final ThemeController theme;
  final VoidCallback onAbout;
  final VoidCallback onHowItWorks;
  final VoidCallback onSignUp;
  final VoidCallback? onLogoTap;
  // Explore is browsable before sign-up, so the public bar can point at
  // it. Optional: pages that don't pass it simply don't show the link.
  final VoidCallback? onExplore;

  const GZTopBar({
    super.key,
    required this.locale,
    required this.theme,
    required this.onAbout,
    required this.onHowItWorks,
    required this.onSignUp,
    this.onLogoTap,
    this.onExplore,
  });

  @override
  Size get preferredSize => const Size.fromHeight(86);

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final width = MediaQuery.of(context).size.width;
    final wide = width >= 900;

    final capsule = Container(
      height: 62,
      padding: EdgeInsets.symmetric(horizontal: wide ? 14 : 10),
      decoration: BoxDecoration(
        color: ink.paper.withOpacity(0.96),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: ink.hairline, width: 1),
        boxShadow: ink.softShadow,
      ),
      child: Row(
        children: [
          _Logo(onTap: onLogoTap),
          const Spacer(),
          if (wide) ...[
            if (onExplore != null) _NavLink(label: 'Explore', onTap: onExplore!),
            _NavLink(label: t('nav_about'), onTap: onAbout),
            _NavLink(label: t('nav_how'), onTap: onHowItWorks),
            const SizedBox(width: 8),
            _RoundIcon(
              icon: Icons.translate,
              tooltip: t('nav_translate'),
              onTap: () => showLanguagePicker(context: context, locale: locale),
            ),
            const SizedBox(width: 8),
            _RoundIcon(
              icon: Icons.brightness_6,
              tooltip: t('nav_theme'),
              onTap: () => showThemePicker(context: context, theme: theme, locale: locale),
            ),
            const SizedBox(width: 12),
            GZStickerButton(label: t('nav_signup'), onPressed: onSignUp, compact: true),
          ] else ...[
            _RoundIcon(icon: Icons.menu, tooltip: t('nav_menu'), onTap: () => _showMobileMenu(context)),
          ],
        ],
      ),
    );

    return Padding(
      padding: EdgeInsets.fromLTRB(wide ? 24 : 12, 12, wide ? 24 : 12, 12),
      child: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 1180), child: capsule),
      ),
    );
  }

  void _showMobileMenu(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: ink.paper,
      shape: RoundedRectangleBorder(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(26)),
        side: BorderSide(color: ink.hairline, width: 1),
      ),
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            if (onExplore != null)
              ListTile(
                leading: const Icon(Icons.explore_outlined),
                title: const Text('Explore'),
                onTap: () {
                  Navigator.of(sheetContext).pop();
                  onExplore!();
                },
              ),
            ListTile(
              leading: const Icon(Icons.info_outline),
              title: Text(t('nav_about')),
              onTap: () {
                Navigator.of(sheetContext).pop();
                onAbout();
              },
            ),
            ListTile(
              leading: const Icon(Icons.route_outlined),
              title: Text(t('nav_how')),
              onTap: () {
                Navigator.of(sheetContext).pop();
                onHowItWorks();
              },
            ),
            ListTile(
              leading: const Icon(Icons.translate),
              title: Text(t('nav_translate')),
              onTap: () {
                Navigator.of(sheetContext).pop();
                showLanguagePicker(context: context, locale: locale);
              },
            ),
            ListTile(
              leading: const Icon(Icons.brightness_6),
              title: Text(t('nav_theme')),
              onTap: () {
                Navigator.of(sheetContext).pop();
                showThemePicker(context: context, theme: theme, locale: locale);
              },
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
              child: GZStickerButton(
                label: t('nav_signup'),
                expand: true,
                onPressed: () {
                  Navigator.of(sheetContext).pop();
                  onSignUp();
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Logo extends StatelessWidget {
  final VoidCallback? onTap;
  const _Logo({this.onTap});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return MouseRegion(
      cursor: onTap == null ? MouseCursor.defer : SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: ink.accent,
                shape: BoxShape.circle,
                border: Border.all(color: ink.hairline, width: 1),
              ),
              child: Icon(Icons.explore_rounded, size: 23, color: ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE)),
            ),
            const SizedBox(width: 10),
            Text(
              'groundzero',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(color: ink.text, fontWeight: FontWeight.w800, letterSpacing: -0.8),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavLink extends StatefulWidget {
  final String label;
  final VoidCallback onTap;
  const _NavLink({required this.label, required this.onTap});

  @override
  State<_NavLink> createState() => _NavLinkState();
}

class _NavLinkState extends State<_NavLink> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final onAccent = ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE);
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          margin: const EdgeInsets.symmetric(horizontal: 2),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
          decoration: BoxDecoration(
            color: _hover ? ink.accent : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            widget.label.toUpperCase(),
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: _hover ? onAccent : ink.text,
                  letterSpacing: 1.3,
                  fontWeight: FontWeight.w700,
                ),
          ),
        ),
      ),
    );
  }
}

class _RoundIcon extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  const _RoundIcon({required this.icon, required this.tooltip, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Tooltip(
      message: tooltip,
      child: InkResponse(
        onTap: onTap,
        radius: 24,
        child: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: ink.hairline, width: 1)),
          child: Icon(icon, size: 19, color: ink.text),
        ),
      ),
    );
  }
}
