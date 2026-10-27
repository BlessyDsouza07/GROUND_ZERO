import 'package:flutter/material.dart';

import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/top_bar.dart';
import '../widgets/tiara/gz_frame_card.dart';
import '../widgets/tiara/gz_grid.dart';
import '../widgets/tiara/gz_page.dart';
import '../widgets/tiara/gz_reveal.dart';
import 'auth_screen.dart';
import 'explore/explore_screen.dart';
import 'how_it_works_screen.dart';

class AboutScreen extends StatelessWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;

  const AboutScreen({super.key, required this.locale, required this.theme, required this.auth});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([locale, theme]),
      builder: (context, _) => _buildScaffold(context),
    );
  }

  Widget _buildScaffold(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final wide = MediaQuery.of(context).size.width >= 760;

    void openHow() => Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => HowItWorksScreen(locale: locale, theme: theme, auth: auth)),
        );
    void openSignUp() => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => AuthScreen(locale: locale, theme: theme, auth: auth, startOnSignUp: true)),
        );
    void openExplore() => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => ExploreScreen(auth: auth, locale: locale, theme: theme)),
        );

    final values = [
      (Icons.person_outline, t('p1_t'), t('p1_d')),
      (Icons.verified_outlined, t('p2_t'), t('p2_d')),
      (Icons.shield_outlined, t('p3_t'), t('p3_d')),
      (Icons.spa_outlined, t('p4_t'), t('p4_d')),
    ];

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: GZTopBar(
        locale: locale,
        theme: theme,
        onLogoTap: () => Navigator.of(context).popUntil((r) => r.isFirst),
        onAbout: () {},
        onHowItWorks: openHow,
        onSignUp: openSignUp,
        onExplore: openExplore,
      ),
      body: GZPageShell(
        kicker: 'about',
        title: t('about_title'),
        subtitle: t('about_intro'),
        footerCredit: t('footer'),
        footerLinks: [
          ('Explore', openExplore),
          (t('nav_how'), openHow),
          (t('nav_signup'), openSignUp),
        ],
        children: [
          GZReveal(
            child: GZFrameCard(
              padding: const EdgeInsets.all(28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('about_why_t'), style: text.titleLarge?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  Text(t('about_why_d'), style: text.bodyLarge?.copyWith(color: ink.muted, height: 1.55)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 44),
          GZReveal(child: Text(t('about_values_t'), style: text.headlineMedium?.copyWith(color: ink.text))),
          const SizedBox(height: 20),
          GZEqualGrid(
            columns: wide ? 2 : 1,
            gap: 20,
            children: [
              for (var i = 0; i < values.length; i++)
                GZReveal(
                  delay: Duration(milliseconds: 80 * (i % 2)),
                  child: GZFrameCard(
                    lift: true,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            GZTag((i + 1).toString().padLeft(2, '0'), filled: true),
                            const Spacer(),
                            Icon(values[i].$1, color: ink.accent),
                          ],
                        ),
                        const SizedBox(height: 14),
                        Text(values[i].$2, style: text.titleMedium?.copyWith(color: ink.text, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        Text(values[i].$3, style: text.bodyMedium?.copyWith(color: ink.muted, height: 1.5)),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 40),
          GZReveal(
            child: GZFrameCard(
              color: ink.paperAlt.withOpacity(ink.dark ? 0.6 : 0.55),
              padding: const EdgeInsets.all(26),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.location_on_outlined, color: ink.accent, size: 28),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('about_local_t'), style: text.titleMedium?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        Text(t('about_local_d'), style: text.bodyMedium?.copyWith(color: ink.text, height: 1.5)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
