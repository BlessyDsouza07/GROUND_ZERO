import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/trips_api_client.dart';
import '../../design/gz_ink.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../widgets/gz_journey_loader.dart';
import '../../widgets/tiara/gz_art_data.dart';
import '../../widgets/tiara/gz_sticker_button.dart';
import 'itinerary_screen.dart';

/// Carol's exact 9-question New Trip survey. The step ORDER is driven
/// entirely by the backend's `next_step` (see trips/service.py) — this
/// screen just renders whichever step name comes back next, so if the
/// backend's auto-fill/skip logic decides a question isn't needed for
/// this answer, it simply never appears here. See trips/README_TRIPS.md
/// for exactly which 9 steps that is and why.
///
/// English only for this screen (chunk 1's public pages are still fully
/// translated in 5 languages — this new flow isn't, yet; see the top-
/// level README for why that's an honest, disclosed trim rather than a
/// silently half-done translation).
class SurveyScreen extends StatefulWidget {
  final AuthController auth;
  const SurveyScreen({super.key, required this.auth});

  @override
  State<SurveyScreen> createState() => _SurveyScreenState();
}

class _SurveyScreenState extends State<SurveyScreen> {
  final _api = TripsApiClient();
  String? _sessionId;
  String? _step;
  bool _loading = true;
  bool _generating = false;
  final Map<String, dynamic> _answers = {};
  String? _error;

  // Per-step working state
  final _openingController = TextEditingController();
  double _energy = 50;
  double _crowd = 50;
  double _budget = 1500;
  final Set<String> _dietary = {'no_restrictions'};
  bool _hasAllergy = false;
  final _allergyController = TextEditingController();
  bool _hasAccessibilityNeed = false;
  final Set<String> _accessibilityFlags = {};
  int _days = 1; // 1, 2, 3+
  String _dayPart = 'flexible'; // morning | mid_morning | afternoon | flexible
  bool _visitedBefore = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void dispose() {
    _api.close();
    _openingController.dispose();
    _allergyController.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    // BUG FIX (6th audit response, Oct 2026): the backend requires auth
    // on /trips/survey/start (see trips_api_client.dart's startSurvey
    // for the live-verified 401), so this guard matches the one
    // _finalizeAndGenerate() already had — rather than letting the
    // request go out tokenless and surface a generic "something went
    // wrong" error from GZApiException.
    final token = widget.auth.accessToken;
    if (token == null) {
      setState(() {
        _error = 'You need to be signed in to plan a trip.';
        _loading = false;
      });
      return;
    }
    try {
      final state = await _api.startSurvey(token);
      setState(() {
        _sessionId = state.sessionId;
        _step = state.nextStep;
        _loading = false;
      });
    } on GZApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _submit(dynamic value) async {
    final token = widget.auth.accessToken;
    if (token == null) {
      setState(() {
        _error = 'You need to be signed in to plan a trip.';
        _loading = false;
      });
      return;
    }
    _answers[_step!] = value;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final state = await _api.answerSurvey(_sessionId!, _step!, value, token);
      if (state.done) {
        await _finalizeAndGenerate();
        return;
      }
      setState(() {
        _step = state.nextStep;
        _loading = false;
      });
    } on GZApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  /// Go back to an earlier question. The server only moves forward, so this
  /// opens a fresh session and quietly replays the answers given before the
  /// target; the controls keep what the traveller picked, so nothing is lost.
  Future<void> _goTo(int target) async {
    final token = widget.auth.accessToken;
    if (token == null || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      var state = await _api.startSurvey(token);
      var sid = state.sessionId;
      var step = state.nextStep;
      var guard = 0;
      while (step != null && _order.indexOf(step) < target && _answers.containsKey(step) && guard++ < 12) {
        state = await _api.answerSurvey(sid, step, _answers[step], token);
        if (state.done) break;
        step = state.nextStep;
      }
      if (!mounted) return;
      setState(() {
        _sessionId = sid;
        _step = step ?? _order[target];
        _loading = false;
      });
    } on GZApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _finalizeAndGenerate() async {
    if (mounted) setState(() => _generating = true);
    final token = widget.auth.accessToken;
    if (token == null) {
      setState(() {
        _error = 'You need to be signed in to plan a trip.';
        _loading = false;
      });
      return;
    }
    try {
      final profileId = await _api.finalizeSurvey(_sessionId!, token);

      // The tourist's real position "as they switch on the app" — the
      // geofence HiveEngine centers the itinerary on (see hive_engine.py).
      // Falls back to central Mangaluru if location isn't available/granted
      // rather than failing the whole flow over a permission prompt.
      double lat = 12.9141, lon = 74.8560;
      try {
        var permission = await Geolocator.checkPermission();
        if (permission == LocationPermission.denied) {
          permission = await Geolocator.requestPermission();
        }
        if (permission == LocationPermission.always || permission == LocationPermission.whileInUse) {
          final pos = await Geolocator.getCurrentPosition(
            locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium),
          ).timeout(const Duration(seconds: 8));
          lat = pos.latitude;
          lon = pos.longitude;
        }
      } on Object {
        // Location unavailable/denied/timed out — the Mangaluru-center
        // fallback above already covers this; nothing further to do.
      }

      GZTrip trip;
      try {
        trip = await _api.generateTrip(
          token: token, profileId: profileId, startLatitude: lat, startLongitude: lon,
        );
      } on GZApiException catch (e) {
        if (e.statusCode != null) rethrow;
        // Network/timeout: the server may have finished anyway.
        final recovered = await _api.latestDraft(token);
        if (recovered == null) rethrow;
        trip = recovered;
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ItineraryScreen(auth: widget.auth, trip: trip)),
      );
    } on GZApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } on Object {
      if (!mounted) return;
      setState(() {
        _error = 'Your trip was planned but could not be displayed. Open it from Trips.';
        _loading = false;
      });
    }
  }

  static const _order = [
    'opening_prompt', 'q2_energy', 'q3_crowd_tolerance', 'q4_budget', 'q5_dietary',
    'accessibility', 'q8_trip_duration', 'q9_start_time', 'return_visitor_check',
  ];

  static const _stepMeta = [
    ('Your vibe', Icons.auto_awesome_outlined),
    ('Energy', Icons.bolt),
    ('Crowds', Icons.groups_2_outlined),
    ('Budget', Icons.currency_rupee),
    ('Food', Icons.restaurant_menu),
    ('Access', Icons.accessible_forward),
    ('Days', Icons.calendar_month_outlined),
    ('Start', Icons.schedule),
    ('History', Icons.history),
  ];

  String _answerFor(int i) {
    switch (i) {
      case 0:
        final t = _openingController.text.trim();
        return t.isEmpty ? 'Surprise me' : (t.length > 34 ? '${t.substring(0, 32)}...' : t);
      case 1:
        return _energy < 34 ? 'Slow and easy' : (_energy > 66 ? 'Full speed' : 'Balanced');
      case 2:
        return _crowd < 34 ? 'Quiet please' : (_crowd > 66 ? 'Love the buzz' : 'Either way');
      case 3:
        return '₹${_budget.toInt()}';
      case 4:
        return _dietary.isEmpty ? 'No restrictions' : _dietary.map((e) => e.replaceAll('_', ' ')).join(', ');
      case 5:
        return _hasAccessibilityNeed ? 'Planned around you' : 'All good';
      case 6:
        return _days == 1 ? '1 day' : (_days == 2 ? '2 days' : '3+ days');
      case 7:
        return _dayPart == 'flexible' ? 'Flexible' : _dayPart.replaceAll('_', '-');
      default:
        return _visitedBefore ? "Been before" : 'First time';
    }
  }

  Widget _trail(GZInk ink, int idx, {required bool wide}) {
    const cream = Color(0xFFFBF3E2);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('PLAN YOUR MANGALURU', style: TextStyle(color: cream.withOpacity(0.9), fontWeight: FontWeight.w800, letterSpacing: 2.2, fontSize: 12)),
      const SizedBox(height: 8),
      Text('Build your day,\none answer at a time.', style: const TextStyle(color: cream, fontWeight: FontWeight.w900, fontSize: 30, height: 1.1)),
      const SizedBox(height: 22),
      for (var i = 0; i < _order.length; i++)
        InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: i < idx ? () => _goTo(i) : null,
          child: Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Column(children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: 30,
                height: 30,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i < idx ? cream : (i == idx ? Colors.white.withOpacity(0.22) : Colors.transparent),
                  border: Border.all(color: cream.withOpacity(i <= idx ? 1 : 0.4), width: i == idx ? 2.2 : 1.2),
                ),
                child: Icon(i < idx ? Icons.check_rounded : _stepMeta[i].$2, size: 16, color: i < idx ? const Color(0xFF0B4A63) : cream.withOpacity(i <= idx ? 1 : 0.6)),
              ),
              if (i != _order.length - 1) Container(width: 2, height: 16, color: cream.withOpacity(i < idx ? 0.8 : 0.25)),
            ]),
            const SizedBox(width: 12),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(_stepMeta[i].$1,
                      style: TextStyle(color: cream.withOpacity(i <= idx ? 1 : 0.6), fontWeight: i == idx ? FontWeight.w900 : FontWeight.w700, fontSize: 14)),
                  if (i < idx)
                    Text('${_answerFor(i)}  ·  tap to change', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: cream.withOpacity(0.85), fontSize: 12)),
                ]),
              ),
            ),
          ]),
        )),
    ]);
  }

  Widget _card(GZInk ink, int idx, bool wide) {
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(wide ? 40 : 16, wide ? 40 : 16, wide ? 40 : 16, 40),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              if (idx > 0) ...[
                TextButton.icon(
                  onPressed: _loading ? null : () => _goTo(idx - 1),
                  icon: const Icon(Icons.arrow_back_rounded, size: 18),
                  label: const Text('Back'),
                ),
                const SizedBox(width: 8),
              ],
              Text('QUESTION ${idx + 1} OF ${_order.length}', style: TextStyle(color: ink.accent, fontWeight: FontWeight.w900, letterSpacing: 1.6, fontSize: 12)),
              const Spacer(),
              Text(_stepMeta[idx].$1, style: TextStyle(color: ink.muted, fontWeight: FontWeight.w700, fontSize: 12)),
            ]),
            const SizedBox(height: 10),
            _Segments(count: _order.length, index: idx),
            const SizedBox(height: 18),
            Container(
              padding: EdgeInsets.all(wide ? 32 : 22),
              decoration: BoxDecoration(
                color: ink.paper,
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: ink.hairline),
                boxShadow: ink.softShadow,
              ),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 320),
                switchInCurve: Curves.easeOutCubic,
                transitionBuilder: (child, anim) => FadeTransition(
                  opacity: anim,
                  child: SlideTransition(position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(anim), child: child),
                ),
                child: KeyedSubtree(
                  key: ValueKey('${_step}_${_loading}_${_error != null}'),
                  child: _loading
                      ? const Padding(padding: EdgeInsets.symmetric(vertical: 70), child: Center(child: CircularProgressIndicator()))
                      : _buildStep(context),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(Icons.lock_outline, size: 14, color: ink.muted),
              const SizedBox(width: 6),
              Flexible(child: Text('Your answers only shape this plan.', style: TextStyle(color: ink.muted, fontSize: 12))),
            ]),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    if (_generating) {
      return GZJourneyLoader(
        error: _error,
        onRetry: () => setState(() {
          _generating = false;
          _error = null;
          _loading = false;
        }),
      );
    }
    final wide = MediaQuery.of(context).size.width >= 860;
    final idx = _step == null ? 0 : _order.indexOf(_step!).clamp(0, _order.length - 1).toInt();
    const cream = Color(0xFFFBF3E2);
    return Scaffold(
      body: SafeArea(
        child: wide
            ? Row(children: [
                SizedBox(
                  width: 380,
                  child: Stack(fit: StackFit.expand, children: [
                    const DecoratedBox(
                      decoration: BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFF06384F), Color(0xFF006996), Color(0xFF0699BA)])),
                    ),
                    Align(alignment: Alignment.bottomCenter, child: SizedBox(height: 190, width: double.infinity, child: SvgPicture.string(kGZArtSvgs['coast']![0], fit: BoxFit.cover, alignment: Alignment.bottomCenter))),
                    SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(36, 56, 28, 210),
                      child: _trail(ink, idx, wide: true),
                    ),
                  ]),
                ),
                Expanded(child: Stack(children: [
                  Positioned.fill(child: _card(ink, idx, true)),
                  Positioned(top: 8, right: 8, child: IconButton(tooltip: 'Close', icon: const Icon(Icons.close), onPressed: () => Navigator.of(context).maybePop())),
                ])),
              ])
            : Column(children: [
                SizedBox(
                  height: 132,
                  width: double.infinity,
                  child: _PanelBg(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(56, 12, 16, 16),
                      child: Align(
                        alignment: Alignment.bottomLeft,
                        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('PLAN YOUR MANGALURU', style: TextStyle(color: cream.withOpacity(0.9), fontWeight: FontWeight.w800, letterSpacing: 2, fontSize: 11)),
                          const SizedBox(height: 4),
                          Text(_stepMeta[idx].$1, style: const TextStyle(color: cream, fontWeight: FontWeight.w900, fontSize: 26, height: 1.1)),
                        ]),
                      ),
                    ),
                  ),
                ),
                Expanded(child: _card(ink, idx, false)),
              ]),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.startTop,
      floatingActionButton: wide
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 8),
              child: IconButton(
                tooltip: 'Close',
                style: IconButton.styleFrom(backgroundColor: Colors.black.withOpacity(0.28)),
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
    );
  }

  Widget _buildStep(BuildContext context) {
    if (_error != null) {
      return _ErrorRetry(message: _error!, onRetry: () {
        setState(() => _error = null);
        if (_sessionId == null) {
          _start();
        } else {
          setState(() => _loading = false);
        }
      });
    }
    switch (_step) {
      case 'opening_prompt':
        return _OpeningPromptStep(controller: _openingController, onNext: () => _submit(_openingController.text.trim()));
      case 'q2_energy':
        return _SliderStep(
          title: "What's your energy level like today?",
          icon: Icons.bolt, lowLabel: 'Take it slow', highLabel: 'Full speed ahead',
          value: _energy, onChanged: (v) => setState(() => _energy = v),
          onNext: () => _submit(_energy),
        );
      case 'q3_crowd_tolerance':
        return _SliderStep(
          title: 'How do you feel about crowds?',
          icon: Icons.groups_2_outlined, lowLabel: 'Prefer it quiet', highLabel: 'Love the buzz',
          value: _crowd, onChanged: (v) => setState(() => _crowd = v),
          onNext: () => _submit(_crowd),
        );
      case 'q4_budget':
        return _BudgetStep(
          value: _budget,
          onChanged: (v) => setState(() => _budget = v),
          onNext: () => _submit(_budget),
        );
      case 'q5_dietary':
        return _DietaryStep(
          selected: _dietary,
          hasAllergy: _hasAllergy,
          allergyController: _allergyController,
          onToggle: (v) => setState(() {
            if (_dietary.contains(v)) {
              _dietary.remove(v);
            } else {
              _dietary.add(v);
            }
          }),
          onAllergyChanged: (v) => setState(() => _hasAllergy = v),
          onNext: () => _submit(_dietary.isEmpty ? ['no_restrictions'] : _dietary.toList()),
        );
      case 'accessibility':
        return _AccessibilityStep(
          hasNeed: _hasAccessibilityNeed,
          selected: _accessibilityFlags,
          onHasNeedChanged: (v) => setState(() => _hasAccessibilityNeed = v),
          onToggle: (v) => setState(() {
            if (_accessibilityFlags.contains(v)) {
              _accessibilityFlags.remove(v);
            } else {
              _accessibilityFlags.add(v);
            }
          }),
          onNext: () => _submit(_hasAccessibilityNeed ? _accessibilityFlags.toList() : <String>[]),
        );
      case 'q8_trip_duration':
        return _DurationStep(
          days: _days,
          onChanged: (v) => setState(() => _days = v),
          onNext: () {
            if (_days == 1) {
              _submit({'duration': 'full_day'});
            } else {
              _submit({'duration': 'multi_day', 'days': _days});
            }
          },
        );
      case 'q9_start_time':
        return _DayPartStep(
          value: _dayPart,
          onChanged: (v) => setState(() => _dayPart = v),
          onNext: () => _submit(_dayPart),
        );
      case 'return_visitor_check':
        return _YesNoStep(
          title: 'Have you visited Mangaluru before?',
          subtitle: "If yes, we'll leave out places you've already been to.",
          value: _visitedBefore,
          onChanged: (v) => setState(() => _visitedBefore = v),
          onNext: () => _submit(_visitedBefore),
        );
      default:
        return const Padding(padding: EdgeInsets.only(top: 80), child: CircularProgressIndicator());
    }
  }
}

class _PanelBg extends StatelessWidget {
  final Widget child;
  const _PanelBg({required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(fit: StackFit.expand, children: [
      const DecoratedBox(decoration: BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFF06384F), Color(0xFF006996), Color(0xFF0699BA)]))),
      Align(alignment: Alignment.bottomCenter, child: SizedBox(height: 70, width: double.infinity, child: SvgPicture.string(kGZArtSvgs['coast']![0], fit: BoxFit.cover, alignment: Alignment.bottomCenter))),
      child,
    ]);
  }
}

class _Segments extends StatelessWidget {
  final int count;
  final int index;
  const _Segments({required this.count, required this.index});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Row(children: [
      for (var i = 0; i < count; i++)
        Expanded(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 350),
            height: 6,
            margin: EdgeInsets.only(right: i == count - 1 ? 0 : 5),
            decoration: BoxDecoration(
              color: i <= index ? ink.accent : ink.hairline.withOpacity(0.35),
              borderRadius: BorderRadius.circular(99),
            ),
          ),
        ),
    ]);
  }
}

class _ErrorRetry extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorRetry({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error, size: 36),
        const SizedBox(height: 10),
        Text(message, style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 16), textAlign: TextAlign.center),
        const SizedBox(height: 18),
        GZStickerButton(label: 'Try again', onPressed: onRetry),
      ],
    );
  }
}

/// Shared frame for every question: a round icon, a large readable title,
/// a friendly subtitle, the answer controls, then a big Continue button.
class _StepScaffold extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget child;
  final VoidCallback onNext;
  final bool nextEnabled;

  const _StepScaffold({
    required this.icon, required this.title, this.subtitle, required this.child, required this.onNext, this.nextEnabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(shape: BoxShape.circle, color: ink.accent.withOpacity(0.14), border: Border.all(color: ink.accent, width: 1.6)),
          child: Icon(icon, color: ink.accent, size: 28),
        ),
        const SizedBox(height: 18),
        Text(title, style: text.headlineMedium?.copyWith(fontWeight: FontWeight.w900, height: 1.15, fontSize: 28)),
        if (subtitle != null) ...[
          const SizedBox(height: 10),
          Text(subtitle!, style: text.bodyLarge?.copyWith(color: ink.muted, height: 1.4)),
        ],
        const SizedBox(height: 26),
        child,
        const SizedBox(height: 30),
        GZStickerButton(label: 'Continue', icon: Icons.arrow_forward_rounded, expand: true, onPressed: nextEnabled ? onNext : null),
      ],
    );
  }
}

/// A big tappable choice tile (icon + label + optional line).
class _Choice extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? hint;
  final bool selected;
  final VoidCallback onTap;
  final double? width;
  const _Choice({required this.icon, required this.label, this.hint, required this.selected, required this.onTap, this.width});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final fg = selected ? (ink.dark ? const Color(0xFF240002) : Colors.white) : ink.text;
    return SizedBox(
      width: width,
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          decoration: BoxDecoration(
            color: selected ? ink.accent : ink.paperAlt.withOpacity(0.35),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: selected ? ink.accent : ink.hairline, width: selected ? 1.6 : 1),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, color: fg, size: 24),
            const SizedBox(width: 12),
            Flexible(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                Text(label, style: text.titleSmall?.copyWith(color: fg, fontWeight: FontWeight.w800, fontSize: 16)),
                if (hint != null) Text(hint!, style: text.bodySmall?.copyWith(color: fg.withOpacity(0.85))),
              ]),
            ),
            if (selected) ...[const SizedBox(width: 8), Icon(Icons.check_circle, color: fg, size: 20)],
          ]),
        ),
      ),
    );
  }
}

class _OpeningPromptStep extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onNext;
  const _OpeningPromptStep({required this.controller, required this.onNext});

  static const _ideas = [
    ('Old temples and heritage', Icons.temple_hindu_outlined),
    ('Beaches and sunsets', Icons.beach_access_outlined),
    ('Local seafood and street food', Icons.ramen_dining_outlined),
    ('Quiet green places', Icons.park_outlined),
    ('Markets and everyday life', Icons.storefront_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return _StepScaffold(
      icon: Icons.auto_awesome_outlined,
      title: 'What do you want to explore in Mangaluru?',
      subtitle: "Tell us in your own words. The more specific you are, the fewer questions we need to ask.",
      onNext: onNext,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextField(
          controller: controller,
          maxLines: 4,
          minLines: 3,
          style: const TextStyle(fontSize: 17, height: 1.4),
          decoration: InputDecoration(
            filled: true,
            fillColor: ink.paperAlt.withOpacity(0.3),
            contentPadding: const EdgeInsets.all(18),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(18)),
            hintText: 'e.g. "I love old temples, beaches, and trying local seafood"',
          ),
        ),
        const SizedBox(height: 16),
        Text('Need an idea? Tap one:', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: ink.muted)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final idea in _ideas)
            ActionChip(
              avatar: Icon(idea.$2, size: 18, color: ink.accent),
              label: Text(idea.$1),
              onPressed: () {
                final cur = controller.text.trim();
                controller.text = cur.isEmpty ? idea.$1 : '$cur, ${idea.$1.toLowerCase()}';
                controller.selection = TextSelection.collapsed(offset: controller.text.length);
              },
            ),
        ]),
      ]),
    );
  }
}

class _SliderStep extends StatelessWidget {
  final String title;
  final String lowLabel;
  final String highLabel;
  final double value;
  final ValueChanged<double> onChanged;
  final VoidCallback onNext;
  final IconData icon;

  const _SliderStep({
    required this.title, required this.lowLabel, required this.highLabel,
    required this.value, required this.onChanged, required this.onNext, this.icon = Icons.tune,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final word = value < 34 ? lowLabel : (value > 66 ? highLabel : 'A bit of both');
    return _StepScaffold(
      icon: icon,
      title: title,
      onNext: onNext,
      child: Column(
        children: [
          Center(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: Text(word, key: ValueKey(word), style: text.headlineSmall?.copyWith(color: ink.accent, fontWeight: FontWeight.w900)),
            ),
          ),
          const SizedBox(height: 8),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(trackHeight: 10, thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 14), overlayShape: const RoundSliderOverlayShape(overlayRadius: 26)),
            child: Slider(value: value, min: 0, max: 100, divisions: 20, onChanged: onChanged),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(lowLabel, style: text.bodyMedium?.copyWith(color: ink.muted)),
              Text(highLabel, style: text.bodyMedium?.copyWith(color: ink.muted)),
            ],
          ),
        ],
      ),
    );
  }
}

class _BudgetStep extends StatelessWidget {
  final double value;
  final ValueChanged<double> onChanged;
  final VoidCallback onNext;
  const _BudgetStep({required this.value, required this.onChanged, required this.onNext});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return _StepScaffold(
      icon: Icons.currency_rupee,
      title: "What's your budget for the day?",
      subtitle: 'In rupees. It covers entry fees, food and local transport.',
      onNext: onNext,
      nextEnabled: value > 0,
      child: Column(children: [
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconButton.filledTonal(onPressed: () => onChanged((value - 100).clamp(0, 10000).toDouble()), icon: const Icon(Icons.remove)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: Text('₹${value.toInt()}', style: text.displaySmall?.copyWith(fontWeight: FontWeight.w900, color: ink.accent)),
          ),
          IconButton.filledTonal(onPressed: () => onChanged((value + 100).clamp(0, 10000).toDouble()), icon: const Icon(Icons.add)),
        ]),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(trackHeight: 8),
          child: Slider(value: value.clamp(0, 10000).toDouble(), min: 0, max: 10000, divisions: 100, onChanged: onChanged),
        ),
        const SizedBox(height: 6),
        Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
          for (final v in const [500, 1000, 1500, 2500, 4000])
            ChoiceChip(label: Text('₹$v'), selected: value.toInt() == v, onSelected: (_) => onChanged(v.toDouble())),
        ]),
      ]),
    );
  }
}

const _dietaryOptions = [
  ('no_restrictions', 'No restrictions', Icons.restaurant_outlined),
  ('veg', 'Vegetarian', Icons.eco_outlined),
  ('vegan', 'Vegan', Icons.spa_outlined),
  ('no_beef', 'No beef', Icons.do_not_disturb_alt_outlined),
  ('halal', 'Halal', Icons.verified_outlined),
];

class _DietaryStep extends StatelessWidget {
  final Set<String> selected;
  final bool hasAllergy;
  final TextEditingController allergyController;
  final ValueChanged<String> onToggle;
  final ValueChanged<bool> onAllergyChanged;
  final VoidCallback onNext;

  const _DietaryStep({
    required this.selected, required this.hasAllergy, required this.allergyController,
    required this.onToggle, required this.onAllergyChanged, required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return _StepScaffold(
      icon: Icons.restaurant_menu,
      title: 'Any dietary preferences?',
      subtitle: 'Pick all that apply. We only suggest food that fits.',
      onNext: onNext,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 10, runSpacing: 10,
            children: [for (final o in _dietaryOptions) _Choice(icon: o.$3, label: o.$2, selected: selected.contains(o.$1), onTap: () => onToggle(o.$1))],
          ),
          const SizedBox(height: 18),
          Container(
            decoration: BoxDecoration(color: ink.paperAlt.withOpacity(0.3), borderRadius: BorderRadius.circular(18), border: Border.all(color: ink.hairline)),
            child: SwitchListTile(
              title: const Text('I have food allergies', style: TextStyle(fontWeight: FontWeight.w700)),
              value: hasAllergy,
              onChanged: onAllergyChanged,
            ),
          ),
          if (hasAllergy)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: TextField(
                controller: allergyController,
                decoration: InputDecoration(border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)), hintText: 'e.g. peanuts, shellfish'),
              ),
            ),
        ],
      ),
    );
  }
}

const _accessibilityOptions = [
  ('wheelchair', 'Wheelchair access needed', Icons.accessible_forward),
  ('limited_walking', 'Limited walking', Icons.directions_walk),
  ('visual_impairment', 'Visual impairment', Icons.visibility_off_outlined),
  ('hearing_impairment', 'Hearing impairment', Icons.hearing_disabled_outlined),
];

class _AccessibilityStep extends StatelessWidget {
  final bool hasNeed;
  final Set<String> selected;
  final ValueChanged<bool> onHasNeedChanged;
  final ValueChanged<String> onToggle;
  final VoidCallback onNext;

  const _AccessibilityStep({
    required this.hasNeed, required this.selected, required this.onHasNeedChanged, required this.onToggle, required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return _StepScaffold(
      icon: Icons.accessible_forward,
      title: 'Any accessibility needs we should plan around?',
      subtitle: 'This stays private and only shapes your plan.',
      onNext: onNext,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(child: _Choice(icon: Icons.thumb_up_alt_outlined, label: 'No, all good', selected: !hasNeed, onTap: () => onHasNeedChanged(false))),
            const SizedBox(width: 10),
            Expanded(child: _Choice(icon: Icons.tune, label: 'Yes, I do', selected: hasNeed, onTap: () => onHasNeedChanged(true))),
          ]),
          if (hasNeed) ...[
            const SizedBox(height: 16),
            Text('Which of these?', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: ink.muted)),
            const SizedBox(height: 8),
            Wrap(spacing: 10, runSpacing: 10, children: [
              for (final o in _accessibilityOptions) _Choice(icon: o.$3, label: o.$2, selected: selected.contains(o.$1), onTap: () => onToggle(o.$1)),
            ]),
          ],
        ],
      ),
    );
  }
}

class _DurationStep extends StatelessWidget {
  final int days;
  final ValueChanged<int> onChanged;
  final VoidCallback onNext;
  const _DurationStep({required this.days, required this.onChanged, required this.onNext});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return _StepScaffold(
      icon: Icons.calendar_month_outlined,
      title: 'How long are you in Mangaluru?',
      onNext: onNext,
      child: Row(children: [
        for (final d in const [1, 2, 3]) ...[
          Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: () => onChanged(d),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                padding: const EdgeInsets.symmetric(vertical: 22),
                decoration: BoxDecoration(
                  color: days == d ? ink.accent : ink.paperAlt.withOpacity(0.35),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: days == d ? ink.accent : ink.hairline),
                ),
                child: Column(children: [
                  Text(d == 3 ? '3+' : '$d',
                      style: text.displaySmall?.copyWith(fontWeight: FontWeight.w900, color: days == d ? (ink.dark ? const Color(0xFF240002) : Colors.white) : ink.text)),
                  Text(d == 1 ? 'day' : 'days', style: text.bodyMedium?.copyWith(color: days == d ? (ink.dark ? const Color(0xFF240002) : Colors.white) : ink.muted)),
                ]),
              ),
            ),
          ),
          if (d != 3) const SizedBox(width: 10),
        ],
      ]),
    );
  }
}

const _dayPartOptions = [
  ('morning', 'Morning', '7 to 9 AM', Icons.wb_twilight_outlined),
  ('mid_morning', 'Mid-morning', '9 to 11 AM', Icons.wb_sunny_outlined),
  ('afternoon', 'Afternoon', '11 AM to 2 PM', Icons.light_mode_outlined),
  ('flexible', "I'm flexible", 'Starting right now', Icons.bolt_outlined),
];

class _DayPartStep extends StatelessWidget {
  final String value;
  final ValueChanged<String> onChanged;
  final VoidCallback onNext;
  const _DayPartStep({required this.value, required this.onChanged, required this.onNext});

  @override
  Widget build(BuildContext context) {
    return _StepScaffold(
      icon: Icons.schedule,
      title: 'When do you want to start?',
      subtitle: 'You can pick the exact start time once you have seen the plan.',
      onNext: onNext,
      child: Column(children: [
        for (final o in _dayPartOptions)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: SizedBox(width: double.infinity, child: _Choice(icon: o.$4, label: o.$2, hint: o.$3, selected: value == o.$1, onTap: () => onChanged(o.$1))),
          ),
      ]),
    );
  }
}

class _YesNoStep extends StatelessWidget {
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final VoidCallback onNext;

  const _YesNoStep({
    required this.title, this.subtitle, required this.value, required this.onChanged, required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return _StepScaffold(
      icon: Icons.history,
      title: title, subtitle: subtitle, onNext: onNext,
      child: Row(children: [
        Expanded(child: _Choice(icon: Icons.explore_outlined, label: 'First time', selected: !value, onTap: () => onChanged(false))),
        const SizedBox(width: 10),
        Expanded(child: _Choice(icon: Icons.replay, label: "I've been", selected: value, onTap: () => onChanged(true))),
      ]),
    );
  }
}
