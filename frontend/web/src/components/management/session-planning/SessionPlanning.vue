<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { CurrentUser } from '../../../services/auth'
import { listClassDivisions, type ClassDivision } from '../../../services/classDivisions'
import { listParaTeachers, type ParaTeacher } from '../../../services/teachers'
import ManagementModal from '../schools/ManagementModal.vue'
import {
  createItem,
  createTeachingSession,
  createWeek,
  deleteItem,
  getContent,
  getWeek,
  saveContent,
  updateItem,
  validateItem,
  deleteAttachment,
  downloadAttachment,
  listAttachments,
  uploadAttachment,
  type SessionPlanContent,
  type SessionPlanItem,
  type SessionPlanAttachment,
  type SessionPlanTeachingSession,
  type SessionPlanWeek,
} from '../../../services/sessionPlans'

const route = useRoute()
const MIN_WEEKLY_ITEMS = 6
const props = defineProps<{ currentUser: CurrentUser | null }>()

const hasViewAll = computed(() =>
  props.currentUser?.permissions.includes('session_plan.view_all') ?? false,
)

const hasPlanningActions = computed(() =>
  canValidate.value ||
  canLinkSession.value ||
  canUpdate.value ||
  canDelete.value
)

const canView = computed(() =>
  props.currentUser?.permissions.includes('session_plan.view') ?? false,
)

const selectedTeacherId = ref(props.currentUser?.user_id ?? '')
const isOwnPlan = computed(() =>
  selectedTeacherId.value === props.currentUser?.user_id,
)

const canCreate = computed(() =>
  isOwnPlan.value &&
  (props.currentUser?.permissions.includes('session_plan.create') ?? false),
)
const canUpdate = computed(() =>
  isOwnPlan.value &&
  (props.currentUser?.permissions.includes('session_plan.update') ?? false),
)
const canDelete = computed(() =>
  isOwnPlan.value &&
  (props.currentUser?.permissions.includes('session_plan.delete') ?? false),
)
const canLinkSession = computed(() =>
  isOwnPlan.value &&
  (props.currentUser?.permissions.includes('session.create') ?? false),
)
const canValidate = canUpdate
const canViewClasses = computed(() =>
  props.currentUser?.permissions.includes('class.view') ?? false,
)

const teachers = ref<ParaTeacher[]>([])
const teachersLoading = ref(false)
const teachersError = ref('')
const weeklyMinimumMet = computed(() =>
  items.value.length >= MIN_WEEKLY_ITEMS,
)
const weekStart = ref(toDateInput(getMonday(new Date())))
let weekRequestId = 0
const week = ref<SessionPlanWeek | null>(null)
const items = ref<SessionPlanItem[]>([])
const divisions = ref<ClassDivision[]>([])
const loading = ref(false)
const loadingClasses = ref(false)
const error = ref('')
const classError = ref('')
const missingWeek = ref(false)
const modal = ref<'create' | 'edit' | 'content' | null>(null)
const selectedItem = ref<SessionPlanItem | null>(null)
const saving = ref(false)
const formError = ref('')
const formDate = ref('')
const formDivisionId = ref('')
const formSequence = ref(1)
const formStart = ref('')
const formEnd = ref('')
const content = ref<SessionPlanContent | null>(null)
const contentText = ref('')
const contentLoading = ref(false)
const contentSaving = ref(false)
const contentError = ref('')
const attachments = ref<SessionPlanAttachment[]>([])
const attachmentsLoading = ref(false)
const attachmentUploading = ref(false)
const attachmentError = ref('')
const downloadingAttachmentId = ref<string | null>(null)
const deletingAttachmentId = ref<string | null>(null)
const readiness = ref(new Map<string, { ready: boolean; message: string }>())
const linking = ref(false)
const linkMessage = ref('')

const weekEnd = computed(() => week.value?.week_end_date ?? addDays(weekStart.value, 6))
const weekLabel = computed(() => `${formatDate(weekStart.value)} – ${formatDate(weekEnd.value)}`)
const sortedItems = computed(() => items.value.slice().sort((a, b) =>
  a.planned_date.localeCompare(b.planned_date) || a.sequence_no - b.sequence_no))
const selectedDivisionFilter = ref('')
const selectedWeekdayFilter = ref('')

const weekdayOptions = [
  { value: '1', label: 'Monday' },
  { value: '2', label: 'Tuesday' },
  { value: '3', label: 'Wednesday' },
  { value: '4', label: 'Thursday' },
  { value: '5', label: 'Friday' },
  { value: '6', label: 'Saturday' },
  { value: '0', label: 'Sunday' },
]

const filteredItems = computed(() => sortedItems.value.filter(item => {
  if (
    selectedDivisionFilter.value &&
    item.class_division_id !== selectedDivisionFilter.value
  ) return false

  if (
    selectedWeekdayFilter.value &&
    String(new Date(`${item.planned_date}T00:00:00`).getDay()) !== selectedWeekdayFilter.value
  ) return false

  return true
}))
const availableDivisions = computed(() => divisions.value
  .filter(division => division.status === 'ACTIVE' && division.data_origin === 'PRODUCTION')
  .sort((a, b) => a.class_level - b.class_level || a.division.localeCompare(b.division)))
const classById = computed(() => new Map(divisions.value.map(division => [division.id, division])))
const formDays = computed(() => {
  const days: string[] = []
  for (let index = 0; index < 7; index += 1) days.push(addDays(weekStart.value, index))
  return days
})
const contentDirty = computed(() => content.value !== null && content.value.content !== contentText.value)

function toDateInput(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function getMonday(date: Date) {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const day = result.getDay()
  result.setDate(result.getDate() - (day === 0 ? 6 : day - 1))
  return result
}

function addDays(dateInput: string, days: number) {
  const [year, month, day] = dateInput.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  date.setDate(date.getDate() + days)
  return toDateInput(date)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    .format(new Date(`${value}T00:00:00`))
}

function formatTime(value: string | null, end: string | null) {
  if (!value || !end) return 'Time not set'
  return `${value.slice(0, 5)} – ${end.slice(0, 5)}`
}

function divisionLabel(id: string) {
  const division = classById.value.get(id)
  return division ? `Class ${division.class_level} · ${division.division}` : 'Class/division unavailable'
}

function serviceMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback
}

async function loadClasses() {
  if (!canViewClasses.value) {
    classError.value = 'Class/division options are unavailable because class access is restricted.'
    return
  }
  loadingClasses.value = true
  classError.value = ''
  try {
    divisions.value = await listClassDivisions()
  } catch (reason) {
    classError.value = serviceMessage(reason, 'Unable to load class/division options.')
  } finally {
    loadingClasses.value = false
  }
}

async function loadTeachers() {
  if (!hasViewAll.value) return

  teachersLoading.value = true
  teachersError.value = ''

  try {
    teachers.value = (await listParaTeachers())
      .filter(teacher => teacher.status === 'ACTIVE')
      .sort((a, b) => a.full_name.localeCompare(b.full_name))
  } catch (reason) {
    teachersError.value = serviceMessage(
      reason,
      'Unable to load Para-Teachers.',
    )
  } finally {
    teachersLoading.value = false
  }
}

async function loadWeek() {
  if (!canView.value || !props.currentUser) return

  const requestId = ++weekRequestId
  const requestedWeek = weekStart.value
  const requestedTeacher = selectedTeacherId.value

  if (!requestedTeacher) return

  loading.value = true
  error.value = ''
  missingWeek.value = false
  week.value = null
  items.value = []
  readiness.value = new Map()

  try {
    const result = await getWeek(
      requestedWeek,
      requestedTeacher === props.currentUser.user_id
        ? undefined
        : requestedTeacher,
    )

    if (requestId !== weekRequestId) return

    week.value = result.week
    items.value = result.items
  } catch (reason) {
    if (requestId !== weekRequestId) return

    if (
      reason instanceof Error &&
      'status' in reason &&
      (reason as { status?: number }).status === 404
    ) {
      week.value = null
      items.value = []
      missingWeek.value = true
    } else {
      error.value = serviceMessage(
        reason,
        'Unable to load the selected planning week.',
      )
    }
  } finally {
    if (requestId === weekRequestId) {
      loading.value = false
    }
  }
}

function changeTeacher(teacherId: string) {
  if (!hasViewAll.value) return

  selectedTeacherId.value = teacherId
  selectedDivisionFilter.value = ''
  selectedWeekdayFilter.value = ''

  void loadWeek()
}

async function ensureWeek() {
  if (week.value) return week.value
  if (!canCreate.value) {
    formError.value = 'You do not have permission to create a planning week.'
    return null
  }
  try {
    week.value = await createWeek({ week_start_date: weekStart.value })
    missingWeek.value = false
    return week.value
  } catch (reason) {
    formError.value = serviceMessage(reason, 'Unable to create the planning week.')
    return null
  }
}

function moveWeek(days: number) {
  weekStart.value = addDays(weekStart.value, days)
  void loadWeek()
}

async function openCreate() {
  if (!canCreate.value) return
  const currentWeek = await ensureWeek()
  if (!currentWeek) return
  selectedItem.value = null
  formDate.value = weekStart.value
  formDivisionId.value = ''
  formSequence.value = items.value.length + 1
  formStart.value = ''
  formEnd.value = ''
  formError.value = ''
  modal.value = 'create'
}

function openEdit(item: SessionPlanItem) {
  if (!canUpdate.value) return
  selectedItem.value = item
  formDate.value = item.planned_date
  formDivisionId.value = item.class_division_id
  formSequence.value = item.sequence_no
  formStart.value = item.planned_start_time?.slice(0, 5) ?? ''
  formEnd.value = item.planned_end_time?.slice(0, 5) ?? ''
  formError.value = ''
  modal.value = 'edit'
}

function closeModal() {
  if (!saving.value && !contentSaving.value) modal.value = null
}

async function submitItem() {
  formError.value = ''
  if (!canCreate.value && !canUpdate.value) return
  if (!formDivisionId.value || !formDate.value || formSequence.value < 1) {
    formError.value = 'Select a class/division, date and positive sequence number.'
    return
  }
  if ((formStart.value && !formEnd.value) || (!formStart.value && formEnd.value)) {
    formError.value = 'Start and end times must be supplied together.'
    return
  }
  if (selectedItem.value && (selectedItem.value.planned_start_time || selectedItem.value.planned_end_time)
    && !formStart.value && !formEnd.value) {
    formError.value = 'The existing API does not support clearing a planned time; edit both times instead.'
    return
  }
  if (formStart.value && formEnd.value && formEnd.value <= formStart.value) {
    formError.value = 'End time must be later than start time.'
    return
  }
  if (!formDays.value.includes(formDate.value)) {
    formError.value = 'The planned date must be within the selected Monday–Sunday week.'
    return
  }

  saving.value = true
  try {
    if (selectedItem.value) {
      await updateItem(selectedItem.value.id, {
        class_division_id: formDivisionId.value,
        planned_date: formDate.value,
        sequence_no: formSequence.value,
        ...(formStart.value && formEnd.value
          ? { planned_start_time: formStart.value, planned_end_time: formEnd.value }
          : {}),
      })
    } else {
      await createItem({
        session_plan_week_id: week.value!.id,
        class_division_id: formDivisionId.value,
        planned_date: formDate.value,
        sequence_no: formSequence.value,
        ...(formStart.value && formEnd.value
          ? { planned_start_time: formStart.value, planned_end_time: formEnd.value }
          : {}),
      })
    }
    modal.value = null
    await loadWeek()
  } catch (reason) {
    formError.value = serviceMessage(reason, 'Unable to save the planned session.')
  } finally {
    saving.value = false
  }
}

async function removeItem(item: SessionPlanItem) {
  if (!window.confirm(`Delete the planned session on ${formatDate(item.planned_date)} (${divisionLabel(item.class_division_id)})?`)) return
  try {
    await deleteItem(item.id)
    await loadWeek()
  } catch (reason) {
    error.value = serviceMessage(reason, 'Unable to delete the planned session.')
  }
}

async function openContent(item: SessionPlanItem) {
  selectedItem.value = item
  content.value = null
  contentText.value = ''
  contentError.value = ''
  attachments.value = []
  attachmentError.value = ''
  contentLoading.value = true
  modal.value = 'content'

  try {
    const result = await getContent(item.id)

    if (!result) {
      content.value = null
      return
    }

    content.value = result
    contentText.value = result.content

    await loadAttachments(item.id)
  } catch (reason) {
    contentError.value = serviceMessage(
      reason,
      'Unable to load lesson-plan content.',
    )
  } finally {
    contentLoading.value = false
  }
}

function closeContent() {
  if (contentDirty.value && !window.confirm('Discard unsaved lesson-plan changes?')) return
  modal.value = null
  attachments.value = []
  attachmentError.value = ''
}

async function submitContent() {
  if (!canUpdate.value) return
  if (!selectedItem.value) return
  if (!contentText.value.trim()) {
    contentError.value = 'Lesson-plan content cannot be blank.'
    return
  }
  if (contentText.value.length > 20000) {
    contentError.value = 'Lesson-plan content cannot exceed 20,000 characters.'
    return
  }
  contentSaving.value = true
  contentError.value = ''
  try {
    content.value = await saveContent(selectedItem.value.id, { content: contentText.value })
    contentText.value = content.value.content
  } catch (reason) {
    contentError.value = serviceMessage(reason, 'Unable to save lesson-plan content.')
  } finally {
    contentSaving.value = false
  }
}

async function loadAttachments(itemId: string) {
  attachmentsLoading.value = true
  attachmentError.value = ''

  try {
    attachments.value = await listAttachments(itemId)
  } catch (reason) {
    attachmentError.value = serviceMessage(
      reason,
      'Unable to load lesson-plan attachments.',
    )
  } finally {
    attachmentsLoading.value = false
  }
}

async function handleAttachmentSelection(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]

  if (!file || !selectedItem.value) return

  if (!content.value) {
    attachmentError.value = 'Save the lesson-plan content before uploading attachments.'
    input.value = ''
    return
  }

  if (contentDirty.value) {
    attachmentError.value = 'Save your lesson-plan changes before uploading attachments.'
    input.value = ''
    return
  }

  if (file.size > 5 * 1024 * 1024) {
    attachmentError.value = 'The maximum attachment size is 5 MiB.'
    input.value = ''
    return
  }

  attachmentUploading.value = true
  attachmentError.value = ''

  try {
    await uploadAttachment(selectedItem.value.id, file)
    await loadAttachments(selectedItem.value.id)
  } catch (reason) {
    attachmentError.value = serviceMessage(
      reason,
      'Unable to upload the attachment.',
    )
  } finally {
    attachmentUploading.value = false
    input.value = ''
  }
}

async function downloadLessonAttachment(attachment: SessionPlanAttachment) {
  if (!selectedItem.value) return

  downloadingAttachmentId.value = attachment.id
  attachmentError.value = ''

  try {
    const blob = await downloadAttachment(
      selectedItem.value.id,
      attachment.id,
    )

    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')

    link.href = url
    link.download = attachment.original_filename
    document.body.appendChild(link)
    link.click()
    link.remove()

    window.URL.revokeObjectURL(url)
  } catch (reason) {
    attachmentError.value = serviceMessage(
      reason,
      'Unable to download the attachment.',
    )
  } finally {
    downloadingAttachmentId.value = null
  }
}

async function removeLessonAttachment(attachment: SessionPlanAttachment) {
  if (!selectedItem.value) return

  if (!window.confirm(`Delete attachment "${attachment.original_filename}"?`)) {
    return
  }

  deletingAttachmentId.value = attachment.id
  attachmentError.value = ''

  try {
    await deleteAttachment(selectedItem.value.id, attachment.id)
    attachments.value = attachments.value.filter(
      item => item.id !== attachment.id,
    )
  } catch (reason) {
    attachmentError.value = serviceMessage(
      reason,
      'Unable to delete the attachment.',
    )
  } finally {
    deletingAttachmentId.value = null
  }
}

function formatAttachmentSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

async function validate(item: SessionPlanItem) {
  if (!canValidate.value) return
  linkMessage.value = ''
  try {
    await validateItem(item.id)
    readiness.value = new Map(readiness.value).set(item.id, { ready: true, message: 'Ready for TeachingSession linkage.' })
  } catch (reason) {
    readiness.value = new Map(readiness.value).set(item.id, {
      ready: false,
      message: serviceMessage(reason, 'This item is not ready.'),
    })
  }
}

async function linkTeachingSession(item: SessionPlanItem) {
  const result = readiness.value.get(item.id)
  if (!canLinkSession.value) return
  if (!result?.ready) {
    linkMessage.value = 'Validate this planning item successfully before creating a TeachingSession.'
    return
  }
  if (!window.confirm('Create a TeachingSession from this planned item? This is a deliberate workflow transition.')) return
  linking.value = true
  linkMessage.value = ''
  try {
    const session: SessionPlanTeachingSession = await createTeachingSession(item.id)
    linkMessage.value = `TeachingSession ${session.id} created with status ${session.status}.`
    await loadWeek()
  } catch (reason) {
    linkMessage.value = serviceMessage(reason, 'Unable to create the TeachingSession.')
  } finally {
    linking.value = false
  }
}

watch(
  () => props.currentUser?.user_id,
  userId => {
    if (userId) {
      selectedTeacherId.value = userId
      void loadWeek()
    }
  },
)

onMounted(async () => {
  const requestedItemId =
    typeof route.query.item_id === 'string'
      ? route.query.item_id
      : ''

  const requestedTeacherId =
    typeof route.query.teacher_id === 'string'
      ? route.query.teacher_id
      : ''

  const requestedWeek =
    typeof route.query.week_start === 'string'
      ? route.query.week_start
      : ''

  if (
    requestedWeek &&
    /^\d{4}-\d{2}-\d{2}$/.test(requestedWeek)
  ) {
    weekStart.value = requestedWeek
  }

  if (hasViewAll.value && requestedTeacherId) {
    selectedTeacherId.value = requestedTeacherId
  } else if (props.currentUser) {
    selectedTeacherId.value = props.currentUser.user_id
  }

  await Promise.all([
    loadClasses(),
    loadTeachers(),
  ])

  await loadWeek()

  if (requestedItemId) {
    const requestedItem = items.value.find(
      item => item.id === requestedItemId,
    )

    if (requestedItem) {
      await openContent(requestedItem)
    } else {
      error.value =
        'The requested session was not found in the selected planning week, or you do not have access to it.'
    }
  }
})
</script>

<template>
  <div class="planning-page">
    <header class="planning-header">
      <div>
        <p class="planning-eyebrow">Academic Operations</p>
        <h2>Session Planning</h2>
        <p>Prepare the authenticated Para-Teacher’s weekly class schedule and lesson-plan content.</p>
      </div>
      <button v-if="canCreate" class="planning-primary" type="button" @click="openCreate">Add session</button>
    </header>
    <section v-if="canView" class="planning-filter-panel">
      <div class="planning-filter-heading">
        <div>
          <h3>Planning Filters</h3>
          <p v-if="hasViewAll">
            Select a Para-Teacher to view their weekly session plan.
          </p>
          <p v-else>
            Filter your weekly sessions by class and weekday.
          </p>
        </div>
      </div>

      <div class="planning-filter-grid">
        <label v-if="hasViewAll" class="planning-filter-field">
          <span>Para-Teacher</span>

          <select v-model="selectedTeacherId" :disabled="teachersLoading" @change="changeTeacher(selectedTeacherId)">
            <option :value="currentUser?.user_id">
              My plan — {{ currentUser?.full_name }}
            </option>

            <option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">
              {{ teacher.full_name }}
            </option>
          </select>
        </label>

        <label class="planning-filter-field">
          <span>Class / Division</span>

          <select v-model="selectedDivisionFilter">
            <option value="">All classes</option>
            <option v-for="division in availableDivisions" :key="division.id" :value="division.id">
              Class {{ division.class_level }} · {{ division.division }}
            </option>
          </select>
        </label>

        <label class="planning-filter-field">
          <span>Weekday</span>

          <select v-model="selectedWeekdayFilter">
            <option value="">All days</option>
            <option v-for="day in weekdayOptions" :key="day.value" :value="day.value">
              {{ day.label }}
            </option>
          </select>
        </label>
      </div>

      <p v-if="teachersError" class="planning-error" role="alert">
        {{ teachersError }}
      </p>

      <p v-if="!isOwnPlan" class="planning-filter-note">
        Read-only management view — changes are disabled for another teacher's plan.
      </p>
    </section>
    <section v-if="!canView" class="planning-restricted" role="status">
      You do not have permission to view Session Planning.
    </section>
    <template v-else>
      <section class="planning-weekbar" aria-label="Planning week navigation">
        <button class="planning-secondary" type="button" @click="moveWeek(-7)">Previous week</button>
        <div class="planning-week">
          <span class="planning-eyebrow">Monday–Sunday</span>
          <strong>{{ weekLabel }}</strong>
        </div>
        <button class="planning-secondary" type="button"
          @click="weekStart = toDateInput(getMonday(new Date())); void loadWeek()">Current week</button>
        <button class="planning-secondary" type="button" @click="moveWeek(7)">Next week</button>
      </section>

      <p v-if="classError" class="planning-notice" role="status">{{ classError }}</p>
      <p v-if="linkMessage" class="planning-notice" role="status">{{ linkMessage }}</p>
      <p v-if="error" class="planning-error" role="alert">{{ error }} <button class="planning-link" type="button"
          @click="loadWeek">Retry</button></p>

      <section class="planning-summary" aria-label="Weekly summary">
        <article class="planning-card">
          <span>Sessions planned</span>
          <strong>{{ items.length }}</strong>
          <small>Loaded for this week</small>
        </article>

        <article class="planning-card">
          <span>Weekly minimum</span>
          <strong>{{ items.length }} / {{ MIN_WEEKLY_ITEMS }}</strong>
          <small>
            {{ weeklyMinimumMet
              ? 'Minimum met'
              : `${MIN_WEEKLY_ITEMS - items.length} more required`
            }}
          </small>
        </article>

        <article class="planning-card">
          <span>Readiness checked</span>
          <strong>{{ readiness.size }}</strong>
          <small>Only explicit validations shown</small>
        </article>
      </section>

      <section v-if="missingWeek" class="planning-empty">
        <h3>No planning week exists</h3>
        <p>The selected week has not been created for your account.</p>
        <button v-if="canCreate" class="planning-primary" type="button" @click="openCreate">Create week and add
          session</button>
      </section>
      <section v-else class="planning-panel" aria-labelledby="planning-list-title">
        <div class="planning-panel-heading">
          <div>
            <p class="planning-eyebrow">Weekly workspace</p>
            <h3 id="planning-list-title">Planned sessions</h3>
          </div>
          <span class="planning-muted">
            Showing {{ filteredItems.length }} of {{ items.length }} planned
          </span>
        </div>
        <p v-if="loading" class="planning-muted" role="status">Loading planning week…</p>
        <div v-else-if="!filteredItems.length" class="planning-empty">
          No sessions match the selected filters.
        </div>
        <div v-else class="planning-table-wrap">
          <table class="planning-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Seq.</th>
                <th>Class/division</th>
                <th>Planned time</th>
                <th>Content</th>
                <th>Readiness</th>
                <th v-if="hasPlanningActions">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredItems" :key="item.id">
                <td>{{ formatDate(item.planned_date) }}</td>
                <td>{{ item.sequence_no }}</td>
                <td>{{ divisionLabel(item.class_division_id) }}</td>
                <td>{{ formatTime(item.planned_start_time, item.planned_end_time) }}</td>
                <td><button class="planning-link" type="button" @click="openContent(item)">View / edit</button></td>
                <td>
                  <span v-if="readiness.get(item.id)" class="planning-badge"
                    :class="readiness.get(item.id)?.ready ? 'is-ready' : 'is-not-ready'">
                    {{ readiness.get(item.id)?.ready ? 'Ready' : 'Not ready' }}
                  </span>
                  <span v-else class="planning-muted">Not checked</span>
                </td>
                <td v-if="hasPlanningActions" class="planning-actions">
                  <button v-if="canValidate" class="planning-link" type="button"
                    @click="validate(item)">Validate</button>
                  <button v-if="canLinkSession" class="planning-link" type="button" :disabled="linking"
                    @click="linkTeachingSession(item)">Link session</button>
                  <button v-if="canUpdate" class="planning-link" type="button" @click="openEdit(item)">Edit</button>
                  <button v-if="canDelete" class="planning-danger" type="button"
                    @click="removeItem(item)">Delete</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <ManagementModal v-if="modal === 'create' || modal === 'edit'"
      :title="modal === 'create' ? 'Add planned session' : 'Edit planned session'" :busy="saving" @close="closeModal">
      <form class="planning-form" @submit.prevent="submitItem">
        <label>Planned date<select v-model="formDate">
            <option v-for="day in formDays" :key="day" :value="day">{{ formatDate(day) }}</option>
          </select></label>
        <label>Class/division<select v-model="formDivisionId" :disabled="loadingClasses || !availableDivisions.length"
            required>
            <option value="">Select class/division</option>
            <option v-for="division in availableDivisions" :key="division.id" :value="division.id">Class {{
              division.class_level }} · {{ division.division }}</option>
          </select></label>
        <label>Sequence number<input v-model.number="formSequence" type="number" min="1" required /></label>
        <label>Start time<input v-model="formStart" type="time" /></label>
        <label>End time<input v-model="formEnd" type="time" /></label>
        <p v-if="formError" class="planning-error" role="alert">{{ formError }}</p>
        <div class="planning-form-actions"><button type="button" class="planning-secondary" :disabled="saving"
            @click="closeModal">Cancel</button><button type="submit" class="planning-primary"
            :disabled="saving || !availableDivisions.length">{{ saving ? 'Saving…' : 'Save session' }}</button></div>
      </form>
    </ManagementModal>

    <ManagementModal v-if="modal === 'content'" title="Lesson-plan content" :busy="contentSaving" @close="closeContent">
      <div class="planning-content-editor">
        <p class="planning-muted">{{ selectedItem ? `${formatDate(selectedItem.planned_date)} ·
          ${divisionLabel(selectedItem.class_division_id)}` : '' }}</p>
        <p v-if="contentLoading" class="planning-muted" role="status">Loading content…</p>
        <template v-else>
          <textarea v-model="contentText" maxlength="20000" rows="12" placeholder="Describe the planned lesson…"
            :readonly="!canUpdate"></textarea>
          <div class="planning-content-meta">
            <span>{{ contentText.length }} / 20,000 characters</span>
            <span v-if="!canUpdate">Read-only</span>
          </div>
          <section class="planning-attachments">
            <h3>Attachments</h3>

            <p class="planning-muted">
              PDF, DOC, DOCX, PPT, PPTX, JPG and PNG · Maximum 5 MiB per file
            </p>

            <div v-if="canUpdate" class="planning-attachment-upload">
              <input ref="attachmentInput" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png"
                :disabled="!content || contentDirty || contentSaving || attachmentUploading"
                @change="handleAttachmentSelection" />

              <p v-if="!content" class="planning-muted">
                Save the lesson-plan content before uploading attachments.
              </p>

              <p v-else-if="contentDirty" class="planning-muted">
                Save your changes before uploading attachments.
              </p>

              <p v-if="attachmentUploading" class="planning-muted" role="status">
                Uploading attachment…
              </p>
            </div>

            <p v-if="attachmentsLoading" class="planning-muted" role="status">
              Loading attachments…
            </p>

            <p v-else-if="!attachments.length" class="planning-muted">
              No attachments uploaded yet.
            </p>

            <ul v-else class="planning-attachment-list">
              <li v-for="attachment in attachments" :key="attachment.id">
                <div>
                  <strong>{{ attachment.original_filename }}</strong>
                  <span class="planning-muted">
                    {{ formatAttachmentSize(attachment.file_size_bytes) }}
                  </span>
                </div>

                <div class="planning-attachment-actions">
                  <button type="button" class="planning-secondary" :disabled="downloadingAttachmentId === attachment.id"
                    @click="downloadLessonAttachment(attachment)">
                    {{ downloadingAttachmentId === attachment.id ? 'Downloading…' : 'Download' }}
                  </button>

                  <button v-if="canUpdate" type="button" class="planning-secondary"
                    :disabled="deletingAttachmentId === attachment.id" @click="removeLessonAttachment(attachment)">
                    {{ deletingAttachmentId === attachment.id ? 'Deleting…' : 'Delete' }}
                  </button>
                </div>
              </li>
            </ul>

            <p v-if="attachmentError" class="planning-error" role="alert">
              {{ attachmentError }}
            </p>
          </section>
          <p v-if="contentError" class="planning-error" role="alert">{{ contentError }}</p>
          <div class="planning-form-actions"><button type="button" class="planning-secondary" :disabled="contentSaving"
              @click="closeContent">Close</button><button v-if="canUpdate" type="button" class="planning-primary"
              :disabled="contentSaving" @click="submitContent">{{ contentSaving ? 'Saving…' : 'Save content' }}</button>
          </div>
        </template>
      </div>
    </ManagementModal>
  </div>
</template>

<style scoped>
.planning-page {
  display: grid;
  gap: 20px;
}

.planning-header,
.planning-panel-heading,
.planning-weekbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.planning-header h2,
.planning-panel h3,
.planning-empty h3 {
  margin: 0;
  color: var(--ov-text-primary);
}

.planning-header h2 {
  font-size: 30px;
}

.planning-header p:last-child {
  margin: 6px 0 0;
  color: var(--ov-text-muted);
}

.planning-eyebrow {
  margin: 0 0 4px;
  color: var(--ov-brand);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.planning-weekbar,
.planning-card,
.planning-panel,
.planning-empty,
.planning-restricted,
.planning-notice {
  padding: 18px 20px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
}

.planning-weekbar {
  align-items: center;
}

.planning-week {
  display: grid;
  justify-items: center;
  gap: 4px;
  color: var(--ov-text-primary);
}

.planning-week strong {
  font-size: 18px;
}

.planning-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.planning-card {
  display: grid;
  gap: 5px;
}

.planning-attachments {
  display: grid;
  gap: 12px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--border-color, #e5e0d6);
}

.planning-attachments h3 {
  margin: 0;
}

.planning-attachment-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.planning-filter-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
}

.planning-filter-heading h3 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 15px;
  font-weight: 700;
}

.planning-filter-heading p {
  margin: 4px 0 0;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.planning-filter-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr);
  gap: 14px;
  max-width: 420px;
}

.planning-filter-field {
  display: grid;
  gap: 7px;
  color: var(--ov-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.planning-filter-field select {
  box-sizing: border-box;
  width: 100%;
  min-height: 40px;
  padding: 9px 12px;
  border: 1px solid var(--ov-border);
  border-radius: 7px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font: inherit;
}

.planning-filter-field select:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.planning-filter-note {
  margin: 0;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.planning-attachment-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-color, #e5e0d6);
  border-radius: 8px;
}

.planning-attachment-list li>div:first-child {
  display: grid;
  gap: 4px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.planning-attachment-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.planning-card span,
.planning-card small,
.planning-muted {
  color: var(--ov-text-muted);
  font-size: 12px;
}

.planning-card strong {
  color: var(--ov-text-primary);
  font-size: 28px;
}

.planning-panel {
  display: grid;
  gap: 18px;
}

.planning-table-wrap {
  overflow-x: auto;
}

.planning-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  color: var(--ov-text-primary);
  font-size: 13px;
}

.planning-table th,
.planning-table td {
  padding: 13px 10px;
  border-bottom: 1px solid var(--ov-border-subtle);
  text-align: left;
  vertical-align: top;
}

.planning-table th {
  color: var(--ov-text-muted);
  font-size: 11px;
  text-transform: uppercase;
}

.planning-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.planning-link,
.planning-danger {
  padding: 0;
  border: 0;
  background: none;
  color: var(--ov-brand);
  cursor: pointer;
  font-weight: 600;
}

.planning-danger {
  color: var(--ov-tag-terra-fg);
}

.planning-link:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.planning-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.planning-badge.is-ready {
  color: var(--ov-tag-accent-fg);
  background: var(--ov-tag-accent-bg);
}

.planning-badge.is-not-ready {
  color: var(--ov-tag-terra-fg);
  background: var(--ov-tag-terra-bg);
}

.planning-primary,
.planning-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 600;
}

.planning-primary {
  color: var(--ov-button-primary-text);
  background: var(--ov-brand);
}

.planning-primary:disabled,
.planning-secondary:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.planning-secondary {
  color: var(--ov-text-primary);
  background: var(--ov-bg-surface-subtle);
}

.planning-error {
  margin: 0;
  color: var(--ov-tag-terra-fg);
}

.planning-notice,
.planning-restricted {
  color: var(--ov-text-muted);
}

.planning-empty {
  color: var(--ov-text-muted);
  text-align: center;
}

.planning-form,
.planning-content-editor {
  display: grid;
  gap: 15px;
}

.planning-form label {
  display: grid;
  gap: 6px;
  color: var(--ov-text-secondary);
  font-size: 13px;
}

.planning-form input,
.planning-form select,
.planning-content-editor textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--ov-border);
  border-radius: 6px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font: inherit;
}

.planning-content-editor textarea {
  resize: vertical;
}

.planning-content-meta,
.planning-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.planning-form-actions {
  align-items: center;
  margin-top: 4px;
}

.planning-filter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 14px;
}

@media (max-width: 900px) {
  .planning-filter-grid {
    grid-template-columns: repeat(2, minmax(160px, 1fr));
  }
}

@media (max-width: 560px) {
  .planning-filter-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 800px) {
  .planning-weekbar {
    flex-wrap: wrap;
    justify-content: center;
  }

  .planning-summary {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .planning-header {
    flex-direction: column;
  }

  .planning-header .planning-primary {
    width: 100%;
  }

  .planning-weekbar {
    padding: 14px;
  }

  .planning-weekbar button {
    flex: 1 1 40%;
  }

  .planning-panel,
  .planning-empty {
    padding: 16px;
  }
}
</style>
