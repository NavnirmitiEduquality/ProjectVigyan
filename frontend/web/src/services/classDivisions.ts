import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export interface ClassDivision {
  id: string
  school_id: string
  class_level: 5 | 6 | 7
  division: string
  status: 'ACTIVE' | 'INACTIVE'
  data_origin: string
}

export interface ClassDivisionCreateInput {
  school_id: string
  class_level: 5 | 6 | 7
  division: string
  status: 'ACTIVE' | 'INACTIVE'
}

export interface ClassDivisionUpdateInput {
  division?: string
  status?: 'ACTIVE' | 'INACTIVE'
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getSessionToken()
  if (!token) throw new Error('Your session is missing. Please sign in again.')
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json', 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new Error('Unable to reach the class divisions service.')
  }
  if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
  if (response.status === 403) throw new Error('You do not have permission to access this class resource.')
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Unable to complete the request (HTTP ${response.status}).`)
  }
  try {
    return await response.json() as T
  } catch {
    throw new Error('The class divisions service returned an invalid response.')
  }
}

export const listClassDivisions = (schoolId?: string) =>
  request<ClassDivision[]>(`/class-divisions${schoolId ? `?school_id=${encodeURIComponent(schoolId)}` : ''}`)
export const getClassDivision = (id: string) => request<ClassDivision>(`/class-divisions/${id}`)
export const createClassDivision = (input: ClassDivisionCreateInput) =>
  request<ClassDivision>('/class-divisions', { method: 'POST', body: JSON.stringify(input) })
export const updateClassDivision = (id: string, input: ClassDivisionUpdateInput) =>
  request<ClassDivision>(`/class-divisions/${id}`, { method: 'PATCH', body: JSON.stringify(input) })
