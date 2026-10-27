import 'package:flutter/material.dart';

import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/top_bar.dart';
import '../widgets/tiara/gz_footer.dart';
import '../widgets/tiara/gz_frame_card.dart';
import '../widgets/tiara/gz_golden_hour.dart';
import '../widgets/tiara/gz_grid.dart';
import '../widgets/tiara/gz_marquee.dart';
import '../widgets/tiara/gz_reveal.dart';
import '../widgets/tiara/gz_scene.dart';
import '../widgets/tiara/gz_sticker_button.dart';
import 'about_screen.dart';
import 'auth_screen.dart';
import 'explore/explore_screen.dart';
import 'how_it_works_screen.dart';

/// The very first page of GroundZero: the public landing page. Reachable
/// only while nobody is signed in — see main.dart, which swaps the whole
/// app over to [StartScreen] the moment sign-in succeeds.
///
/// Visual language is taken from the Tiara'26 festival site (retro
/// illustrated hero with drifting layers, floating capsule nav, framed
/// cards, ticker strip, numbered "signal" cards, countdown block, big
/// illustrated footer) and re-drawn for the Mangaluru coast.
class HomeScreen extends StatefulWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;

  const HomeScreen({super.key, required this.locale, required this.theme, required this.auth});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ScrollController _scroll = ScrollController();

  LocaleController get locale => widget.locale;
  ThemeController get theme => widget.theme;
  AuthController get auth => widget.auth;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _openAbout() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => AboutScreen(locale: locale, theme: theme, auth: auth),
    ));
  }

  void _openHowItWorks() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => HowItWorksScreen(locale: locale, theme: theme, auth: auth),
    ));
  }

  void _openSignUp() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => AuthScreen(locale: locale, theme: theme, auth: auth, startOnSignUp: true),
    ));
  }

  // Explore is deliberately reachable before sign-up — browsing works for
  // a signed-out tourist; the sign-up wall only appears at save/add-to-trip.
  void _openExplore() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ExploreScreen(auth: auth, locale: locale, theme: theme),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([locale, theme]),
      builder: (context, _) => _buildScaffold(context),
    );
  }

  Widget _buildScaffold(BuildContext context) {
    final t = locale.t;
    final wide = MediaQuery.of(context).size.width >= 900;
    final screenH = MediaQuery.of(context).size.height;
    final heroH = screenH.clamp(640.0, 820.0).toDouble();

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: GZTopBar(
        locale: locale,
        theme: theme,
        onAbout: _openAbout,
        onHowItWorks: _openHowItWorks,
        onSignUp: _openSignUp,
        onExplore: _openExplore,
      ),
      body: SingleChildScrollView(
        controller: _scroll,
        child: Column(
          children: [
            SizedBox(
              height: heroH,
              width: double.infinity,
              child: GZScene(
                scroll: _scroll,
                child: _HeroContent(locale: locale, wide: wide, onStart: _openSignUp, onHow: _openHowItWorks),
              ),
            ),
            _IntroStrip(locale: locale, wide: wide),
            const GZMarquee(
              items: ['Beaches', 'Temples', 'Churches', 'Seafood', 'Heritage', 'Markets', 'Sunsets', 'Local secrets'],
            ),
            _FeaturesSection(locale: locale, wide: wide),
            _PlacesSection(onExplore: _openExplore),
            _SignalsSection(locale: locale, wide: wide),
            _FinalCta(locale: locale, wide: wide, onStart: _openSignUp, onExplore: _openExplore),
            GZFooter(
              credit: t('footer'),
              explore: [
                ('Explore', _openExplore),
                (t('nav_about'), _openAbout),
                (t('nav_how'), _openHowItWorks),
                (t('nav_signup'), _openSignUp),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

const _cream = Color(0xFFFBF3E2);

class _SectionHead extends StatelessWidget {
  final String kicker;
  final String title;
  final bool center;
  const _SectionHead({required this.kicker, required this.title, this.center = false});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: center ? CrossAxisAlignment.center : CrossAxisAlignment.start,
      children: [
        Text(kicker.toUpperCase(), style: text.labelMedium?.copyWith(color: ink.accent, letterSpacing: 2.6, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Text(
          title,
          textAlign: center ? TextAlign.center : TextAlign.start,
          style: text.displaySmall?.copyWith(color: ink.text, letterSpacing: -1.2),
        ),
      ],
    );
  }
}

class _HeroContent extends StatelessWidget {
  final LocaleController locale;
  final bool wide;
  final VoidCallback onStart;
  final VoidCallback onHow;

  const _HeroContent({required this.locale, required this.wide, required this.onStart, required this.onHow});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final width = MediaQuery.of(context).size.width;
    final wordSize = (width * (wide ? 0.115 : 0.15)).clamp(40.0, 132.0).toDouble();

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 100, 20, 36),
      child: Column(
        children: [
          const Spacer(flex: 2),
          GZReveal(
            child: GZTag(t('hero_kicker'), icon: Icons.waves_rounded),
          ),
          const SizedBox(height: 14),
          GZReveal(
            delay: const Duration(milliseconds: 120),
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                'groundzero',
                style: text.displayLarge?.copyWith(
                  fontSize: wordSize,
                  color: _cream,
                  letterSpacing: -wordSize * 0.045,
                  shadows: [Shadow(color: Color(0x55000000), blurRadius: 16, offset: Offset(0, 3))],
                ),
              ),
            ),
          ),
          const SizedBox(height: 18),
          GZReveal(
            delay: const Duration(milliseconds: 260),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 680),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
                decoration: BoxDecoration(
                  color: ink.paper,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: ink.hairline, width: 1),
                  boxShadow: ink.softShadow,
                ),
                child: Text(
                  t('hero_title'),
                  textAlign: TextAlign.center,
                  style: (wide ? text.titleLarge : text.titleMedium)?.copyWith(color: ink.text, fontWeight: FontWeight.w800),
                ),
              ),
            ),
          ),
          const SizedBox(height: 26),
          GZReveal(
            delay: const Duration(milliseconds: 380),
            child: Wrap(
              alignment: WrapAlignment.center,
              spacing: 16,
              runSpacing: 16,
              children: [
                GZStickerButton(label: t('cta_start'), icon: Icons.arrow_outward_rounded, onPressed: onStart),
                GZStickerButton(label: t('cta_how'), outlined: true, onPressed: onHow),
              ],
            ),
          ),
          const Spacer(flex: 3),
          const _ScrollCue(),
        ],
      ),
    );
  }
}

class _ScrollCue extends StatefulWidget {
  const _ScrollCue();

  @override
  State<_ScrollCue> createState() => _ScrollCueState();
}

class _ScrollCueState extends State<_ScrollCue> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, _) => Transform.translate(
        offset: Offset(0, Curves.easeInOut.transform(_c.value) * 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('SCROLL TO EXPLORE', style: text.labelMedium?.copyWith(color: _cream, letterSpacing: 2.4)),
            const Icon(Icons.keyboard_arrow_down_rounded, color: _cream, size: 26),
          ],
        ),
      ),
    );
  }
}

class _IntroStrip extends StatelessWidget {
  final LocaleController locale;
  final bool wide;
  const _IntroStrip({required this.locale, required this.wide});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 72 : 48),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: GZReveal(
            child: Column(
              children: [
                Text(
                  t('hero_sub'),
                  textAlign: TextAlign.center,
                  style: text.bodyLarge?.copyWith(fontSize: wide ? 22 : 18, height: 1.55, color: ink.text),
                ),
                const SizedBox(height: 24),
                const Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    GZTag('Mangaluru', icon: Icons.place_outlined),
                    GZTag('12.87°N 74.84°E'),
                    GZTag('5 languages', icon: Icons.translate),
                    GZTag('Free to start', filled: true),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FeaturesSection extends StatelessWidget {
  final LocaleController locale;
  final bool wide;
  const _FeaturesSection({required this.locale, required this.wide});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final items = <(IconData, String, String, GZPlaceArt)>[
      (Icons.route, t('f1_t'), t('f1_d'), GZPlaceArt.beach),
      (Icons.volume_off_outlined, t('f2_t'), t('f2_d'), GZPlaceArt.temple),
      (Icons.bolt_outlined, t('f3_t'), t('f3_d'), GZPlaceArt.nature),
      (Icons.diversity_3_outlined, t('f4_t'), t('f4_d'), GZPlaceArt.heritage),
      (Icons.translate, t('f5_t'), t('f5_d'), GZPlaceArt.fort),
    ];
    return Container(
      width: double.infinity,
      color: ink.paperAlt.withOpacity(ink.dark ? 0.35 : 0.30),
      padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 88 : 56),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1120),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const GZReveal(child: _SectionHead(kicker: '01 · What you get', title: 'What GroundZero does')),
              const SizedBox(height: 36),
              LayoutBuilder(builder: (context, box) {
                final cols = box.maxWidth >= 980 ? 3 : (box.maxWidth >= 640 ? 2 : 1);
                return GZEqualGrid(
                  columns: cols,
                  gap: 24,
                  children: [
                    for (var i = 0; i < items.length; i++)
                      GZReveal(
                        delay: Duration(milliseconds: 90 * (i % cols)),
                        child: _FeatureCard(index: i + 1, icon: items[i].$1, title: items[i].$2, desc: items[i].$3, art: items[i].$4),
                      ),
                  ],
                );
              }),
            ],
          ),
        ),
      ),
    );
  }
}

class _FeatureCard extends StatelessWidget {
  final int index;
  final IconData icon;
  final String title;
  final String desc;
  final GZPlaceArt art;

  const _FeatureCard({required this.index, required this.icon, required this.title, required this.desc, required this.art});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return GZFrameCard(
      padding: EdgeInsets.zero,
      lift: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 130,
            width: double.infinity,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CustomPaint(painter: GZPlaceArtPainter(kind: art, dark: ink.dark)),
                Positioned(left: 14, top: 14, child: GZTag(index.toString().padLeft(2, '0'), filled: true)),
              ],
            ),
          ),
          Container(height: 2, color: ink.border),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, color: ink.accent, size: 22),
                    const SizedBox(width: 10),
                    Expanded(child: Text(title, style: text.titleMedium?.copyWith(color: ink.text, fontWeight: FontWeight.w800))),
                  ],
                ),
                const SizedBox(height: 10),
                Text(desc, style: text.bodyMedium?.copyWith(color: ink.muted, height: 1.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PlacesSection extends StatelessWidget {
  final VoidCallback onExplore;
  const _PlacesSection({required this.onExplore});

  static const _places = <(String, String, GZPlaceArt)>[
    ('Panambur Beach', 'beach', GZPlaceArt.beach),
    ('Kadri Manjunath Temple', 'temple', GZPlaceArt.temple),
    ('St Aloysius Chapel', 'heritage', GZPlaceArt.heritage),
    ('Tannirbhavi Beach', 'beach', GZPlaceArt.beach),
    ('Sultan Battery', 'fort', GZPlaceArt.fort),
    ('Pilikula Nisargadhama', 'nature', GZPlaceArt.nature),
    ('Mangaladevi Temple', 'temple', GZPlaceArt.temple),
    ('Someshwar Beach', 'beach', GZPlaceArt.beach),
  ];

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final wide = MediaQuery.of(context).size.width >= 900;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.only(top: wide ? 88 : 56, bottom: wide ? 88 : 56),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.symmetric(horizontal: wide ? (MediaQuery.of(context).size.width - 1120).clamp(24.0, 9999.0) / 2 : 24),
            child: const GZReveal(child: _SectionHead(kicker: '02 · The coast', title: 'Places you will meet')),
          ),
          const SizedBox(height: 32),
          SizedBox(
            height: 318,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(horizontal: wide ? (MediaQuery.of(context).size.width - 1120).clamp(24.0, 9999.0) / 2 : 24, vertical: 8),
              itemCount: _places.length,
              separatorBuilder: (_, __) => const SizedBox(width: 24),
              itemBuilder: (context, i) {
                final p = _places[i];
                return SizedBox(
                  width: 230,
                  child: Transform.rotate(
                    angle: (i.isEven ? -1 : 1) * 0.018,
                    child: GZFrameCard(
                      padding: EdgeInsets.zero,
                      radius: 18,
                      onTap: onExplore,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(
                            height: 190,
                            width: double.infinity,
                            child: Stack(
                              fit: StackFit.expand,
                              children: [
                                CustomPaint(painter: GZPlaceArtPainter(kind: p.$3, dark: ink.dark)),
                                Positioned(
                                  right: 10,
                                  top: 10,
                                  child: Icon(Icons.photo_camera_outlined, color: ink.dark ? const Color(0xFFFBE9C6) : const Color(0xFFF7F4EE), size: 20),
                                ),
                              ],
                            ),
                          ),
                          Container(height: 2, color: ink.border),
                          Padding(
                            padding: const EdgeInsets.all(14),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(p.$1, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.titleSmall?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
                                const SizedBox(height: 8),
                                GZTag(p.$2),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Tiara's "transmission 01–03 / counter" block: a paged set of numbered
/// cards, here carrying the five steps of how GroundZero works.
class _SignalsSection extends StatefulWidget {
  final LocaleController locale;
  final bool wide;
  const _SignalsSection({required this.locale, required this.wide});

  @override
  State<_SignalsSection> createState() => _SignalsSectionState();
}

class _SignalsSectionState extends State<_SignalsSection> {
  static const _count = 5;
  final ScrollController _list = ScrollController();
  int _page = 0;
  double _stride = 400;

  @override
  void initState() {
    super.initState();
    _list.addListener(_onScroll);
  }

  void _onScroll() {
    if (!_list.hasClients || _stride <= 0) return;
    final pos = _list.position;
    var i = (pos.pixels / _stride).round().clamp(0, _count - 1).toInt();
    if (pos.maxScrollExtent > 0 && pos.pixels >= pos.maxScrollExtent - 4) i = _count - 1;
    if (i != _page) setState(() => _page = i);
  }

  @override
  void dispose() {
    _list.removeListener(_onScroll);
    _list.dispose();
    super.dispose();
  }

  void _go(int delta) {
    if (!_list.hasClients) return;
    final next = (_page + delta).clamp(0, _count - 1).toInt();
    final target = (next * _stride).clamp(0.0, _list.position.maxScrollExtent).toDouble();
    _list.animateTo(target, duration: const Duration(milliseconds: 420), curve: Curves.easeOutCubic);
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final steps = <(IconData, String, String)>[
      (Icons.checklist_outlined, t('s1_t'), t('s1_d')),
      (Icons.auto_awesome_outlined, t('s2_t'), t('s2_d')),
      (Icons.alt_route_outlined, t('s3_t'), t('s3_d')),
      (Icons.navigation_outlined, t('s4_t'), t('s4_d')),
      (Icons.forum_outlined, t('s5_t'), t('s5_d')),
    ];
    final width = MediaQuery.of(context).size.width;
    final padX = width >= 900 ? (width - 1120).clamp(24.0, 9999.0) / 2 : 24.0;
    final cardW = width >= 900 ? 420.0 : (width - 48) * 0.88;
    _stride = cardW + 22;

    return Container(
      width: double.infinity,
      color: ink.paperAlt.withOpacity(ink.dark ? 0.35 : 0.30),
      padding: EdgeInsets.symmetric(vertical: widget.wide ? 88 : 56),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.symmetric(horizontal: padX),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                const Expanded(child: GZReveal(child: _SectionHead(kicker: '03 · First question to last stop', title: 'Five steps, one day'))),
                const SizedBox(width: 12),
                Text(
                  '${(_page + 1).toString().padLeft(2, '0')}/${_count.toString().padLeft(2, '0')}',
                  style: text.headlineSmall?.copyWith(color: ink.accent, fontWeight: FontWeight.w800),
                ),
              ],
            ),
          ),
          const SizedBox(height: 28),
          SizedBox(
            height: 300,
            child: ListView.separated(
              controller: _list,
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.fromLTRB(padX, 6, padX, 14),
              itemCount: steps.length,
              separatorBuilder: (_, __) => const SizedBox(width: 22),
              itemBuilder: (context, i) {
                final s = steps[i];
                return SizedBox(
                  width: cardW,
                  child: GZFrameCard(
                    lift: true,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            GZTag('Step ${(i + 1).toString().padLeft(2, '0')}', filled: true),
                            const Spacer(),
                            Icon(s.$1, color: ink.accent, size: 26),
                          ],
                        ),
                        const SizedBox(height: 18),
                        Text(s.$2, style: text.titleLarge?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 10),
                        Expanded(
                          child: SingleChildScrollView(
                            physics: const NeverScrollableScrollPhysics(),
                            child: Text(s.$3, style: text.bodyMedium?.copyWith(color: ink.muted, height: 1.5)),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 12),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: padX),
            child: Row(
              children: [
                _ArrowButton(icon: Icons.arrow_back_rounded, onTap: _page == 0 ? null : () => _go(-1)),
                const SizedBox(width: 12),
                _ArrowButton(icon: Icons.arrow_forward_rounded, onTap: _page == _count - 1 ? null : () => _go(1)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ArrowButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  const _ArrowButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Opacity(
      opacity: onTap == null ? 0.4 : 1,
      child: InkResponse(
        onTap: onTap,
        radius: 28,
        child: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: ink.paper,
            shape: BoxShape.circle,
            border: Border.all(color: ink.hairline, width: 1),
            boxShadow: ink.softShadow,
          ),
          child: Icon(icon, color: ink.text),
        ),
      ),
    );
  }
}

class _FinalCta extends StatelessWidget {
  final LocaleController locale;
  final bool wide;
  final VoidCallback onStart;
  final VoidCallback onExplore;
  const _FinalCta({required this.locale, required this.wide, required this.onStart, required this.onExplore});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 96 : 56),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 940),
          child: GZReveal(
            child: GZFrameCard(
              padding: EdgeInsets.symmetric(horizontal: wide ? 56 : 24, vertical: wide ? 52 : 32),
              radius: 30,
              shadowOffset: 9,
              child: Column(
                children: [
                  GZTag('Ready when you are', icon: Icons.wb_twilight_outlined),
                  const SizedBox(height: 18),
                  Text(
                    t('cta_final_t'),
                    textAlign: TextAlign.center,
                    style: (wide ? text.displaySmall : text.headlineMedium)?.copyWith(color: ink.text, letterSpacing: -1),
                  ),
                  const SizedBox(height: 12),
                  Text(t('cta_final_d'), textAlign: TextAlign.center, style: text.bodyLarge?.copyWith(color: ink.muted)),
                  const SizedBox(height: 30),
                  const GZGoldenHourCountdown(),
                  const SizedBox(height: 32),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: 16,
                    runSpacing: 16,
                    children: [
                      GZStickerButton(label: t('cta_start'), icon: Icons.arrow_outward_rounded, onPressed: onStart),
                      GZStickerButton(label: 'Explore places', outlined: true, onPressed: onExplore),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
