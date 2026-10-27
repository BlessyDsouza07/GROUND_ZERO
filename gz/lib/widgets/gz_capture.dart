import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import '../core/gz_consent.dart';
import 'package:image_picker/image_picker.dart';

import '../design/gz_ink.dart';

/// Picks one photo, always by explicit choice: the sheet explains what will
/// happen, nothing is accessed until the person taps, and the browser/phone
/// shows its own permission prompt for the camera. A taken photo is shown
/// for confirmation (Use / Retake) before anything is kept.
class GZMediaPicker {
  static final _picker = ImagePicker();

  static Future<Uint8List?> pick(BuildContext context, {String title = 'Add a photo'}) async {
    // Camera and photos are only used once the person has said yes.
    final tk = GZConsent.token;
    if (!GZConsent.photos && tk != null) {
      final ok = await GZConsent.ask(context, tk, 'photos');
      if (!ok || !context.mounted) return null;
    }
    final ink = GZInk.of(context);
    final choice = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(
              'GroundZero only uses your camera or photos when you tap one of these, and only for this picture. Your device will ask for permission first.',
              style: Theme.of(ctx).textTheme.bodySmall?.copyWith(color: ink.muted),
            ),
            const SizedBox(height: 12),
            ListTile(
              leading: Icon(Icons.photo_camera_outlined, color: ink.accent),
              title: const Text('Take a photo'),
              subtitle: const Text('Opens your camera'),
              onTap: () => Navigator.pop(ctx, 'camera'),
            ),
            ListTile(
              leading: Icon(Icons.photo_library_outlined, color: ink.accent),
              title: const Text('Choose from gallery'),
              subtitle: const Text('Pick one existing photo'),
              onTap: () => Navigator.pop(ctx, 'gallery'),
            ),
          ]),
        ),
      ),
    );
    if (choice == null || !context.mounted) return null;
    if (choice == 'gallery') return _fromPicker(ImageSource.gallery);

    final result = await Navigator.of(context).push<Object?>(MaterialPageRoute(fullscreenDialog: true, builder: (_) => const GZCameraScreen()));
    if (result is Uint8List) return result;
    if (result == 'fallback') return _fromPicker(ImageSource.camera);
    return null;
  }

  static Future<Uint8List?> _fromPicker(ImageSource src) async {
    try {
      final f = await _picker.pickImage(source: src, maxWidth: 1600, imageQuality: 85);
      return f == null ? null : await f.readAsBytes();
    } on Object {
      return null;
    }
  }
}

/// In-app camera: live preview, shutter, then Use photo / Retake.
class GZCameraScreen extends StatefulWidget {
  const GZCameraScreen({super.key});

  @override
  State<GZCameraScreen> createState() => _GZCameraScreenState();
}

class _GZCameraScreenState extends State<GZCameraScreen> {
  CameraController? _c;
  List<CameraDescription> _cams = const [];
  int _idx = 0;
  Uint8List? _shot;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      _cams = await availableCameras();
      if (_cams.isEmpty) throw StateError('no camera');
      // prefer the back camera on phones
      final back = _cams.indexWhere((c) => c.lensDirection == CameraLensDirection.back);
      _idx = back >= 0 ? back : 0;
      await _open();
    } on Object {
      if (mounted) setState(() => _error = 'The camera is not available or permission was not given.');
    }
  }

  Future<void> _open() async {
    await _c?.dispose();
    final c = CameraController(_cams[_idx], ResolutionPreset.high, enableAudio: false);
    _c = c;
    await c.initialize();
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  Future<void> _snap() async {
    final c = _c;
    if (c == null || !c.value.isInitialized || _busy) return;
    setState(() => _busy = true);
    try {
      final f = await c.takePicture();
      final bytes = await f.readAsBytes();
      if (mounted) setState(() => _shot = bytes);
    } on Object {
      if (mounted) setState(() => _error = 'Could not take the photo. Try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        leading: IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
        title: Text(_shot == null ? 'Take a photo' : 'Use this photo?'),
        actions: [
          if (_shot == null && _cams.length > 1)
            IconButton(
              tooltip: 'Switch camera',
              icon: const Icon(Icons.cameraswitch_outlined),
              onPressed: () async {
                _idx = (_idx + 1) % _cams.length;
                try {
                  await _open();
                } on Object {/* keep going */}
              },
            ),
        ],
      ),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: () => Navigator.pop(context, 'fallback'), child: const Text('Use the device camera or files instead')),
                ]),
              ),
            )
          : _shot != null
              ? Column(children: [
                  Expanded(child: Center(child: Image.memory(_shot!, fit: BoxFit.contain))),
                  SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(children: [
                        Expanded(child: OutlinedButton(onPressed: () => setState(() => _shot = null), child: const Text('Retake'))),
                        const SizedBox(width: 12),
                        Expanded(child: FilledButton(onPressed: () => Navigator.pop(context, _shot), child: const Text('Use photo'))),
                      ]),
                    ),
                  ),
                ])
              : (_c == null || !_c!.value.isInitialized)
                  ? const Center(child: CircularProgressIndicator())
                  : Column(children: [
                      Expanded(child: Center(child: CameraPreview(_c!))),
                      SafeArea(
                        child: Padding(
                          padding: const EdgeInsets.all(18),
                          child: GestureDetector(
                            onTap: _snap,
                            child: Container(
                              width: 74,
                              height: 74,
                              decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 4)),
                              padding: const EdgeInsets.all(6),
                              child: DecoratedBox(decoration: BoxDecoration(shape: BoxShape.circle, color: _busy ? Colors.grey : ink.accent)),
                            ),
                          ),
                        ),
                      ),
                    ]),
    );
  }
}
