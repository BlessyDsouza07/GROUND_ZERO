import 'dart:io';
import 'package:flutter/material.dart';

Widget mediaImage(String path, {BoxFit fit = BoxFit.cover}) {
  if (path.startsWith('http')) {
    return Image.network(path, fit: fit, errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.broken_image_outlined)));
  }
  final file = File(path);
  if (!file.existsSync()) {
    return const ColoredBox(
      color: Color(0x1F808080),
      child: Center(child: Icon(Icons.image_outlined)),
    );
  }
  return Image.file(file, fit: fit, errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.broken_image_outlined)));
}
