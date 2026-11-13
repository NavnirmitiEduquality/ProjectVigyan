<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createSchool, getSchool, listSchools, updateSchool, type School, type SchoolStatus } from '../../../services/schools'
import ManagementModal from './ManagementModal.vue'

const schools = ref<School[]>([])
const props = withDefaults(defineProps<{ canCreate?: boolean; canUpdate?: boolean }>(), { canCreate: false, canUpdate: false })
const loading = ref(true)
const error = ref('')
const search = ref('')
const modal = ref<'create' | 'edit' | 'view' | null>(null)
const saving = ref(false)
const selected = ref<School | null>(null)
const code = ref('')
const name = ref('')
const status = ref<SchoolStatus>('ACTIVE')

const filteredSchools = computed(() => {
  const term = search.value.trim().toLowerCase()
  return term
    ? schools.value.filter((school) =>
      school.school_name.toLowerCase().includes(term) || school.school_code.toLowerCase().includes(term))
    : schools.value
})

async function load() {
  loading.value = true
  try {
    schools.value = await listSchools()
    error.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to load schools.'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  selected.value = null
  code.value = ''
  name.value = ''
  status.value = 'ACTIVE'
  modal.value = 'create'
}

function openEdit(school: School) {
  selected.value = school
  code.value = school.school_code
  name.value = school.school_name
  status.value = school.status
  modal.value = 'edit'
}

async function openView(school: School) {
  try {
    selected.value = await getSchool(school.id)
    code.value = selected.value.school_code
    name.value = selected.value.school_name
    status.value = selected.value.status
    modal.value = 'view'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to load the school.'
  }
}

async function submit() {
  const schoolName = name.value.trim()
  const schoolCode = code.value.trim()
  if (!schoolName || (modal.value === 'create' && !schoolCode)) return

  saving.value = true
  error.value = ''
  try {
    if (selected.value) {
      await updateSchool(selected.value.id, { school_name: schoolName, status: status.value })
    } else {
      await createSchool({ school_code: schoolCode, school_name: schoolName, status: status.value })
    }
    modal.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to save school.'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="schools-panel" aria-labelledby="schools-directory-title">
    <div class="schools-panel-heading">
      <div>
        <p class="schools-eyebrow">Directory</p>
        <h2 id="schools-directory-title">Registered Schools</h2>
        <p class="schools-muted">Manage the schools available to authorised operations users.</p>
      </div>
      <button v-if="props.canCreate" class="schools-primary" type="button" @click="openCreate">Add school</button>
    </div>
    <p v-if="error" class="schools-error" role="alert">{{ error }}</p>
    <label class="schools-search">Search by school name or code
      <input v-model="search" type="search" placeholder="Search schools" />
    </label>
    <p v-if="loading" class="schools-muted" role="status">Loading schools…</p>
    <div v-else-if="!schools.length" class="schools-empty">No schools are registered.</div>
    <div v-else-if="!filteredSchools.length" class="schools-empty">No schools match your search.</div>
    <div v-else class="schools-table-wrap">
      <table class="schools-table">
        <thead>
          <tr>
            <th>School name</th>
            <th>School code</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="school in filteredSchools" :key="school.id">
            <td><strong>{{ school.school_name }}</strong></td>
            <td>{{ school.school_code }}</td>
            <td><span class="schools-status" :class="`is-${school.status.toLowerCase()}`">{{ school.status }}</span>
            </td>
            <td class="schools-row-actions">
              <button class="schools-link" type="button" @click="openView(school)">View</button>
              <button v-if="props.canUpdate" class="schools-link" type="button" @click="openEdit(school)">Edit</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ManagementModal v-if="modal"
      :title="modal === 'create' ? 'Add school' : modal === 'edit' ? 'Edit school' : 'View school'" :busy="saving"
      @close="modal = null">
      <form class="schools-form" @submit.prevent="submit">
        <label>School code<input v-model.trim="code" maxlength="20" required :readonly="modal !== 'create'" /></label>
        <label>School name<input v-model.trim="name" maxlength="200" required :readonly="modal === 'view'" /></label>
        <label>Status<select v-model="status" :disabled="modal === 'view'">
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select></label>
        <div class="schools-actions">
          <button type="button" class="schools-secondary" :disabled="saving" @click="modal = null">Close</button>
          <button v-if="modal !== 'view'" type="submit" class="schools-primary" :disabled="saving">{{ saving ? 'Saving…'
            : 'Save school' }}</button>
        </div>
      </form>
    </ManagementModal>
  </section>
</template>

<style scoped>
.schools-panel {
  display: grid;
  gap: 20px;
  padding: 24px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
}

.schools-panel-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
}

.schools-panel h2 {
  margin: 0;
  font-size: 24px;
}

.schools-eyebrow {
  margin: 0 0 4px;
  color: var(--ov-brand);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.schools-muted {
  margin: 6px 0 0;
  color: var(--ov-text-muted);
  font-size: 13px;
}

.schools-error {
  margin: 0;
  color: var(--ov-tag-terra-fg);
}

.schools-search {
  display: grid;
  gap: 6px;
  max-width: 420px;
  color: var(--ov-text-secondary);
  font-size: 13px;
}

.schools-search input,
.schools-form input,
.schools-form select {
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid var(--ov-border);
  border-radius: 6px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
}

.schools-empty {
  padding: 28px;
  color: var(--ov-text-muted);
  text-align: center;
  background: var(--ov-bg-surface-subtle);
  border-radius: 8px;
}

.schools-table-wrap {
  overflow-x: auto;
}

.schools-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.schools-table th,
.schools-table td {
  padding: 14px 12px;
  border-bottom: 1px solid var(--ov-border-subtle);
  text-align: left;
}

.schools-table th {
  color: var(--ov-text-muted);
  font-size: 11px;
  text-transform: uppercase;
}

.schools-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.schools-status {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.is-active {
  color: var(--ov-tag-accent-fg);
  background: var(--ov-tag-accent-bg);
}

.is-inactive {
  color: var(--ov-text-muted);
  background: var(--ov-bg-surface-subtle);
}

.schools-primary,
.schools-secondary {
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 600;
}

.schools-primary {
  color: var(--ov-button-primary-text);
  background: var(--ov-brand);
  transition: background-color 160ms ease, opacity 160ms ease;
}

.schools-primary:hover:not(:disabled) {
  background: var(--ov-brand-hover);
}

.schools-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.schools-secondary {
  color: var(--ov-text-primary);
  background: var(--ov-bg-surface-subtle);
}

.schools-link {
  border: 0;
  background: none;
  color: var(--ov-brand);
  cursor: pointer;
  font-weight: 600;
}

.schools-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}

.schools-form {
  display: grid;
  gap: 16px;
}

.schools-form label {
  display: grid;
  gap: 6px;
  color: var(--ov-text-secondary);
  font-size: 13px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}

@media (max-width: 600px) {
  .schools-panel {
    padding: 16px;
  }

  .schools-panel-heading {
    flex-direction: column;
  }

  .schools-primary {
    width: 100%;
  }
}
</style>
