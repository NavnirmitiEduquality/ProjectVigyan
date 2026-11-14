import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export type StudentStatus = 'ACTIVE' | 'INACTIVE'

export interface Student {
  id: string
  student_code: string
  full_name: string
  gender: string
  roll_no: number
  class_division_id: string
  status: StudentStatus
  data_origin: string
}

export interface StudentCreateInput {
  student_code: string
  full_name: string
  gender: string
  roll_no: number
  class_division_id: string
  status: StudentStatus
}

export interface StudentUpdateInput {
  full_name?: string
  gender?: string
  roll_no?: number
  status?: StudentStatus
}

export interface StudentFilters {
  school_id?: string
  class_division_id?: string
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
    throw new Error('Unable to reach the students service.')
  }

  if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
  if (response.status === 403) throw new Error('You do not have permission to access this student resource.')
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Unable to complete the request (HTTP ${response.status}).`)
  }

  try {
    return await response.json() as T
  } catch {
    throw new Error('The students service returned an invalid response.')
  }
}

export const listStudents = (filters: StudentFilters = {}) => {
  const params = new URLSearchParams()
  if (filters.school_id) params.set('school_id', filters.school_id)
  if (filters.class_division_id) params.set('class_division_id', filters.class_division_id)
  const query = params.toString()
  return request<Student[]>(`/students${query ? `?${query}` : ''}`)
}

export const getStudent = (id: string) => request<Student>(`/students/${id}`)
export const createStudent = (input: StudentCreateInput) =>
  request<Student>('/students', { method: 'POST', body: JSON.stringify(input) })
export const updateStudent = (id: string, input: StudentUpdateInput) =>
  request<Student>(`/students/${id}`, { method: 'PATCH', body: JSON.stringify(input) })
