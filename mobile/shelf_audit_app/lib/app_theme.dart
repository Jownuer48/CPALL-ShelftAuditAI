import 'package:flutter/material.dart';

class AppColors {
  static const Color blue = Color(0xFF173D8F);
  static const Color sky = Color(0xFF1F72BD);
  static const Color green = Color(0xFF19A15F);
  static const Color orange = Color(0xFFF36F21);
  static const Color red = Color(0xFFE23B3B);
  static const Color ink = Color(0xFF152238);
  static const Color muted = Color(0xFF68758A);
  static const Color surface = Color(0xFFF5F7FB);
  static const Color card = Color(0xFFFFFFFF);
  static const Color line = Color(0xFFE0E7F0);
}

Color statusColor(String status) {
  switch (status.toUpperCase()) {
    case 'PASS':
      return AppColors.green;
    case 'WARNING':
      return AppColors.orange;
    case 'FAIL':
    case 'FAILED':
      return AppColors.red;
    case 'PENDING':
    case 'PROCESSING':
    case 'QUEUED':
      return AppColors.sky;
    case 'NEED_RETAKE':
    case 'UNKNOWN_MODEL':
      return const Color(0xFF64748B);
    default:
      return AppColors.muted;
  }
}

ThemeData buildShelfAuditTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.blue,
    brightness: Brightness.light,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme.copyWith(
      primary: AppColors.blue,
      secondary: AppColors.green,
      surface: AppColors.card,
    ),
    scaffoldBackgroundColor: AppColors.surface,
    appBarTheme: const AppBarTheme(
      elevation: 0,
      centerTitle: false,
      backgroundColor: Colors.transparent,
      foregroundColor: AppColors.ink,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TextStyle(
        color: AppColors.ink,
        fontSize: 20,
        fontWeight: FontWeight.w900,
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.card,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: AppColors.line),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xFFF9FBFE),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.blue, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w900),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(50),
        side: const BorderSide(color: AppColors.line),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
      ),
    ),
  );
}

String formatPercent(double? value, {int digits = 1}) {
  if (value == null) return '-';
  return '${(value * 100).toStringAsFixed(digits)}%';
}

String formatDate(DateTime? value) {
  if (value == null) return '-';
  final local = value.toLocal();
  final year = local.year.toString().padLeft(4, '0');
  final month = local.month.toString().padLeft(2, '0');
  final day = local.day.toString().padLeft(2, '0');
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$day/$month/$year $hour:$minute';
}

class AppLogo extends StatelessWidget {
  const AppLogo({this.size = 64, super.key});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size * 0.28),
        gradient: const LinearGradient(
          colors: [AppColors.blue, AppColors.sky],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.blue.withValues(alpha: 0.20),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(Icons.shelves, color: Colors.white, size: size * 0.46),
          Positioned(
            right: size * 0.15,
            bottom: size * 0.15,
            child: Container(
              width: size * 0.31,
              height: size * 0.31,
              decoration: const BoxDecoration(
                color: AppColors.green,
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.check, color: Colors.white, size: size * 0.20),
            ),
          ),
        ],
      ),
    );
  }
}
