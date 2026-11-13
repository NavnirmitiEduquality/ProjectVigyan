import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export type SchoolStatus = 'ACTIVE' | 'INACTIVE'

export interface School {
  id: string
  school_code: string
  school_name: string
  status: SchoolStatus
  data_origin: string
}

export interface SchoolCreateInput {
  school_code: string
  school_name: string
  status: SchoolStatus
}

export interface SchoolUpdateInput {
  school_name?: string
  status?: SchoolStatus
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
    throw new Error('Unable to reach the schools service.')
  }
  if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
  if (response.status === 403) throw new Error('You do not have permission to access this school resource.')
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Unable to complete the request (HTTP ${response.status}).`)
  }
  try {
    return await response.json() as T
  } catch {
    throw new Error('The schools service returned an invalid response.')
  }
}

export const listSchools = () => request<School[]>('/schools')
export const getSchool = (id: string) => request<School>(`/schools/${id}`)
export const createSchool = (input: SchoolCreateInput) =>
  request<School>('/schools', { method: 'POST', body: JSON.stringify(input) })
export const updateSchool = (id: string, input: SchoolUpdateInput) =>
  request<School>(`/schools/${id}`, { method: 'PATCH', body: JSON.stringify(input) })
