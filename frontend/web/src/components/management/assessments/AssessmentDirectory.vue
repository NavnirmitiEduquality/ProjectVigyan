<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { CurrentUser } from '../../../services/auth'
import {
    listAssessments,
    type Assessment,
    type AssessmentStatus,
    type AssessmentType,
} from '../../../services/assessments'
import { listAcademicYears } from '../../../services/academicCalendar'
import type { AcademicYear } from '../../../services/academicCalendar'
import { listSchools } from '../../../services/schools'
import type { School } from '../../../services/schools'

const props = defineProps<{
    currentUser: CurrentUser | null
}>()

const emit = defineEmits<{
    create: []
    open: [assessmentId: string]
}>()

const assessments = ref<Assessment[]>([])
const academicYears = ref<AcademicYear[]>([])
const schools = ref<School[]>([])

const loading = ref(true)
const error = ref('')
const referenceDataWarning = ref('')

const search = ref('')
const selectedYear = ref('')
const selectedSchool = ref('')
const selectedType = ref('')
const selectedStatus = ref('')

const canCreate = computed(
    () => props.currentUser?.permissions.includes('assessment.create') ?? false,
)

const yearById = computed(
    () => new Map(academicYears.value.map((year) => [year.id, year.name])),
)

const schoolById = computed(
    () => new Map(schools.value.map((school) => [school.id, school.school_name])),
)

const totalCount = computed(() => assessments.value.length)
const draftCount = computed(
    () => assessments.value.filter((item) => item.status === 'DRAFT').length,
)
const submittedCount = computed(
    () => assessments.value.filter((item) => item.status === 'SUBMITTED').length,
)

const filteredAssessments = computed(() => {
    const query = search.value.trim().toLowerCase()

    return assessments.value.filter((assessment) => {
        const matchesSearch =
            !query ||
            assessment.name.toLowerCase().includes(query) ||
            assessment.assessment_type.toLowerCase().includes(query)

        const matchesYear =
            !selectedYear.value ||
            assessment.academic_year_id === selectedYear.value

        const matchesSchool =
            !selectedSchool.value ||
            assessment.school_id === selectedSchool.value

        const matchesType =
            !selectedType.value ||
            assessment.assessment_type === selectedType.value

        const matchesStatus =
            !selectedStatus.value ||
            assessment.status === selectedStatus.value

        return (
            matchesSearch &&
            matchesYear &&
            matchesSchool &&
            matchesType &&
            matchesStatus
        )
    })
})

function formatDate(value: string | null): string {
    if (!value) return '—'

    const date = new Date(`${value}T00:00:00`)
    if (Number.isNaN(date.getTime())) return value

    return new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    }).format(date)
}

function formatMarks(value: number): string {
    return new Intl.NumberFormat('en-IN', {
        maximumFractionDigits: 2,
    }).format(value)
}

function typeLabel(type: AssessmentType): string {
    const labels: Record<AssessmentType, string> = {
        BASELINE: 'Baseline',
        MIDLINE: 'Midline',
        ENDLINE: 'Endline',
    }

    return labels[type]
}

function statusLabel(status: AssessmentStatus): string {
    return status === 'SUBMITTED' ? 'Submitted' : 'Draft'
}

function clearFilters(): void {
    search.value = ''
    selectedYear.value = ''
    selectedSchool.value = ''
    selectedType.value = ''
    selectedStatus.value = ''
}

async function loadDirectory(): Promise<void> {
    loading.value = true
    error.value = ''
    referenceDataWarning.value = ''

    const [assessmentResult, yearResult, schoolResult] =
        await Promise.allSettled([
            listAssessments(),
            listAcademicYears(),
            listSchools(),
        ])

    if (assessmentResult.status === 'fulfilled') {
        assessments.value = assessmentResult.value
    } else {
        error.value =
            assessmentResult.reason instanceof Error
                ? assessmentResult.reason.message
                : 'Unable to load assessments.'
    }

    if (yearResult.status === 'fulfilled') {
        academicYears.value = yearResult.value
    } else {
        referenceDataWarning.value =
            'Academic year names could not be loaded. The directory can still be used.'
    }

    if (schoolResult.status === 'fulfilled') {
        schools.value = schoolResult.value
    } else {
        referenceDataWarning.value = referenceDataWarning.value
            ? `${referenceDataWarning.value} School names could not be loaded.`
            : 'School names could not be loaded. The directory can still be used.'
    }

    loading.value = false
}

onMounted(loadDirectory)
</script>

<template>
    <section class="assessment-directory">
        <header class="directory-header">
            <div>
                <p class="eyebrow">ASSESSMENT MANAGEMENT</p>
                <h2>Assessment Directory</h2>
                <p class="header-description">
                    Create, review, and manage school assessments across academic years.
                </p>
            </div>

            <button v-if="canCreate" class="primary-button" type="button" @click="emit('create')">
                <span aria-hidden="true">＋</span>
                Create Assessment
            </button>
        </header>

        <div v-if="referenceDataWarning" class="notice warning-notice">
            {{ referenceDataWarning }}
        </div>

        <div class="summary-grid">
            <article class="summary-card">
                <span class="summary-label">Total assessments</span>
                <strong>{{ totalCount }}</strong>
                <span class="summary-note">Across all available records</span>
            </article>

            <article class="summary-card draft-summary">
                <span class="summary-label">Draft assessments</span>
                <strong>{{ draftCount }}</strong>
                <span class="summary-note">Awaiting completion or submission</span>
            </article>

            <article class="summary-card submitted-summary">
                <span class="summary-label">Submitted assessments</span>
                <strong>{{ submittedCount }}</strong>
                <span class="summary-note">Finalised assessment records</span>
            </article>
        </div>

        <section class="directory-panel">
            <div class="panel-heading">
                <div>
                    <h3>All assessments</h3>
                    <p>Search and filter the assessment register.</p>
                </div>
                <span class="record-count">
                    {{ filteredAssessments.length }} records
                </span>
            </div>

            <div class="filter-grid">
                <label class="filter-field search-field">
                    <span>Search</span>
                    <input v-model="search" type="search" placeholder="Search assessment name or type" />
                </label>

                <label class="filter-field">
                    <span>Academic year</span>
                    <select v-model="selectedYear">
                        <option value="">All academic years</option>
                        <option v-for="year in academicYears" :key="year.id" :value="year.id">
                            {{ year.name }}
                        </option>
                    </select>
                </label>

                <label class="filter-field">
                    <span>School</span>
                    <select v-model="selectedSchool">
                        <option value="">All schools</option>
                        <option v-for="school in schools" :key="school.id" :value="school.id">
                            {{ school.school_name }}
                        </option>
                    </select>
                </label>

                <label class="filter-field">
                    <span>Assessment type</span>
                    <select v-model="selectedType">
                        <option value="">All types</option>
                        <option value="BASELINE">Baseline</option>
                        <option value="MIDLINE">Midline</option>
                        <option value="ENDLINE">Endline</option>
                    </select>
                </label>

                <label class="filter-field">
                    <span>Status</span>
                    <select v-model="selectedStatus">
                        <option value="">All statuses</option>
                        <option value="DRAFT">Draft</option>
                        <option value="SUBMITTED">Submitted</option>
                    </select>
                </label>

                <div class="filter-actions">
                    <button class="text-button" type="button" @click="clearFilters">
                        Clear filters
                    </button>
                </div>
            </div>

            <div v-if="error" class="notice error-notice">
                <span>{{ error }}</span>
                <button class="text-button" type="button" @click="loadDirectory">
                    Retry
                </button>
            </div>

            <div v-else-if="loading" class="table-state">
                Loading assessments…
            </div>

            <div v-else-if="filteredAssessments.length === 0" class="table-state">
                <strong>No assessments found</strong>
                <span>
                    Try changing your search or filters.
                </span>
            </div>

            <div v-else class="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th>Assessment</th>
                            <th>School</th>
                            <th>Academic year</th>
                            <th>Type</th>
                            <th>Date</th>
                            <th class="numeric-cell">Maximum marks</th>
                            <th>Status</th>
                            <th class="action-cell">Action</th>
                        </tr>
                    </thead>

                    <tbody>
                        <tr v-for="assessment in filteredAssessments" :key="assessment.id">
                            <td>
                                <div class="assessment-name">
                                    <strong>{{ assessment.name }}</strong>
                                    <span>Sequence {{ assessment.sequence_no }}</span>
                                </div>
                            </td>

                            <td>
                                {{ schoolById.get(assessment.school_id) || '—' }}
                            </td>

                            <td>
                                {{ yearById.get(assessment.academic_year_id) || '—' }}
                            </td>

                            <td>
                                <span class="type-label">
                                    {{ typeLabel(assessment.assessment_type) }}
                                </span>
                            </td>

                            <td>{{ formatDate(assessment.assessment_date) }}</td>

                            <td class="numeric-cell">
                                {{ formatMarks(assessment.maximum_marks) }}
                            </td>

                            <td>
                                <span class="status-chip" :class="assessment.status === 'SUBMITTED'
                                    ? 'status-submitted'
                                    : 'status-draft'">
                                    {{ statusLabel(assessment.status) }}
                                </span>
                            </td>

                            <td class="action-cell">
                                <button class="open-button" type="button" @click="emit('open', assessment.id)">
                                    {{ assessment.status === 'DRAFT' ? 'Continue' : 'View' }}
                                </button>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>
    </section>
</template>

<style scoped>
.assessment-directory {
    display: flex;
    flex-direction: column;
    gap: 22px;
    color: var(--ov-text-primary);
}

.directory-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
}

.eyebrow {
    margin: 0 0 7px;
    color: var(--ov-brand);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.11em;
}

.directory-header h2 {
    margin: 0;
    font-size: 25px;
    font-weight: 750;
    letter-spacing: -0.025em;
}

.header-description {
    margin: 7px 0 0;
    color: var(--ov-text-muted);
    font-size: 13px;
    line-height: 1.6;
}

.primary-button,
.open-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 40px;
    padding: 0 15px;
    border: 0;
    border-radius: 9px;
    background: var(--ov-brand);
    color: var(--ov-button-primary-text);
    font: inherit;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
}

.primary-button:hover,
.open-button:hover {
    background: var(--ov-brand-hover);
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
    min-height: 112px;
    padding: 17px 19px;
    border: 1px solid var(--ov-border);
    border-radius: 13px;
    background: var(--ov-bg-surface);
}

.summary-label {
    color: var(--ov-text-muted);
    font-size: 12px;
    font-weight: 650;
}

.summary-card strong {
    font-size: 27px;
    line-height: 1.1;
    font-weight: 750;
}

.summary-note {
    color: var(--ov-text-muted);
    font-size: 11px;
}

.draft-summary {
    border-left: 3px solid var(--ov-tag-terra-fg);
}

.submitted-summary {
    border-left: 3px solid var(--ov-brand);
}

.directory-panel {
    min-width: 0;
    overflow: hidden;
    border: 1px solid var(--ov-border);
    border-radius: 14px;
    background: var(--ov-bg-surface);
}

.panel-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 19px 20px;
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

.record-count {
    color: var(--ov-text-muted);
    font-size: 12px;
    white-space: nowrap;
}

.filter-grid {
    display: grid;
    grid-template-columns: minmax(190px, 1.5fr) repeat(4, minmax(130px, 1fr)) auto;
    align-items: end;
    gap: 12px;
    padding: 17px 20px;
    border-bottom: 1px solid var(--ov-border);
}

.filter-field {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 7px;
}

.filter-field>span {
    color: var(--ov-text-muted);
    font-size: 11px;
    font-weight: 700;
}

.filter-field input,
.filter-field select {
    width: 100%;
    min-width: 0;
    height: 38px;
    padding: 0 10px;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    outline: none;
    background: var(--ov-bg-page);
    color: var(--ov-text-primary);
    font: inherit;
    font-size: 12px;
}

.filter-field input:focus,
.filter-field select:focus {
    border-color: var(--ov-brand);
}

.filter-actions {
    display: flex;
    align-items: center;
    height: 38px;
}

.text-button {
    padding: 5px 2px;
    border: 0;
    background: transparent;
    color: var(--ov-brand);
    font: inherit;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
}

.notice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin: 14px 20px;
    padding: 11px 13px;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.5;
}

.warning-notice {
    margin: 0;
    border: 1px solid var(--ov-border);
    background: var(--ov-bg-surface-subtle);
    color: var(--ov-text-muted);
}

.error-notice {
    border: 1px solid var(--ov-tag-terra-fg);
    color: var(--ov-tag-terra-fg);
}

.table-state {
    display: flex;
    min-height: 150px;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px;
    color: var(--ov-text-muted);
    font-size: 13px;
    text-align: center;
}

.table-state strong {
    color: var(--ov-text-primary);
    font-size: 14px;
}

.table-scroll {
    width: 100%;
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    white-space: nowrap;
}

th,
td {
    padding: 13px 15px;
    border-bottom: 1px solid var(--ov-border);
    font-size: 12px;
}

th {
    background: var(--ov-bg-surface-subtle);
    color: var(--ov-text-muted);
    font-size: 10px;
    font-weight: 750;
    letter-spacing: 0.035em;
    text-transform: uppercase;
}

tbody tr:last-child td {
    border-bottom: 0;
}

tbody tr:hover {
    background: var(--ov-bg-surface-subtle);
}

.assessment-name {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.assessment-name strong {
    color: var(--ov-text-primary);
    font-size: 12px;
    font-weight: 700;
}

.assessment-name span {
    color: var(--ov-text-muted);
    font-size: 10px;
}

.type-label {
    color: var(--ov-text-primary);
    font-weight: 650;
}

.status-chip {
    display: inline-flex;
    align-items: center;
    padding: 5px 9px;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 750;
}

.status-draft {
    background: var(--ov-bg-surface-subtle);
    color: var(--ov-text-muted);
}

.status-submitted {
    background: var(--ov-tag-accent-bg);
    color: var(--ov-tag-accent-fg);
}

.numeric-cell {
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.action-cell {
    text-align: right;
}

.open-button {
    min-height: 30px;
    padding: 0 11px;
    border: 1px solid var(--ov-border);
    background: transparent;
    color: var(--ov-brand);
    font-size: 11px;
}

.open-button:hover {
    background: var(--ov-bg-surface-subtle);
}

@media (max-width: 1100px) {
    .filter-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (max-width: 700px) {
    .directory-header {
        flex-direction: column;
    }

    .summary-grid {
        grid-template-columns: 1fr;
    }

    .summary-card {
        min-height: 95px;
    }

    .filter-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .search-field {
        grid-column: 1 / -1;
    }

    .filter-actions {
        grid-column: 1 / -1;
    }

    .panel-heading {
        padding: 16px;
    }
}

@media (max-width: 420px) {
    .filter-grid {
        grid-template-columns: 1fr;
    }

    .search-field,
    .filter-actions {
        grid-column: auto;
    }
}
</style>
