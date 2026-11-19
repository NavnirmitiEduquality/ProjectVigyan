
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  listAssessmentResults,
  type Assessment,
  type AssessmentResult,
} from '../../../services/assessments'

const props = defineProps<{
  assessment: Assessment
}>()

const emit = defineEmits<{
  backToDirectory: []
}>()

const results = ref<AssessmentResult[]>([])
const loading = ref(true)
const error = ref('')

const averageMarks = computed(() => {
  if (!results.value.length) return 0

  return results.value.reduce(
    (total, result) => total + Number(result.aggregate_marks),
    0,
  ) / results.value.length
})

const averagePercentage = computed(() => {
  if (props.assessment.maximum_marks <= 0) return 0

  return (averageMarks.value / props.assessment.maximum_marks) * 100
})

function formatMarks(value: number): string {
  return Number(value).toFixed(2).replace(/\.?0+$/, '')
}

function percentage(value: number): string {
  if (props.assessment.maximum_marks <= 0) return '—'

  return `${(
    (Number(value) / props.assessment.maximum_marks) * 100
  ).toFixed(1)}%`
}

async function loadResults(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    results.value = await listAssessmentResults(props.assessment.id)
  } catch (err) {
    error.value =
      err instanceof Error
        ? err.message
        : 'Unable to load assessment results.'
  } finally {
    loading.value = false
  }
}

onMounted(loadResults)
</script>

<template>
  <section class="assessment-ledger">
    <nav class="workflow-steps" aria-label="Assessment workflow">
      <span class="step complete">1. Details</span>
      <span class="step complete">2. Scope</span>
      <span class="step complete">3. Import</span>
      <span class="step complete">4. Validation</span>
      <span class="step complete">5. Review</span>
      <span class="step complete">6. Confirmation</span>
      <span class="step active">7. Results Ledger</span>
    </nav>

    <header class="page-header">
      <div>
        <p class="eyebrow">Assessment records · Read only</p>
        <h2>Results Ledger</h2>
        <p class="description">
          Persisted student results for {{ assessment.name }}.
          Submitted records cannot be edited.
        </p>
      </div>

      <span class="status-pill">{{ assessment.status }}</span>
    </header>

    <section class="assessment-details">
      <div>
        <span>Assessment</span>
        <strong>{{ assessment.name }}</strong>
      </div>
      <div>
        <span>Type</span>
        <strong>{{ assessment.assessment_type }}</strong>
      </div>
      <div>
        <span>Sequence</span>
        <strong>{{ assessment.sequence_no }}</strong>
      </div>
      <div>
        <span>Maximum marks</span>
        <strong>{{ formatMarks(assessment.maximum_marks) }}</strong>
      </div>
      <div>
        <span>Assessment date</span>
        <strong>{{ assessment.assessment_date || 'Not specified' }}</strong>
      </div>
    </section>

    <section class="summary-grid" aria-label="Results summary">
      <article class="summary-card">
        <span>Students with results</span>
        <strong>{{ results.length }}</strong>
      </article>
      <article class="summary-card">
        <span>Average marks</span>
        <strong>{{ formatMarks(averageMarks) }}</strong>
        <small>Out of {{ formatMarks(assessment.maximum_marks) }}</small>
      </article>
      <article class="summary-card">
        <span>Average percentage</span>
        <strong>{{ averagePercentage.toFixed(1) }}%</strong>
      </article>
    </section>

    <section class="ledger-panel">
      <div class="ledger-heading">
        <div>
          <h3>Student results</h3>
          <p>Final submitted aggregate marks</p>
        </div>

        <button
          class="button button-secondary"
          type="button"
          :disabled="loading"
          @click="loadResults"
        >
          Refresh
        </button>
      </div>

      <div v-if="loading" class="state-message" role="status">
        Loading submitted results…
      </div>

      <div v-else-if="error" class="state-message error-message" role="alert">
        <p>{{ error }}</p>
        <button class="button button-secondary" type="button" @click="loadResults">
          Retry
        </button>
      </div>

      <div v-else-if="results.length === 0" class="state-message">
        No result records were returned for this assessment.
      </div>

      <div v-else class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Student Business ID</th>
              <th scope="col">Aggregate Marks</th>
              <th scope="col">Maximum Marks</th>
              <th scope="col">Percentage</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(result, index) in results" :key="result.id">
              <td>{{ index + 1 }}</td>
              <td class="business-id">{{ result.student_business_id }}</td>
              <td>{{ formatMarks(result.aggregate_marks) }}</td>
              <td>{{ formatMarks(assessment.maximum_marks) }}</td>
              <td>{{ percentage(result.aggregate_marks) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <footer class="page-actions">
      <p>
        <strong>Read-only record:</strong>
        These results reflect the submitted assessment data.
      </p>

      <button
        class="button button-primary"
        type="button"
        @click="emit('backToDirectory')"
      >
        Back to Assessment Directory
      </button>
    </footer>
  </section>
</template>

<style scoped>
.assessment-ledger {
  display: flex;
  flex-direction: column;
  gap: 22px;
  color: var(--text-primary, #18352d);
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

.page-header,
.ledger-heading,
.page-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0 0 6px;
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.page-header h2 {
  margin: 0;
  font-size: 25px;
}

.description,
.ledger-heading p {
  margin: 6px 0 0;
  color: var(--text-secondary, #687b73);
  font-size: 13px;
  line-height: 1.5;
}

.status-pill {
  padding: 7px 13px;
  border-radius: 20px;
  background: #e5f2e9;
  color: #23623d;
  font-size: 12px;
  font-weight: 700;
}

.assessment-details,
.summary-card,
.ledger-panel {
  border: 1px solid var(--border-color, #dce5df);
  border-radius: 12px;
  background: var(--surface-card, #fff);
}

.assessment-details {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 18px;
  padding: 20px;
}

.assessment-details > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.assessment-details span,
.summary-card span {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.assessment-details strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 18px;
}

.summary-card strong {
  font-size: 25px;
}

.summary-card small {
  color: var(--text-secondary, #687b73);
  font-size: 11px;
}

.ledger-panel {
  overflow: hidden;
}

.ledger-heading {
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color, #dce5df);
}

.ledger-heading h3 {
  margin: 0;
  font-size: 17px;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

th,
td {
  padding: 13px 16px;
  border-bottom: 1px solid var(--border-color, #e5ebe7);
  white-space: nowrap;
}

th {
  background: var(--surface-muted, #f1f4f1);
  color: var(--text-secondary, #52675e);
  font-size: 11px;
  font-weight: 700;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.business-id {
  font-weight: 600;
}

.state-message {
  padding: 30px 20px;
  color: var(--text-secondary, #687b73);
  text-align: center;
  font-size: 13px;
}

.error-message {
  color: #a33232;
}

.page-actions {
  flex-wrap: wrap;
}

.page-actions p {
  margin: 0;
  color: var(--text-secondary, #687b73);
  font-size: 12px;
  line-height: 1.5;
}

.button {
  min-height: 38px;
  padding: 8px 14px;
  border: 1px solid transparent;
  border-radius: 7px;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
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

@media (max-width: 900px) {
  .assessment-details {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .assessment-details {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .page-header,
  .page-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .ledger-heading {
    align-items: flex-start;
  }
}
</style>
