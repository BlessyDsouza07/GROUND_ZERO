import 'package:flutter/material.dart';

Widget mediaImage(String path, {BoxFit fit = BoxFit.cover}) {
  if (path.isEmpty) {
    return const ColoredBox(color: Color(0x1F808080), child: Center(child: Icon(Icons.image_outlined)));
  }
  return Image.network(
    path,
    fit: fit,
    errorBuilder: (_, __, ___) => const ColoredBox(
      color: Color(0x1F808080),
      child: Center(child: Icon(Icons.image_outlined)),
    ),
  );
}
