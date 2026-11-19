
import { getSessionToken } from './auth'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/+$/, '')

export type AssessmentType = 'BASELINE' | 'MIDLINE' | 'ENDLINE'
export type AssessmentStatus = 'DRAFT' | 'SUBMITTED'

export interface Assessment {
  id: string
  academic_year_id: string
  school_id: string
  assessment_type: AssessmentType
  sequence_no: number
  name: string
  assessment_date: string | null
  maximum_marks: number
  status: AssessmentStatus
}

export interface AssessmentCreateInput {
  academic_year_id: string
  school_id: string
  assessment_type: AssessmentType
  sequence_no?: number
  name?: string
  assessment_date?: string
  maximum_marks: number
}

export interface AssessmentScopeInput {
  class_division_ids: string[]
}

export type AssessmentValidationStatus =
  | 'VALID'
  | 'WARNING'
  | 'ERROR'
  | 'MAPPED'

export interface AssessmentImportRow {
  id: string
  row_number: number
  student_business_id: string | null
  source_class: string | null
  source_division: string | null
  aggregate_marks: number | null
  student_id: string | null
  validation_status: AssessmentValidationStatus
  validation_message: string | null
  is_mapped: boolean
  warning_acknowledged: boolean
}

export interface AssessmentImport {
  id: string
  assessment_id: string
  status: 'DRAFT' | 'VALIDATED' | 'SUBMITTED'
  total_rows: number
  warning_count: number
  error_count: number
  rows: AssessmentImportRow[]
}

export interface AssessmentWorkflow {
  class_division_ids: string[]
  latest_import: AssessmentImport | null
}

export interface AssessmentRowMappingInput {
  student_id: string
  acknowledge_warning?: boolean
}

export interface AssessmentRowMarksInput {
  aggregate_marks: number
}

export class AssessmentServiceError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'AssessmentServiceError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getSessionToken()

  if (!token) {
    throw new AssessmentServiceError(
      'Your session is missing. Please sign in again.',
    )
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
    throw new AssessmentServiceError(
      'Unable to reach the assessment service.',
    )
  }

  if (response.status === 401) {
    throw new AssessmentServiceError(
      'Your session has expired. Please sign in again.',
      401,
    )
  }

  if (response.status === 403) {
    throw new AssessmentServiceError(
      'You do not have permission to perform this assessment action.',
      403,
    )
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string | { message?: string } } | null

    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail?.message

    throw new AssessmentServiceError(
      detail || `Unable to complete the request (HTTP ${response.status}).`,
      response.status,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  try {
    return await response.json() as T
  } catch {
    throw new AssessmentServiceError(
      'The assessment service returned an invalid response.',
    )
  }
}

async function uploadFile<T>(
  path: string,
  file: File,
): Promise<T> {
  const token = getSessionToken()

  if (!token) {
    throw new AssessmentServiceError(
      'Your session is missing. Please sign in again.',
    )
  }

  const formData = new FormData()
  formData.append('file', file)

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
      body: formData,
    })
  } catch {
    throw new AssessmentServiceError(
      'Unable to reach the assessment service.',
    )
  }

  if (response.status === 401) {
    throw new AssessmentServiceError(
      'Your session has expired. Please sign in again.',
      401,
    )
  }

  if (response.status === 403) {
    throw new AssessmentServiceError(
      'You do not have permission to import assessment results.',
      403,
    )
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as
      { detail?: string | { message?: string } } | null

    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail?.message

    throw new AssessmentServiceError(
      detail || `Unable to upload the CSV (HTTP ${response.status}).`,
      response.status,
    )
  }

  try {
    return await response.json() as T
  } catch {
    throw new AssessmentServiceError(
      'The assessment service returned an invalid import response.',
    )
  }
}

export const listAssessments = (schoolId?: string) => {
  const query = schoolId
    ? `?${new URLSearchParams({ school_id: schoolId }).toString()}`
    : ''

  return request<Assessment[]>(`/assessments${query}`)
}

export const getAssessment = (assessmentId: string) =>
  request<Assessment>(`/assessments/${assessmentId}`)

export const getAssessmentWorkflow = (assessmentId: string) =>
  request<AssessmentWorkflow>(
    `/assessments/${assessmentId}/workflow`,
  )

export const createAssessment = (input: AssessmentCreateInput) =>
  request<Assessment>('/assessments', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const setAssessmentScope = (
  assessmentId: string,
  input: AssessmentScopeInput,
) =>
  request<Assessment>(`/assessments/${assessmentId}/scope`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })

export const importAssessmentCsv = (
  assessmentId: string,
  file: File,
) =>
  uploadFile<AssessmentImport>(
    `/assessments/${assessmentId}/imports/csv`,
    file,
  )

export const mapAssessmentImportRow = (
  rowId: string,
  input: AssessmentRowMappingInput,
) =>
  request<AssessmentImportRow>(
    `/assessments/imports/rows/${rowId}/mapping`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )

export const correctAssessmentRowBusinessId = (
  rowId: string,
  studentBusinessId: string,
) =>
  request<AssessmentImportRow>(
    `/assessments/imports/rows/${rowId}/business-id`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        student_business_id: studentBusinessId,
      }),
    },
  )

export const acknowledgeAssessmentRowWarning = (rowId: string) =>
  request<AssessmentImportRow>(
    `/assessments/imports/rows/${rowId}/acknowledge`,
    {
      method: 'PATCH',
    },
  )

export const updateAssessmentRowMarks = (
  rowId: string,
  input: AssessmentRowMarksInput,
) =>
  request<AssessmentImportRow>(
    `/assessments/imports/rows/${rowId}/marks`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )


export interface AssessmentResult {
  id: string
  assessment_id: string
  student_id: string
  student_business_id: string
  aggregate_marks: number
}

export const submitAssessment = (assessmentId: string) =>
  request<Assessment>(`/assessments/${assessmentId}/submit`, {
    method: 'POST',
  })

export const listAssessmentResults = (assessmentId: string) =>
  request<AssessmentResult[]>(
    `/assessments/${assessmentId}/results`,
  )
