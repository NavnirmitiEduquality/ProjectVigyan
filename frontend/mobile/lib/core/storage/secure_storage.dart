import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  SecureStorage() : _storage = const FlutterSecureStorage();

  static const String _sessionTokenKey = 'vigyan_session_token';

  final FlutterSecureStorage _storage;

  Future<void> saveSessionToken(String token) {
    return _storage.write(key: _sessionTokenKey, value: token);
  }

  Future<String?> getSessionToken() {
    return _storage.read(key: _sessionTokenKey);
  }

  Future<void> clearSessionToken() {
    return _storage.delete(key: _sessionTokenKey);
  }
}
