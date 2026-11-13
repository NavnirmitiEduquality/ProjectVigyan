<script setup lang="ts">
import { ref, watch } from 'vue'
import { createClassDivision, getClassDivision, listClassDivisions, updateClassDivision, type ClassDivision } from '../../../services/classDivisions'
import type { School } from '../../../services/schools'
import ManagementModal from './ManagementModal.vue'

const props = withDefaults(defineProps<{ schools: School[]; canCreate?: boolean; canUpdate?: boolean }>(), { canCreate: false, canUpdate: false })
const divisions = ref<ClassDivision[]>([])
const selectedSchool = ref('')
const loading = ref(false)
const error = ref('')
const modal = ref<'create' | 'edit' | 'view' | null>(null)
const editing = ref<ClassDivision | null>(null)
const saving = ref(false)
const level = ref<5 | 6 | 7>(5)
const division = ref('')
const status = ref<'ACTIVE' | 'INACTIVE'>('ACTIVE')
let requestId = 0

async function load() {
  const currentRequest = ++requestId
  loading.value = true
  try {
    const result = await listClassDivisions(selectedSchool.value || undefined)
    if (currentRequest === requestId) divisions.value = result
    error.value = ''
  }
  catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load class divisions.' }
  finally { loading.value = false }
}
function openCreate() { editing.value = null; level.value = 5; division.value = ''; status.value = 'ACTIVE'; modal.value = 'create' }
function openEdit(item: ClassDivision) { editing.value = item; level.value = item.class_level; division.value = item.division; status.value = item.status; modal.value = 'edit' }
async function openView(item: ClassDivision) {
  try {
    editing.value = await getClassDivision(item.id)
    level.value = editing.value.class_level
    division.value = editing.value.division
    status.value = editing.value.status
    modal.value = 'view'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to load the class division.'
  }
}
async function submit() {
  if (!division.value.trim() || (!editing.value && !selectedSchool.value)) return
  saving.value = true
  try {
    if (editing.value) await updateClassDivision(editing.value.id, { division: division.value.trim(), status: status.value })
    else await createClassDivision({ school_id: selectedSchool.value, class_level: level.value, division: division.value.trim(), status: status.value })
    modal.value = null; await load()
  } catch (e) { error.value = e instanceof Error ? e.message : 'Unable to save class division.' }
  finally { saving.value = false }
}
watch(() => props.schools, (schools) => {
  if (!selectedSchool.value && schools[0]) selectedSchool.value = schools[0].id
  void load()
}, { immediate: true })
</script>

<template>
  <section class="schools-panel" aria-labelledby="divisions-title">
    <div class="schools-panel-heading">
      <div>
        <p class="schools-eyebrow">Class register</p>
        <h2 id="divisions-title">Class divisions</h2>
        <p class="schools-muted">Keep class levels and divisions aligned with the selected school.</p>
      </div><button v-if="props.canCreate" class="schools-primary" type="button" :disabled="!schools.length"
        @click="openCreate">Add division</button>
    </div>
    <div class="division-toolbar"><label>Selected school<select v-model="selectedSchool" @change="load" required>
          <option value="" disabled>Select a school</option>
          <option v-for="school in schools" :key="school.id" :value="school.id">{{ school.school_name }}</option>
        </select></label></div>
    <p v-if="error" class="schools-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="schools-muted">Loading divisions…</p>
    <div v-else-if="!divisions.length" class="schools-empty">No class divisions are available for the selected school.
    </div>
    <div v-else class="schools-table-wrap">
      <table class="schools-table">
        <thead>
          <tr>
            <th>Class</th>
            <th>Division</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in divisions" :key="item.id">
            <td>Class {{ item.class_level }}</td>
            <td>{{ item.division }}</td>
            <td><span class="schools-status" :class="`is-${item.status.toLowerCase()}`">{{ item.status }}</span></td>
            <td class="schools-row-actions"><button class="schools-link" type="button"
                @click="openView(item)">View</button><button v-if="props.canUpdate" class="schools-link" type="button"
                @click="openEdit(item)">Edit</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <ManagementModal v-if="modal"
      :title="modal === 'create' ? 'Add class division' : modal === 'edit' ? 'Edit class division' : 'View class division'"
      :busy="saving" @close="modal = null">
      <form class="schools-form" @submit.prevent="submit"><label>School<select v-model="selectedSchool" required
            :disabled="modal !== 'create'">
            <option value="" disabled>Select a school</option>
            <option v-for="school in schools" :key="school.id" :value="school.id">{{ school.school_name }}</option>
          </select></label><label>Class level<select v-model.number="level" :disabled="modal !== 'create'">
            <option :value="5">Class 5</option>
            <option :value="6">Class 6</option>
            <option :value="7">Class 7</option>
          </select></label><label>Division<input v-model.trim="division" maxlength="20" required
            :readonly="modal === 'view'" /></label><label>Status<select v-model="status" :disabled="modal === 'view'">
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select></label>
        <div class="schools-actions"><button type="button" class="schools-secondary" :disabled="saving"
            @click="modal = null">Close</button><button v-if="modal !== 'view'" type="submit" class="schools-primary"
            :disabled="saving">{{ saving ? 'Saving…' : 'Save division' }}</button></div>
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

.schools-empty {
  padding: 28px;
  color: var(--ov-text-muted);
  text-align: center;
  background: var(--ov-bg-surface-subtle);
  border-radius: 8px;
}

.division-toolbar label,
.schools-form label {
  display: grid;
  gap: 6px;
  color: var(--ov-text-secondary);
  font-size: 13px;
}

.division-toolbar select,
.schools-form input,
.schools-form select {
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid var(--ov-border);
  border-radius: 6px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
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

.schools-status {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.is-active {
  color: var(--ov-tag-teal-fg);
  background: var(--ov-tag-teal-bg);
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

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}
</style>
