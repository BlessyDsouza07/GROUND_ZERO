import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/media_api_client.dart';
import '../core/trips_api_client.dart';
import '../design/gz_ink.dart';
import 'gz_capture.dart';

/// Capture a moment: pick/take a photo, confirm it with an optional caption,
/// upload it, and add it to the trip's journal. Returns true if added.
Future<bool> gzCaptureMoment(BuildContext context, AuthController auth, String tripId, {String? tripPlaceId}) async {
  final token = auth.accessToken;
  if (token == null) return false;
  final bytes = await GZMediaPicker.pick(context, title: 'Capture this moment');
  if (bytes == null || !context.mounted) return false;
  final caption = await _confirm(context, bytes);
  if (caption == null || !context.mounted) return false;

  final messenger = ScaffoldMessenger.of(context);
  final media = MediaApiClient();
  final trips = TripsApiClient();
  try {
    final url = await media.uploadPhoto(token, bytes);
    await trips.addJournalEntry(token, tripId,
        tripPlaceId: tripPlaceId, mediaType: 'photo', mediaUrl: url, caption: caption.trim().isEmpty ? null : caption.trim());
    messenger.showSnackBar(const SnackBar(content: Text('Added to your journal.')));
    return true;
  } on GZApiException catch (e) {
    messenger.showSnackBar(SnackBar(content: Text(e.message)));
    return false;
  } finally {
    media.close();
    trips.close();
  }
}

Future<String?> _confirm(BuildContext context, Uint8List bytes) {
  final ctrl = TextEditingController();
  final ink = GZInk.of(context);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Add to your journal?'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            ClipRRect(borderRadius: BorderRadius.circular(14), child: Image.memory(bytes, height: 240, width: double.infinity, fit: BoxFit.cover)),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              maxLines: 3,
              maxLength: 240,
              decoration: InputDecoration(labelText: 'What made this moment special? (optional)', helperText: 'It becomes a Memory Moment in your story', helperStyle: TextStyle(color: ink.muted)),
            ),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Discard')),
        FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text), child: const Text('Add to journal')),
      ],
    ),
  );
}
