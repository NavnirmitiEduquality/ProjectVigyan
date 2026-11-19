
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  acknowledgeAssessmentRowWarning,
  correctAssessmentRowBusinessId,
  mapAssessmentImportRow,
  updateAssessmentRowMarks,
  type Assessment,
  type AssessmentImport,
  type AssessmentImportRow,
} from '../../../services/assessments'
import {
  listStudents,
  type Student,
} from '../../../services/students'

const props = defineProps<{
  assessment: Assessment
  importResult: AssessmentImport
}>()

const emit = defineEmits<{
  cancel: []
  updated: [result: AssessmentImport]
  continue: [result: AssessmentImport]
}>()

const rows = ref<AssessmentImportRow[]>([])
const students = ref<Student[]>([])
const loadingStudents = ref(false)
const savingRow = ref<string | null>(null)
const pageError = ref('')
const successMessage = ref('')

const drafts = reactive<Record<string, {
  businessId: string
  marks: string
  studentId: string
}>>({})

function initialiseRows(result: AssessmentImport): void {
  rows.value = result.rows.map(row => ({ ...row }))

  for (const row of rows.value) {
    drafts[row.id] = {
      businessId: row.student_business_id ?? '',
      marks: row.aggregate_marks === null ? '' : String(row.aggregate_marks),
      studentId: row.student_id ?? '',
    }
  }
}

watch(
  () => props.importResult,
  result => initialiseRows(result),
  { immediate: true },
)

onMounted(loadStudents)

async function loadStudents(): Promise<void> {
  loadingStudents.value = true
  pageError.value = ''

  try {
    const result = await listStudents({
      school_id: props.assessment.school_id,
    })

    students.value = result.filter(student => student.status === 'ACTIVE')
  } catch (error) {
    pageError.value = error instanceof Error
      ? error.message
      : 'Unable to load students for mapping.'
  } finally {
    loadingStudents.value = false
  }
}

const validCount = computed(() =>
  rows.value.filter(row =>
    row.validation_status === 'VALID' ||
    row.validation_status === 'MAPPED',
  ).length,
)

const warningCount = computed(() =>
  rows.value.filter(row =>
    row.validation_status === 'WARNING' ||
    (row.validation_status === 'MAPPED' && !row.warning_acknowledged),
  ).length,
)

const errorCount = computed(() =>
  rows.value.filter(row => row.validation_status === 'ERROR').length,
)

const unresolvedCount = computed(() =>
  rows.value.filter(row =>
    row.validation_status === 'ERROR' ||
    row.validation_status === 'WARNING' ||
    (row.validation_status === 'MAPPED' && !row.warning_acknowledged),
  ).length,
)

const canContinue = computed(() =>
  rows.value.length > 0 && unresolvedCount.value === 0,
)

const orderedRows = computed(() =>
  [...rows.value].sort((a, b) => a.row_number - b.row_number),
)

function replaceRow(updatedRow: AssessmentImportRow): void {
  const index = rows.value.findIndex(row => row.id === updatedRow.id)

  if (index === -1) return

  rows.value[index] = { ...updatedRow }

  drafts[updatedRow.id] = {
    businessId: updatedRow.student_business_id ?? '',
    marks: updatedRow.aggregate_marks === null
      ? ''
      : String(updatedRow.aggregate_marks),
    studentId: updatedRow.student_id ?? '',
  }

  emitUpdated()
}

function emitUpdated(): void {
  const result: AssessmentImport = {
    ...props.importResult,
    rows: rows.value.map(row => ({ ...row })),
    total_rows: rows.value.length,
    warning_count: rows.value.filter(row =>
      (row.validation_status === 'WARNING' ||
        row.validation_status === 'MAPPED') &&
      !row.warning_acknowledged,
    ).length,
    error_count: rows.value.filter(row =>
      row.validation_status === 'ERROR',
    ).length,
  }

  emit('updated', result)
}

function selectedStudent(row: AssessmentImportRow): Student | undefined {
  const studentId = drafts[row.id]?.studentId
  return students.value.find(student => student.id === studentId)
}

async function saveBusinessId(row: AssessmentImportRow): Promise<void> {
  const draft = drafts[row.id]
  const businessId = draft?.businessId.trim()

  if (!businessId) {
    pageError.value = 'Enter a student Business ID before saving.'
    return
  }

  savingRow.value = row.id
  pageError.value = ''
  successMessage.value = ''

  try {
    const updated = await correctAssessmentRowBusinessId(row.id, businessId)
    replaceRow(updated)
    successMessage.value = `Business ID corrected for row ${row.row_number}.`
  } catch (error) {
    pageError.value = error instanceof Error
      ? error.message
      : 'Unable to correct the Business ID.'
  } finally {
    savingRow.value = null
  }
}

async function saveMarks(row: AssessmentImportRow): Promise<void> {
  const rawMarks = drafts[row.id]?.marks.trim()

  if (!rawMarks) {
    pageError.value = 'Enter aggregate marks before saving.'
    return
  }

  const marks = Number(rawMarks)

  if (!Number.isFinite(marks) || marks < 0) {
    pageError.value = 'Enter a valid non-negative marks value.'
    return
  }

  if (marks > Number(props.assessment.maximum_marks)) {
    pageError.value = `Marks cannot exceed ${props.assessment.maximum_marks}.`
    return
  }

  savingRow.value = row.id
  pageError.value = ''
  successMessage.value = ''

  try {
    const updated = await updateAssessmentRowMarks(row.id, {
      aggregate_marks: marks,
    })

    replaceRow(updated)
    successMessage.value = `Marks corrected for row ${row.row_number}.`
  } catch (error) {
    pageError.value = error instanceof Error
      ? error.message
      : 'Unable to update marks.'
  } finally {
    savingRow.value = null
  }
}

async function saveMapping(row: AssessmentImportRow): Promise<void> {
  const student = selectedStudent(row)

  if (!student) {
    pageError.value = 'Select a student before mapping this row.'
    return
  }

  savingRow.value = row.id
  pageError.value = ''
  successMessage.value = ''

  try {
    // The Business ID must match the selected student's record.
    let currentRow = row

    if (currentRow.student_business_id !== student.student_code) {
      currentRow = await correctAssessmentRowBusinessId(
        row.id,
        student.student_code,
      )
      replaceRow(currentRow)
    }

    const updated = await mapAssessmentImportRow(row.id, {
      student_id: student.id,
    })

    replaceRow(updated)
    successMessage.value = `Student mapped successfully for row ${row.row_number}.`
  } catch (error) {
    pageError.value = error instanceof Error
      ? error.message
      : 'Unable to map this student. Check the student, scope and marks.'
  } finally {
    savingRow.value = null
  }
}

async function acknowledgeWarning(row: AssessmentImportRow): Promise<void> {
  savingRow.value = row.id
  pageError.value = ''
  successMessage.value = ''

  try {
    const updated = await acknowledgeAssessmentRowWarning(row.id)
    replaceRow(updated)
    successMessage.value = `Warning acknowledged for row ${row.row_number}.`
  } catch (error) {
    pageError.value = error instanceof Error
      ? error.message
      : 'Unable to acknowledge this warning.'
  } finally {
    savingRow.value = null
  }
}

function statusLabel(status: AssessmentImportRow['validation_status']): string {
  const labels: Record<AssessmentImportRow['validation_status'], string> = {
    VALID: 'Valid',
    WARNING: 'Warning',
    ERROR: 'Error',
    MAPPED: 'Mapped',
  }

  return labels[status]
}

function statusClass(status: AssessmentImportRow['validation_status']): string {
  return `status-${status.toLowerCase()}`
}
</script>

<template>
  <section class="assessment-validation">
    <header class="page-header">
      <div>
        <p class="eyebrow">Assessment workflow · Step 5</p>
        <h2>Validation &amp; Correction</h2>
        <p class="subtitle">
          Review imported scores, correct errors and map unmatched students
          before submission.
        </p>
      </div>

      <button class="button button-secondary" type="button" @click="emit('cancel')">
        Back
      </button>
    </header>

    <nav class="workflow-steps" aria-label="Assessment workflow">
      <span class="step complete">1. Details</span>
      <span class="step complete">2. Scope</span>
      <span class="step complete">3. Import</span>
      <span class="step active">4. Validation</span>
      <span class="step">5. Review &amp; Submit</span>
    </nav>

    <div class="assessment-context">
      <div>
        <span class="context-label">Assessment</span>
        <strong>{{ assessment.name }}</strong>
      </div>
      <div>
        <span class="context-label">Maximum marks</span>
        <strong>{{ assessment.maximum_marks }}</strong>
      </div>
      <div>
        <span class="context-label">Imported rows</span>
        <strong>{{ rows.length }}</strong>
      </div>
    </div>

    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">Valid / mapped</span>
        <strong class="summary-value">{{ validCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Warnings</span>
        <strong class="summary-value warning-text">{{ warningCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Errors</span>
        <strong class="summary-value error-text">{{ errorCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Unresolved</span>
        <strong class="summary-value">{{ unresolvedCount }}</strong>
      </article>
    </div>

    <div v-if="pageError" class="message message-error" role="alert">
      {{ pageError }}
    </div>

    <div v-if="successMessage" class="message message-success" role="status">
      {{ successMessage }}
    </div>

    <div v-if="loadingStudents" class="loading-message">
      Loading active students for this school…
    </div>

    <div class="section-heading">
      <div>
        <h3>Imported student rows</h3>
        <p>Correct each row and save it before moving to the next step.</p>
      </div>
      <span class="row-count">{{ rows.length }} rows</span>
    </div>

    <div v-if="rows.length === 0" class="empty-state">
      No import rows are available. Return to the import step and upload a CSV.
    </div>

    <div v-else class="rows-list">
      <article
        v-for="row in orderedRows"
        :key="row.id"
        class="row-card"
      >
        <header class="row-header">
          <div class="row-heading">
            <strong>Row {{ row.row_number }}</strong>
            <span class="status-pill" :class="statusClass(row.validation_status)">
              {{ statusLabel(row.validation_status) }}
            </span>
          </div>

          <span v-if="row.warning_acknowledged" class="acknowledged-label">
            Warning acknowledged
          </span>
        </header>

        <p v-if="row.validation_message" class="validation-message">
          {{ row.validation_message }}
        </p>

        <div class="row-details">
          <div class="field">
            <label :for="`business-${row.id}`">Student Business ID</label>
            <input
              :id="`business-${row.id}`"
              v-model="drafts[row.id].businessId"
              type="text"
              autocomplete="off"
              placeholder="Enter Business ID"
            />
            <button
              class="button button-small button-secondary"
              type="button"
              :disabled="savingRow === row.id"
              @click="saveBusinessId(row)"
            >
              Save Business ID
            </button>
          </div>

          <div class="field">
            <label :for="`marks-${row.id}`">
              Aggregate marks (maximum {{ assessment.maximum_marks }})
            </label>
            <input
              :id="`marks-${row.id}`"
              v-model="drafts[row.id].marks"
              type="number"
              min="0"
              :max="Number(assessment.maximum_marks)"
              step="any"
              placeholder="Enter marks"
            />
            <button
              class="button button-small button-secondary"
              type="button"
              :disabled="savingRow === row.id"
              @click="saveMarks(row)"
            >
              Save marks
            </button>
          </div>
        </div>

        <div class="mapping-panel">
          <div class="field mapping-field">
            <label :for="`student-${row.id}`">Map to production student</label>
            <select
              :id="`student-${row.id}`"
              v-model="drafts[row.id].studentId"
              :disabled="loadingStudents || students.length === 0"
            >
              <option value="">Select a student</option>
              <option
                v-for="student in students"
                :key="student.id"
                :value="student.id"
              >
                {{ student.student_code }} — {{ student.full_name }}
                (Class {{ student.roll_no }})
              </option>
            </select>
          </div>

          <button
            class="button button-small button-primary"
            type="button"
            :disabled="savingRow === row.id || loadingStudents || !drafts[row.id].studentId"
            @click="saveMapping(row)"
          >
            {{ savingRow === row.id ? 'Saving…' : 'Map student' }}
          </button>
        </div>

        <footer
          v-if="row.validation_status === 'WARNING' && !row.warning_acknowledged"
          class="row-actions"
        >
          <span class="action-hint">
            Acknowledge only after reviewing the warning.
          </span>
          <button
            class="button button-small button-secondary"
            type="button"
            :disabled="savingRow === row.id"
            @click="acknowledgeWarning(row)"
          >
            Acknowledge warning
          </button>
        </footer>

        <div v-if="savingRow === row.id" class="saving-indicator">
          Saving changes…
        </div>
      </article>
    </div>

    <div class="reconciliation-note">
      <strong>Missing-student reconciliation</strong>
      <p>
        Students missing from the uploaded file appear as blocking error rows.
        Resolve these rows by supplying the correct Business ID, marks and
        student mapping. They cannot be ignored during submission.
      </p>
    </div>

    <footer class="page-footer">
      <div>
        <strong v-if="canContinue" class="ready-text">
          All imported rows are resolved.
        </strong>
        <strong v-else class="pending-text">
          {{ unresolvedCount }} row(s) still require attention.
        </strong>
        <p>Validation must be complete before review and submission.</p>
      </div>

      <button
        class="button button-primary"
        type="button"
        :disabled="!canContinue"
        @click="emit('continue', {
          ...importResult,
          rows: rows.map(row => ({ ...row })),
          total_rows: rows.length,
          warning_count: warningCount,
          error_count: errorCount,
        })"
      >
        Continue to Review
      </button>
    </footer>
  </section>
</template>

<style scoped>
.assessment-validation {
  display: flex;
  flex-direction: column;
  gap: 22px;
  color: var(--text-primary, #18352d);
}

.page-header,
.section-heading,
.page-footer,
.row-header,
.row-heading,
.row-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header h2 {
  margin: 4px 0;
  font-size: 25px;
}

.eyebrow,
.context-label,
.summary-label {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.subtitle,
.section-heading p,
.page-footer p {
  margin: 5px 0 0;
  color: var(--text-secondary, #687b73);
  font-size: 13px;
}

.workflow-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.step {
  padding: 9px 13px;
  border-radius: 8px;
  background: var(--surface-muted, #f1f4f1);
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.step.complete {
  background: #e5f2e9;
  color: #23623d;
}

.step.active {
  background: #173e32;
  color: #fff;
}

.assessment-context,
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.assessment-context > div,
.summary-card {
  padding: 15px;
  border: 1px solid var(--border-color, #dce5df);
  border-radius: 10px;
  background: var(--surface-card, #fff);
}

.assessment-context > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-value {
  font-size: 25px;
}

.warning-text {
  color: #a66b16;
}

.error-text {
  color: #b33a36;
}

.message {
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 13px;
}

.message-error {
  background: #fff0ee;
  color: #a72f2b;
}

.message-success {
  background: #eaf5ed;
  color: #23623d;
}

.section-heading h3 {
  margin: 0;
  font-size: 17px;
}

.row-count {
  color: var(--text-secondary, #687b73);
  font-size: 13px;
}

.rows-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row-card {
  padding: 17px;
  border: 1px solid var(--border-color, #dce5df);
  border-radius: 12px;
  background: var(--surface-card, #fff);
}

.row-heading {
  justify-content: flex-start;
}

.status-pill {
  padding: 4px 9px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}

.status-valid,
.status-mapped {
  background: #e5f2e9;
  color: #23623d;
}

.status-warning {
  background: #fff3dc;
  color: #94600e;
}

.status-error {
  background: #ffebe9;
  color: #a72f2b;
}

.acknowledged-label,
.ready-text {
  color: #23623d;
  font-size: 12px;
}

.validation-message {
  margin: 12px 0;
  color: #a72f2b;
  font-size: 13px;
}

.row-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
}

.field label {
  font-size: 12px;
  font-weight: 600;
}

.field input,
.field select {
  box-sizing: border-box;
  width: 100%;
  min-height: 39px;
  padding: 8px 10px;
  border: 1px solid var(--border-color, #ccd8d0);
  border-radius: 7px;
  background: var(--surface-card, #fff);
  color: inherit;
  font: inherit;
  font-size: 13px;
}

.mapping-panel {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 17px;
  padding-top: 15px;
  border-top: 1px solid var(--border-color, #e1e8e3);
}

.mapping-field {
  flex: 1;
}

.row-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-top: 13px;
}

.action-hint {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.saving-indicator {
  margin-top: 10px;
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.reconciliation-note {
  padding: 15px;
  border-left: 4px solid #bd8a37;
  border-radius: 7px;
  background: #fbf7ed;
  color: #60491f;
  font-size: 13px;
}

.reconciliation-note p {
  margin: 6px 0 0;
}

.page-footer {
  padding-top: 17px;
  border-top: 1px solid var(--border-color, #dce5df);
}

.pending-text {
  color: #a66b16;
  font-size: 13px;
}

.button {
  min-height: 38px;
  padding: 8px 14px;
  border: 1px solid transparent;
  border-radius: 7px;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.button-primary {
  background: #173e32;
  color: white;
}

.button-secondary {
  border-color: var(--border-color, #ccd8d0);
  background: var(--surface-card, #fff);
  color: inherit;
}

.button-small {
  min-height: 32px;
  padding: 6px 10px;
  font-size: 12px;
}

.empty-state,
.loading-message {
  padding: 24px;
  border: 1px dashed var(--border-color, #ccd8d0);
  border-radius: 10px;
  color: var(--text-secondary, #687b73);
  text-align: center;
}

@media (max-width: 760px) {
  .assessment-context,
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .row-details {
    grid-template-columns: 1fr;
  }

  .mapping-panel,
  .page-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .page-header {
    align-items: flex-start;
  }

  .page-footer .button {
    width: 100%;
  }
}
</style>
