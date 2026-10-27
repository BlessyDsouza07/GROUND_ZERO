import 'dart:ui' show PointerDeviceKind;

import 'package:flutter/material.dart';

import 'core/auth_controller.dart';
import 'core/locale_controller.dart';
import 'core/theme_controller.dart';
import 'screens/home_screen.dart';
import 'screens/start_screen.dart';

void main() {
  runApp(const GroundZeroApp());
}

class GroundZeroApp extends StatefulWidget {
  const GroundZeroApp({super.key});

  @override
  State<GroundZeroApp> createState() => _GroundZeroAppState();
}

class _GroundZeroAppState extends State<GroundZeroApp> {
  final LocaleController _locale = LocaleController();
  final ThemeController _theme = ThemeController();
  final AuthController _auth = AuthController();

  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await Future.wait([_locale.load(), _theme.load(), _auth.restore()]);
    if (!mounted) return;
    setState(() => _ready = true);
  }

  @override
  void dispose() {
    _locale.dispose();
    _theme.dispose();
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_locale, _theme, _auth]),
      builder: (context, _) {
        return MaterialApp(
          title: 'GroundZero',
          debugShowCheckedModeBanner: false,
          scrollBehavior: const _GZScrollBehavior(),
          theme: _theme.activeTheme,
          builder: (context, child) => AnimatedTheme(
            duration: const Duration(milliseconds: 900),
            curve: Curves.easeInOut,
            data: _theme.activeTheme,
            child: child ?? const SizedBox.shrink(),
          ),
          home: _ready ? _homeFor() : const _SplashScreen(),
        );
      },
    );
  }

  Widget _homeFor() {
    if (_auth.isSignedIn) {
      return StartScreen(locale: _locale, theme: _theme, auth: _auth);
    }
    return HomeScreen(locale: _locale, theme: _theme, auth: _auth);
  }
}

/// Lets mouse and trackpad users drag horizontal strips (the places
/// gallery, the signal cards) the same way touch users swipe them.
class _GZScrollBehavior extends MaterialScrollBehavior {
  const _GZScrollBehavior();

  @override
  Set<PointerDeviceKind> get dragDevices => {
        PointerDeviceKind.touch,
        PointerDeviceKind.mouse,
        PointerDeviceKind.trackpad,
        PointerDeviceKind.stylus,
      };
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.explore, size: 56, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 16),
            const CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}
