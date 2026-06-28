import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_theme.dart';
import 'splash_home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const ShelfAuditApp());
}

class ShelfAuditApp extends StatelessWidget {
  const ShelfAuditApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Shelf Audit AI',
      debugShowCheckedModeBanner: false,
      theme: buildShelfAuditTheme(),
      home: const SplashScreen(),
    );
  }
}
