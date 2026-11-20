import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'core/config/app_config.dart';
import 'core/config/app_theme.dart';
import 'core/network/api_client.dart';
import 'core/storage/secure_storage.dart';
import 'features/auth/data/auth_service.dart';
import 'features/auth/presentation/auth_controller.dart';
import 'features/auth/presentation/home_screen.dart';
import 'features/auth/presentation/loading_screen.dart';
import 'features/auth/presentation/sign_in_screen.dart';

void main() {
  final controller = AuthController(
    AuthService(apiClient: ApiClient(), secureStorage: SecureStorage()),
  );
  final router = _createRouter(controller);

  runApp(VigyanFieldApp(controller: controller, router: router));
  unawaited(controller.restoreSession());
}

GoRouter _createRouter(AuthController controller) {
  return GoRouter(
    initialLocation: '/loading',
    refreshListenable: controller,
    redirect: (context, state) {
      final path = state.uri.path;
      if (controller.status == AuthStatus.initializing && path != '/loading') {
        return '/loading';
      }
      if (controller.status == AuthStatus.authenticated &&
          (path == '/loading' || path == '/sign-in')) {
        return '/home';
      }
      if (controller.status != AuthStatus.initializing &&
          controller.status != AuthStatus.authenticated &&
          path == '/loading') {
        return '/sign-in';
      }
      if (controller.status != AuthStatus.authenticated &&
          controller.status != AuthStatus.initializing &&
          path == '/home') {
        return '/sign-in';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/loading',
        builder: (context, state) => const LoadingScreen(),
      ),
      GoRoute(
        path: '/sign-in',
        builder: (context, state) => SignInScreen(controller: controller),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => HomeScreen(controller: controller),
      ),
    ],
  );
}

class VigyanFieldApp extends StatelessWidget {
  const VigyanFieldApp({
    required this.controller,
    required this.router,
    super.key,
  });

  final AuthController controller;
  final GoRouter router;

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: AppConfig.appName,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}
