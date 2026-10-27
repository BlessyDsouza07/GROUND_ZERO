import 'package:flutter/material.dart';

Widget mediaImage(String path, {BoxFit fit = BoxFit.cover}) => const ColoredBox(
  color: Color(0x1F808080),
  child: Center(child: Icon(Icons.image_outlined)),
);
