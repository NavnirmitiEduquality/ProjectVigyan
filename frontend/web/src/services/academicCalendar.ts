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

export interface AcademicHoliday {
  id: string
  academic_year_id: string
  holiday_date: string
  name: string
  type: string
  description: string | null
  is_active: boolean
}

export interface CalendarSession {
  session_plan_item_id: string
  para_teacher_id: string
  class_division_id: string
  planned_start_time: string | null
  planned_end_time: string | null
  sequence_no: number
  teaching_session_id: string | null
  teaching_session_status: string | null
  derived_status: 'PLANNED' | 'COMPLETED' | 'RESCHEDULE_REQUIRED'
}

export interface CalendarDay {
  calendar_date: string
  is_working_day: boolean
  is_holiday: boolean
  holiday_name: string | null
  holiday_type: string | null
  sessions: CalendarSession[]
}

export interface CalendarQuery {
  startDate: string
  endDate: string
  paraTeacherId?: string
}

export async function getCalendar(
  query: CalendarQuery,
): Promise<CalendarDay[]> {
  const params = new URLSearchParams({
    start_date: query.startDate,
    end_date: query.endDate,
  })

  if (query.paraTeacherId) {
    params.set('para_teacher_id', query.paraTeacherId)
  }

  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/academic-calendar?${params.toString()}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
        },
      },
    )
  } catch {
    throw new Error('Unable to reach the academic-calendar service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view this calendar.')
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string } | null

    throw new Error(
      body?.detail || 'Unable to load the academic calendar.',
    )
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error(
      'The academic-calendar service returned an invalid response.',
    )
  }

  return data as CalendarDay[]
}

export async function listHolidays(): Promise<AcademicHoliday[]> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/academic-calendar/holidays?active_only=true`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
        },
      },
    )
  } catch {
    throw new Error('Unable to reach the academic-calendar service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view holidays.')
  }

  if (!response.ok) {
    throw new Error('Unable to load academic holidays.')
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('The academic-calendar service returned an invalid response.')
  }

  return data as AcademicHoliday[]
}


export interface CreateAcademicHolidayPayload {
  holiday_date: string
  name: string
  type: string
  description: string | null
}

export interface UpdateAcademicHolidayPayload {
  holiday_date?: string
  name?: string
  type?: string
  description?: string | null
  is_active?: boolean
}

async function holidayRequest<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  payload?: CreateAcademicHolidayPayload | UpdateAcademicHolidayPayload,
): Promise<T> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        ...(payload ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    })
  } catch {
    throw new Error('Unable to reach the academic-calendar service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to manage holidays.')
  }

  if (response.status === 409) {
    throw new Error('A holiday already exists for this date.')
  }

  if (response.status === 404) {
    throw new Error('The holiday could not be found.')
  }

  if (response.status === 422) {
    const body = await response.json().catch(() => null) as
      { detail?: string } | null
    throw new Error(body?.detail || 'The holiday details are invalid.')
  }

  if (!response.ok) {
    throw new Error('Unable to save the holiday. Please try again.')
  }

  return await response.json() as T
}

export function createHoliday(
  payload: CreateAcademicHolidayPayload,
): Promise<AcademicHoliday> {
  return holidayRequest<AcademicHoliday>(
    '/academic-calendar/holidays',
    'POST',
    payload,
  )
}

export function updateHoliday(
  holidayId: string,
  payload: UpdateAcademicHolidayPayload,
): Promise<AcademicHoliday> {
  return holidayRequest<AcademicHoliday>(
    `/academic-calendar/holidays/${encodeURIComponent(holidayId)}`,
    'PATCH',
    payload,
  )
}

export function deactivateHoliday(
  holidayId: string,
): Promise<AcademicHoliday> {
  return holidayRequest<AcademicHoliday>(
    `/academic-calendar/holidays/${encodeURIComponent(holidayId)}`,
    'DELETE',
  )
}
