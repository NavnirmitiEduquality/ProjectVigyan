import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export type AccountCategory =
  | 'PLATFORM_OWNER'
  | 'SYSTEM_ADMIN'
  | 'DATA_MANAGER'
  | 'MANAGEMENT'
  | 'STEM_COORDINATOR'
  | 'PARA_TEACHER'

export type UserStatus = 'ACTIVE' | 'DISABLED'
export type DataOrigin = 'PRODUCTION' | 'DEMO' | 'TEST'
export type SortOrder = 'asc' | 'desc'
export type UserSortField =
  | 'created_at'
  | 'full_name'
  | 'user_code'
  | 'email'
  | 'status'
  | 'account_category'

export interface Role {
  id: string
  name: string
  code: string
  description: string | null
}

export interface UserRole {
  id: string
  role_id: string
  is_active: boolean
  role: Role
}

export interface User {
  id: string
  user_code: string
  account_category: AccountCategory
  full_name: string
  email: string
  status: UserStatus
  data_origin: DataOrigin
  email_verified_at: string | null
  last_login_at: string | null
  created_at: string
  updated_at: string
  user_roles: UserRole[]
}

export interface Pagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface UserListResponse {
  data: User[]
  pagination: Pagination
}

export interface UserFilters {
  page?: number
  page_size?: number
  search?: string
  status?: UserStatus
  role_code?: string
  data_origin?: DataOrigin
  sort_by?: UserSortField
  sort_order?: SortOrder
}

export interface UserCreateInput {
  full_name: string
  email: string
  initial_password: string
  account_category: AccountCategory
}

export interface UserProfileUpdateInput {
  full_name?: string
  email?: string
}

export interface UserStatusUpdateInput {
  status: UserStatus
}

export interface RoleAssignmentInput {
  role_id: string
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getSessionToken()
  if (!token) throw new Error('Your session is missing. Please sign in again.')

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...init.headers,
      },
    })
  } catch {
    throw new Error('Unable to reach the user management service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to perform this user management action.')
  }

  if (response.status === 204) {
    return undefined as T
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as {
      detail?: string | { code?: string; message?: string }
    } | null

    const detail = body?.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || detail?.code

    throw new Error(message || `Unable to complete the request (HTTP ${response.status}).`)
  }

  try {
    return await response.json() as T
  } catch {
    throw new Error('The user management service returned an invalid response.')
  }
}

export const listUsers = (filters: UserFilters = {}) => {
  const params = new URLSearchParams()

  if (filters.page !== undefined) params.set('page', String(filters.page))
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size))
  if (filters.search?.trim()) params.set('search', filters.search.trim())
  if (filters.status) params.set('status', filters.status)
  if (filters.role_code) params.set('role_code', filters.role_code)
  if (filters.data_origin) params.set('data_origin', filters.data_origin)
  if (filters.sort_by) params.set('sort_by', filters.sort_by)
  if (filters.sort_order) params.set('sort_order', filters.sort_order)

  const query = params.toString()
  return request<UserListResponse>(`/users${query ? `?${query}` : ''}`)
}

export const getUser = (id: string) =>
  request<User>(`/users/${encodeURIComponent(id)}`)

export const listRoles = () =>
  request<Role[]>('/users/roles')

export const createUser = (input: UserCreateInput) =>
  request<User>('/users', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const updateUser = (id: string, input: UserProfileUpdateInput) =>
  request<User>(`/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })

export const updateUserStatus = (id: string, input: UserStatusUpdateInput) =>
  request<User>(`/users/${encodeURIComponent(id)}/status`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })

export const assignUserRole = (id: string, input: RoleAssignmentInput) =>
  request<UserRole>(`/users/${encodeURIComponent(id)}/roles`, {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const removeUserRole = (userId: string, roleId: string) =>
  request<void>(
    `/users/${encodeURIComponent(userId)}/roles/${encodeURIComponent(roleId)}`,
    { method: 'DELETE' },
  )
