class AppConfig {
  AppConfig._();

  // Application identity
  static const String appName = 'Vigyan Field';
  static const String appSubtitle = 'Teaching & Field Operations';
  static const String organisationName = 'Navnirmiti';

  // API configuration
  //
  // Android development:
  // ADB reverse forwards device port 8080 to Windows port 8080.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8080/api/v1',
  );

  // Brand identity
  static const int forestGreen = 0xFF193D30;
  static const int mutedGold = 0xFFC8A856;

  // Light theme
  static const int lightCanvas = 0xFFFCF9F0;
  static const int lightSurface = 0xFFFFFFFF;
  static const int lightBorder = 0xFFE2DFD2;
  static const int lightText = 0xFF202A24;
  static const int lightMutedText = 0xFF59665D;

  // Dark theme
  static const int darkCanvas = 0xFF151E19;
  static const int darkSurface = 0xFF1D2922;
  static const int darkBorder = 0xFF35463A;
  static const int darkText = 0xFFF0F1E8;
  static const int darkMutedText = 0xFFC1CCC1;

  // Branding asset
  static const String logoAsset = 'assets/brand/logo-emblem.svg';

  // Backend session timeout
  static const Duration sessionTimeout = Duration(minutes: 30);
}
