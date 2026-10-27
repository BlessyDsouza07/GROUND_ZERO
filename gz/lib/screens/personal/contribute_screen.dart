import 'dart:typed_data';
import '../../widgets/gz_nav.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_controller.dart';
import '../../core/explore_api_client.dart';
import '../../core/personal_api_client.dart';
import '../../design/gz_ink.dart';
import '../../core/media_api_client.dart';
import '../../widgets/gz_photo_field.dart';
import '../../widgets/place_picker.dart';
import '../../widgets/tiara/gz_sticker_button.dart';

enum ContributeKind { suggestUpdate, localTip, reportIncorrect, addMedia }

extension ContributeKindInfo on ContributeKind {
  String get title => switch (this) {
        ContributeKind.suggestUpdate => 'Suggest an update',
        ContributeKind.localTip => 'Share a local tip',
        ContributeKind.reportIncorrect => 'Report incorrect information',
        ContributeKind.addMedia => 'Add useful media',
      };

  String get blurb => switch (this) {
        ContributeKind.suggestUpdate => 'Something about a place has changed? Tell us the correct detail and it goes to review.',
        ContributeKind.localTip => 'Know the best time, the quiet corner, the thing to order? Your tip is reviewed before other explorers see it.',
        ContributeKind.reportIncorrect => 'Wrong hours, closed down, pin in the wrong spot? Flag it so it can be checked.',
        ContributeKind.addMedia => 'Link a photo or video that helps people picture the place. It is reviewed before it appears.',
      };

  IconData get icon => switch (this) {
        ContributeKind.suggestUpdate => Icons.edit_note,
        ContributeKind.localTip => Icons.tips_and_updates_outlined,
        ContributeKind.reportIncorrect => Icons.flag_outlined,
        ContributeKind.addMedia => Icons.photo_camera_outlined,
      };
}

const _kFields = {
  'opening_hours': 'Opening hours',
  'price_band': 'Price / cost',
  'category': 'Category',
  'description': 'Description',
  'best_time': 'Best time to visit',
  'other': 'Something else',
};

const _kIssues = {
  'wrong_hours': 'Wrong opening hours',
  'closed_down': 'Closed down',
  'wrong_location': 'Wrong location on map',
  'wrong_price': 'Wrong price',
  'other': 'Something else',
};

/// One form for the four "improve an existing place" contributions. All
/// four post to the real /personal/contributions/* endpoints and land in
/// "Your impact" as pending, exactly like Add a place.
class ContributeScreen extends StatefulWidget {
  final AuthController auth;
  final ContributeKind kind;
  const ContributeScreen({super.key, required this.auth, required this.kind});

  @override
  State<ContributeScreen> createState() => _ContributeScreenState();
}

class _ContributeScreenState extends State<ContributeScreen> {
  final _formKey = GlobalKey<FormState>();
  final _api = PersonalApiClient();
  final _a = TextEditingController(); // main text
  final _b = TextEditingController(); // optional 1
  final _c = TextEditingController(); // optional 2
  final _d = TextEditingController(); // optional 3
  GZPlaceCard? _place;
  bool _placeMissing = false;
  String _choice = '';
  Uint8List? _photo;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _choice = widget.kind == ContributeKind.suggestUpdate ? 'opening_hours' : 'wrong_hours';
  }

  @override
  void dispose() {
    _api.close();
    _a.dispose();
    _b.dispose();
    _c.dispose();
    _d.dispose();
    super.dispose();
  }

  String? _opt(TextEditingController c) => c.text.trim().isEmpty ? null : c.text.trim();

  Future<GZContribution> _addMedia(String token, String placeId) async {
    var url = _a.text.trim();
    if (_photo != null) {
      final media = MediaApiClient();
      try {
        url = await media.uploadPhoto(token, _photo!);
      } finally {
        media.close();
      }
    }
    return _api.addMedia(token, placeId: placeId, mediaUrl: url, caption: _opt(_b), source: _opt(_c));
  }

  Future<void> _submit() async {
    final valid = _formKey.currentState!.validate();
    setState(() => _placeMissing = _place == null);
    if (!valid || _place == null) return;
    final token = widget.auth.accessToken!;
    final id = _place!.placeId;
    setState(() => _submitting = true);
    try {
      final GZContribution r = switch (widget.kind) {
        ContributeKind.suggestUpdate => await _api.suggestUpdate(token,
            placeId: id, field: _choice, currentValue: _opt(_b), suggestedValue: _a.text.trim(), reason: _opt(_c)),
        ContributeKind.localTip => await _api.localTip(token, placeId: id, tip: _a.text.trim(), bestTime: _opt(_b), context: _opt(_c)),
        ContributeKind.reportIncorrect =>
          await _api.reportIncorrect(token, placeId: id, issueType: _choice, description: _a.text.trim(), evidence: _opt(_b)),
        ContributeKind.addMedia => await _addMedia(token, id),
      };
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: Icon(Icons.check_circle_outline, color: GZInk.of(ctx).accent, size: 36),
          title: const Text('Thank you'),
          content: Text(r.impactMessage),
          actions: [FilledButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Done'))],
        ),
      );
      if (mounted) Navigator.of(context).pop(r);
    } on GZApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String? _required(String? v) => (v == null || v.trim().isEmpty) ? 'Required' : null;

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final k = widget.kind;

    List<Widget> fields;
    switch (k) {
      case ContributeKind.suggestUpdate:
        fields = [
          DropdownButtonFormField<String>(
            value: _choice,
            decoration: const InputDecoration(labelText: 'What needs updating?'),
            items: [for (final e in _kFields.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) => setState(() => _choice = v ?? _choice),
          ),
          TextFormField(controller: _b, decoration: const InputDecoration(labelText: 'What it says now (optional)')),
          TextFormField(
            controller: _a,
            maxLines: 2,
            decoration: const InputDecoration(labelText: 'What it should say'),
            validator: _required,
          ),
          TextFormField(controller: _c, maxLines: 2, decoration: const InputDecoration(labelText: 'Why / how do you know? (optional)')),
        ];
      case ContributeKind.localTip:
        fields = [
          TextFormField(
            controller: _a,
            maxLines: 4,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Your tip', hintText: 'e.g. Go 30 minutes before sunset — the crowd arrives after.'),
            validator: _required,
          ),
          TextFormField(controller: _b, decoration: const InputDecoration(labelText: 'Best time (optional)')),
          TextFormField(controller: _c, decoration: const InputDecoration(labelText: 'Good for… (optional)', hintText: 'families, solo, photography')),
        ];
      case ContributeKind.reportIncorrect:
        fields = [
          DropdownButtonFormField<String>(
            value: _choice,
            decoration: const InputDecoration(labelText: 'What is wrong?'),
            items: [for (final e in _kIssues.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) => setState(() => _choice = v ?? _choice),
          ),
          TextFormField(
            controller: _a,
            maxLines: 4,
            decoration: const InputDecoration(labelText: 'What did you find?'),
            validator: _required,
          ),
          TextFormField(controller: _b, decoration: const InputDecoration(labelText: 'Proof or link (optional)')),
        ];
      case ContributeKind.addMedia:
        fields = [
          GZPhotoField(bytes: _photo, onChanged: (b) => setState(() => _photo = b), label: 'Add a photo of this place'),
          TextFormField(
            controller: _a,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(labelText: 'Or paste a link to a photo or video', hintText: 'https://…'),
            validator: (v) {
              if (_photo != null) return null;
              final s = (v ?? '').trim();
              final u = Uri.tryParse(s);
              return (u != null && (u.scheme == 'http' || u.scheme == 'https') && u.host.isNotEmpty) ? null : 'Add a photo, or enter a full link starting with https://';
            },
          ),
          TextFormField(controller: _b, decoration: const InputDecoration(labelText: 'Caption (optional)')),
          TextFormField(controller: _c, decoration: const InputDecoration(labelText: 'Credit / source (optional)')),
        ];
    }

    return Scaffold(
      appBar: AppBar(leading: const GZBackButton(), title: Text(k.title), actions: const [GZHomeAction()]),
      body: Form(
        key: _formKey,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(k.icon, color: ink.accent),
                    const SizedBox(width: 12),
                    Expanded(child: Text(k.blurb, style: text.bodyLarge?.copyWith(color: ink.muted))),
                  ],
                ),
                const SizedBox(height: 22),
                GZPlacePicker(
                  selected: _place,
                  errorText: _placeMissing && _place == null ? 'Pick a place first' : null,
                  onChanged: (p) => setState(() {
                    _place = p;
                    _placeMissing = false;
                  }),
                ),
                for (final f in fields) ...[const SizedBox(height: 16), f],
                const SizedBox(height: 26),
                GZStickerButton(label: 'Submit for review', expand: true, busy: _submitting, onPressed: _submit),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
