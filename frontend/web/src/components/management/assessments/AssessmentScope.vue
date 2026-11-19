<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Assessment } from '../../../services/assessments'
import { setAssessmentScope } from '../../../services/assessments'
import {
    listClassDivisions,
    type ClassDivision,
} from '../../../services/classDivisions'

const props = defineProps<{
    assessment: Assessment
    initialClassDivisionIds?: string[]
}>()

const emit = defineEmits<{
    cancel: []
    saved: [assessment: Assessment]
}>()

const divisions = ref<ClassDivision[]>([])
const selectedIds = ref<string[]>([])
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const loadError = ref(false)

const classLevels = [5, 6, 7] as const

const groupedDivisions = computed(() =>
    classLevels.map((level) => ({
        level,
        divisions: divisions.value
            .filter((item) => item.class_level === level)
            .sort((a, b) => a.division.localeCompare(b.division)),
    })),
)

const selectedCount = computed(() => selectedIds.value.length)

const allDivisionIds = computed(() =>
    divisions.value.map((item) => item.id),
)

function isSelected(id: string): boolean {
    return selectedIds.value.includes(id)
}

function toggleDivision(id: string): void {
    selectedIds.value = isSelected(id)
        ? selectedIds.value.filter((item) => item !== id)
        : [...selectedIds.value, id]
}

function isGroupSelected(ids: string[]): boolean {
    return ids.length > 0 && ids.every((id) => isSelected(id))
}

function toggleGroup(ids: string[]): void {
    if (isGroupSelected(ids)) {
        selectedIds.value = selectedIds.value.filter(
            (id) => !ids.includes(id),
        )
    } else {
        selectedIds.value = [
            ...new Set([...selectedIds.value, ...ids]),
        ]
    }
}

function selectAll(): void {
    selectedIds.value = [...allDivisionIds.value]
}

function clearAll(): void {
    selectedIds.value = []
}

async function loadDivisions(): Promise<void> {
    loading.value = true
    loadError.value = false
    errorMessage.value = ''

    try {
        const result = await listClassDivisions(props.assessment.school_id)

        divisions.value = result
            .filter((item) =>
                item.status === 'ACTIVE'
                && item.school_id === props.assessment.school_id,
            )
            .sort((a, b) =>
                a.class_level - b.class_level
                || a.division.localeCompare(b.division),
            )
        selectedIds.value = (props.initialClassDivisionIds ?? [])
            .filter(id => divisions.value.some(division => division.id === id))
    } catch (error) {
        loadError.value = true
        errorMessage.value = error instanceof Error
            ? error.message
            : 'Unable to load class divisions.'
    } finally {
        loading.value = false
    }
}

async function saveScope(): Promise<void> {
    if (selectedIds.value.length === 0 || saving.value) return

    saving.value = true
    errorMessage.value = ''

    try {
        const updatedAssessment = await setAssessmentScope(
            props.assessment.id,
            { class_division_ids: selectedIds.value },
        )

        emit('saved', updatedAssessment)
    } catch (error) {
        errorMessage.value = error instanceof Error
            ? error.message
            : 'Unable to save the assessment scope.'
    } finally {
        saving.value = false
    }
}

onMounted(loadDivisions)
</script>

<template>
    <section class="assessment-scope">
        <header class="scope-header">
            <div>
                <p class="eyebrow">ASSESSMENT SETUP · STEP 2 OF 3</p>
                <h2>Configure assessment scope</h2>
                <p class="subtitle">
                    Choose the classes and divisions whose students will be included
                    in this assessment.
                </p>
            </div>

            <span class="step-status">Draft assessment</span>
        </header>

        <div class="assessment-context">
            <div>
                <span class="context-label">Assessment</span>
                <strong>{{ assessment.name }}</strong>
            </div>
            <div>
                <span class="context-label">Assessment type</span>
                <strong>{{ assessment.assessment_type }}</strong>
            </div>
            <div>
                <span class="context-label">Maximum marks</span>
                <strong>{{ assessment.maximum_marks }}</strong>
            </div>
        </div>

        <div class="scope-toolbar">
            <div>
                <h3>Select class and divisions</h3>
                <p>
                    Only active divisions belonging to this assessment's school
                    are shown.
                </p>
            </div>

            <div class="selection-summary">
                <strong>{{ selectedCount }}</strong>
                <span>of {{ divisions.length }} selected</span>
            </div>
        </div>

        <div class="bulk-actions">
            <button type="button" class="text-action" :disabled="loading || divisions.length === 0" @click="selectAll">
                Select all
            </button>
            <button type="button" class="text-action" :disabled="loading || selectedCount === 0" @click="clearAll">
                Clear selection
            </button>
        </div>

        <div v-if="loading" class="loading-state">
            Loading active class divisions…
        </div>

        <div v-else-if="loadError" class="error-panel" role="alert">
            {{ errorMessage }}
            <button type="button" class="text-action" @click="loadDivisions">
                Try again
            </button>
        </div>

        <div v-else-if="divisions.length === 0" class="empty-state">
            <h3>No active class divisions found</h3>
            <p>
                Add active class divisions to this school before configuring
                the assessment scope.
            </p>
        </div>

        <div v-else class="class-groups">
            <article v-for="group in groupedDivisions" :key="group.level" v-show="group.divisions.length > 0"
                class="class-card">
                <header class="class-card-header">
                    <div>
                        <h3>Class {{ group.level }}</h3>
                        <span>
                            {{ group.divisions.length }}
                            {{ group.divisions.length === 1 ? 'division' : 'divisions' }}
                        </span>
                    </div>

                    <button type="button" class="text-action"
                        @click="toggleGroup(group.divisions.map((item) => item.id))">
                        {{
                            isGroupSelected(group.divisions.map((item) => item.id))
                                ? 'Clear class'
                                : 'Select class'
                        }}
                    </button>
                </header>

                <div class="division-list">
                    <label v-for="division in group.divisions" :key="division.id" class="division-option"
                        :class="{ selected: isSelected(division.id) }">
                        <input type="checkbox" :checked="isSelected(division.id)"
                            @change="toggleDivision(division.id)" />
                        <span class="division-name">
                            Division {{ division.division }}
                        </span>
                        <span v-if="isSelected(division.id)" class="selected-mark">
                            Selected
                        </span>
                    </label>
                </div>
            </article>
        </div>

        <p v-if="errorMessage && !loadError" class="error-message" role="alert">
            {{ errorMessage }}
        </p>

        <footer class="scope-footer">
            <button type="button" class="secondary-button" :disabled="saving" @click="emit('cancel')">
                Back
            </button>

            <div class="footer-right">
                <span v-if="selectedCount === 0" class="selection-hint">
                    Select at least one division to continue.
                </span>
                <button type="button" class="primary-button"
                    :disabled="loading || loadError || selectedCount === 0 || saving" @click="saveScope">
                    {{ saving ? 'Saving…' : 'Save scope & continue' }}
                </button>
            </div>
        </footer>
    </section>
</template>

<style scoped>
.assessment-scope {
    color: var(--text-primary, #18352d);
}

.scope-header,
.scope-toolbar,
.class-card-header,
.scope-footer,
.footer-right,
.bulk-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.scope-header {
    margin-bottom: 24px;
}

.eyebrow,
.context-label {
    display: block;
    color: var(--text-muted, #718078);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.eyebrow {
    margin: 0 0 8px;
}

.scope-header h2 {
    margin: 0;
    font-size: 25px;
}

.subtitle,
.scope-toolbar p,
.class-card-header span,
.empty-state p {
    color: var(--text-muted, #718078);
    font-size: 13px;
    line-height: 1.6;
}

.subtitle {
    margin: 8px 0 0;
}

.step-status {
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
    margin-bottom: 28px;
    padding: 18px;
    border: 1px solid var(--border-color, #e3e9e4);
    border-radius: 12px;
    background: var(--surface-muted, #f7f9f6);
}

.context-label {
    margin-bottom: 7px;
    font-size: 10px;
}

.assessment-context strong {
    font-size: 14px;
}

.scope-toolbar {
    align-items: flex-end;
}

.scope-toolbar h3,
.class-card-header h3 {
    margin: 0;
    font-size: 16px;
}

.scope-toolbar p {
    margin: 5px 0 0;
}

.selection-summary {
    text-align: right;
    white-space: nowrap;
}

.selection-summary strong {
    display: block;
    color: #26734d;
    font-size: 22px;
}

.selection-summary span {
    color: var(--text-muted, #718078);
    font-size: 11px;
}

.bulk-actions {
    justify-content: flex-start;
    margin: 16px 0;
}

.text-action {
    padding: 5px 0;
    border: 0;
    background: transparent;
    color: #28724f;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
}

.text-action:disabled {
    cursor: not-allowed;
    opacity: 0.45;
}

.class-groups {
    display: grid;
    gap: 14px;
}

.class-card {
    overflow: hidden;
    border: 1px solid var(--border-color, #e3e9e4);
    border-radius: 12px;
    background: var(--surface-card, #fff);
}

.class-card-header {
    padding: 15px 18px;
    background: var(--surface-muted, #f7f9f6);
}

.class-card-header span {
    display: block;
    margin-top: 3px;
    font-size: 11px;
}

.division-list {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    padding: 16px 18px;
}

.division-option {
    display: flex;
    align-items: center;
    gap: 9px;
    min-height: 42px;
    padding: 9px 12px;
    border: 1px solid var(--border-color, #dce5de);
    border-radius: 8px;
    cursor: pointer;
}

.division-option.selected {
    border-color: #4a966d;
    background: #eff7f0;
}

.division-option input {
    accent-color: #28724f;
}

.division-name {
    font-size: 13px;
    font-weight: 600;
}

.selected-mark {
    color: #28724f;
    font-size: 10px;
    font-weight: 700;
}

.loading-state,
.empty-state,
.error-panel {
    padding: 30px;
    border: 1px solid var(--border-color, #e3e9e4);
    border-radius: 12px;
    text-align: center;
}

.empty-state h3 {
    margin: 0;
}

.empty-state p {
    margin-bottom: 0;
}

.error-panel,
.error-message {
    color: #a52d2d;
}

.error-message {
    margin-top: 14px;
    font-size: 13px;
}

.scope-footer {
    margin-top: 26px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color, #e3e9e4);
}

.footer-right {
    justify-content: flex-end;
}

.selection-hint {
    color: var(--text-muted, #718078);
    font-size: 11px;
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

.primary-button:disabled,
.secondary-button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
}

.secondary-button {
    border: 1px solid var(--border-color, #dce5de);
    background: transparent;
    color: var(--text-primary, #18352d);
}

@media (max-width: 640px) {

    .scope-header,
    .scope-toolbar,
    .scope-footer {
        align-items: flex-start;
        flex-direction: column;
    }

    .assessment-context {
        grid-template-columns: 1fr;
    }

    .footer-right {
        width: 100%;
        align-items: flex-end;
        flex-direction: column;
    }

    .primary-button {
        width: 100%;
    }
}
</style>
