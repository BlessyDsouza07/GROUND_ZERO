import 'dart:async';

import 'package:flutter/material.dart';

import '../core/explore_api_client.dart';
import '../design/gz_ink.dart';

/// Search-as-you-type picker for an existing GroundZero place. Calls the
/// same public /explore/search the Explore tab uses.
class GZPlacePicker extends StatefulWidget {
  final GZPlaceCard? selected;
  final ValueChanged<GZPlaceCard?> onChanged;
  final String? errorText;

  const GZPlacePicker({super.key, required this.selected, required this.onChanged, this.errorText});

  @override
  State<GZPlacePicker> createState() => _GZPlacePickerState();
}

class _GZPlacePickerState extends State<GZPlacePicker> {
  final _api = ExploreApiClient();
  final _ctrl = TextEditingController();
  Timer? _debounce;
  List<GZPlaceCard> _results = const [];
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _debounce?.cancel();
    _ctrl.dispose();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    final query = q.trim();
    if (query.length < 2) {
      setState(() {
        _results = const [];
        _error = null;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 350), () => _search(query));
  }

  Future<void> _search(String query) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final (results, _) = await _api.search(query);
      if (!mounted || _ctrl.text.trim() != query) return;
      setState(() => _results = results.take(6).toList());
    } on Object {
      if (mounted) setState(() => _error = "Couldn't search right now.");
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ink = GZInk.of(context);
    final text = Theme.of(context).textTheme;
    final sel = widget.selected;
    if (sel != null) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: ink.accent.withOpacity(0.10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: ink.accent, width: 1.2),
        ),
        child: Row(
          children: [
            Icon(Icons.place, color: ink.accent),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(sel.name, style: text.titleSmall?.copyWith(color: ink.text)),
                  Text(sel.category, style: text.bodySmall),
                ],
              ),
            ),
            TextButton(onPressed: () => widget.onChanged(null), child: const Text('Change')),
          ],
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _ctrl,
          onChanged: _onChanged,
          decoration: InputDecoration(
            labelText: 'Which place?',
            hintText: 'Start typing a place name',
            prefixIcon: const Icon(Icons.search),
            errorText: widget.errorText,
            suffixIcon: _loading
                ? const Padding(padding: EdgeInsets.all(14), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))
                : null,
          ),
        ),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_error!, style: text.bodySmall)),
        if (_results.isNotEmpty)
          Container(
            margin: const EdgeInsets.only(top: 8),
            decoration: BoxDecoration(
              color: ink.paper,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: ink.border.withOpacity(0.6)),
            ),
            child: Column(
              children: [
                for (final p in _results)
                  ListTile(
                    dense: true,
                    leading: Icon(Icons.place_outlined, color: ink.accent),
                    title: Text(p.name, style: text.titleSmall?.copyWith(color: ink.text)),
                    subtitle: Text(p.category),
                    onTap: () {
                      widget.onChanged(p);
                      setState(() => _results = const []);
                    },
                  ),
              ],
            ),
          )
        else if (!_loading && _ctrl.text.trim().length >= 2 && _error == null)
          Padding(padding: const EdgeInsets.only(top: 8), child: Text('No matching places yet.', style: text.bodySmall)),
      ],
    );
  }
}
