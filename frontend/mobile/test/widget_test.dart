import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigyan_field/features/auth/data/auth_service.dart';
import 'package:vigyan_field/features/auth/domain/auth_models.dart';
import 'package:vigyan_field/features/auth/presentation/auth_controller.dart';
import 'package:vigyan_field/features/auth/presentation/sign_in_screen.dart';

class _FakeAuthGateway implements AuthGateway {
  bool loginCalled = false;

  @override
  Future<CurrentUser?> restoreSession() async => null;

  @override
  Future<void> login(String email, String password) async {
    loginCalled = true;
  }

  @override
  Future<CurrentUser> currentUser() async => const CurrentUser(
    userId: 'user-id',
    userCode: 'PT001',
    fullName: 'Test User',
    email: 'test@example.com',
    status: 'ACTIVE',
    permissions: [],
  );

  @override
  Future<void> clearSession() async {}

  @override
  Future<void> logout() async {}
}

void main() {
  testWidgets('validates sign-in fields before submitting', (tester) async {
    final gateway = _FakeAuthGateway();
    final controller = AuthController(gateway);

    await tester.pumpWidget(
      MaterialApp(home: SignInScreen(controller: controller)),
    );

    await tester.tap(find.text('Sign in'));
    await tester.pump();

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(find.text('Password is required.'), findsOneWidget);
    expect(gateway.loginCalled, isFalse);
  });

  testWidgets('toggles password visibility', (tester) async {
    final controller = AuthController(_FakeAuthGateway());

    await tester.pumpWidget(
      MaterialApp(home: SignInScreen(controller: controller)),
    );

    TextField passwordField() =>
        tester.widget<TextField>(find.byType(TextField).last);

    expect(passwordField().obscureText, isTrue);
    await tester.tap(find.byTooltip('Show password'));
    await tester.pump();
    expect(passwordField().obscureText, isFalse);
  });
}
