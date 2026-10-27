import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/personal_api_client.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/tiara/gz_frame_card.dart';
import '../widgets/tiara/gz_grid.dart';
import '../widgets/tiara/gz_reveal.dart';
import '../widgets/tiara/gz_scene.dart';
import '../widgets/tiara/gz_sticker_button.dart';
import '../core/gz_consent.dart';
import '../widgets/gz_nudge_watcher.dart';
import 'explore/explore_screen.dart';
import 'hive/today_screen.dart';
import 'privacy/privacy_screen.dart';
import 'new_trip/survey_screen.dart';
import 'personal/contributions_screen.dart';
import 'personal/journal_hub_screen.dart';
import 'personal/my_trips_screen.dart';
import 'personal/notifications_screen.dart';
import 'guide_screen.dart';
import 'placeholder_screen.dart';
import 'settings_screen.dart';

enum _Tier { primary, secondary, tertiary }

class _SidebarItem {
  final IconData icon;
  final String Function(LocaleController) label;
  final _Tier tier;
  const _SidebarItem(this.icon, this.label, this.tier);
}

// Per Carol's chunk-4 spec: Explore + "Plan a Trip" get top visual
// priority; My Trips/Journal are a clear second tier; Notifications/
// Contributions/Settings sit lower still. Not every destination is
// equally important, so the sidebar stops pretending they are.
final List<_SidebarItem> _kSidebarItems = [
  _SidebarItem(Icons.add_location_alt_outlined, (l) => l.t('side_new'), _Tier.primary),
  _SidebarItem(Icons.explore_outlined, (l) => l.t('side_explore'), _Tier.primary),
  _SidebarItem(Icons.forum_outlined, (l) => l.t('side_guide'), _Tier.tertiary),
  _SidebarItem(Icons.card_travel_outlined, (l) => l.t('side_trips'), _Tier.secondary),
  _SidebarItem(Icons.menu_book_outlined, (l) => l.t('side_journal'), _Tier.secondary),
  _SidebarItem(Icons.notifications_outlined, (l) => l.t('side_notif'), _Tier.tertiary),
  _SidebarItem(Icons.settings_outlined, (l) => l.t('side_settings'), _Tier.tertiary),
  _SidebarItem(Icons.volunteer_activism_outlined, (l) => l.t('side_contrib'), _Tier.tertiary),
  _SidebarItem(Icons.wb_twilight_outlined, (l) => 'Your day', _Tier.primary),
  _SidebarItem(Icons.shield_outlined, (l) => 'Privacy & safety', _Tier.tertiary),
];

/// The screen a person lands on right after signing in. A left sidebar
/// (a permanent rail on wide screens, a drawer on phones) holds the
/// destinations Carol listed. Index 6 (Settings) still swaps the
/// dashboard panel in place; every other real destination (New Trip,
/// Explore, My Trips, Journal, Notifications, Contributions) pushes its
/// own full screen — chunk 4 made all of these real, so only "Talk to
/// Guide" remains a "coming soon" panel.
class StartScreen extends StatefulWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;

  const StartScreen({super.key, required this.locale, required this.theme, required this.auth});

  @override
  State<StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<StartScreen> {
  int? _selected;

  @override
  void initState() {
    super.initState();
    final token = widget.auth.accessToken;
    if (token != null) {
      GZConsent.load(token).then((_) {
        if (mounted) GZConsent.showIntroOnce(context, token);
      });
    }
  }

  Future<void> _confirmSignOut() async {
    final t = widget.locale.t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(t('signout_q')),
        content: Text(t('signout_d')),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: Text(t('cancel'))),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: Text(t('side_signout'))),
        ],
      ),
    );
    if (confirmed == true) {
      GZConsent.clear();
      await widget.auth.signOut();
      // main.dart's root listener swaps back to the public landing page.
    }
  }

  void _handleSelect(int index) {
    switch (index) {
      case 0:
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => SurveyScreen(auth: widget.auth)));
        return;
      case 1:
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ExploreScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
        ));
        return;
      case 2:
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => GuideScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
        ));
        return;
      case 3:
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => MyTripsScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
        ));
        return;
      case 4:
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => JournalHubScreen(auth: widget.auth, locale: widget.locale, theme: widget.theme),
        ));
        return;
      case 5:
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => NotificationsScreen(auth: widget.auth)));
        return;
      case 7:
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => ContributionsScreen(auth: widget.auth)));
        return;
      case 8:
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => TodayScreen(auth: widget.auth)));
        return;
      case 9:
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => PrivacyScreen(auth: widget.auth)));
        return;
      default:
        setState(() => _selected = index);
    }
  }

  Widget _content(BuildContext context) {
    if (_selected == null) {
      return _GroundZeroHub(
        locale: widget.locale,
        auth: widget.auth,
        onOpen: _handleSelect,
      );
    }
    if (_selected == 6) {
      return SettingsPanel(
        locale: widget.locale,
        theme: widget.theme,
        auth: widget.auth,
        onSignOut: _confirmSignOut,
      );
    }
    final item = _kSidebarItems[_selected!];
    return ComingSoonPanel(locale: widget.locale, icon: item.icon, title: item.label(widget.locale));
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([widget.locale, widget.theme, widget.auth]),
      builder: (context, _) => NudgeWatcher(auth: widget.auth, child: _buildScaffold(context)),
    );
  }

  Widget _buildScaffold(BuildContext context) {
    final wide = MediaQuery.of(context).size.width >= 900;
    final t = widget.locale.t;

    final sidebar = _Sidebar(
      locale: widget.locale,
      selected: _selected,
      onSelect: _handleSelect,
      onHome: () => setState(() => _selected = null),
      onSignOut: _confirmSignOut,
    );

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            sidebar,
            Expanded(child: _content(context)),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('GroundZero')),
      drawer: Drawer(child: sidebar),
      body: _content(context),
      floatingActionButton: _selected == null
          ? null
          : FloatingActionButton.extended(
              onPressed: () => setState(() => _selected = null),
              icon: const Icon(Icons.home_outlined),
              label: Text(t('home_sub')),
            ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  final LocaleController locale;
  final int? selected;
  final ValueChanged<int> onSelect;
  final VoidCallback onHome;
  final VoidCallback onSignOut;

  const _Sidebar({
    required this.locale,
    required this.selected,
    required this.onSelect,
    required this.onHome,
    required this.onSignOut,
  });

  Widget _tile(BuildContext context, int index) {
    final item = _kSidebarItems[index];
    final ink = GZInk.of(context);
    final isSelected = selected == index;
    final isPrimaryTier = item.tier == _Tier.primary;
    final onAccent = ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE);
    final fg = isSelected ? onAccent : (isPrimaryTier ? ink.text : ink.muted);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: isSelected ? ink.accent : Colors.transparent,
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: () => onSelect(index),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: isPrimaryTier ? 13 : 10),
            child: Row(
              children: [
                Icon(item.icon, color: isSelected ? onAccent : (isPrimaryTier ? ink.accent : ink.muted), size: isPrimaryTier ? 23 : 20),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    item.label(locale),
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: fg,
                          fontWeight: isPrimaryTier || isSelected ? FontWeight.w800 : FontWeight.w600,
                          fontSize: isPrimaryTier ? 15 : 14,
                        ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final scheme = Theme.of(context).colorScheme;
    final primaryIdx = <int>[], secondaryIdx = <int>[], tertiaryIdx = <int>[];
    for (int i = 0; i < _kSidebarItems.length; i++) {
      switch (_kSidebarItems[i].tier) {
        case _Tier.primary: primaryIdx.add(i); break;
        case _Tier.secondary: secondaryIdx.add(i); break;
        case _Tier.tertiary: tertiaryIdx.add(i); break;
      }
    }
    Widget rule() => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 8),
          child: Divider(height: 1, color: ink.border.withOpacity(0.35)),
        );
    return Container(
      width: 272,
      decoration: BoxDecoration(
        color: ink.paper,
        border: Border(right: BorderSide(color: ink.hairline, width: 1)),
      ),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            InkWell(
              onTap: onHome,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 22, 20, 16),
                child: Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(color: ink.accent, shape: BoxShape.circle, border: Border.all(color: ink.hairline, width: 1)),
                      child: Icon(Icons.explore_rounded, size: 23, color: ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE)),
                    ),
                    const SizedBox(width: 10),
                    Text('groundzero', style: Theme.of(context).textTheme.titleLarge?.copyWith(color: ink.text, fontWeight: FontWeight.w800, letterSpacing: -0.8)),
                  ],
                ),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: 4),
                children: [
                  for (final i in primaryIdx) _tile(context, i),
                  rule(),
                  for (final i in secondaryIdx) _tile(context, i),
                  rule(),
                  for (final i in tertiaryIdx) _tile(context, i),
                ],
              ),
            ),
            rule(),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 14),
              child: InkWell(
                borderRadius: BorderRadius.circular(999),
                onTap: onSignOut,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Icon(Icons.logout, color: scheme.error, size: 20),
                      const SizedBox(width: 12),
                      Text(t('side_signout'), style: Theme.of(context).textTheme.titleSmall?.copyWith(color: scheme.error, fontWeight: FontWeight.w700)),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Only wraps in [Expanded] when the surrounding [Flex] is horizontal
/// (bounded width). In the vertical/phone layout the Flex's height is
/// unbounded (it sits inside a Card inside a scroll view), so an
/// Expanded child there would crash with "RenderFlex children have
/// non-zero flex but incoming height constraints are unbounded".
Widget _flexChild({required bool wide, required Widget child}) {
  return wide ? Expanded(child: child) : child;
}

/// "YOUR GROUNDZERO" — chunk 4's replacement for the old generic
/// profile dashboard. Real stats (journeys/places/memories/
/// contributions), a "continue your journey" card when there's an
/// active trip, and the same "Plan a new trip" CTA chunk 1 had. Every
/// number comes from GET /trips and GET /personal/contributions — none
/// of it is invented, and a quiet account shows honest zeros rather
/// than filler.
class _GroundZeroHub extends StatefulWidget {
  final LocaleController locale;
  final AuthController auth;
  final ValueChanged<int> onOpen;

  const _GroundZeroHub({required this.locale, required this.auth, required this.onOpen});

  @override
  State<_GroundZeroHub> createState() => _GroundZeroHubState();
}

class _GroundZeroHubState extends State<_GroundZeroHub> {
  final _api = PersonalApiClient();
  GZMyTrips? _trips;
  GZMyContributions? _contributions;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _load() async {
    final token = widget.auth.accessToken;
    if (token == null) return;
    try {
      final results = await Future.wait([_api.myTrips(token), _api.myContributions(token)]);
      if (mounted) {
        setState(() {
          _trips = results[0] as GZMyTrips;
          _contributions = results[1] as GZMyContributions;
        });
      }
    } on GZApiException {
      // The hub degrades gracefully to zero-stats rather than erroring out.
    }
  }

  String _greeting(LocaleController locale) {
    final hour = DateTime.now().hour;
    if (hour < 12) return locale.t('greet_morning');
    if (hour < 17) return locale.t('greet_afternoon');
    return locale.t('greet_evening');
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final wide = MediaQuery.of(context).size.width >= 900;
    final rawName = widget.auth.user?.displayName?.trim();
    final name = (rawName != null && rawName.isNotEmpty) ? rawName.split(' ').first : t('traveller');

    final activeTrips = _trips?.upcoming.where((tr) => tr.status == 'active' || tr.status == 'paused').toList() ?? [];
    final active = activeTrips.isEmpty ? null : activeTrips.first;
    final journeyCount = (_trips?.upcoming.length ?? 0) + (_trips?.completed.length ?? 0);
    final memoryCount = (_trips?.completed.fold<int>(0, (sum, tr) => sum + tr.visitedCount) ?? 0) +
        (_trips?.upcoming.fold<int>(0, (sum, tr) => sum + tr.visitedCount) ?? 0);
    final contributionCount = _contributions?.contributions.length ?? 0;
    final onAccent = ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE);

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: wide ? 260 : 230,
            width: double.infinity,
            child: GZScene(
              child: Padding(
                padding: EdgeInsets.fromLTRB(wide ? 40 : 24, 24, 24, wide ? 70 : 56),
                child: Align(
                  alignment: Alignment.bottomLeft,
                  child: Text(
                    t('home_hello', {'greeting': _greeting(widget.locale), 'name': name}),
                    style: (wide ? text.displaySmall : text.headlineMedium)?.copyWith(
                      color: const Color(0xFFFBF3E2),
                      shadows: [Shadow(color: Color(0x55000000), blurRadius: 16, offset: Offset(0, 3))],
                    ),
                  ),
                ),
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.all(wide ? 40 : 20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 980),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('home_sub'), style: text.bodyLarge?.copyWith(color: ink.muted)),
                  const SizedBox(height: 24),

                  // Real stats row — honest zeros for a brand-new account.
                  GZEqualGrid(columns: 3, gap: 16, children: [
                    _Stat(label: 'JOURNEYS', value: '$journeyCount'),
                    _Stat(label: 'PLACES VISITED', value: '$memoryCount'),
                    _Stat(label: 'CONTRIBUTIONS', value: '$contributionCount'),
                  ]),
                  const SizedBox(height: 30),

                  if (active != null) ...[
                    GZFrameCard(
                      onTap: () => widget.onOpen(3),
                      padding: const EdgeInsets.all(18),
                      child: Row(
                        children: [
                          Icon(Icons.play_circle_outline, color: ink.accent, size: 30),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Continue your journey', style: text.titleMedium?.copyWith(color: ink.text, fontWeight: FontWeight.w800)),
                                const SizedBox(height: 2),
                                Text(active.nextPlaceName != null ? 'Next stop: ${active.nextPlaceName}' : 'Ready whenever you are', style: text.bodyMedium?.copyWith(color: ink.muted)),
                              ],
                            ),
                          ),
                          Icon(Icons.chevron_right, color: ink.text),
                        ],
                      ),
                    ),
                    const SizedBox(height: 28),
                  ],

                  GZReveal(
                    child: GZFrameCard(
                      onTap: () => widget.onOpen(8),
                      radius: 28,
                      shadowOffset: 8,
                      padding: const EdgeInsets.all(24),
                      child: Row(
                        children: [
                          Container(
                            width: 56,
                            height: 56,
                            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: ink.accent, width: 2)),
                            child: Icon(Icons.wb_twilight_outlined, color: ink.accent, size: 28),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Your Mangaluru, today', style: text.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                                const SizedBox(height: 4),
                                Text('What is open, near and right for you this hour. Every pick says why.', style: text.bodyMedium?.copyWith(color: ink.muted)),
                              ],
                            ),
                          ),
                          Icon(Icons.arrow_outward_rounded, color: ink.accent),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  GZReveal(
                    child: GZFrameCard(
                      color: ink.accent,
                      radius: 28,
                      shadowOffset: 8,
                      padding: const EdgeInsets.all(28),
                      child: Flex(
                        direction: wide ? Axis.horizontal : Axis.vertical,
                        crossAxisAlignment: wide ? CrossAxisAlignment.center : CrossAxisAlignment.start,
                        children: [
                          _flexChild(
                            wide: wide,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(t('home_plan_t'), style: text.titleLarge?.copyWith(color: onAccent, fontWeight: FontWeight.w800)),
                                const SizedBox(height: 6),
                                Text(t('home_plan_d'), style: text.bodyMedium?.copyWith(color: onAccent)),
                              ],
                            ),
                          ),
                          SizedBox(height: wide ? 0 : 18, width: wide ? 24 : 0),
                          GZStickerButton(label: t('home_plan_btn'), outlined: true, icon: Icons.arrow_outward_rounded, onPressed: () => widget.onOpen(0)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 30),
                  GZEqualGrid(
                    columns: wide ? 4 : 2,
                    gap: 16,
                    children: [
                      (Icons.explore_outlined, t('side_explore'), t('q_explore_d'), 1),
                      (Icons.card_travel_outlined, t('side_trips'), t('q_trips_d'), 3),
                      (Icons.menu_book_outlined, t('side_journal'), t('q_journal_d'), 4),
                      (Icons.volunteer_activism_outlined, t('side_contrib'), 'Help build GroundZero.', 7),
                      (Icons.shield_outlined, 'Privacy & safety', 'Your choices, your data.', 9),
                    ]
                        .map((q) => GZFrameCard(
                              onTap: () => widget.onOpen(q.$4),
                              padding: const EdgeInsets.all(20),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Icon(q.$1, color: ink.accent, size: 26),
                                  const SizedBox(height: 14),
                                  Text(q.$2, style: text.titleSmall?.copyWith(color: ink.text, fontWeight: FontWeight.w700)),
                                  const SizedBox(height: 4),
                                  Text(q.$3, style: text.bodySmall?.copyWith(color: ink.muted)),
                                ],
                              ),
                            ))
                        .toList(),
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

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  const _Stat({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return GZFrameCard(
      radius: 18,
      shadowOffset: 4,
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: text.headlineSmall?.copyWith(color: ink.accent, fontWeight: FontWeight.w800)),
          const SizedBox(height: 2),
          Text(label, style: text.labelSmall?.copyWith(color: ink.muted, letterSpacing: 1.4)),
        ],
      ),
    );
  }
}
