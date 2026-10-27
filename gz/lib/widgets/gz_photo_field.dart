import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../design/gz_ink.dart';
import 'gz_capture.dart';

/// "Add a photo" box: take one with the camera or choose from the gallery
/// (always by explicit tap), preview it, and replace or remove it.
class GZPhotoField extends StatelessWidget {
  final Uint8List? bytes;
  final ValueChanged<Uint8List?> onChanged;
  final String label;
  const GZPhotoField({super.key, required this.bytes, required this.onChanged, this.label = 'Add a photo'});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    Future<void> pick() async {
      final b = await GZMediaPicker.pick(context, title: label);
      if (b != null) onChanged(b);
    }

    if (bytes == null) {
      return InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: pick,
        child: Container(
          height: 120,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: ink.border.withOpacity(0.5)),
          ),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(Icons.add_a_photo_outlined, color: ink.accent, size: 28),
            const SizedBox(height: 8),
            Text(label, style: Theme.of(context).textTheme.titleSmall),
            Text('Camera or gallery', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: ink.muted)),
          ]),
        ),
      );
    }
    return Stack(children: [
      ClipRRect(borderRadius: BorderRadius.circular(16), child: Image.memory(bytes!, height: 200, width: double.infinity, fit: BoxFit.cover)),
      Positioned(
        right: 8,
        top: 8,
        child: Row(children: [
          IconButton.filledTonal(onPressed: pick, icon: const Icon(Icons.swap_horiz), tooltip: 'Change photo'),
          const SizedBox(width: 6),
          IconButton.filledTonal(onPressed: () => onChanged(null), icon: const Icon(Icons.close), tooltip: 'Remove photo'),
        ]),
      ),
    ]);
  }
}
