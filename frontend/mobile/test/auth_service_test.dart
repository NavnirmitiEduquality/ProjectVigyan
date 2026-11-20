import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigyan_field/core/network/api_client.dart';
import 'package:vigyan_field/core/storage/secure_storage.dart';
import 'package:vigyan_field/features/auth/data/auth_service.dart';
import 'package:vigyan_field/features/auth/domain/auth_models.dart';
import 'package:vigyan_field/features/auth/presentation/auth_controller.dart';

class _FakeStorage extends SecureStorage {
  _FakeStorage({this.token}) : super();

  String? token;
  bool cleared = false;

  @override
  Future<void> saveSessionToken(String value) async => token = value;

  @override
  Future<String?> getSessionToken() async => token;

  @override
  Future<void> clearSessionToken() async {
    cleared = true;
    token = null;
  }
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super();

  Object? postData;
  Object? getData;
  DioException? postError;
  DioException? getError;
  String? token;
  bool tokenCleared = false;

  @override
  void setToken(String value) => token = value;

  @override
  void clearToken() {
    tokenCleared = true;
    token = null;
  }

  @override
  Future<Response<dynamic>> post(String path, {Object? data}) async {
    if (postError != null) {
      throw postError!;
    }
    return Response(
      requestOptions: RequestOptions(path: path),
      data: postData,
    );
  }

  @override
  Future<Response<dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    if (getError != null) {
      throw getError!;
    }
    return Response(
      requestOptions: RequestOptions(path: path),
      data: getData,
    );
  }
}

class _FakeGateway implements AuthGateway {
  bool clearSessionCalled = false;
  bool logoutThrows = false;

  @override
  Future<CurrentUser?> restoreSession() async => null;

  @override
  Future<void> login(String email, String password) async {}

  @override
  Future<CurrentUser> currentUser() async {
    throw const AuthException(
      kind: AuthErrorKind.network,
      message: 'Network failure.',
    );
  }

  @override
  Future<void> clearSession() async => clearSessionCalled = true;

  @override
  Future<void> logout() async {
    if (logoutThrows) {
      throw StateError('logout failed');
    }
  }
}

Response<dynamic> _response(Object data, int statusCode) {
  return Response(
    requestOptions: RequestOptions(path: '/auth'),
    data: data,
    statusCode: statusCode,
  );
}

DioException _httpError(int statusCode, {Object? data}) {
  return DioException(
    requestOptions: RequestOptions(path: '/auth'),
    response: _response(data ?? <String, dynamic>{}, statusCode),
    type: DioExceptionType.badResponse,
  );
}

CurrentUser _user() {
  return const CurrentUser(
    userId: 'user-id',
    userCode: 'PT001',
    fullName: 'Test User',
    email: 'test@example.com',
    status: 'ACTIVE',
    permissions: [],
  );
}

AuthService _service(_FakeApiClient api, _FakeStorage storage) {
  return AuthService(apiClient: api, secureStorage: storage);
}

void main() {
  test('persists the token after successful login', () async {
    final api = _FakeApiClient()
      ..postData = <String, dynamic>{
        'message': 'Login successful.',
        'user_id': 'user-id',
        'user_code': 'PT001',
        'full_name': 'Test User',
        'session_token': 'session-token',
      };
    final storage = _FakeStorage();

    await _service(api, storage).login('test@example.com', 'password');

    expect(storage.token, 'session-token');
    expect(api.token, 'session-token');
  });

  test('restores a valid session', () async {
    final api = _FakeApiClient()..getData = _userJson();
    final storage = _FakeStorage(token: 'session-token');

    final user = await _service(api, storage).restoreSession();

    expect(user?.userId, 'user-id');
    expect(api.token, 'session-token');
    expect(storage.cleared, isFalse);
  });

  test('clears the token when restoration receives 401', () async {
    final api = _FakeApiClient()..getError = _httpError(401);
    final storage = _FakeStorage(token: 'expired-token');

    await expectLater(
      _service(api, storage).restoreSession(),
      throwsA(
        isA<AuthException>().having(
          (error) => error.kind,
          'kind',
          AuthErrorKind.expiredSession,
        ),
      ),
    );

    expect(storage.cleared, isTrue);
    expect(api.tokenCleared, isTrue);
  });

  test('preserves the token on restoration network failure', () async {
    final api = _FakeApiClient()
      ..getError = DioException(
        requestOptions: RequestOptions(path: '/auth/me'),
        type: DioExceptionType.connectionError,
      );
    final storage = _FakeStorage(token: 'session-token');

    await expectLater(
      _service(api, storage).restoreSession(),
      throwsA(isA<AuthException>()),
    );

    expect(storage.token, 'session-token');
    expect(storage.cleared, isFalse);
  });

  test('preserves the token on restoration server failure', () async {
    final api = _FakeApiClient()..getError = _httpError(503);
    final storage = _FakeStorage(token: 'session-token');

    await expectLater(
      _service(api, storage).restoreSession(),
      throwsA(isA<AuthException>()),
    );

    expect(storage.token, 'session-token');
    expect(storage.cleared, isFalse);
  });

  test('logout clears local storage when the API fails', () async {
    final api = _FakeApiClient()..postError = _httpError(503);
    final storage = _FakeStorage(token: 'session-token');

    await _service(api, storage).logout();

    expect(storage.cleared, isTrue);
    expect(api.tokenCleared, isTrue);
  });

  test(
    'only the backend inactive-account detail maps login 403 to inactive',
    () async {
      final inactiveApi = _FakeApiClient()
        ..postError = _httpError(
          403,
          data: <String, dynamic>{'detail': 'User account is not active.'},
        );
      final inactiveError = await _loginError(
        _service(inactiveApi, _FakeStorage()),
      );
      expect(inactiveError.kind, AuthErrorKind.inactiveAccount);

      final forbiddenApi = _FakeApiClient()
        ..postError = _httpError(
          403,
          data: <String, dynamic>{'detail': 'Access denied.'},
        );
      final forbiddenError = await _loginError(
        _service(forbiddenApi, _FakeStorage()),
      );
      expect(forbiddenError.kind, AuthErrorKind.forbidden);
    },
  );

  test('clears a session when login succeeds but current-user fails', () async {
    final gateway = _FakeGateway();
    final controller = AuthController(gateway);

    expect(await controller.signIn('test@example.com', 'password'), isFalse);
    expect(gateway.clearSessionCalled, isTrue);
    expect(controller.status, AuthStatus.unauthenticated);
  });

  test(
    'sign-out clears controller state after an unexpected gateway error',
    () async {
      final gateway = _FakeGateway()..logoutThrows = true;
      final controller = AuthController(gateway)
        ..currentUser = _user()
        ..status = AuthStatus.authenticated;

      await controller.signOut();

      expect(controller.currentUser, isNull);
      expect(controller.status, AuthStatus.unauthenticated);
    },
  );
}

Map<String, dynamic> _userJson() => <String, dynamic>{
  'user_id': 'user-id',
  'user_code': 'PT001',
  'full_name': 'Test User',
  'email': 'test@example.com',
  'status': 'ACTIVE',
  'permissions': <String>[],
};

Future<AuthException> _loginError(AuthService service) async {
  try {
    await service.login('test@example.com', 'password');
  } on AuthException catch (error) {
    return error;
  }
  throw StateError('Expected login to fail.');
}
