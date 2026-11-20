import 'package:flutter/foundation.dart';

import '../data/auth_service.dart';
import '../domain/auth_models.dart';

enum AuthStatus { initializing, unauthenticated, authenticated, error }

class AuthController extends ChangeNotifier {
  AuthController(this._authGateway);

  final AuthGateway _authGateway;

  AuthStatus status = AuthStatus.initializing;
  CurrentUser? currentUser;
  AuthException? error;
  bool isSubmitting = false;

  Future<void> restoreSession() async {
    status = AuthStatus.initializing;
    error = null;
    notifyListeners();

    try {
      currentUser = await _authGateway.restoreSession();
      status = currentUser == null
          ? AuthStatus.unauthenticated
          : AuthStatus.authenticated;
    } on AuthException catch (value) {
      error = value;
      status = AuthStatus.error;
    } on Object {
      error = const AuthException(
        kind: AuthErrorKind.server,
        message: 'Unable to restore the previous session. Please try again.',
      );
      status = AuthStatus.error;
    }
    notifyListeners();
  }

  Future<bool> signIn(String email, String password) async {
    isSubmitting = true;
    error = null;
    notifyListeners();

    try {
      await _authGateway.login(email, password);
      try {
        currentUser = await _authGateway.currentUser();
      } on Object {
        await _authGateway.clearSession();
        rethrow;
      }
      status = AuthStatus.authenticated;
      return true;
    } on AuthException catch (value) {
      error = value;
      status = AuthStatus.unauthenticated;
      return false;
    } on Object {
      error = const AuthException(
        kind: AuthErrorKind.server,
        message: 'Unable to complete sign in. Please try again.',
      );
      status = AuthStatus.unauthenticated;
      return false;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  Future<void> signOut() async {
    AuthException? signOutError;
    try {
      await _authGateway.logout();
    } on Object {
      signOutError = const AuthException(
        kind: AuthErrorKind.server,
        message: 'The session was cleared on this device.',
      );
    }
    currentUser = null;
    error = signOutError;
    status = AuthStatus.unauthenticated;
    notifyListeners();
  }
}
