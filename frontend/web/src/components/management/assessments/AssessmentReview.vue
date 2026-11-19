
<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  submitAssessment,
  type Assessment,
  type AssessmentImport,
} from '../../../services/assessments'

const props = defineProps<{
  assessment: Assessment
  importResult: AssessmentImport
}>()

const emit = defineEmits<{
  back: []
  submitted: [assessment: Assessment]
}>()

const isSubmitting = ref(false)
const errorMessage = ref('')
const showConfirmation = ref(false)

const rows = computed(() => props.importResult.rows)

const validRows = computed(() =>
  rows.value.filter(row =>
    (row.validation_status === 'VALID' ||
      row.validation_status === 'MAPPED') &&
    row.is_mapped &&
    row.student_id !== null &&
    row.aggregate_marks !== null,
  ),
)

const unresolvedRows = computed(() =>
  rows.value.filter(row =>
    row.validation_status === 'ERROR' ||
    row.validation_status === 'WARNING' ||
    (row.validation_status === 'MAPPED' && !row.warning_acknowledged) ||
    !row.is_mapped ||
    row.student_id === null ||
    row.aggregate_marks === null,
  ),
)

const totalMarks = computed(() =>
  validRows.value.reduce(
    (total, row) => total + Number(row.aggregate_marks ?? 0),
    0,
  ),
)

const averageMarks = computed(() =>
  validRows.value.length > 0
    ? totalMarks.value / validRows.value.length
    : 0,
)

const isReady = computed(() =>
  rows.value.length > 0 &&
  unresolvedRows.value.length === 0 &&
  validRows.value.length === rows.value.length,
)

const formattedAverage = computed(() =>
  averageMarks.value.toFixed(2),
)

function requestConfirmation(): void {
  errorMessage.value = ''

  if (!isReady.value) {
    errorMessage.value =
      'Submission is blocked because unresolved or incomplete rows remain.'
    return
  }

  showConfirmation.value = true
}

function cancelConfirmation(): void {
  if (isSubmitting.value) return
  showConfirmation.value = false
}

async function confirmSubmission(): Promise<void> {
  if (!isReady.value || isSubmitting.value) return

  isSubmitting.value = true
  errorMessage.value = ''

  try {
    const submittedAssessment = await submitAssessment(props.assessment.id)

    showConfirmation.value = false
    emit('submitted', submittedAssessment)
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : 'Unable to submit the assessment. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="assessment-review">
    <header class="page-header">
      <div>
        <p class="eyebrow">Assessment workflow · Final review</p>
        <h2>Review &amp; Submission</h2>
        <p class="subtitle">
          Verify the imported student results before submitting this assessment.
        </p>
      </div>

      <button
        class="button button-secondary"
        type="button"
        @click="emit('back')"
      >
        Back to validation
      </button>
    </header>

    <nav class="workflow-steps" aria-label="Assessment workflow">
      <span class="step complete">1. Details</span>
      <span class="step complete">2. Scope</span>
      <span class="step complete">3. Import</span>
      <span class="step complete">4. Validation</span>
      <span class="step active">5. Review &amp; Submit</span>
    </nav>

    <section class="assessment-card">
      <div class="card-heading">
        <div>
          <p class="eyebrow">Assessment details</p>
          <h3>{{ assessment.name }}</h3>
        </div>
        <span class="draft-pill">Draft</span>
      </div>

      <div class="details-grid">
        <div>
          <span>Assessment type</span>
          <strong>{{ assessment.assessment_type }}</strong>
        </div>
        <div>
          <span>Sequence</span>
          <strong>{{ assessment.sequence_no }}</strong>
        </div>
        <div>
          <span>Maximum marks</span>
          <strong>{{ assessment.maximum_marks }}</strong>
        </div>
        <div>
          <span>Assessment date</span>
          <strong>{{ assessment.assessment_date || 'Not specified' }}</strong>
        </div>
        <div>
          <span>Import reference</span>
          <strong>{{ importResult.id }}</strong>
        </div>
        <div>
          <span>Import status</span>
          <strong>{{ importResult.status }}</strong>
        </div>
      </div>
    </section>

    <section class="summary-grid">
      <article class="summary-card">
        <span>Total imported rows</span>
        <strong>{{ rows.length }}</strong>
      </article>
      <article class="summary-card">
        <span>Ready student results</span>
        <strong class="success-text">{{ validRows.length }}</strong>
      </article>
      <article class="summary-card">
        <span>Unresolved rows</span>
        <strong :class="unresolvedRows.length ? 'error-text' : 'success-text'">
          {{ unresolvedRows.length }}
        </strong>
      </article>
      <article class="summary-card">
        <span>Average marks</span>
        <strong>{{ formattedAverage }}</strong>
      </article>
    </section>

    <section class="review-section">
      <div class="section-heading">
        <div>
          <h3>Student results review</h3>
          <p>
            Review the aggregate marks and student mapping for every imported row.
          </p>
        </div>
        <span class="row-count">{{ validRows.length }} ready</span>
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Row</th>
              <th>Student Business ID</th>
              <th>Aggregate marks</th>
              <th>Maximum marks</th>
              <th>Mapping</th>
              <th>Validation</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>{{ row.row_number }}</td>
              <td>{{ row.student_business_id || '—' }}</td>
              <td>{{ row.aggregate_marks ?? '—' }}</td>
              <td>{{ assessment.maximum_marks }}</td>
              <td>
                <span :class="row.is_mapped ? 'success-text' : 'error-text'">
                  {{ row.is_mapped ? 'Mapped' : 'Not mapped' }}
                </span>
              </td>
              <td>
                <span
                  class="status-pill"
                  :class="`status-${row.validation_status.toLowerCase()}`"
                >
                  {{ row.validation_status }}
                </span>
                <p v-if="row.validation_message" class="row-message">
                  {{ row.validation_message }}
                </p>
                <small
                  v-if="row.warning_acknowledged"
                  class="acknowledged-text"
                >
                  Warning acknowledged
                </small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="total-summary">
        <span>Total aggregate marks across ready results</span>
        <strong>{{ totalMarks.toFixed(2) }}</strong>
      </div>
    </section>

    <div
      v-if="errorMessage"
      class="message message-error"
      role="alert"
    >
      {{ errorMessage }}
    </div>

    <section
      class="readiness-panel"
      :class="isReady ? 'readiness-ready' : 'readiness-blocked'"
    >
      <div>
        <strong>
          {{ isReady ? 'Assessment ready for submission' : 'Submission is blocked' }}
        </strong>
        <p v-if="isReady">
          All imported rows have complete marks, student mappings and resolved
          validation statuses.
        </p>
        <p v-else>
          Return to Validation &amp; Correction and resolve all outstanding
          rows before submitting.
        </p>
      </div>

      <span class="readiness-count">
        {{ unresolvedRows.length }} unresolved
      </span>
    </section>

    <footer class="page-footer">
      <div>
        <strong>Submission is irreversible</strong>
        <p>
          Once submitted, the assessment and its results become immutable.
        </p>
      </div>

      <button
        class="button button-primary"
        type="button"
        :disabled="!isReady || isSubmitting"
        @click="requestConfirmation"
      >
        Review and submit
      </button>
    </footer>

    <div
      v-if="showConfirmation"
      class="modal-backdrop"
      role="presentation"
      @click.self="cancelConfirmation"
    >
      <section
        class="confirmation-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-description"
      >
        <div class="confirmation-icon">!</div>

        <h3 id="confirmation-title">Confirm assessment submission</h3>

        <p id="confirmation-description">
          You are about to submit
          <strong>{{ assessment.name }}</strong>
          with {{ validRows.length }} student results.
        </p>

        <p class="irreversible-warning">
          This action cannot be undone. The assessment and submitted results
          will become immutable.
        </p>

        <div class="modal-actions">
          <button
            class="button button-secondary"
            type="button"
            :disabled="isSubmitting"
            @click="cancelConfirmation"
          >
            Cancel
          </button>

          <button
            class="button button-primary"
            type="button"
            :disabled="isSubmitting"
            @click="confirmSubmission"
          >
            {{ isSubmitting ? 'Submitting…' : 'Confirm submission' }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.assessment-review {
  display: flex;
  flex-direction: column;
  gap: 22px;
  color: var(--text-primary, #18352d);
}

.page-header,
.card-heading,
.section-heading,
.page-footer,
.total-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header h2 {
  margin: 4px 0;
  font-size: 25px;
}

.eyebrow {
  margin: 0;
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

.assessment-card,
.summary-card,
.review-section {
  padding: 17px;
  border: 1px solid var(--border-color, #dce5df);
  border-radius: 11px;
  background: var(--surface-card, #fff);
}

.card-heading h3,
.section-heading h3 {
  margin: 4px 0;
  font-size: 17px;
}

.draft-pill,
.status-pill {
  padding: 5px 10px;
  border-radius: 20px;
  background: #fff3dc;
  color: #94600e;
  font-size: 11px;
  font-weight: 600;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  margin-top: 20px;
}

.details-grid > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.details-grid span,
.summary-card span {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.details-grid strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.summary-card strong {
  font-size: 24px;
}

.success-text {
  color: #23623d;
}

.error-text {
  color: #b33a36;
}

.section-heading {
  margin-bottom: 15px;
}

.row-count {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  text-align: left;
}

th,
td {
  padding: 11px 10px;
  border-bottom: 1px solid var(--border-color, #e1e8e3);
  vertical-align: top;
}

th {
  background: var(--surface-muted, #f1f4f1);
  color: var(--text-secondary, #687b73);
  font-weight: 600;
  white-space: nowrap;
}

td {
  overflow-wrap: anywhere;
}

.row-message {
  margin: 5px 0 0;
  color: #a72f2b;
}

.acknowledged-text {
  display: block;
  margin-top: 5px;
  color: #23623d;
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

.total-summary {
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color, #dce5df);
  font-size: 13px;
}

.total-summary strong {
  font-size: 17px;
}

.readiness-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  padding: 15px;
  border-radius: 9px;
  font-size: 13px;
}

.readiness-panel p {
  margin: 5px 0 0;
}

.readiness-ready {
  background: #eaf5ed;
  color: #23623d;
}

.readiness-blocked {
  background: #fff3dc;
  color: #805819;
}

.readiness-count {
  white-space: nowrap;
  font-weight: 600;
}

.page-footer {
  padding-top: 17px;
  border-top: 1px solid var(--border-color, #dce5df);
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
  color: #fff;
}

.button-secondary {
  border-color: var(--border-color, #ccd8d0);
  background: var(--surface-card, #fff);
  color: inherit;
}

.message-error {
  padding: 12px 14px;
  border-radius: 8px;
  background: #fff0ee;
  color: #a72f2b;
  font-size: 13px;
}

.modal-backdrop {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgb(12 28 22 / 55%);
}

.confirmation-modal {
  width: min(100%, 460px);
  padding: 25px;
  border-radius: 13px;
  background: var(--surface-card, #fff);
  color: var(--text-primary, #18352d);
  box-shadow: 0 20px 60px rgb(0 0 0 / 22%);
}

.confirmation-modal h3 {
  margin: 14px 0 9px;
  font-size: 19px;
}

.confirmation-modal p {
  font-size: 13px;
  line-height: 1.6;
}

.confirmation-icon {
  display: grid;
  width: 35px;
  height: 35px;
  place-items: center;
  border-radius: 50%;
  background: #fff3dc;
  color: #94600e;
  font-size: 20px;
  font-weight: 700;
}

.irreversible-warning {
  padding: 11px;
  border-radius: 7px;
  background: #fff0ee;
  color: #a72f2b;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

@media (max-width: 760px) {
  .details-grid,
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-header,
  .page-footer,
  .readiness-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .page-footer .button {
    width: 100%;
  }

  .modal-actions {
    flex-direction: column-reverse;
  }

  .modal-actions .button {
    width: 100%;
  }
}
</style>
