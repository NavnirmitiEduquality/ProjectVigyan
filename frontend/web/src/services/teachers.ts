import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export interface ParaTeacherRole {
  id: string
  role_id: string
  is_active: boolean
  role: { id: string; name: string; code: string; description: string | null }
}

export interface ParaTeacher {
  id: string
  user_code: string
  account_category: string
  full_name: string
  status: 'ACTIVE' | 'DISABLED'
  data_origin: string
  user_roles: ParaTeacherRole[]
}

export interface UserPagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

interface ParaTeacherPage {
  data: ParaTeacher[]
  pagination: UserPagination
}

export interface SchoolTeacher {
  id: string
  full_name: string
  school_id: string
  status: 'ACTIVE' | 'INACTIVE'
  subjects: string[]
}

export interface School {
  id: string
  school_name: string
}

export class TeacherServiceError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.status = status
    this.name = 'TeacherServiceError'
  }
}

async function request<T>(path: string): Promise<T> {
  const token = getSessionToken()
  if (!token) throw new TeacherServiceError('Your session is missing. Please sign in again.')

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    })
  } catch {
    throw new TeacherServiceError('Unable to reach the teachers service.')
  }

  if (response.status === 401) {
    throw new TeacherServiceError('Your session has expired. Please sign in again.', 401)
  }
  if (response.status === 403) {
    throw new TeacherServiceError('You do not have permission to access this teacher resource.', 403)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new TeacherServiceError(detail || `Unable to complete the request (HTTP ${response.status}).`, response.status)
  }

  try {
    return await response.json() as T
  } catch {
    throw new TeacherServiceError('The teachers service returned an invalid response.')
  }
}

export async function listParaTeachers(): Promise<ParaTeacher[]> {
  const pageSize = 100
  const first = await request<ParaTeacherPage>(
    `/users?page=1&page_size=${pageSize}&role_code=PARA_TEACHER`,
  )
  const pages = [first.data]
  for (let page = 2; page <= first.pagination.total_pages; page += 1) {
    const result = await request<ParaTeacherPage>(
      `/users?page=${page}&page_size=${pageSize}&role_code=PARA_TEACHER`,
    )
    pages.push(result.data)
  }
  return pages.flat().filter(teacher =>
    teacher.account_category === 'PARA_TEACHER' &&
    teacher.user_roles.some(role => role.is_active && role.role.code === 'PARA_TEACHER'),
  )
}

export const listSchoolTeachers = () => request<SchoolTeacher[]>('/school-teachers')
export const listTeacherSchools = () => request<School[]>('/schools')
