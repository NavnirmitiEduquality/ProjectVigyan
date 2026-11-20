import 'package:flutter/material.dart';

import 'app_config.dart';

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    return _theme(
      brightness: Brightness.light,
      background: const Color(AppConfig.lightCanvas),
      surface: const Color(AppConfig.lightSurface),
      border: const Color(AppConfig.lightBorder),
      text: const Color(AppConfig.lightText),
      mutedText: const Color(AppConfig.lightMutedText),
    );
  }

  static ThemeData dark() {
    return _theme(
      brightness: Brightness.dark,
      background: const Color(AppConfig.darkCanvas),
      surface: const Color(AppConfig.darkSurface),
      border: const Color(AppConfig.darkBorder),
      text: const Color(AppConfig.darkText),
      mutedText: const Color(AppConfig.darkMutedText),
    );
  }

  static ThemeData _theme({
    required Brightness brightness,
    required Color background,
    required Color surface,
    required Color border,
    required Color text,
    required Color mutedText,
  }) {
    final scheme = ColorScheme(
      brightness: brightness,
      primary: const Color(AppConfig.forestGreen),
      onPrimary: Colors.white,
      secondary: const Color(AppConfig.mutedGold),
      onSecondary: const Color(AppConfig.lightText),
      error: Colors.red.shade700,
      onError: Colors.white,
      surface: surface,
      onSurface: text,
    );

    return ThemeData(
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      fontFamily: 'Inter',
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        labelStyle: TextStyle(color: mutedText),
        hintStyle: TextStyle(color: mutedText),
        enabledBorder: OutlineInputBorder(
          borderSide: BorderSide(color: border),
          borderRadius: BorderRadius.circular(10),
        ),
        focusedBorder: OutlineInputBorder(
          borderSide: const BorderSide(
            color: Color(AppConfig.forestGreen),
            width: 2,
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        errorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: scheme.error),
          borderRadius: BorderRadius.circular(10),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: scheme.error, width: 2),
          borderRadius: BorderRadius.circular(10),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(AppConfig.forestGreen),
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
      textTheme: TextTheme(
        headlineMedium: TextStyle(color: text, fontWeight: FontWeight.w700),
        titleLarge: TextStyle(color: text, fontWeight: FontWeight.w700),
        bodyLarge: TextStyle(color: text),
        bodyMedium: TextStyle(color: mutedText),
      ),
    );
  }
}
