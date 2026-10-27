import 'package:flutter/material.dart';
import 'privacy/legal_screen.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/tiara/gz_frame_card.dart';
import '../widgets/tiara/gz_scene.dart';
import '../widgets/tiara/gz_sticker_button.dart';

/// The screen behind "Sign Up for free": a two-tab email + password form
/// (log in / sign up) set against the painted coast. On success it just
/// calls [AuthController], which notifies its listeners — main.dart is
/// watching that and swaps the whole app over to the signed-in start
/// page, so this screen doesn't need to navigate anywhere itself.
class AuthScreen extends StatefulWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;
  final bool startOnSignUp;

  const AuthScreen({
    super.key,
    required this.locale,
    required this.theme,
    required this.auth,
    this.startOnSignUp = false,
  });

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _isSignUp = false;
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  bool _obscure = true;
  bool _accepted = false;
  bool _adult = false;
  bool _submitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _isSignUp = widget.startOnSignUp;
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  String? _validateEmail(String? value) {
    final email = (value ?? '').trim();
    final ok = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email);
    return ok ? null : widget.locale.t('err_email');
  }

  String? _validatePassword(String? value) {
    return (value ?? '').length >= 8 ? null : widget.locale.t('err_password');
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_isSignUp && !(_accepted && _adult)) {
      setState(() => _errorMessage = 'Please tick both boxes: you accept the Terms and Privacy Policy, and you are 18 or over.');
      return;
    }
    setState(() {
      _submitting = true;
      _errorMessage = null;
    });
    try {
      if (_isSignUp) {
        await widget.auth.register(
          email: _emailController.text,
          password: _passwordController.text,
          displayName: _nameController.text,
          acceptedTerms: _accepted,
          adultConfirmed: _adult,
        );
      } else {
        await widget.auth.login(email: _emailController.text, password: _passwordController.text);
      }
      // main.dart swaps its home to the signed-in start page, but this screen
      // was PUSHED on top of the landing page, so it must close itself or the
      // person keeps staring at the login form until a reload.
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
    } on GZApiException catch (e) {
      if (mounted) setState(() => _errorMessage = _friendlyMessage(e));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _friendlyMessage(GZApiException e) {
    final t = widget.locale.t;
    final code = e.statusCode;
    if (code == 401) return t('err_bad_login');
    if (code == 409) return t('err_exists');
    if (code == null) return '${t('err_network')}\n$gzApiBaseUrl';
    // 5xx: the backend now answers with a plain-language reason (database
    // not running, missing secret…). Show it instead of a generic shrug.
    if (code >= 500 && e.message.isNotEmpty) return e.message;
    return t('err_generic');
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.locale,
      builder: (context, _) => _buildScaffold(context),
    );
  }

  Widget _buildScaffold(BuildContext context) {
    final t = widget.locale.t;
    final ink = GZInk.of(context);
    final wide = MediaQuery.of(context).size.width >= 900;

    final form = _FormCard(
      isSignUp: _isSignUp,
      formKey: _formKey,
      nameController: _nameController,
      emailController: _emailController,
      passwordController: _passwordController,
      obscure: _obscure,
      submitting: _submitting,
      errorMessage: _errorMessage,
      accepted: _accepted,
      adult: _adult,
      onAccepted: (v) => setState(() => _accepted = v),
      onAdult: (v) => setState(() => _adult = v),
      locale: widget.locale,
      validateEmail: _validateEmail,
      validatePassword: _validatePassword,
      onToggleObscure: () => setState(() => _obscure = !_obscure),
      onSubmit: _submit,
      onMode: (signUp) => setState(() {
        _isSignUp = signUp;
        _errorMessage = null;
      }),
    );

    final backButton = Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 0, 0),
      child: Align(
        alignment: Alignment.topLeft,
        child: Tooltip(
          message: t('back'),
          child: InkResponse(
            onTap: () => Navigator.of(context).maybePop(),
            radius: 26,
            child: Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                color: ink.paper,
                shape: BoxShape.circle,
                border: Border.all(color: ink.hairline, width: 1),
                boxShadow: ink.softShadow,
              ),
              child: Icon(Icons.arrow_back_rounded, color: ink.text),
            ),
          ),
        ),
      ),
    );

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            Expanded(
              flex: 11,
              child: GZScene(
                child: Stack(
                  children: [
                    SafeArea(child: backButton),
                    Positioned(
                      left: 48,
                      right: 48,
                      top: 120,
                      child: _Pitch(isSignUp: _isSignUp, locale: widget.locale),
                    ),
                  ],
                ),
              ),
            ),
            Expanded(
              flex: 10,
              child: Container(
                color: Theme.of(context).scaffoldBackgroundColor,
                child: Center(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 32),
                    child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 480), child: form),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            SizedBox(
              height: 250,
              width: double.infinity,
              child: GZScene(
                child: Stack(
                  children: [
                    SafeArea(child: backButton),
                    Positioned(left: 24, right: 24, bottom: 44, child: _Pitch(isSignUp: _isSignUp, locale: widget.locale, compact: true)),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 22, 20, 36),
              child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 480), child: form)),
            ),
          ],
        ),
      ),
    );
  }
}

class _Pitch extends StatelessWidget {
  final bool isSignUp;
  final LocaleController locale;
  final bool compact;
  const _Pitch({required this.isSignUp, required this.locale, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final style = (compact ? text.headlineSmall : text.displayMedium)?.copyWith(
      color: const Color(0xFFFBF3E2),
      shadows: [Shadow(color: Color(0x55000000), blurRadius: 16, offset: Offset(0, 3))],
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('groundzero', style: text.labelLarge?.copyWith(color: const Color(0xFFFBF3E2), letterSpacing: 3)),
        const SizedBox(height: 10),
        Text((isSignUp ? t('auth_signup_t') : t('auth_login_t')), style: style),
      ],
    );
  }
}

class _FormCard extends StatelessWidget {
  final bool isSignUp;
  final GlobalKey<FormState> formKey;
  final TextEditingController nameController;
  final TextEditingController emailController;
  final TextEditingController passwordController;
  final bool obscure;
  final bool submitting;
  final String? errorMessage;
  final bool accepted;
  final bool adult;
  final ValueChanged<bool> onAccepted;
  final ValueChanged<bool> onAdult;
  final LocaleController locale;
  final String? Function(String?) validateEmail;
  final String? Function(String?) validatePassword;
  final VoidCallback onToggleObscure;
  final VoidCallback onSubmit;
  final ValueChanged<bool> onMode;

  const _FormCard({
    required this.isSignUp,
    required this.formKey,
    required this.nameController,
    required this.emailController,
    required this.passwordController,
    required this.obscure,
    required this.submitting,
    required this.errorMessage,
    required this.accepted,
    required this.adult,
    required this.onAccepted,
    required this.onAdult,
    required this.locale,
    required this.validateEmail,
    required this.validatePassword,
    required this.onToggleObscure,
    required this.onSubmit,
    required this.onMode,
  });

  @override
  Widget build(BuildContext context) {
    final t = locale.t;
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;

    return GZFrameCard(
      padding: const EdgeInsets.all(26),
      radius: 26,
      shadowOffset: 8,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  isSignUp ? t('auth_signup_d') : t('auth_login_d'),
                  style: text.bodyMedium?.copyWith(color: ink.muted),
                ),
              ),
              const SizedBox(width: 10),
              const _ServerPill(),
            ],
          ),
          const SizedBox(height: 18),
          _SegmentedTabs(
            loginLabel: t('tab_login'),
            signUpLabel: t('tab_signup'),
            isSignUp: isSignUp,
            onChanged: onMode,
          ),
          const SizedBox(height: 22),
          Form(
            key: formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (isSignUp) ...[
                  TextFormField(
                    controller: nameController,
                    textInputAction: TextInputAction.next,
                    decoration: InputDecoration(labelText: t('f_name')),
                  ),
                  const SizedBox(height: 16),
                ],
                TextFormField(
                  controller: emailController,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.email],
                  decoration: InputDecoration(labelText: t('f_email')),
                  validator: validateEmail,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: passwordController,
                  obscureText: obscure,
                  textInputAction: TextInputAction.done,
                  autofillHints: [isSignUp ? AutofillHints.newPassword : AutofillHints.password],
                  onFieldSubmitted: (_) => onSubmit(),
                  decoration: InputDecoration(
                    labelText: t('f_password'),
                    helperText: isSignUp ? t('f_password_hint') : null,
                    suffixIcon: IconButton(
                      tooltip: obscure ? t('pw_show') : t('pw_hide'),
                      icon: Icon(obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                      onPressed: onToggleObscure,
                    ),
                  ),
                  validator: validatePassword,
                ),
                if (errorMessage != null) ...[
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: scheme.error.withOpacity(0.10),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: scheme.error, width: 1.4),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.error_outline, size: 18, color: scheme.error),
                        const SizedBox(width: 10),
                        Expanded(child: Text(errorMessage!, style: text.bodyMedium?.copyWith(color: scheme.error))),
                      ],
                    ),
                  ),
                ],
                if (isSignUp) ...[
                  const SizedBox(height: 14),
                  _ConsentRow(
                    value: accepted,
                    onChanged: onAccepted,
                    child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
                      Text('I accept the ', style: text.bodySmall),
                      _LegalLink('Terms', 'terms', 'Terms of Use'),
                      Text(' and ', style: text.bodySmall),
                      _LegalLink('Privacy Policy', 'privacy', 'Privacy Policy'),
                      Text('.', style: text.bodySmall),
                    ]),
                  ),
                  _ConsentRow(
                    value: adult,
                    onChanged: onAdult,
                    child: Text('I am 18 years or older.', style: text.bodySmall),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: 36, top: 2),
                    child: Text('Location, personalisation and camera are asked separately, only when you use them.',
                        style: text.bodySmall?.copyWith(color: ink.muted, fontSize: 11.5)),
                  ),
                ],
                const SizedBox(height: 22),
                GZStickerButton(
                  label: isSignUp ? t('btn_signup') : t('btn_login'),
                  expand: true,
                  busy: submitting,
                  onPressed: onSubmit,
                ),
                const SizedBox(height: 10),
                TextButton(
                  onPressed: () => onMode(!isSignUp),
                  child: Text(
                    (isSignUp ? t('switch_to_login') : t('switch_to_signup')),
                    style: text.labelLarge?.copyWith(color: ink.accent, fontSize: 11.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Small "server online / offline" pill. Probes GET /health once on open
/// and again whenever it is tapped, so a person (or Carol, testing) can
/// see immediately whether a failed login is a backend problem.
class _ServerPill extends StatefulWidget {
  const _ServerPill();

  @override
  State<_ServerPill> createState() => _ServerPillState();
}

class _ServerPillState extends State<_ServerPill> {
  final GZApiClient _api = GZApiClient();
  bool? _online; // null = checking

  @override
  void initState() {
    super.initState();
    _probe();
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _probe() async {
    final ok = await _api.health();
    if (mounted) setState(() => _online = ok);
  }

  void _check() {
    setState(() => _online = null);
    _probe();
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final scheme = Theme.of(context).colorScheme;
    final color = _online == null ? ink.muted : (_online! ? const Color(0xFF2E9E5B) : scheme.error);
    final label = _online == null ? 'checking' : (_online! ? 'server online' : 'server offline · retry');
    return Tooltip(
      message: gzApiBaseUrl,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: _check,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: color, width: 1.4),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
              const SizedBox(width: 6),
              Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color, fontSize: 10.5)),
            ],
          ),
        ),
      ),
    );
  }
}

class _SegmentedTabs extends StatelessWidget {
  final String loginLabel;
  final String signUpLabel;
  final bool isSignUp;
  final ValueChanged<bool> onChanged;

  const _SegmentedTabs({
    required this.loginLabel,
    required this.signUpLabel,
    required this.isSignUp,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final onAccent = ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE);
    Widget segment(String label, bool selected, VoidCallback onTap) {
      return Expanded(
        child: GestureDetector(
          onTap: onTap,
          behavior: HitTestBehavior.opaque,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: selected ? ink.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              label.toUpperCase(),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: selected ? onAccent : ink.text,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.4,
                  ),
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: ink.hairline, width: 1),
      ),
      child: Row(
        children: [
          segment(loginLabel, !isSignUp, () => onChanged(false)),
          segment(signUpLabel, isSignUp, () => onChanged(true)),
        ],
      ),
    );
  }
}

class _ConsentRow extends StatelessWidget {
  final bool value;
  final ValueChanged<bool> onChanged;
  final Widget child;
  const _ConsentRow({required this.value, required this.onChanged, required this.child});

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Checkbox(value: value, onChanged: (v) => onChanged(v ?? false), visualDensity: VisualDensity.compact),
      Expanded(child: GestureDetector(onTap: () => onChanged(!value), child: child)),
    ]);
  }
}

class _LegalLink extends StatelessWidget {
  final String label;
  final String doc;
  final String title;
  const _LegalLink(this.label, this.doc, this.title);

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return InkWell(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => LegalScreen(doc: doc, title: title))),
      child: Text(label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: ink.accent, decoration: TextDecoration.underline, fontWeight: FontWeight.w700)),
    );
  }
}
