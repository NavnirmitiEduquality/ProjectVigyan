class LoginResponse {
  const LoginResponse({
    required this.message,
    required this.userId,
    required this.userCode,
    required this.fullName,
    required this.sessionToken,
  });

  factory LoginResponse.fromJson(Map<String, dynamic> json) {
    return LoginResponse(
      message: json['message'] as String,
      userId: json['user_id'] as String,
      userCode: json['user_code'] as String,
      fullName: json['full_name'] as String,
      sessionToken: json['session_token'] as String,
    );
  }

  final String message;
  final String userId;
  final String userCode;
  final String fullName;
  final String sessionToken;
}

class CurrentUser {
  const CurrentUser({
    required this.userId,
    required this.userCode,
    required this.fullName,
    required this.email,
    required this.status,
    required this.permissions,
  });

  factory CurrentUser.fromJson(Map<String, dynamic> json) {
    return CurrentUser(
      userId: json['user_id'] as String,
      userCode: json['user_code'] as String,
      fullName: json['full_name'] as String,
      email: json['email'] as String,
      status: json['status'] as String,
      permissions: (json['permissions'] as List<dynamic>).cast<String>(),
    );
  }

  final String userId;
  final String userCode;
  final String fullName;
  final String email;
  final String status;
  final List<String> permissions;
}

enum AuthErrorKind {
  invalidCredentials,
  inactiveAccount,
  expiredSession,
  invalidRequest,
  forbidden,
  network,
  server,
}

class AuthException implements Exception {
  const AuthException({
    required this.kind,
    required this.message,
    this.statusCode,
  });

  final AuthErrorKind kind;
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}
