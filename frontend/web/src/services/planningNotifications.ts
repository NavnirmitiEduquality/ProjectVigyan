
import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export interface PlanningNotification {
  id: string
  notification_type: string
  para_teacher_id: string
  session_plan_item_id: string | null
  week_start_date: string | null
  message: string
  is_read: boolean
  created_at: string
}

export async function listPlanningNotifications(): Promise<PlanningNotification[]> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/notifications/planning`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    })
  } catch {
    throw new Error('Unable to reach the planning-notifications service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view planning notifications.')
  }

  if (!response.ok) {
    throw new Error('Unable to load planning notifications. Please try again later.')
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('The planning-notifications service returned an invalid response.')
  }

  return data as PlanningNotification[]
}
