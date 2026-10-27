import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/auth_controller.dart';
import '../core/guide_api_client.dart';
import '../core/gz_location.dart';
import '../core/guide_voice.dart';
import '../widgets/gz_nav.dart';
import '../core/locale_controller.dart';
import '../core/theme_controller.dart';
import '../design/gz_ink.dart';
import '../widgets/tiara/gz_frame_card.dart';
import 'explore/place_detail_screen.dart';

class _Msg {
  final bool fromUser;
  final String text;
  final List<GZGuidePlace> places;
  final String? note;
  final bool isError;
  _Msg({required this.fromUser, required this.text, this.places = const [], this.note, this.isError = false});
}

/// TALK TO GUIDE — a chat about Mangaluru grounded in GroundZero's own
/// place records. Replies in the app's current language.
class GuideScreen extends StatefulWidget {
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  const GuideScreen({super.key, required this.auth, required this.locale, required this.theme});

  @override
  State<GuideScreen> createState() => _GuideScreenState();
}

class _GuideScreenState extends State<GuideScreen> {
  final _api = GuideApiClient();
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _focus = FocusNode();
  final List<_Msg> _msgs = [];
  final _voice = GuideVoice();
  bool _busy = false;
  bool _listening = false;
  bool _speakReplies = false;
  String? _speakingText;

  static const _starters = [
    'Plan a relaxed day in Mangaluru',
    'Where can I eat fresh seafood?',
    'Best beaches for sunset',
    'How do I get from the airport to the city?',
    'What should I try at a local restaurant?',
    'What to do on a rainy day',
  ];

  @override
  void initState() {
    super.initState();
    GZLocation.ensure(); // so answers can say what is open near you
    _voice.fetchAudio = (t, c) async => widget.auth.accessToken == null ? null : _api.speak(widget.auth.accessToken!, t, c);
  }

  @override
  void dispose() {
    _api.close();
    _voice.dispose();
    _input.dispose();
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send([String? preset]) async {
    final text = (preset ?? _input.text).trim();
    final token = widget.auth.accessToken;
    if (text.isEmpty || _busy || token == null) return;
    final history = [
      for (final m in _msgs.where((m) => !m.isError)) (role: m.fromUser ? 'user' : 'assistant', content: m.text),
    ];
    setState(() {
      _msgs.add(_Msg(fromUser: true, text: text));
      _busy = true;
      _input.clear();
    });
    _scrollDown();
    try {
      final r = await _api.chat(token, message: text, language: widget.locale.code, history: history, spoken: _speakReplies);
      if (!mounted) return;
      setState(() => _msgs.add(_Msg(fromUser: false, text: r.reply, places: r.places, note: r.mode == 'extractive' ? r.note : null)));
      if (_speakReplies) _speak(r.reply);
    } on GZApiException catch (e) {
      if (!mounted) return;
      setState(() => _msgs.add(_Msg(fromUser: false, text: e.message, isError: true)));
    } finally {
      if (mounted) setState(() => _busy = false);
      _scrollDown();
      _focus.requestFocus();
    }
  }

  Future<void> _toggleMic() async {
    if (_listening) {
      await _voice.stopListening();
      if (mounted) setState(() => _listening = false);
      return;
    }
    await _voice.stopSpeaking();
    final ok = _voice.sttReady || await _voice.initListen(onError: (_) {
      if (mounted) setState(() => _listening = false);
    });
    if (!ok) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Voice input needs microphone permission and a supported browser (Chrome or Edge). You can still type.'),
      ));
      return;
    }
    setState(() => _listening = true);
    await _voice.listen(widget.locale.code, onText: (t, done) {
      if (!mounted) return;
      _input.text = t;
      _input.selection = TextSelection.collapsed(offset: t.length);
      if (done) {
        setState(() => _listening = false);
        if (t.trim().isNotEmpty) {
          _speakReplies = true; // you spoke, so the guide speaks back
          _send();
        }
      }
    });
  }

  Future<void> _speak(String t) async {
    setState(() => _speakingText = t);
    await _voice.speak(t, widget.locale.code, onDone: () {
      if (mounted) setState(() => _speakingText = null);
    });
  }

  Future<void> _connectAi() async {
    final ctrl = TextEditingController();
    String? err;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: const Text('Connect the AI guide'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Paste your Groq API key (starts with gsk_). Get a free one at console.groq.com/keys.'),
            const SizedBox(height: 12),
            TextField(controller: ctrl, decoration: InputDecoration(labelText: 'Groq API key', errorText: err), obscureText: true),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () async {
                final (good, msg) = await _api.setKey(widget.auth.accessToken!, ctrl.text);
                if (good) {
                  if (ctx.mounted) Navigator.of(ctx).pop(true);
                } else {
                  setD(() => err = msg);
                }
              },
              child: const Text('Connect'),
            ),
          ],
        ),
      ),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('AI guide connected. Ask me anything.')));
    }
  }

  Future<void> _stopSpeaking() async {
    await _voice.stopSpeaking();
    if (mounted) setState(() => _speakingText = null);
  }

  void _openPlace(GZGuidePlace p) {
    final id = p.placeId;
    if (id == null) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlaceDetailScreen(placeId: id, auth: widget.auth, locale: widget.locale, theme: widget.theme),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        leading: const GZBackButton(),
        title: const Text('Talk to Guide'),
        actions: [
          const GZHomeAction(),
          IconButton(
            tooltip: _speakReplies ? 'Voice replies on' : 'Voice replies off',
            icon: Icon(_speakReplies ? Icons.volume_up_rounded : Icons.volume_off_outlined),
            onPressed: () {
              setState(() => _speakReplies = !_speakReplies);
              if (!_speakReplies) _stopSpeaking();
            },
          ),
          if (_msgs.isNotEmpty)
            IconButton(
              tooltip: 'New chat',
              icon: const Icon(Icons.add_comment_outlined),
              onPressed: _busy ? null : () => setState(_msgs.clear),
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 820),
                child: _msgs.isEmpty
                    ? _Welcome(starters: _starters, onPick: _send)
                    : ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                        itemCount: _msgs.length + (_busy ? 1 : 0),
                        itemBuilder: (context, i) {
                          if (i == _msgs.length) return const _Typing();
                          final m = _msgs[i];
                          return _Bubble(
                            msg: m,
                            onPlace: _openPlace,
                            onConnect: _connectAi,
                            speaking: _speakingText == m.text,
                            onSpeak: m.fromUser || m.isError ? null : () => (_speakingText == m.text ? _stopSpeaking() : _speak(m.text)),
                          );
                        },
                      ),
              ),
            ),
          ),
          Container(
            decoration: BoxDecoration(color: ink.paper, border: Border(top: BorderSide(color: ink.border.withOpacity(0.5)))),
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            child: SafeArea(
              top: false,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 820),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _input,
                          focusNode: _focus,
                          minLines: 1,
                          maxLines: 4,
                          maxLength: 1000,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => _send(),
                          decoration: InputDecoration(
                            hintText: _listening ? 'Listening…' : 'Ask anything about Mangaluru…',
                            counterText: '',
                            contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                            hintStyle: text.bodyMedium,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      SizedBox(
                        height: 50,
                        width: 50,
                        child: IconButton.outlined(
                          tooltip: _listening ? 'Stop listening' : 'Speak to the guide',
                          style: IconButton.styleFrom(
                            backgroundColor: _listening ? ink.accent : null,
                            foregroundColor: _listening ? (ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE)) : null,
                          ),
                          onPressed: _busy ? null : _toggleMic,
                          icon: Icon(_listening ? Icons.graphic_eq_rounded : Icons.mic_none_rounded),
                        ),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        height: 50,
                        width: 50,
                        child: FilledButton(
                          style: FilledButton.styleFrom(padding: EdgeInsets.zero, shape: const CircleBorder()),
                          onPressed: _busy ? null : _send,
                          child: const Icon(Icons.arrow_upward_rounded),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Welcome extends StatelessWidget {
  final List<String> starters;
  final ValueChanged<String> onPick;
  const _Welcome({required this.starters, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 24),
        Icon(Icons.forum_outlined, size: 34, color: ink.accent),
        const SizedBox(height: 14),
        Text('Ask your Mangaluru guide', style: text.headlineSmall?.copyWith(color: ink.text)),
        const SizedBox(height: 8),
        Text(
          'Ask anything — where to eat, how to get around, what to do on a rainy day. Tap the mic to talk and the guide will talk back.',
          style: text.bodyLarge?.copyWith(color: ink.muted),
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final s in starters)
              ActionChip(
                label: Text(s),
                onPressed: () => onPick(s),
              ),
          ],
        ),
      ],
    );
  }
}

class _Bubble extends StatelessWidget {
  final _Msg msg;
  final ValueChanged<GZGuidePlace> onPlace;
  final VoidCallback? onSpeak;
  final VoidCallback? onConnect;
  final bool speaking;
  const _Bubble({required this.msg, required this.onPlace, this.onSpeak, this.onConnect, this.speaking = false});

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final onAccent = ink.dark ? const Color(0xFF240002) : const Color(0xFFF7F4EE);
    final user = msg.fromUser;
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Align(
        alignment: user ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82 > 620 ? 620 : MediaQuery.of(context).size.width * 0.82),
          child: Column(
            crossAxisAlignment: user ? CrossAxisAlignment.end : CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: user ? ink.accent : (msg.isError ? scheme.error.withOpacity(0.12) : ink.paper),
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(18),
                    topRight: const Radius.circular(18),
                    bottomLeft: Radius.circular(user ? 18 : 4),
                    bottomRight: Radius.circular(user ? 4 : 18),
                  ),
                  border: user ? null : Border.all(color: msg.isError ? scheme.error : ink.border.withOpacity(0.6)),
                ),
                child: SelectableText(
                  msg.text,
                  style: text.bodyLarge?.copyWith(color: user ? onAccent : (msg.isError ? scheme.error : ink.text), height: 1.5),
                ),
              ),
              if (onSpeak != null)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: TextButton.icon(
                    style: TextButton.styleFrom(visualDensity: VisualDensity.compact, padding: const EdgeInsets.symmetric(horizontal: 6)),
                    onPressed: onSpeak,
                    icon: Icon(speaking ? Icons.stop_circle_outlined : Icons.volume_up_outlined, size: 18),
                    label: Text(speaking ? 'Stop' : 'Listen'),
                  ),
                ),
              if (msg.places.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final p in msg.places)
                      ActionChip(
                        avatar: const Icon(Icons.place_outlined, size: 16),
                        label: Text(p.name),
                        onPressed: p.placeId == null ? null : () => onPlace(p),
                      ),
                  ],
                ),
              ],
              if (msg.note != null) ...[
                const SizedBox(height: 6),
                Text(msg.note!, style: text.labelSmall?.copyWith(color: ink.muted)),
                if ((msg.note!.contains('not found') || msg.note!.contains('rejected')) && onConnect != null)
                  TextButton.icon(onPressed: onConnect, icon: const Icon(Icons.key_rounded, size: 18), label: const Text('Connect AI guide')),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Typing extends StatelessWidget {
  const _Typing();
  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Align(
        alignment: Alignment.centerLeft,
        child: GZFrameCard(
          radius: 16,
          shadowOffset: 0,
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          child: SizedBox(width: 36, child: LinearProgressIndicator(minHeight: 3, color: ink.accent, backgroundColor: ink.accent.withOpacity(0.2))),
        ),
      ),
    );
  }
}
