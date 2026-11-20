import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage.dart';
import '../domain/auth_models.dart';

abstract interface class AuthGateway {
  Future<CurrentUser?> restoreSession();
  Future<void> login(String email, String password);
  Future<CurrentUser> currentUser();
  Future<void> clearSession();
  Future<void> logout();
}

class AuthService implements AuthGateway {
  AuthService({required this._apiClient, required this._secureStorage});

  final ApiClient _apiClient;
  final SecureStorage _secureStorage;

  @override
  Future<CurrentUser?> restoreSession() async {
    final token = await _secureStorage.getSessionToken();
    if (token == null || token.isEmpty) {
      return null;
    }

    _apiClient.setToken(token);
    try {
      return await currentUser();
    } on AuthException catch (error) {
      if (error.statusCode == 401) {
        await _clearLocalSession();
      }
      rethrow;
    }
  }

  @override
  Future<void> login(String email, String password) async {
    try {
      final response = await _apiClient.post(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      final result = LoginResponse.fromJson(
        response.data as Map<String, dynamic>,
      );
      await _secureStorage.saveSessionToken(result.sessionToken);
      _apiClient.setToken(result.sessionToken);
    } on DioException catch (error) {
      throw _mapDioError(error, loginRequest: true);
    } on TypeError {
      throw const AuthException(
        kind: AuthErrorKind.server,
        message: 'The authentication service returned an unexpected response.',
      );
    }
  }

  @override
  Future<CurrentUser> currentUser() async {
    try {
      final response = await _apiClient.get('/auth/me');
      return CurrentUser.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (error) {
      if (error.response?.statusCode == 401) {
        await _clearLocalSession();
      }
      throw _mapDioError(error);
    } on TypeError {
      throw const AuthException(
        kind: AuthErrorKind.server,
        message:
            'The session validation service returned an unexpected response.',
      );
    }
  }

  @override
  Future<void> clearSession() => _clearLocalSession();

  @override
  Future<void> logout() async {
    try {
      await _apiClient.post('/auth/logout');
    } on DioException {
      // Local credentials must still be removed when the server is unreachable.
    } finally {
      await _clearLocalSession();
    }
  }

  Future<void> _clearLocalSession() async {
    _apiClient.clearToken();
    await _secureStorage.clearSessionToken();
  }

  AuthException _mapDioError(DioException error, {bool loginRequest = false}) {
    final statusCode = error.response?.statusCode;
    if (statusCode == 401) {
      return AuthException(
        kind: loginRequest
            ? AuthErrorKind.invalidCredentials
            : AuthErrorKind.expiredSession,
        message: loginRequest
            ? 'Invalid email or password.'
            : 'Your session is invalid or has expired.',
        statusCode: statusCode,
      );
    }
    if (statusCode == 403) {
      final detail = error.response?.data is Map<String, dynamic>
          ? (error.response!.data as Map<String, dynamic>)['detail']
          : null;
      final inactive = loginRequest && detail == 'User account is not active.';
      return AuthException(
        kind: inactive
            ? AuthErrorKind.inactiveAccount
            : AuthErrorKind.forbidden,
        message: inactive
            ? 'User account is not active.'
            : 'You are not authorised to continue.',
        statusCode: statusCode,
      );
    }
    if (statusCode == 422) {
      return AuthException(
        kind: AuthErrorKind.invalidRequest,
        message: 'Please check the information entered and try again.',
        statusCode: statusCode,
      );
    }
    if (statusCode != null && statusCode >= 500) {
      return AuthException(
        kind: AuthErrorKind.server,
        message: 'The authentication service is temporarily unavailable.',
        statusCode: statusCode,
      );
    }
    if (error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout) {
      return const AuthException(
        kind: AuthErrorKind.network,
        message: 'Unable to reach the authentication service.',
      );
    }
    return AuthException(
      kind: AuthErrorKind.server,
      message: 'The authentication service returned an unexpected error.',
      statusCode: statusCode,
    );
  }
}
