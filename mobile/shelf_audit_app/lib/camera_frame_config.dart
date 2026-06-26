import 'package:flutter/material.dart';

class CameraFrameConfig {
  // ขนาดและตำแหน่งกรอบ ใช้ค่า 0.0 - 1.0 อิงจากขนาดหน้าจอ
  static const double frameWidthRatio = 0.60;
  static const double frameHeightRatio = 0.82;
  static const double frameTopRatio = 0.10;

  // รูปทรงกรอบ
  static const double borderRadius = 22;
  static const double borderWidth = 3.5;
  static const double cornerLength = 52;
  static const double cornerWidth = 7;

  // สี
  static const Color frameColor = Color(0xFF00FF8A);
  static const Color cornerColor = Colors.white;
  static const double overlayOpacity = 0.55;

  // เส้น grid ด้านใน
  static const bool showGrid = true;
  static const bool showCenterLine = true;

  // ข้อความแนะนำ
  static const String title = 'ถ่ายภาพเชลฟ์';
  static const String instruction =
      'จัดเชลฟ์ให้อยู่ในกรอบสีเขียว ให้เห็นครบทั้งแผง และพยายามถ่ายให้ตรงที่สุด';
}
