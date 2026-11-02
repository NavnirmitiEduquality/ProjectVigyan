import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export interface AcademicYear {
  id: string
  name: string
  start_date: string
  end_date: string
  is_active: boolean
}

export async function listAcademicYears(): Promise<AcademicYear[]> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/academic-calendar/years`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    })
  } catch {
    throw new Error('Unable to reach the academic-calendar service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view academic years.')
  }

  if (!response.ok) {
    throw new Error('Unable to load academic years. Please try again later.')
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('The academic-calendar service returned an invalid response.')
  }

  return data as AcademicYear[]
}

export interface CreateAcademicYearPayload {
  name: string
  start_date: string
  end_date: string
  is_active: boolean
}

export async function createAcademicYear(
  payload: CreateAcademicYearPayload,
): Promise<AcademicYear> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/academic-calendar/years`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new Error('Unable to reach the academic-calendar service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to create academic years.')
  }

  if (response.status === 409) {
    throw new Error('An academic year with this name already exists.')
  }

  if (response.status === 422) {
    throw new Error('The academic-year details are invalid. Check the name and date range.')
  }

  if (!response.ok) {
    throw new Error('Unable to create the academic year. Please try again later.')
  }

  const data: unknown = await response.json()

  if (
    typeof data !== 'object' ||
    data === null ||
    !('id' in data) ||
    !('name' in data) ||
    !('start_date' in data) ||
    !('end_date' in data) ||
    !('is_active' in data)
  ) {
    throw new Error('The academic-calendar service returned an invalid response.')
  }

  return data as AcademicYear
}
