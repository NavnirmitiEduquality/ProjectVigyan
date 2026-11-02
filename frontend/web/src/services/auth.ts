export interface LoginResponse {
  message: string
  user_id: string
  user_code: string
  full_name: string
  session_token: string
}

export type AuthErrorKind = 'invalid-credentials' | 'inactive' | 'network' | 'server' | 'forbidden'

export interface AuthError extends Error {
  kind: AuthErrorKind
  status?: number
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')
const SESSION_STORAGE_KEY = 'vigyan_session_token'

let sessionToken: string | null = sessionStorage.getItem(SESSION_STORAGE_KEY)

function createAuthError(kind: AuthErrorKind, message: string, status?: number): AuthError {
  const error = new Error(message) as AuthError
  error.kind = kind
  error.status = status
  return error
}

export function getSessionToken() {
  return sessionToken
}

export function clearSession(): void {
  sessionToken = null
  sessionStorage.removeItem(SESSION_STORAGE_KEY)
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  } catch {
    throw createAuthError('network', 'Unable to reach the authentication service.')
  }

  if (response.ok) {
    const result = (await response.json()) as LoginResponse
    sessionToken = result.session_token
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionToken)
    return result
  }

  if (response.status === 401) {
    throw createAuthError('invalid-credentials', 'Invalid email or password.', response.status)
  }

  if (response.status === 403) {
    throw createAuthError('inactive', 'User account is not active.', response.status)
  }

  throw createAuthError('server', 'The authentication service returned an unexpected error.', response.status)
}

export async function logout(): Promise<void> {
  if (!sessionToken) {
    return
  }

  const token = sessionToken
  clearSession()

  try {
    await fetch(`${apiBaseUrl}/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    // The local session is already cleared; the server session will expire naturally.
  }
}
export interface CurrentUser {
  user_id: string
  user_code: string
  full_name: string
  email: string
  status: string
  permissions: string[]
}

export async function getMe(): Promise<CurrentUser> {
  if (!sessionToken) {
    throw createAuthError('invalid-credentials', 'No active session is available.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/auth/me`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${sessionToken}`,
      },
    })
  } catch {
    throw createAuthError('network', 'Unable to validate the current session.')
  }

  if (response.ok) {
    return (await response.json()) as CurrentUser
  }

  if (response.status === 401) {
    clearSession()
    throw createAuthError('invalid-credentials', 'Your session is invalid or has expired.', response.status)
  }

  if (response.status === 403) {
    throw createAuthError('forbidden', 'The current session could not be validated.', response.status)
  }

  throw createAuthError('server', 'The session validation service returned an unexpected error.', response.status)
}