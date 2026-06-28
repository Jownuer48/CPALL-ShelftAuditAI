import 'package:flutter/material.dart';

class CameraFrameConfig {
  static const double frameWidthRatio = 0.60;
  static const double frameHeightRatio = 0.82;
  static const double frameTopRatio = 0.10;

  static const double borderRadius = 22;
  static const double borderWidth = 3.5;
  static const double cornerLength = 52;
  static const double cornerWidth = 7;

  static const Color frameColor = Color(0xFF19A15F);
  static const Color cornerColor = Colors.white;
  static const double overlayOpacity = 0.55;

  static const bool showGrid = true;
  static const bool showCenterLine = true;

  static const String title = 'Capture Shelf Image';
  static const String instruction =
      'Place the shelf inside the green frame. Keep the full display visible and hold the phone steady.';
}
