import 'package:flutter/material.dart';

import '../core/locale_controller.dart';

/// Bottom sheet used by the top bar's Translate action and by Settings.
/// Shows every supported language with a live search box, since five
/// languages is few enough that a search field is a nice-to-have rather
/// than a necessity — but the brief asked for the best translate
/// experience available, so it's here from the start.
Future<void> showLanguagePicker({
  required BuildContext context,
  required LocaleController locale,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) => _LanguageSheetBody(locale: locale),
  );
}

class _LanguageSheetBody extends StatefulWidget {
  final LocaleController locale;
  const _LanguageSheetBody({required this.locale});

  @override
  State<_LanguageSheetBody> createState() => _LanguageSheetBodyState();
}

class _LanguageSheetBodyState extends State<_LanguageSheetBody> {
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.locale.t;
    final query = _query.trim().toLowerCase();
    final results = kSupportedLanguages.where((lang) {
      if (query.isEmpty) return true;
      return lang.nativeName.toLowerCase().contains(query) ||
          lang.englishName.toLowerCase().contains(query) ||
          lang.code.toLowerCase().contains(query);
    }).toList();

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
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
            Text(t('lang_choose'), style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(
              t('lang_note'),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _searchController,
              onChanged: (v) => setState(() => _query = v),
              decoration: InputDecoration(
                hintText: t('lang_choose'),
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 360),
              child: results.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: Text(t('lang_none'))),
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: results.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final lang = results[index];
                        final selected = lang.code == widget.locale.code;
                        return ListTile(
                          title: Text(lang.nativeName),
                          subtitle: lang.nativeName != lang.englishName ? Text(lang.englishName) : null,
                          trailing: selected
                              ? Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary)
                              : null,
                          onTap: () {
                            widget.locale.setLanguage(lang.code);
                            Navigator.of(context).pop();
                          },
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
