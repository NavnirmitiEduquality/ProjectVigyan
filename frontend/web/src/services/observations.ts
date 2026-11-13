
import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export interface ObservationRecord {
  id: string
  school_id: string
  class_division_id: string | null
  topic: string | null
  observed_at: string | null
  report_status: string
}

export interface InspectionRecord {
  id: string
  school_id: string
  class_division_id: string | null
  topic: string | null
  inspected_at: string | null
  report_status: string
}

async function listRecords<T>(endpoint: string): Promise<T[]> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}${endpoint}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    })
  } catch {
    throw new Error('Unable to reach the observations service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view these records.')
  }

  if (!response.ok) {
    throw new Error('Unable to load operational records.')
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('The service returned an invalid response.')
  }

  return data as T[]
}

export const listObservations = () =>
  listRecords<ObservationRecord>('/observations')

export const listInspections = () =>
  listRecords<InspectionRecord>('/inspections')
