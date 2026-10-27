import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/locale_controller.dart';
import '../core/personal_api_client.dart';
import '../core/theme.dart';
import '../core/theme_controller.dart';
import '../widgets/language_sheet.dart';
import '../widgets/theme_sheet.dart';

/// Settings, reorganized per Carol's chunk-4 spec into ACCOUNT / TRAVEL /
/// NOTIFICATIONS / PRIVACY / APPEARANCE / DATA / SUPPORT — not "20
/// different settings screens," one scrollable panel with clear
/// sections. APPEARANCE is the permanent home of the light/dark/
/// automatic theme picker and language picker chunk 1 already built —
/// moved here, not rebuilt. Only what's genuinely backed by the backend
/// is interactive (theme, language, delete account); a few sections are
/// honestly informational rather than faking settings that don't
/// persist anywhere yet — each says so.
class SettingsPanel extends StatefulWidget {
  final LocaleController locale;
  final ThemeController theme;
  final AuthController auth;
  final VoidCallback onSignOut;

  const SettingsPanel({
    super.key,
    required this.locale,
    required this.theme,
    required this.auth,
    required this.onSignOut,
  });

  @override
  State<SettingsPanel> createState() => _SettingsPanelState();
}

class _SettingsPanelState extends State<SettingsPanel> {
  final _personalApi = PersonalApiClient();
  bool _deleting = false;

  @override
  void dispose() {
    _personalApi.close();
    super.dispose();
  }

  Future<void> _confirmDeleteAccount() async {
    final scheme = Theme.of(context).colorScheme;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete your account?'),
        content: const Text(
          'This permanently deletes your trips, journal, and contributions. '
          'This is different from logging out, and it cannot be undone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('CANCEL')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: scheme.error),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('DELETE ACCOUNT'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _deleting = true);
    try {
      await _personalApi.deleteAccount(widget.auth.accessToken!);
      await widget.auth.signOut();
      // main.dart's root listener swaps back to the public landing page.
    } on GZApiException catch (e) {
      if (mounted) {
        setState(() => _deleting = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.locale.t;
    final scheme = Theme.of(context).colorScheme;
    final theme = widget.theme;
    final locale = widget.locale;
    final auth = widget.auth;
    final modeLabel = switch (theme.mode) {
      GZThemeMode.automatic => t('theme_auto'),
      GZThemeMode.light => t('theme_light'),
      GZThemeMode.dark => t('theme_dark'),
    };

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t('side_settings'), style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 24),

            _SectionLabel('ACCOUNT'),
            Card(
              child: ListTile(
                leading: Icon(Icons.person_outline, color: scheme.primary),
                title: Text(t('set_signed_in', {'email': auth.user?.email ?? ''})),
                subtitle: Text(auth.user?.displayName ?? ''),
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('TRAVEL'),
            Card(
              child: ListTile(
                leading: Icon(Icons.card_travel_outlined, color: scheme.primary),
                title: const Text('Travel preferences'),
                subtitle: const Text('Your budget, energy, and pace come from your most recent trip survey — answer it again on your next trip to update them.'),
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('NOTIFICATIONS'),
            Card(
              child: ListTile(
                leading: Icon(Icons.notifications_outlined, color: scheme.primary),
                title: const Text('In-trip notifications'),
                subtitle: const Text('Turned on or off per trip, when you confirm your itinerary — see "Your Journeys" for an active trip\'s setting.'),
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('PRIVACY'),
            Card(
              child: ListTile(
                leading: Icon(Icons.privacy_tip_outlined, color: scheme.primary),
                title: const Text('Your journal stays yours'),
                subtitle: const Text('GroundZero never imports your phone\'s photo gallery. Only what you capture during a trip becomes part of your journal.'),
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('APPEARANCE'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: Icon(Icons.brightness_6, color: scheme.primary),
                    title: Text(t('theme_choose')),
                    subtitle: Text(modeLabel),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => showThemePicker(context: context, theme: theme, locale: locale),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: Icon(Icons.translate, color: scheme.primary),
                    title: Text(t('lang_choose')),
                    subtitle: Text(locale.current.nativeName),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => showLanguagePicker(context: context, locale: locale),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('DATA'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: Icon(Icons.download_outlined, color: scheme.primary),
                    title: const Text('Download my data'),
                    subtitle: const Text('Coming soon.'),
                    onTap: () => ScaffoldMessenger.of(context)
                        .showSnackBar(const SnackBar(content: Text('Downloading your data is coming in a future update.'))),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: Icon(Icons.delete_outline, color: scheme.error),
                    title: const Text('Delete account'),
                    subtitle: const Text('Permanently removes your trips, journal, and contributions.'),
                    trailing: _deleting ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                    onTap: _deleting ? null : _confirmDeleteAccount,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            _SectionLabel('SUPPORT'),
            Card(
              child: ListTile(
                leading: Icon(Icons.help_outline, color: scheme.primary),
                title: const Text('Need help?'),
                subtitle: const Text('Reach the GroundZero team any time.'),
              ),
            ),
            const SizedBox(height: 24),

            Card(
              child: ListTile(
                leading: Icon(Icons.logout, color: scheme.error),
                title: Text(t('side_signout'), style: TextStyle(color: scheme.error)),
                onTap: widget.onSignOut,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(text, style: TextStyle(color: scheme.onSurfaceVariant, fontWeight: FontWeight.w800, letterSpacing: 1.0, fontSize: 12)),
    );
  }
}
