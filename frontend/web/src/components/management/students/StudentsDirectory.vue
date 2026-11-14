<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { CurrentUser } from '../../../services/auth'
import { listClassDivisions, type ClassDivision } from '../../../services/classDivisions'
import { listSchools, type School } from '../../../services/schools'
import {
  createStudent,
  getStudent,
  listStudents,
  updateStudent,
  type Student,
  type StudentCreateInput,
  type StudentStatus,
} from '../../../services/students'
import ManagementModal from '../schools/ManagementModal.vue'

const props = defineProps<{ currentUser: CurrentUser | null }>()

const canCreate = computed(() => props.currentUser?.permissions.includes('student.create') ?? false)
const canUpdate = computed(() => props.currentUser?.permissions.includes('student.update') ?? false)

const students = ref<Student[]>([])
const schools = ref<School[]>([])
const divisions = ref<ClassDivision[]>([])
const loading = ref(true)
const loadingOptions = ref(true)
const error = ref('')
const optionsError = ref('')
const search = ref('')
const statusFilter = ref<'ALL' | StudentStatus>('ALL')
const originFilter = ref('ALL')
const selectedSchoolId = ref('')
const selectedDivisionId = ref('')
const modal = ref<'create' | 'edit' | 'view' | null>(null)
const selected = ref<Student | null>(null)
const saving = ref(false)
const formError = ref('')
const formStudentCode = ref('')
const formName = ref('')
const formGender = ref('')
const formRollNo = ref<number | null>(null)
const formSchoolId = ref('')
const formDivisionId = ref('')
const formStatus = ref<StudentStatus>('ACTIVE')

const schoolById = computed(() => new Map(schools.value.map(school => [school.id, school])))
const divisionById = computed(() => new Map(divisions.value.map(division => [division.id, division])))
const originOptions = computed(() => [...new Set(students.value.map(student => student.data_origin))].sort())
const formDivisions = computed(() => divisions.value
  .filter(division => !formSchoolId.value || division.school_id === formSchoolId.value)
  .sort((a, b) => a.class_level - b.class_level || a.division.localeCompare(b.division)))
const filteredStudents = computed(() => {
  const term = search.value.trim().toLowerCase()
  return students.value.filter(student => {
    const matchesSearch = !term ||
      student.student_code.toLowerCase().includes(term) ||
      student.full_name.toLowerCase().includes(term)
    const matchesStatus = statusFilter.value === 'ALL' || student.status === statusFilter.value
    const matchesOrigin = originFilter.value === 'ALL' || student.data_origin === originFilter.value
    return matchesSearch && matchesStatus && matchesOrigin
  })
})
const productionCount = computed(() => students.value.filter(student => student.data_origin === 'PRODUCTION').length)
const activeCount = computed(() => students.value.filter(student => student.status === 'ACTIVE').length)
const inactiveCount = computed(() => students.value.filter(student => student.status === 'INACTIVE').length)
const isFiltered = computed(() => Boolean(search.value || selectedSchoolId.value || selectedDivisionId.value ||
  statusFilter.value !== 'ALL' || originFilter.value !== 'ALL'))

function schoolName(student: Student) {
  const division = divisionById.value.get(student.class_division_id)
  return schoolById.value.get(division?.school_id ?? '')?.school_name ?? 'Unavailable'
}

function divisionLabel(student: Student) {
  const division = divisionById.value.get(student.class_division_id)
  return division ? `Class ${division.class_level} · ${division.division}` : 'Unavailable'
}

async function loadStudents() {
  loading.value = true
  error.value = ''
  try {
    students.value = await listStudents({
      school_id: selectedSchoolId.value || undefined,
      class_division_id: selectedDivisionId.value || undefined,
    })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Unable to load students.'
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  loadingOptions.value = true
  optionsError.value = ''
  const [schoolResult, divisionResult] = await Promise.allSettled([
    listSchools(),
    listClassDivisions(),
  ])
  if (schoolResult.status === 'fulfilled') schools.value = schoolResult.value
  else optionsError.value = 'School names are unavailable. Student records remain accessible.'
  if (divisionResult.status === 'fulfilled') divisions.value = divisionResult.value
  else optionsError.value = optionsError.value
    ? `${optionsError.value} Class labels are unavailable.`
    : 'Class labels are unavailable. Student records remain accessible.'
  loadingOptions.value = false
}

function clearFilters() {
  search.value = ''
  selectedSchoolId.value = ''
  selectedDivisionId.value = ''
  statusFilter.value = 'ALL'
  originFilter.value = 'ALL'
}

function resetForm() {
  formStudentCode.value = ''
  formName.value = ''
  formGender.value = ''
  formRollNo.value = null
  formSchoolId.value = ''
  formDivisionId.value = ''
  formStatus.value = 'ACTIVE'
  formError.value = ''
}

function openCreate() {
  selected.value = null
  resetForm()
  modal.value = 'create'
}

function openEdit(student: Student) {
  selected.value = student
  populateForm(student)
  formError.value = ''
  modal.value = 'edit'
}

function populateForm(student: Student) {
  formStudentCode.value = student.student_code
  formName.value = student.full_name
  formGender.value = student.gender
  formRollNo.value = student.roll_no
  formDivisionId.value = student.class_division_id
  formSchoolId.value = divisionById.value.get(student.class_division_id)?.school_id ?? ''
  formStatus.value = student.status
}

async function openView(student: Student) {
  formError.value = ''
  try {
    selected.value = await getStudent(student.id)
    populateForm(selected.value)
    modal.value = 'view'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Unable to load the student.'
  }
}

function closeModal() {
  if (!saving.value) modal.value = null
}

async function submit() {
  const name = formName.value.trim()
  const gender = formGender.value.trim()
  if (!name || !gender || !formRollNo.value || (modal.value === 'create' && !formStudentCode.value.trim())) {
    formError.value = 'Complete all required fields before saving.'
    return
  }
  if (formRollNo.value < 1 || formRollNo.value > 999) {
    formError.value = 'Roll number must be between 1 and 999.'
    return
  }
  if (modal.value === 'create' && !formDivisionId.value) {
    formError.value = 'Select a class and division.'
    return
  }

  saving.value = true
  formError.value = ''
  try {
    if (selected.value) {
      await updateStudent(selected.value.id, {
        full_name: name,
        gender,
        roll_no: formRollNo.value,
        status: formStatus.value,
      })
    } else {
      const input: StudentCreateInput = {
        student_code: formStudentCode.value.trim(),
        full_name: name,
        gender,
        roll_no: formRollNo.value,
        class_division_id: formDivisionId.value,
        status: formStatus.value,
      }
      await createStudent(input)
    }
    modal.value = null
    await loadStudents()
  } catch (reason) {
    formError.value = reason instanceof Error ? reason.message : 'Unable to save the student.'
  } finally {
    saving.value = false
  }
}

watch(selectedSchoolId, () => {
  selectedDivisionId.value = ''
  void loadStudents()
})
watch(selectedDivisionId, () => void loadStudents())
watch(formSchoolId, () => {
  if (formDivisionId.value && !formDivisions.value.some(division => division.id === formDivisionId.value)) {
    formDivisionId.value = ''
  }
})

onMounted(() => {
  void loadOptions()
  void loadStudents()
})
</script>

<template>
  <div class="students-directory">
    <header class="students-header">
      <div>
        <p class="students-eyebrow">Management</p>
        <h2>Students Directory</h2>
        <p>Review authorised student records across schools and class divisions.</p>
      </div>
      <button v-if="canCreate" class="students-primary" type="button" @click="openCreate">
        <span class="material-symbols-outlined" aria-hidden="true">person_add</span>
        Add student
      </button>
    </header>

    <p v-if="optionsError" class="students-notice" role="status">{{ optionsError }}</p>
    <section class="students-summary" aria-label="Student summary">
      <article class="students-card"><span>Total students</span><strong>{{ students.length }}</strong><small>Loaded
          records</small></article>
      <article class="students-card"><span>Active students</span><strong>{{ activeCount }}</strong><small>Loaded
          records</small></article>
      <article class="students-card"><span>Inactive students</span><strong>{{ inactiveCount }}</strong><small>Loaded
          records</small></article>
      <article class="students-card students-card--origin"><span>Production records</span><strong>{{ productionCount
          }}</strong><small>Origin is distinguished below</small></article>
    </section>

    <section class="students-panel" aria-labelledby="students-directory-title">
      <div class="students-panel-heading">
        <div>
          <p class="students-eyebrow">Directory</p>
          <h3 id="students-directory-title">Student records</h3>
        </div>
        <button class="students-secondary" type="button" :disabled="!isFiltered" @click="clearFilters">Clear
          filters</button>
      </div>

      <div class="students-filters">
        <label>Search
          <input v-model="search" type="search" placeholder="Student code or name" />
        </label>
        <label>School
          <select v-model="selectedSchoolId" :disabled="loadingOptions">
            <option value="">All schools</option>
            <option v-for="school in schools" :key="school.id" :value="school.id">{{ school.school_name }}</option>
          </select>
        </label>
        <label>Class/division
          <select v-model="selectedDivisionId" :disabled="loadingOptions || !divisions.length">
            <option value="">All classes</option>
            <option
              v-for="division in divisions.filter(item => !selectedSchoolId || item.school_id === selectedSchoolId)"
              :key="division.id" :value="division.id">Class {{ division.class_level }} · {{ division.division }}
            </option>
          </select>
        </label>
        <label>Status
          <select v-model="statusFilter">
            <option value="ALL">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
        </label>
        <label>Data origin
          <select v-model="originFilter">
            <option value="ALL">All origins</option>
            <option v-for="origin in originOptions" :key="origin" :value="origin">{{ origin }}</option>
          </select>
        </label>
      </div>

      <p v-if="error" class="students-error" role="alert">
        {{ error }}
        <button class="students-link" type="button" @click="loadStudents">Retry</button>
      </p>
      <p v-if="loading" class="students-muted" role="status">Loading students…</p>
      <div v-else-if="!students.length" class="students-empty">
        {{ isFiltered ? 'No students match the selected filters.' : 'No student records are available.' }}
      </div>
      <div v-else-if="!filteredStudents.length" class="students-empty">No students match your search and status filters.
      </div>
      <div v-else class="students-table-wrap">
        <table class="students-table">
          <thead>
            <tr>
              <th class="students-frozen">Student code</th>
              <th>Student name</th>
              <th>Gender</th>
              <th>Roll</th>
              <th>School</th>
              <th>Class/division</th>
              <th>Status</th>
              <th>Origin</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="student in filteredStudents" :key="student.id">
              <td class="students-frozen"><strong>{{ student.student_code }}</strong></td>
              <td>{{ student.full_name }}</td>
              <td>{{ student.gender }}</td>
              <td>{{ student.roll_no }}</td>
              <td>{{ schoolName(student) }}</td>
              <td>{{ divisionLabel(student) }}</td>
              <td><span class="students-status" :class="`is-${student.status.toLowerCase()}`">{{ student.status
                  }}</span></td>
              <td><span class="students-origin">{{ student.data_origin }}</span></td>
              <td class="students-actions">
                <button class="students-link" type="button" @click="openView(student)">View</button>
                <button v-if="canUpdate" class="students-link" type="button" @click="openEdit(student)">Edit</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <ManagementModal v-if="modal"
      :title="modal === 'create' ? 'Add student' : modal === 'edit' ? 'Edit student' : 'Student details'" :busy="saving"
      @close="closeModal">
      <form class="students-form" @submit.prevent="submit">
        <label>Student code
          <input v-model.trim="formStudentCode" maxlength="30" required :readonly="modal !== 'create'" />
        </label>
        <label>Full name
          <input v-model.trim="formName" maxlength="150" required :readonly="modal === 'view'" />
        </label>
        <label>Gender
          <input v-model.trim="formGender" maxlength="20" required :readonly="modal === 'view'" />
        </label>
        <label>Roll number
          <input v-model.number="formRollNo" type="number" min="1" max="999" required :readonly="modal === 'view'" />
        </label>
        <label>School
          <select v-model="formSchoolId" :disabled="modal !== 'create'" required>
            <option value="">Select school</option>
            <option v-for="school in schools" :key="school.id" :value="school.id">{{ school.school_name }}</option>
          </select>
        </label>
        <label>Class/division
          <select v-model="formDivisionId" :disabled="modal !== 'create' || !formSchoolId" required>
            <option value="">Select class/division</option>
            <option v-for="division in formDivisions" :key="division.id" :value="division.id">
              Class {{ division.class_level }} · {{ division.division }}
            </option>
          </select>
        </label>
        <label>Status
          <select v-model="formStatus" :disabled="modal === 'view'">
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
        </label>
        <p v-if="modal !== 'create'" class="students-readonly">Class/division assignment is read-only through this
          workflow.</p>
        <p v-if="formError" class="students-error" role="alert">{{ formError }}</p>
        <div class="students-form-actions">
          <button type="button" class="students-secondary" :disabled="saving" @click="closeModal">Close</button>
          <button v-if="modal !== 'view'" type="submit" class="students-primary" :disabled="saving">
            {{ saving ? 'Saving…' : modal === 'create' ? 'Create student' : 'Save changes' }}
          </button>
        </div>
      </form>
    </ManagementModal>
  </div>
</template>

<style scoped>
.students-directory {
  display: grid;
  gap: 20px;
}

.students-header,
.students-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.students-header h2,
.students-panel h3 {
  margin: 0;
  color: var(--ov-text-primary);
}

.students-header h2 {
  font-size: 30px;
}

.students-header p:last-child,
.students-muted,
.students-readonly {
  margin: 6px 0 0;
  color: var(--ov-text-muted);
}

.students-eyebrow {
  margin: 0 0 4px;
  color: var(--ov-brand);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.students-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.students-card,
.students-panel {
  padding: 20px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
}

.students-card {
  display: grid;
  gap: 6px;
}

.students-card span,
.students-card small {
  color: var(--ov-text-muted);
  font-size: 12px;
}

.students-card strong {
  color: var(--ov-text-primary);
  font-size: 28px;
}

.students-panel {
  display: grid;
  gap: 20px;
}

.students-filters {
  display: grid;
  grid-template-columns: minmax(180px, 1.5fr) repeat(4, minmax(130px, 1fr));
  gap: 12px;
}

.students-filters label,
.students-form label {
  display: grid;
  gap: 6px;
  color: var(--ov-text-secondary);
  font-size: 13px;
}

.students-filters input,
.students-filters select,
.students-form input,
.students-form select {
  box-sizing: border-box;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--ov-border);
  border-radius: 6px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
}

.students-table-wrap {
  overflow-x: auto;
}

.students-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  color: var(--ov-text-primary);
  font-size: 13px;
}

.students-table th,
.students-table td {
  padding: 13px 10px;
  border-bottom: 1px solid var(--ov-border-subtle);
  text-align: left;
  white-space: nowrap;
}

.students-table th {
  color: var(--ov-text-muted);
  font-size: 11px;
  text-transform: uppercase;
}

.students-frozen {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--ov-bg-surface);
}

.students-status,
.students-origin {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.students-status.is-active {
  color: var(--ov-tag-accent-fg);
  background: var(--ov-tag-accent-bg);
}

.students-status.is-inactive,
.students-origin {
  color: var(--ov-text-muted);
  background: var(--ov-bg-surface-subtle);
}

.students-actions {
  display: flex;
  gap: 12px;
}

.students-link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--ov-brand);
  cursor: pointer;
  font-weight: 600;
}

.students-primary,
.students-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 600;
}

.students-primary {
  color: var(--ov-button-primary-text);
  background: var(--ov-brand);
}

.students-primary:hover:not(:disabled) {
  background: var(--ov-brand-hover);
}

.students-primary:disabled,
.students-secondary:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.students-secondary {
  color: var(--ov-text-primary);
  background: var(--ov-bg-surface-subtle);
}

.students-empty {
  padding: 28px;
  color: var(--ov-text-muted);
  text-align: center;
  background: var(--ov-bg-surface-subtle);
  border-radius: 8px;
}

.students-error {
  margin: 0;
  color: var(--ov-tag-terra-fg);
}

.students-notice {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  color: var(--ov-text-muted);
  background: var(--ov-bg-surface);
  font-size: 13px;
}

.students-form {
  display: grid;
  gap: 15px;
}

.students-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 5px;
}

@media (max-width: 1000px) {
  .students-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .students-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {

  .students-header,
  .students-panel-heading {
    flex-direction: column;
  }

  .students-header .students-primary,
  .students-header .students-secondary {
    width: 100%;
  }

  .students-summary,
  .students-filters {
    grid-template-columns: 1fr;
  }

  .students-card,
  .students-panel {
    padding: 16px;
  }
}
</style>
