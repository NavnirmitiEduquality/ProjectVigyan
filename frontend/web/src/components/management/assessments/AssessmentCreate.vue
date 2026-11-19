
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { AcademicYear } from '../../../services/academicCalendar'
import { listAcademicYears } from '../../../services/academicCalendar'
import type { School } from '../../../services/schools'
import { listSchools } from '../../../services/schools'
import {
  createAssessment,
  type Assessment,
  type AssessmentCreateInput,
  type AssessmentType,
} from '../../../services/assessments'

const emit = defineEmits<{
  cancel: []
  created: [assessment: Assessment]
}>()

const academicYears = ref<AcademicYear[]>([])
const schools = ref<School[]>([])

const loadingOptions = ref(true)
const saving = ref(false)
const error = ref('')
const optionsError = ref('')

const academicYearId = ref('')
const schoolId = ref('')
const assessmentType = ref<AssessmentType>('BASELINE')
const sequenceNo = ref(1)
const assessmentName = ref('')
const assessmentDate = ref('')
const maximumMarks = ref('100')

const isMidline = computed(() => assessmentType.value === 'MIDLINE')

const canSubmit = computed(() => {
  const marks = Number(maximumMarks.value)

  return (
    !loadingOptions.value &&
    !saving.value &&
    academicYearId.value !== '' &&
    schoolId.value !== '' &&
    Number.isFinite(marks) &&
    marks > 0 &&
    (!isMidline.value ||
      (Number.isInteger(sequenceNo.value) && sequenceNo.value >= 1))
  )
})

async function loadOptions(): Promise<void> {
  loadingOptions.value = true
  optionsError.value = ''

  const [yearsResult, schoolsResult] = await Promise.allSettled([
    listAcademicYears(),
    listSchools(),
  ])

  if (yearsResult.status === 'fulfilled') {
    academicYears.value = yearsResult.value.filter((year) => year.is_active)

    if (academicYears.value.length === 1) {
      academicYearId.value = academicYears.value[0].id
    }
  } else {
    optionsError.value = 'Unable to load academic years.'
  }

  if (schoolsResult.status === 'fulfilled') {
    schools.value = schoolsResult.value.filter(
      (school) => school.status === 'ACTIVE',
    )

    if (schools.value.length === 1) {
      schoolId.value = schools.value[0].id
    }
  } else {
    optionsError.value = optionsError.value
      ? `${optionsError.value} Unable to load schools.`
      : 'Unable to load schools.'
  }

  loadingOptions.value = false
}

function handleTypeChange(): void {
  if (!isMidline.value) {
    sequenceNo.value = 1
  }
}

async function submit(): Promise<void> {
  error.value = ''

  if (!canSubmit.value) {
    error.value = 'Complete all required fields with valid values.'
    return
  }

  const input: AssessmentCreateInput = {
    academic_year_id: academicYearId.value,
    school_id: schoolId.value,
    assessment_type: assessmentType.value,
    maximum_marks: Number(maximumMarks.value),
  }

  if (isMidline.value) {
    input.sequence_no = sequenceNo.value
  }

  if (assessmentName.value.trim()) {
    input.name = assessmentName.value.trim()
  }

  if (assessmentDate.value) {
    input.assessment_date = assessmentDate.value
  }

  saving.value = true

  try {
    const assessment = await createAssessment(input)
    emit('created', assessment)
  } catch (err) {
    error.value =
      err instanceof Error
        ? err.message
        : 'Unable to create the assessment.'
  } finally {
    saving.value = false
  }
}

onMounted(loadOptions)
</script>

<template>
  <section class="assessment-create">
    <header class="page-header">
      <div>
        <p class="eyebrow">ASSESSMENT MANAGEMENT</p>
        <h2>Create Assessment</h2>
        <p class="description">
          Set up the assessment details before configuring its class and
          division scope.
        </p>
      </div>

      <button class="secondary-button" type="button" @click="emit('cancel')">
        Cancel
      </button>
    </header>

    <div class="workflow-progress" aria-label="Assessment workflow progress">
      <div class="progress-step active">
        <span class="step-number">1</span>
        <span>Assessment details</span>
      </div>
      <div class="progress-line" />
      <div class="progress-step">
        <span class="step-number">2</span>
        <span>Configure scope</span>
      </div>
      <div class="progress-line" />
      <div class="progress-step">
        <span class="step-number">3</span>
        <span>Import scores</span>
      </div>
    </div>

    <div v-if="loadingOptions" class="form-state">
      Loading academic years and schools…
    </div>

    <div v-else-if="optionsError" class="notice error-notice">
      <span>{{ optionsError }}</span>
      <button class="text-button" type="button" @click="loadOptions">
        Retry
      </button>
    </div>

    <form v-else class="form-panel" @submit.prevent="submit">
      <div class="panel-heading">
        <div>
          <h3>Assessment information</h3>
          <p>Fields marked with * are required.</p>
        </div>
      </div>

      <div class="form-grid">
        <label class="form-field">
          <span>Academic year *</span>
          <select v-model="academicYearId" required>
            <option value="" disabled>Select academic year</option>
            <option
              v-for="year in academicYears"
              :key="year.id"
              :value="year.id"
            >
              {{ year.name }}
            </option>
          </select>
          <small>Select the academic year for this assessment.</small>
        </label>

        <label class="form-field">
          <span>School *</span>
          <select v-model="schoolId" required>
            <option value="" disabled>Select school</option>
            <option
              v-for="school in schools"
              :key="school.id"
              :value="school.id"
            >
              {{ school.school_name }}
            </option>
          </select>
          <small>Select the school being assessed.</small>
        </label>

        <label class="form-field">
          <span>Assessment type *</span>
          <select
            v-model="assessmentType"
            required
            @change="handleTypeChange"
          >
            <option value="BASELINE">Baseline</option>
            <option value="MIDLINE">Midline</option>
            <option value="ENDLINE">Endline</option>
          </select>
          <small>Choose the assessment stage.</small>
        </label>

        <label v-if="isMidline" class="form-field">
          <span>Midline sequence number *</span>
          <input
            v-model.number="sequenceNo"
            type="number"
            min="1"
            step="1"
            required
          />
          <small>Enter the sequence for this Midline assessment.</small>
        </label>

        <label class="form-field">
          <span>Assessment name</span>
          <input
            v-model="assessmentName"
            type="text"
            maxlength="150"
            placeholder="e.g. Midline 1 — Mathematics"
          />
          <small>
            Optional. Leave blank to use the system-generated name.
          </small>
        </label>

        <label class="form-field">
          <span>Assessment date</span>
          <input v-model="assessmentDate" type="date" />
          <small>Optional date of the assessment.</small>
        </label>

        <label class="form-field">
          <span>Maximum marks *</span>
          <input
            v-model="maximumMarks"
            type="number"
            min="0.01"
            step="0.01"
            required
          />
          <small>
            The maximum aggregate score students can receive.
          </small>
        </label>
      </div>

      <div v-if="error" class="notice error-notice">
        {{ error }}
      </div>

      <footer class="form-footer">
        <button
          class="secondary-button"
          type="button"
          :disabled="saving"
          @click="emit('cancel')"
        >
          Cancel
        </button>

        <button
          class="primary-button"
          type="submit"
          :disabled="!canSubmit"
        >
          {{ saving ? 'Creating…' : 'Create & Configure Scope' }}
        </button>
      </footer>
    </form>
  </section>
</template>

<style scoped>
.assessment-create {
  display: flex;
  flex-direction: column;
  gap: 22px;
  color: var(--ov-text-primary);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.eyebrow {
  margin: 0 0 7px;
  color: var(--ov-brand);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.11em;
}

.page-header h2 {
  margin: 0;
  font-size: 25px;
  font-weight: 750;
}

.description {
  margin: 7px 0 0;
  color: var(--ov-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.workflow-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 17px 20px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--ov-text-muted);
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
}

.step-number {
  display: grid;
  width: 27px;
  height: 27px;
  flex: 0 0 27px;
  place-items: center;
  border: 1px solid var(--ov-border);
  border-radius: 50%;
  font-size: 11px;
}

.progress-step.active {
  color: var(--ov-brand);
}

.progress-step.active .step-number {
  border-color: var(--ov-brand);
  background: var(--ov-brand);
  color: var(--ov-button-primary-text);
}

.progress-line {
  height: 1px;
  flex: 1;
  background: var(--ov-border);
}

.form-panel {
  overflow: hidden;
  border: 1px solid var(--ov-border);
  border-radius: 14px;
  background: var(--ov-bg-surface);
}

.panel-heading {
  padding: 20px;
  border-bottom: 1px solid var(--ov-border);
}

.panel-heading h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 750;
}

.panel-heading p {
  margin: 5px 0 0;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 21px;
  padding: 23px 20px;
}

.form-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
}

.form-field > span {
  font-size: 12px;
  font-weight: 700;
}

.form-field input,
.form-field select {
  width: 100%;
  min-width: 0;
  height: 42px;
  padding: 0 12px;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  outline: none;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font: inherit;
  font-size: 13px;
}

.form-field input:focus,
.form-field select:focus {
  border-color: var(--ov-brand);
}

.form-field small {
  color: var(--ov-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.form-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 17px 20px;
  border-top: 1px solid var(--ov-border);
}

.primary-button,
.secondary-button {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  border: 1px solid transparent;
  border-radius: 8px;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.primary-button {
  background: var(--ov-brand);
  color: var(--ov-button-primary-text);
}

.primary-button:hover:not(:disabled) {
  background: var(--ov-brand-hover);
}

.primary-button:disabled,
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.secondary-button {
  border-color: var(--ov-border);
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
}

.text-button {
  border: 0;
  background: transparent;
  color: var(--ov-brand);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.error-notice {
  border: 1px solid var(--ov-tag-terra-fg);
  color: var(--ov-tag-terra-fg);
}

.form-state {
  display: flex;
  min-height: 130px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  color: var(--ov-text-muted);
  font-size: 13px;
}

@media (max-width: 700px) {
  .page-header {
    flex-direction: column;
  }

  .workflow-progress {
    align-items: flex-start;
    flex-direction: column;
  }

  .progress-line {
    width: 1px;
    height: 13px;
    margin-left: 13px;
    flex: 0 0 13px;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-footer {
    flex-direction: column-reverse;
    align-items: stretch;
  }
}
</style>
