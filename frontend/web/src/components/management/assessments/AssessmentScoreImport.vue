
<script setup lang="ts">
import { computed, ref } from 'vue'
import type {
  Assessment,
  AssessmentImport,
} from '../../../services/assessments'
import { importAssessmentCsv } from '../../../services/assessments'

const props = defineProps<{
  assessment: Assessment
}>()

const emit = defineEmits<{
  cancel: []
  imported: [result: AssessmentImport]
}>()

const selectedFile = ref<File | null>(null)
const importResult = ref<AssessmentImport | null>(null)
const uploading = ref(false)
const dragging = ref(false)
const errorMessage = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const maxFileSize = 5 * 1024 * 1024

const validCount = computed(() =>
  importResult.value?.rows.filter(
    (row) => row.validation_status === 'VALID',
  ).length ?? 0,
)

const warningCount = computed(() =>
  importResult.value?.warning_count ?? 0,
)

const errorCount = computed(() =>
  importResult.value?.error_count ?? 0,
)

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function chooseFile(file: File | undefined): void {
  errorMessage.value = ''
  importResult.value = null

  if (!file) return

  if (!file.name.toLowerCase().endsWith('.csv')) {
    errorMessage.value = 'Please select a CSV file.'
    selectedFile.value = null
    return
  }

  if (file.size > maxFileSize) {
    errorMessage.value = 'The CSV file must not exceed 5 MiB.'
    selectedFile.value = null
    return
  }

  if (file.size === 0) {
    errorMessage.value = 'The selected CSV file is empty.'
    selectedFile.value = null
    return
  }

  selectedFile.value = file
}

function onFileInput(event: Event): void {
  const target = event.target as HTMLInputElement
  chooseFile(target.files?.[0])
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  chooseFile(event.dataTransfer?.files?.[0])
}

function downloadTemplate(): void {
  const content = [
    'student_business_id,class,division,aggregate_marks',
    'STU001,5,A,78',
    'STU002,5,B,82',
    'STU003,6,A,65',
  ].join('\n')

  const blob = new Blob([content], {
    type: 'text/csv;charset=utf-8',
  })

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  anchor.href = url
  anchor.download = 'assessment_scores_template.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()

  URL.revokeObjectURL(url)
}

async function uploadCsv(): Promise<void> {
  if (!selectedFile.value || uploading.value) return

  uploading.value = true
  errorMessage.value = ''

  try {
    importResult.value = await importAssessmentCsv(
      props.assessment.id,
      selectedFile.value,
    )
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : 'Unable to import the CSV file.'
  } finally {
    uploading.value = false
  }
}

function continueToValidation(): void {
  if (importResult.value) {
    emit('imported', importResult.value)
  }
}
</script>

<template>
  <section class="score-import">
    <header class="page-header">
      <div>
        <p class="eyebrow">ASSESSMENT SETUP · STEP 3 OF 3</p>
        <h2>Import student scores</h2>
        <p class="subtitle">
          Upload the consolidated student assessment results for the
          selected class and division scope.
        </p>
      </div>
      <span class="draft-label">Draft assessment</span>
    </header>

    <div class="assessment-context">
      <div>
        <span>Assessment</span>
        <strong>{{ assessment.name }}</strong>
      </div>
      <div>
        <span>Type</span>
        <strong>{{ assessment.assessment_type }}</strong>
      </div>
      <div>
        <span>Maximum marks</span>
        <strong>{{ assessment.maximum_marks }}</strong>
      </div>
    </div>

    <template v-if="!importResult">
      <section class="upload-card">
        <div class="upload-heading">
          <div>
            <h3>Upload score sheet</h3>
            <p>Use the prescribed CSV structure for accurate validation.</p>
          </div>
          <button
            type="button"
            class="template-button"
            @click="downloadTemplate"
          >
            Download CSV template
          </button>
        </div>

        <div
          class="drop-zone"
          :class="{ dragging }"
          role="button"
          tabindex="0"
          @click="fileInput?.click()"
          @keydown.enter.prevent="fileInput?.click()"
          @keydown.space.prevent="fileInput?.click()"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".csv,text/csv"
            hidden
            @change="onFileInput"
          />

          <div class="upload-icon">↑</div>
          <h3>Drop your CSV file here</h3>
          <p>or click to browse your device</p>
          <span>CSV format · Maximum file size 5 MiB</span>
        </div>

        <div v-if="selectedFile" class="selected-file">
          <div>
            <strong>{{ selectedFile.name }}</strong>
            <span>{{ formatSize(selectedFile.size) }}</span>
          </div>
          <button
            type="button"
            class="remove-file"
            :disabled="uploading"
            aria-label="Remove selected file"
            @click="selectedFile = null"
          >
            Remove
          </button>
        </div>

        <div class="format-guide">
          <h4>Required CSV headers</h4>
          <code>student_business_id, class, division, aggregate_marks</code>
          <p>
            All four headers must be present exactly as shown. Do not add
            extra columns or duplicate headers. Use UTF-8 encoding.
          </p>
        </div>

        <p v-if="errorMessage" class="error-message" role="alert">
          {{ errorMessage }}
        </p>

        <footer class="actions">
          <button
            type="button"
            class="secondary-button"
            :disabled="uploading"
            @click="emit('cancel')"
          >
            Back to scope
          </button>

          <button
            type="button"
            class="primary-button"
            :disabled="!selectedFile || uploading"
            @click="uploadCsv"
          >
            {{ uploading ? 'Uploading and validating…' : 'Upload and validate' }}
          </button>
        </footer>
      </section>
    </template>

    <template v-else>
      <section class="result-card">
        <div class="result-heading">
          <div>
            <span class="success-icon">✓</span>
            <div>
              <h3>CSV imported successfully</h3>
              <p>
                The backend has processed the file and reconciled the
                selected student roster.
              </p>
            </div>
          </div>
        </div>

        <div class="summary-grid">
          <div class="summary-item">
            <strong>{{ importResult.total_rows }}</strong>
            <span>Total rows</span>
          </div>
          <div class="summary-item valid">
            <strong>{{ validCount }}</strong>
            <span>Valid rows</span>
          </div>
          <div class="summary-item warning">
            <strong>{{ warningCount }}</strong>
            <span>Warnings</span>
          </div>
          <div class="summary-item error">
            <strong>{{ errorCount }}</strong>
            <span>Errors</span>
          </div>
        </div>

        <div class="reconciliation-notice">
          <strong>Missing-student reconciliation included</strong>
          <p>
            Active production students missing from the uploaded score sheet
            have been added as error rows. They must be resolved before
            submission.
          </p>
        </div>

        <div class="preview-heading">
          <h3>Import row preview</h3>
          <span>First 10 rows</span>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Row</th>
                <th>Student Business ID</th>
                <th>Class / Division</th>
                <th>Marks</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in importResult.rows.slice(0, 10)"
                :key="row.id"
              >
                <td>{{ row.row_number }}</td>
                <td>{{ row.student_business_id || '—' }}</td>
                <td>
                  {{ row.source_class || '—' }}
                  /
                  {{ row.source_division || '—' }}
                </td>
                <td>{{ row.aggregate_marks ?? '—' }}</td>
                <td>
                  <span
                    class="status-pill"
                    :class="row.validation_status.toLowerCase()"
                  >
                    {{ row.validation_status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="preview-note">
          The complete import, including all generated reconciliation rows,
          will be available in the next step.
        </p>

        <footer class="actions">
          <button
            type="button"
            class="secondary-button"
            @click="importResult = null"
          >
            Upload another file
          </button>

          <button
            type="button"
            class="primary-button"
            @click="continueToValidation"
          >
            Continue to validation
          </button>
        </footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
.score-import {
  color: var(--text-primary, #18352d);
}

.page-header,
.upload-heading,
.actions,
.result-heading,
.preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--text-muted, #718078);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-header h2 {
  margin: 0;
  font-size: 25px;
}

.subtitle,
.upload-heading p,
.format-guide p,
.reconciliation-notice p {
  color: var(--text-muted, #718078);
  font-size: 13px;
  line-height: 1.6;
}

.subtitle {
  margin: 8px 0 0;
}

.draft-label {
  padding: 7px 12px;
  border-radius: 20px;
  background: #edf5ef;
  color: #286344;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.assessment-context {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  padding: 18px;
  border: 1px solid var(--border-color, #e3e9e4);
  border-radius: 12px;
  background: var(--surface-muted, #f7f9f6);
}

.assessment-context span,
.assessment-context strong {
  display: block;
}

.assessment-context span {
  margin-bottom: 7px;
  color: var(--text-muted, #718078);
  font-size: 11px;
}

.assessment-context strong {
  font-size: 14px;
}

.upload-card,
.result-card {
  padding: 22px;
  border: 1px solid var(--border-color, #e3e9e4);
  border-radius: 12px;
  background: var(--surface-card, #fff);
}

.upload-heading {
  align-items: flex-start;
  margin-bottom: 20px;
}

.upload-heading h3,
.result-heading h3,
.preview-heading h3 {
  margin: 0;
  font-size: 16px;
}

.upload-heading p {
  margin: 5px 0 0;
}

.template-button,
.remove-file {
  padding: 8px 12px;
  border: 1px solid var(--border-color, #dce5de);
  border-radius: 7px;
  background: transparent;
  color: #28724f;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.drop-zone {
  display: flex;
  min-height: 210px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  border: 2px dashed #b8c9bd;
  border-radius: 12px;
  background: #fafcf9;
  cursor: pointer;
  text-align: center;
  transition: border-color 0.15s, background 0.15s;
}

.drop-zone.dragging {
  border-color: #28724f;
  background: #eff7f0;
}

.upload-icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 50%;
  background: #e9f3eb;
  color: #28724f;
  font-size: 25px;
}

.drop-zone h3 {
  margin: 12px 0 4px;
  font-size: 15px;
}

.drop-zone p,
.drop-zone span {
  margin: 0;
  color: var(--text-muted, #718078);
  font-size: 12px;
}

.drop-zone span {
  margin-top: 12px;
  font-size: 11px;
}

.selected-file {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--border-color, #e3e9e4);
  border-radius: 8px;
}

.selected-file strong,
.selected-file span {
  display: block;
}

.selected-file strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.selected-file span {
  margin-top: 4px;
  color: var(--text-muted, #718078);
  font-size: 11px;
}

.format-guide {
  margin-top: 20px;
  padding: 16px;
  border-radius: 9px;
  background: var(--surface-muted, #f7f9f6);
}

.format-guide h4 {
  margin: 0 0 10px;
  font-size: 12px;
}

.format-guide code {
  display: block;
  overflow-wrap: anywhere;
  color: #286344;
  font-size: 12px;
}

.format-guide p {
  margin: 10px 0 0;
  font-size: 11px;
}

.error-message {
  margin: 14px 0 0;
  color: #a52d2d;
  font-size: 13px;
}

.actions {
  justify-content: space-between;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--border-color, #e3e9e4);
}

.primary-button,
.secondary-button {
  min-height: 40px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.primary-button {
  border: 1px solid #286c4a;
  background: #286c4a;
  color: white;
}

.primary-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.secondary-button {
  border: 1px solid var(--border-color, #dce5de);
  background: transparent;
  color: var(--text-primary, #18352d);
}

.result-heading > div {
  display: flex;
  align-items: center;
  gap: 12px;
}

.success-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  place-items: center;
  border-radius: 50%;
  background: #e9f3eb;
  color: #28724f;
  font-weight: 800;
}

.result-heading p {
  margin: 5px 0 0;
  color: var(--text-muted, #718078);
  font-size: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 22px 0;
}

.summary-item {
  padding: 15px;
  border: 1px solid var(--border-color, #e3e9e4);
  border-radius: 9px;
}

.summary-item strong,
.summary-item span {
  display: block;
}

.summary-item strong {
  font-size: 23px;
}

.summary-item span {
  margin-top: 4px;
  color: var(--text-muted, #718078);
  font-size: 11px;
}

.summary-item.valid strong {
  color: #28724f;
}

.summary-item.warning strong {
  color: #a66a12;
}

.summary-item.error strong {
  color: #b13d3d;
}

.reconciliation-notice {
  padding: 15px;
  border: 1px solid #e5d7b9;
  border-radius: 9px;
  background: #fffaf0;
}

.reconciliation-notice strong {
  font-size: 12px;
}

.reconciliation-notice p {
  margin: 6px 0 0;
  font-size: 12px;
}

.preview-heading {
  margin: 22px 0 12px;
}

.preview-heading span,
.preview-note {
  color: var(--text-muted, #718078);
  font-size: 11px;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12px;
}

th,
td {
  padding: 11px 9px;
  border-bottom: 1px solid var(--border-color, #e3e9e4);
  white-space: nowrap;
}

th {
  color: var(--text-muted, #718078);
  font-size: 10px;
  text-transform: uppercase;
}

.status-pill {
  display: inline-block;
  padding: 4px 7px;
  border-radius: 12px;
  background: #eef2ef;
  font-size: 10px;
  font-weight: 700;
}

.status-pill.valid {
  background: #e9f3eb;
  color: #28724f;
}

.status-pill.warning,
.status-pill.mapped {
  background: #fff4dc;
  color: #92600f;
}

.status-pill.error {
  background: #fbeaea;
  color: #a52d2d;
}

.preview-note {
  margin: 12px 0 0;
}

@media (max-width: 640px) {
  .page-header,
  .upload-heading,
  .actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .assessment-context {
    grid-template-columns: 1fr;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .template-button,
  .primary-button,
  .secondary-button {
    width: 100%;
  }

  .upload-card,
  .result-card {
    padding: 15px;
  }
}
</style>
