import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export interface ReportingFilters {
  academicYearId: string
  startDate?: string
  endDate?: string
  schoolId?: string
  classDivisionId?: string
  paraTeacherId?: string
}

export type ReportingGroup =
  | 'project'
  | 'school'
  | 'class_division'
  | 'para_teacher'

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
  para_teacher_id?: string
  para_teacher_code?: string
  para_teacher_name?: string
  school_id?: string
  school_code?: string
  school_name?: string
  class_division_id?: string
  class_level?: number
  division?: string
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

export interface TlmReportItem {
  eligible_sessions: number
  sessions_with_tlm: number
  explicit_na_sessions: number
  missing_tlm_sessions: number
  distinct_tlms_used: number
  sessions_with_tlm_evidence: number
  usage_coverage_percentage: number
  recording_completeness_percentage: number
}

export interface ClassMonitoringItem {
  status: 'ACTIVE' | 'INACTIVE'
  active_students: number
  evidence: {
    eligible_completed_sessions: number
    sessions_with_evidence: number
    completeness_percentage: number | null
  }
}

interface ClassMonitoringResponse {
  items: ClassMonitoringItem[]
}

interface ReportResponse<T> {
  group_by: string
  items: T[]
}

async function getReport<T>(
  endpoint: string,
  filters: ReportingFilters,
  groupBy: ReportingGroup = 'project',
): Promise<ReportResponse<T>> {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  const params = new URLSearchParams({
    group_by: groupBy,
    academic_year_id: filters.academicYearId,
  })

  if (filters.startDate) params.set('start_date', filters.startDate)
  if (filters.endDate) params.set('end_date', filters.endDate)
  if (filters.schoolId) params.set('school_id', filters.schoolId)
  if (filters.classDivisionId) {
    params.set('class_division_id', filters.classDivisionId)
  }
  if (filters.paraTeacherId) {
    params.set('para_teacher_id', filters.paraTeacherId)
  }

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

export const getDeliveryReport = (
  filters: ReportingFilters,
  groupBy: ReportingGroup = 'project',
) => getReport<DeliveryReportItem>('delivery', filters, groupBy)

export const getAttendanceReport = (
  filters: ReportingFilters,
) => {
  const attendanceFilters: ReportingFilters = {
    academicYearId: filters.academicYearId,
    startDate: filters.startDate,
    endDate: filters.endDate,
    schoolId: filters.schoolId,
    classDivisionId: filters.classDivisionId,
  }

  return getReport<AttendanceReportItem>(
    'attendance',
    attendanceFilters,
  )
}

export const getEngagementReport = (
  filters: ReportingFilters,
  groupBy: ReportingGroup = 'project',
) => getReport<EngagementReportItem>('engagement', filters, groupBy)

export const getDeliveryTrend = (
  filters: ReportingFilters,
  groupBy: ReportingGroup = 'project',
) => getReport<DeliveryTrendItem>('trends/delivery', filters, groupBy)

export const getTlmReport = (
  filters: ReportingFilters,
  groupBy: ReportingGroup = 'project',
) => getReport<TlmReportItem>('tlm', filters, groupBy)

export const getClassesReport = async (
  filters: ReportingFilters,
): Promise<ClassMonitoringResponse> => {
  const token = getSessionToken()

  if (!token) {
    throw new Error('Your session is missing. Please sign in again.')
  }

  const params = new URLSearchParams({
    academic_year_id: filters.academicYearId,
  })

  if (filters.startDate) params.set('start_date', filters.startDate)
  if (filters.endDate) params.set('end_date', filters.endDate)
  if (filters.schoolId) params.set('school_id', filters.schoolId)
  if (filters.classDivisionId) {
    params.set('class_division_id', filters.classDivisionId)
  }

  let response: Response

  try {
    response = await fetch(
      `${apiBaseUrl}/reporting/classes?${params.toString()}`,
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
      `Unable to load class monitoring data (HTTP ${response.status}).`,
    )
  }

  const data: unknown = await response.json()

  if (
    typeof data !== 'object' ||
    data === null ||
    !('items' in data) ||
    !Array.isArray(data.items)
  ) {
    throw new Error(
      'The class monitoring service returned an invalid response.',
    )
  }

  return data as ClassMonitoringResponse
}

export interface ClassAssessmentRecord {
  assessment_id: string
  academic_year_id: string
  assessment_type: 'BASELINE' | 'MIDLINE' | 'ENDLINE'
  sequence_no: number
  name: string
  assessment_date: string
  maximum_marks: number
  status: string
  result_scope: string
  result_count: number
  average_marks: number | null
  average_percentage: number | null
  assessment_import_scope: string
  assessment_import_class_divisions: Array<{
    class_division_id: string
    class_level: number
    division: string
  }>
}

export interface ClassLongitudinalAssessment {
  baseline_assessment_id: string
  endline_assessment_id: string
  matched_students: number
  average_baseline_percentage: number | null
  average_endline_percentage: number | null
  average_percentage_point_change: number | null
  result_scope: string
  results: Array<{
    student_id: string
    baseline_percentage: number
    endline_percentage: number
    percentage_point_change: number
  }>
}

export interface ClassMonitoringItem {
  class_division_id: string
  school_id: string
  school_code: string
  school_name: string
  class_level: number
  division: string
  status: 'ACTIVE' | 'INACTIVE'
  active_students: number
  para_teachers: number

  evidence: {
    eligible_completed_sessions: number
    sessions_with_evidence: number
    completeness_percentage: number | null
  }

  delivery: DeliveryReportItem | null

  attendance: AttendanceReportItem | null

  assessment: {
    latest: ClassAssessmentRecord | null
    baseline: ClassAssessmentRecord | null
    endline: ClassAssessmentRecord | null
    longitudinal: ClassLongitudinalAssessment | null
  }
}
