<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { listSchools, type School } from '../../../services/schools'
import type { CurrentUser } from '../../../services/auth'
import SchoolsDirectory from './SchoolsDirectory.vue'
import ClassDivisionsPanel from './ClassDivisionsPanel.vue'

const schools = ref<School[]>([])
const props = defineProps<{ currentUser: CurrentUser | null }>()
const canCreate = computed(() => props.currentUser?.permissions.includes('school.create') ?? false)
const canUpdate = computed(() => props.currentUser?.permissions.includes('school.update') ?? false)
const loading = ref(true)
const error = ref('')
async function load() {
  loading.value = true
  try { schools.value = await listSchools(); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load schools.' }
  finally { loading.value = false }
}
watch(() => schools.value.length, () => undefined)
void load()
</script>

<template>
  <div class="schools-view">
    <header class="schools-view-header">
      <div>
        <p class="schools-eyebrow">Management</p>
        <h2>Schools &amp; Classes</h2>
        <p>Authorised directory and class-division workflows.</p>
      </div>
    </header>
    <p v-if="error" class="schools-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="schools-muted">Loading directory…</p>
    <template v-else>
      <SchoolsDirectory :can-create="canCreate" :can-update="canUpdate" />
      <ClassDivisionsPanel :schools="schools"
        :can-create="props.currentUser?.permissions.includes('class.create') ?? false"
        :can-update="props.currentUser?.permissions.includes('class.update') ?? false" />
    </template>

  </div>
</template>

<style scoped>
.schools-view {
  display: grid;
  gap: 20px;
}

.schools-view-header {
  padding: 4px 0;
}

.schools-view-header h2 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 30px;
}

.schools-view-header p:last-child {
  margin: 6px 0 0;
  color: var(--ov-text-muted);
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
  color: var(--ov-text-muted);
}

.schools-error {
  color: var(--ov-tag-terra-fg);
}
</style>
