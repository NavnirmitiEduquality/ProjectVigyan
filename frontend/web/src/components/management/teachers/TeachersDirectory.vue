<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { CurrentUser } from '../../../services/auth'
import {
  listParaTeachers,
  listSchoolTeachers,
  listTeacherSchools,
  type ParaTeacher,
  type School,
  type SchoolTeacher,
} from '../../../services/teachers'

const props = defineProps<{ currentUser: CurrentUser | null }>()

const canViewParaTeachers = computed(() => props.currentUser?.permissions.includes('user.view') ?? false)
const canViewSchoolTeachers = computed(() => props.currentUser?.permissions.includes('school_teacher.manage') ?? false)
const canViewSchools = computed(() => props.currentUser?.permissions.includes('school.view') ?? false)

const activeTab = ref<'para' | 'school'>('para')
const paraTeachers = ref<ParaTeacher[]>([])
const schoolTeachers = ref<SchoolTeacher[]>([])
const schools = ref<School[]>([])
const paraLoading = ref(false)
const schoolLoading = ref(false)
const paraError = ref('')
const schoolError = ref('')
const schoolLookupError = ref('')
const paraSearch = ref('')
const schoolSearch = ref('')
const paraStatus = ref<'ALL' | 'ACTIVE' | 'DISABLED'>('ALL')
const schoolStatus = ref<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL')
const paraOrigin = ref('ALL')
const schoolFilter = ref('ALL')

const paraOrigins = computed(() => [...new Set(paraTeachers.value.map(teacher => teacher.data_origin))].sort())
const schoolById = computed(() => new Map(schools.value.map(school => [school.id, school.school_name])))
const schoolOptions = computed(() =>
  schools.value.slice().sort((a, b) => a.school_name.localeCompare(b.school_name)),
)
const filteredParaTeachers = computed(() => {
  const term = paraSearch.value.trim().toLowerCase()
  return paraTeachers.value.filter(teacher =>
    (!term || teacher.user_code.toLowerCase().includes(term) || teacher.full_name.toLowerCase().includes(term)) &&
    (paraStatus.value === 'ALL' || teacher.status === paraStatus.value) &&
    (paraOrigin.value === 'ALL' || teacher.data_origin === paraOrigin.value),
  )
})
const filteredSchoolTeachers = computed(() => {
  const term = schoolSearch.value.trim().toLowerCase()
  return schoolTeachers.value.filter(teacher =>
    (!term || teacher.full_name.toLowerCase().includes(term)) &&
    (schoolStatus.value === 'ALL' || teacher.status === schoolStatus.value) &&
    (schoolFilter.value === 'ALL' || teacher.school_id === schoolFilter.value),
  )
})

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback
}

async function loadParaTeachers() {
  if (!canViewParaTeachers.value) return
  paraLoading.value = true
  paraError.value = ''
  try {
    paraTeachers.value = await listParaTeachers()
  } catch (reason) {
    paraError.value = errorMessage(reason, 'Unable to load Para-Teachers.')
  } finally {
    paraLoading.value = false
  }
}

async function loadSchoolTeachers() {
  if (!canViewSchoolTeachers.value) return
  schoolLoading.value = true
  schoolError.value = ''
  try {
    schoolTeachers.value = await listSchoolTeachers()
  } catch (reason) {
    schoolError.value = errorMessage(reason, 'Unable to load School Teachers.')
  } finally {
    schoolLoading.value = false
  }
}

async function loadSchools() {
  if (!canViewSchools.value) {
    schoolLookupError.value = 'School names are unavailable because school directory access is restricted.'
    return
  }
  try {
    schools.value = await listTeacherSchools()
  } catch (reason) {
    schoolLookupError.value = errorMessage(reason, 'School names are unavailable.')
  }
}

function clearParaFilters() {
  paraSearch.value = ''
  paraStatus.value = 'ALL'
  paraOrigin.value = 'ALL'
}

function clearSchoolFilters() {
  schoolSearch.value = ''
  schoolStatus.value = 'ALL'
  schoolFilter.value = 'ALL'
}

function retryActiveTab() {
  if (activeTab.value === 'para') void loadParaTeachers()
  else void loadSchoolTeachers()
}

onMounted(() => {
  void loadParaTeachers()
  void loadSchoolTeachers()
  void loadSchools()
})
</script>

<template>
  <div class="teachers-directory">
    <header class="teachers-header">
      <div>
        <p class="teachers-eyebrow">Management</p>
        <h2>Teachers Directory</h2>
        <p>Read-only view of Para-Teachers and School Teachers available to authorised users.</p>
      </div>
    </header>

    <div class="teachers-tabs" role="tablist" aria-label="Teacher populations">
      <button class="teachers-tab" :class="{ 'is-active': activeTab === 'para' }" role="tab"
        :aria-selected="activeTab === 'para'" type="button" @click="activeTab = 'para'">
        Para-Teachers
      </button>
      <button class="teachers-tab" :class="{ 'is-active': activeTab === 'school' }" role="tab"
        :aria-selected="activeTab === 'school'" type="button" @click="activeTab = 'school'">
        School Teachers
      </button>
    </div>

    <section v-if="activeTab === 'para'" class="teachers-panel" aria-labelledby="para-teachers-title">
      <div class="teachers-panel-heading">
        <div>
          <p class="teachers-eyebrow">Users</p>
          <h3 id="para-teachers-title">Para-Teachers</h3>
          <p class="teachers-muted">Active Para-Teacher role holders, without inferred school assignments.</p>
        </div>
        <strong class="teachers-count">{{ paraTeachers.length }} total</strong>
      </div>

      <div v-if="!canViewParaTeachers" class="teachers-restricted" role="status">
        You do not have permission to view Para-Teachers.
      </div>
      <template v-else>
        <div class="teachers-filters">
          <label>Search<input v-model="paraSearch" type="search" placeholder="Code or teacher name" /></label>
          <label>Status<select v-model="paraStatus"><option value="ALL">All statuses</option><option value="ACTIVE">Active</option><option value="DISABLED">Disabled</option></select></label>
          <label>Data origin<select v-model="paraOrigin"><option value="ALL">All origins</option><option v-for="origin in paraOrigins" :key="origin" :value="origin">{{ origin }}</option></select></label>
          <button class="teachers-secondary" type="button" @click="clearParaFilters">Clear filters</button>
        </div>
        <p v-if="paraError" class="teachers-error" role="alert">{{ paraError }} <button class="teachers-link" type="button" @click="retryActiveTab">Retry</button></p>
        <p v-else-if="paraLoading" class="teachers-muted" role="status">Loading Para-Teachers…</p>
        <div v-else-if="!paraTeachers.length" class="teachers-empty">No Para-Teacher records are available.</div>
        <div v-else-if="!filteredParaTeachers.length" class="teachers-empty">No Para-Teachers match these filters.</div>
        <div v-else class="teachers-table-wrap">
          <table class="teachers-table">
            <thead><tr><th>Teacher code</th><th>Full name</th><th>Account status</th><th>Data origin</th></tr></thead>
            <tbody><tr v-for="teacher in filteredParaTeachers" :key="teacher.id">
              <td><strong>{{ teacher.user_code }}</strong></td><td>{{ teacher.full_name }}</td>
              <td><span class="teachers-status" :class="`is-${teacher.status.toLowerCase()}`">{{ teacher.status }}</span></td>
              <td><span class="teachers-origin">{{ teacher.data_origin }}</span></td>
            </tr></tbody>
          </table>
        </div>
      </template>
    </section>

    <section v-else class="teachers-panel" aria-labelledby="school-teachers-title">
      <div class="teachers-panel-heading">
        <div>
          <p class="teachers-eyebrow">School workforce</p>
          <h3 id="school-teachers-title">School Teachers</h3>
          <p class="teachers-muted">School-based teachers and their active subject assignments.</p>
        </div>
        <strong class="teachers-count">{{ schoolTeachers.length }} total</strong>
      </div>

      <div v-if="!canViewSchoolTeachers" class="teachers-restricted" role="status">
        You do not have permission to view School Teachers.
      </div>
      <template v-else>
        <p v-if="schoolLookupError" class="teachers-notice" role="status">{{ schoolLookupError }}</p>
        <div class="teachers-filters">
          <label>Search<input v-model="schoolSearch" type="search" placeholder="Teacher name" /></label>
          <label>School<select v-model="schoolFilter" :disabled="!schools.length"><option value="ALL">All schools</option><option v-for="school in schoolOptions" :key="school.id" :value="school.id">{{ school.school_name }}</option></select></label>
          <label>Status<select v-model="schoolStatus"><option value="ALL">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select></label>
          <button class="teachers-secondary" type="button" @click="clearSchoolFilters">Clear filters</button>
        </div>
        <p v-if="schoolError" class="teachers-error" role="alert">{{ schoolError }} <button class="teachers-link" type="button" @click="retryActiveTab">Retry</button></p>
        <p v-else-if="schoolLoading" class="teachers-muted" role="status">Loading School Teachers…</p>
        <div v-else-if="!schoolTeachers.length" class="teachers-empty">No School Teacher records are available.</div>
        <div v-else-if="!filteredSchoolTeachers.length" class="teachers-empty">No School Teachers match these filters.</div>
        <div v-else class="teachers-table-wrap">
          <table class="teachers-table">
            <thead><tr><th>Teacher name</th><th>School</th><th>Active subjects</th><th>Status</th></tr></thead>
            <tbody><tr v-for="teacher in filteredSchoolTeachers" :key="teacher.id">
              <td><strong>{{ teacher.full_name }}</strong></td>
              <td>{{ schoolById.get(teacher.school_id) ?? 'School name unavailable' }}</td>
              <td>{{ teacher.subjects.length ? teacher.subjects.join(', ') : 'No active subjects' }}</td>
              <td><span class="teachers-status" :class="`is-${teacher.status.toLowerCase()}`">{{ teacher.status }}</span></td>
            </tr></tbody>
          </table>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.teachers-directory { display: grid; gap: 20px; }
.teachers-header, .teachers-panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.teachers-header h2, .teachers-panel h3 { margin: 0; color: var(--ov-text-primary); }
.teachers-header h2 { font-size: 30px; }
.teachers-header p:last-child, .teachers-muted { margin: 6px 0 0; color: var(--ov-text-muted); }
.teachers-eyebrow { margin: 0 0 4px; color: var(--ov-brand); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
.teachers-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--ov-border); }
.teachers-tab { padding: 11px 16px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--ov-text-muted); cursor: pointer; font-weight: 600; }
.teachers-tab.is-active { border-bottom-color: var(--ov-brand); color: var(--ov-text-primary); }
.teachers-panel { display: grid; gap: 20px; padding: 20px; border: 1px solid var(--ov-border); border-radius: 12px; background: var(--ov-bg-surface); }
.teachers-count { color: var(--ov-text-muted); font-size: 13px; white-space: nowrap; }
.teachers-filters { display: grid; grid-template-columns: minmax(180px, 1.5fr) repeat(2, minmax(140px, 1fr)) auto; align-items: end; gap: 12px; }
.teachers-filters label { display: grid; gap: 6px; color: var(--ov-text-secondary); font-size: 13px; }
.teachers-filters input, .teachers-filters select { box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid var(--ov-border); border-radius: 6px; background: var(--ov-bg-page); color: var(--ov-text-primary); }
.teachers-table-wrap { overflow-x: auto; }
.teachers-table { width: 100%; min-width: 620px; border-collapse: collapse; color: var(--ov-text-primary); font-size: 13px; }
.teachers-table th, .teachers-table td { padding: 13px 10px; border-bottom: 1px solid var(--ov-border-subtle); text-align: left; }
.teachers-table th { color: var(--ov-text-muted); font-size: 11px; text-transform: uppercase; }
.teachers-status, .teachers-origin { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 11px; }
.teachers-status.is-active { color: var(--ov-tag-accent-fg); background: var(--ov-tag-accent-bg); }
.teachers-status.is-disabled, .teachers-status.is-inactive, .teachers-origin { color: var(--ov-text-muted); background: var(--ov-bg-surface-subtle); }
.teachers-secondary { padding: 10px 14px; border: 0; border-radius: 6px; background: var(--ov-bg-surface-subtle); color: var(--ov-text-primary); cursor: pointer; font-weight: 600; }
.teachers-link { padding: 0; border: 0; background: none; color: var(--ov-brand); cursor: pointer; font-weight: 600; }
.teachers-error { margin: 0; color: var(--ov-tag-terra-fg); }
.teachers-notice, .teachers-restricted { margin: 0; padding: 12px; border: 1px solid var(--ov-border); border-radius: 8px; color: var(--ov-text-muted); background: var(--ov-bg-surface-subtle); }
.teachers-empty { padding: 28px; border-radius: 8px; background: var(--ov-bg-surface-subtle); color: var(--ov-text-muted); text-align: center; }
@media (max-width: 800px) { .teachers-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .teachers-header, .teachers-panel-heading { flex-direction: column; } .teachers-filters { grid-template-columns: 1fr; } .teachers-panel { padding: 16px; } .teachers-tabs { overflow-x: auto; } }
</style>
