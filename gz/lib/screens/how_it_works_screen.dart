import 'package:flutter/material.dart';

import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/top_bar.dart';
import '../widgets/tiara/gz_frame_card.dart';
import '../widgets/tiara/gz_page.dart';
import '../widgets/tiara/gz_reveal.dart';
import '../widgets/tiara/gz_sticker_button.dart';
import 'about_screen.dart';
import 'auth_screen.dart';
import 'explore/explore_screen.dart';

class HowItWorksScreen extends StatelessWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;

  const HowItWorksScreen({super.key, required this.locale, required this.theme, required this.auth});

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
    final steps = [
      (Icons.checklist_outlined, t('s1_t'), t('s1_d')),
      (Icons.auto_awesome_outlined, t('s2_t'), t('s2_d')),
      (Icons.alt_route_outlined, t('s3_t'), t('s3_d')),
      (Icons.navigation_outlined, t('s4_t'), t('s4_d')),
      (Icons.forum_outlined, t('s5_t'), t('s5_d')),
    ];

    void openAbout() => Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => AboutScreen(locale: locale, theme: theme, auth: auth)),
        );
    void openSignUp() => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => AuthScreen(locale: locale, theme: theme, auth: auth, startOnSignUp: true)),
        );
    void openExplore() => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => ExploreScreen(auth: auth, locale: locale, theme: theme)),
        );

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: GZTopBar(
        locale: locale,
        theme: theme,
        onLogoTap: () => Navigator.of(context).popUntil((r) => r.isFirst),
        onAbout: openAbout,
        onHowItWorks: () {},
        onSignUp: openSignUp,
        onExplore: openExplore,
      ),
      body: GZPageShell(
        kicker: 'how it works',
        title: t('how_title'),
        subtitle: t('how_sub'),
        footerCredit: t('footer'),
        footerLinks: [
          ('Explore', openExplore),
          (t('nav_about'), openAbout),
          (t('nav_signup'), openSignUp),
        ],
        children: [
          for (var i = 0; i < steps.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 26),
              child: GZReveal(
                child: GZFrameCard(
                  lift: true,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 56,
                        height: 56,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: ink.accent,
                          shape: BoxShape.circle,
                          border: Border.all(color: ink.hairline, width: 1),
                        ),
                        child: Text(
                          (i + 1).toString().padLeft(2, '0'),
                          style: text.titleMedium?.copyWith(
                            color: ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE),
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      const SizedBox(width: 20),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(steps[i].$1, size: 20, color: ink.accent),
                                const SizedBox(width: 8),
                                Expanded(child: Text(steps[i].$2, style: text.titleMedium?.copyWith(color: ink.text, fontWeight: FontWeight.w800))),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(steps[i].$3, style: text.bodyMedium?.copyWith(color: ink.muted, height: 1.5)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          const SizedBox(height: 10),
          GZStickerButton(label: t('how_cta'), icon: Icons.arrow_outward_rounded, onPressed: openSignUp),
        ],
      ),
    );
  }
}
