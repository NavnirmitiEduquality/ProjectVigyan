import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export interface DeliveryReportItem {
  total_sessions: number
  planned_sessions: number
  upcoming_sessions: number
  in_progress_sessions: number
  completed_sessions: number
  cancelled_sessions: number
  completed_duration_minutes: number
  teaching_hours: number
  completed_sessions_with_duration: number
  average_completed_duration_minutes: number | null
  completion_percentage: number | null
}

export interface AttendanceReportItem {
  eligible_record_count: number
  present_record_count: number
  absent_record_count: number
  attendance_percentage: number
}

export interface EngagementReportItem {
  session_count: number
  scored_session_count: number
  missing_engagement_count: number
  average_engagement: number | null
  distribution: Record<string, number>
}

export interface DeliveryTrendItem {
  month: string
  session_count: number
  completed_sessions: number
  completed_duration_minutes: number
}

interface ReportResponse<T> {
  group_by: string
  items: T[]
}

async function getReport<T>(
  endpoint: string,
  academicYearId: string,
): Promise<ReportResponse<T>> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  const params = new URLSearchParams({
    group_by: 'project',
    academic_year_id: academicYearId,
  })

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/reporting/${endpoint}?${params.toString()}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
        },
      },
    )
  } catch {
    throw new Error('Unable to reach the reporting service.')
  }

  if (response.status === 401) {
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (response.status === 403) {
    throw new Error('You do not have permission to view reporting data.')
  }

  if (!response.ok) {
    throw new Error(
      `Unable to load the ${endpoint.replaceAll('/', ' ')} report (HTTP ${response.status}).`,
    )
  }

  const data: unknown = await response.json()

  if (
    typeof data !== 'object' ||
    data === null ||
    !('items' in data) ||
    !Array.isArray(data.items)
  ) {
    throw new Error('The reporting service returned an invalid response.')
  }

  return data as ReportResponse<T>
}

export async function getDeliveryReport(
  academicYearId: string,
): Promise<ReportResponse<DeliveryReportItem>> {
  return getReport<DeliveryReportItem>('delivery', academicYearId)
}

export async function getAttendanceReport(
  academicYearId: string,
): Promise<ReportResponse<AttendanceReportItem>> {
  return getReport<AttendanceReportItem>('attendance', academicYearId)
}

export async function getEngagementReport(
  academicYearId: string,
): Promise<ReportResponse<EngagementReportItem>> {
  return getReport<EngagementReportItem>('engagement', academicYearId)
}

export async function getDeliveryTrend(
  academicYearId: string,
): Promise<ReportResponse<DeliveryTrendItem>> {
  return getReport<DeliveryTrendItem>('trends/delivery', academicYearId)
}
