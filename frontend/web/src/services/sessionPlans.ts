import { getSessionToken } from './auth'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export interface SessionPlanWeek {
  id: string
  para_teacher_id: string
  week_start_date: string
  week_end_date: string
  data_origin: string
  created_at: string
  updated_at: string
}

export interface SessionPlanItem {
  id: string
  session_plan_week_id: string
  class_division_id: string
  planned_date: string
  planned_start_time: string | null
  planned_end_time: string | null
  sequence_no: number
  data_origin: string
  created_at: string
  updated_at: string
}

export interface SessionPlanContent {
  id: string
  session_plan_item_id: string
  content: string
  data_origin: string
  created_at: string
  updated_at: string
}

export interface SessionPlanWeekDetail {
  week: SessionPlanWeek
  items: SessionPlanItem[]
}

export interface SessionPlanTeachingSession {
  id: string
  session_plan_item_id: string | null
  class_division_id: string
  para_teacher_id: string
  session_date: string
  planned_start_time: string | null
  planned_end_time: string | null
  actual_start_time: string | null
  actual_end_time: string | null
  duration_minutes: number | null
  status: string
  remarks: string | null
  feedback_submitted: boolean
  submitted_at: string | null
  data_origin: string
}

export interface SessionPlanCreateWeekInput {
  week_start_date: string
}

export interface SessionPlanCreateItemInput {
  session_plan_week_id: string
  class_division_id: string
  planned_date: string
  sequence_no: number
  planned_start_time?: string
  planned_end_time?: string
}

export interface SessionPlanUpdateItemInput {
  class_division_id?: string
  planned_date?: string
  sequence_no?: number
  planned_start_time?: string
  planned_end_time?: string
}

export interface SessionPlanContentInput {
  content: string
}

export interface SessionPlanAttachment {
  id: string
  session_plan_content_id: string
  original_filename: string
  content_type: string
  file_size_bytes: number
  data_origin: string
  created_at: string
  updated_at: string
}

export class SessionPlanServiceError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'SessionPlanServiceError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getSessionToken()
  if (!token) {
    throw new SessionPlanServiceError('Your session is missing. Please sign in again.')
  }

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
    throw new SessionPlanServiceError('Unable to reach the session-planning service.')
  }

  if (response.status === 401) {
    throw new SessionPlanServiceError('Your session has expired. Please sign in again.', 401)
  }
  if (response.status === 403) {
    throw new SessionPlanServiceError('You do not have permission to access session planning.', 403)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string | { message?: string } } | null
    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail?.message
    throw new SessionPlanServiceError(
      detail || `Unable to complete the request (HTTP ${response.status}).`,
      response.status,
    )
  }

  if (response.status === 204) return undefined as T
  try {
    return await response.json() as T
  } catch {
    throw new SessionPlanServiceError('The session-planning service returned an invalid response.')
  }
}

export const getWeek = (weekStartDate: string, paraTeacherId?: string) => {
  const query = paraTeacherId
    ? `?${new URLSearchParams({ para_teacher_id: paraTeacherId }).toString()}`
    : ''

  return request<SessionPlanWeekDetail>(
    `/session-plans/weeks/${weekStartDate}${query}`,
  )
}

export const createWeek = (input: SessionPlanCreateWeekInput) =>
  request<SessionPlanWeek>('/session-plans/weeks', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const createItem = (input: SessionPlanCreateItemInput) =>
  request<SessionPlanItem>('/session-plans/items', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const updateItem = (id: string, input: SessionPlanUpdateItemInput) =>
  request<SessionPlanItem>(`/session-plans/items/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })

export const deleteItem = (id: string) =>
  request<void>(`/session-plans/items/${id}`, { method: 'DELETE' })

export async function getContent(id: string): Promise<SessionPlanContent | null> {
  try {
    return await request<SessionPlanContent>(`/session-plans/items/${id}/content`)
  } catch (error) {
    if (error instanceof SessionPlanServiceError && error.status === 404) return null
    throw error
  }
}

export const saveContent = (id: string, input: SessionPlanContentInput) =>
  request<SessionPlanContent>(`/session-plans/items/${id}/content`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })

export const validateItem = (id: string) =>
  request<SessionPlanItem>(`/session-plans/items/${id}/validate`, { method: 'POST' })

export const createTeachingSession = (id: string) =>
  request<SessionPlanTeachingSession>(`/session-plans/items/${id}/teaching-session`, {
    method: 'POST',
  })

export const listAttachments = (itemId: string) =>
  request<SessionPlanAttachment[]>(
    `/session-plans/items/${itemId}/attachments`,
  )

export async function uploadAttachment(
  itemId: string,
  file: File,
): Promise<SessionPlanAttachment> {
  const token = getSessionToken()

  if (!token) {
    throw new SessionPlanServiceError(
      'Your session is missing. Please sign in again.',
    )
  }

  const formData = new FormData()
  formData.append('attachment', file)

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/session-plans/items/${itemId}/attachments`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
        },
        body: formData,
      },
    )
  } catch {
    throw new SessionPlanServiceError(
      'Unable to reach the session-planning service.',
    )
  }

  if (response.status === 401) {
    throw new SessionPlanServiceError(
      'Your session has expired. Please sign in again.',
      401,
    )
  }

  if (response.status === 403) {
    throw new SessionPlanServiceError(
      'You do not have permission to upload attachments.',
      403,
    )
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string | { message?: string } } | null

    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail?.message

    throw new SessionPlanServiceError(
      detail || `Unable to upload attachment (HTTP ${response.status}).`,
      response.status,
    )
  }

  try {
    return await response.json() as SessionPlanAttachment
  } catch {
    throw new SessionPlanServiceError(
      'The session-planning service returned an invalid attachment response.',
    )
  }
}

export async function downloadAttachment(
  itemId: string,
  attachmentId: string,
): Promise<Blob> {
  const token = getSessionToken()

  if (!token) {
    throw new SessionPlanServiceError(
      'Your session is missing. Please sign in again.',
    )
  }

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/session-plans/items/${itemId}/attachments/${attachmentId}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    )
  } catch {
    throw new SessionPlanServiceError(
      'Unable to reach the session-planning service.',
    )
  }

  if (response.status === 401) {
    throw new SessionPlanServiceError(
      'Your session has expired. Please sign in again.',
      401,
    )
  }

  if (response.status === 403) {
    throw new SessionPlanServiceError(
      'You do not have permission to download this attachment.',
      403,
    )
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string | { message?: string } } | null

    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail?.message

    throw new SessionPlanServiceError(
      detail || `Unable to download attachment (HTTP ${response.status}).`,
      response.status,
    )
  }

  return response.blob()
}

export const deleteAttachment = (
  itemId: string,
  attachmentId: string,
) =>
  request<void>(
    `/session-plans/items/${itemId}/attachments/${attachmentId}`,
    { method: 'DELETE' },
  )
