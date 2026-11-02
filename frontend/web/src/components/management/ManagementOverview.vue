<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CurrentUser } from '../../services/auth'
import {
  createAcademicYear,
  listAcademicYears,
} from '../../services/academicCalendar'
import {
  getAttendanceReport,
  getDeliveryReport,
  getDeliveryTrend,
  getEngagementReport,
} from '../../services/reporting'
import type {
  AttendanceReportItem,
  DeliveryReportItem,
  DeliveryTrendItem,
  EngagementReportItem,
} from '../../services/reporting'
import type { AcademicYear } from '../../services/academicCalendar'
import { saveTheme, type ThemeMode } from '../../services/theme'
import ManagementSidebar from './ManagementSidebar.vue'
import ManagementHeader from './ManagementHeader.vue'
import ManagementMetricCard from './ManagementMetricCard.vue'
import DeliveryTrajectoryChart from './DeliveryTrajectoryChart.vue'
import ManagementAttentionPanel from './ManagementAttentionPanel.vue'

// ─── Props ───────────────────────────────────────────────────────────────────
const props = defineProps<{
  currentUser: CurrentUser | null
  initialTheme?: ThemeMode
}>()

const emit = defineEmits<{
  returnToSignIn: []
}>()

// ─── Theme ────────────────────────────────────────────────────────────────────
const themeMode = ref<ThemeMode>(props.initialTheme ?? 'light')

const darkMediaQuery = ref<MediaQueryList | null>(null)

function applyTheme(mode: ThemeMode) {
  themeMode.value = mode
  saveTheme(mode)
  const root = document.documentElement
  let isDark = mode === 'dark'
  if (mode === 'system' && window.matchMedia) {
    isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  root.setAttribute('data-ov-theme', isDark ? 'dark' : 'light')
}

function handleSystemThemeChange() {
  if (themeMode.value === 'system') {
    applyTheme('system')
  }
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────
const isRailCollapsed = ref(false)
const isMobileDrawerOpen = ref(false)

function handleResize() {
  const w = window.innerWidth
  if (w < 768) {
    // mobile: ensure drawer is closed unless explicitly opened
    if (!isMobileDrawerOpen.value) {
      // off-screen handled by CSS translate
    }
    isRailCollapsed.value = false
  } else if (w >= 768 && w < 1024) {
    isMobileDrawerOpen.value = false
    isRailCollapsed.value = true
  } else {
    isMobileDrawerOpen.value = false
    if (w >= 1280 && isRailCollapsed.value) {
      // Keep user's preference on large screens
    }
  }
}

function toggleSidebarCollapse() {
  if (window.innerWidth < 768) {
    isMobileDrawerOpen.value = !isMobileDrawerOpen.value
    return
  }
  isRailCollapsed.value = !isRailCollapsed.value
}

function openMobileDrawer() {
  isMobileDrawerOpen.value = true
}

function closeMobileDrawer() {
  isMobileDrawerOpen.value = false
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isMobileDrawerOpen.value) {
    closeMobileDrawer()
  }
}

// ─── Derived sidebar classes ──────────────────────────────────────────────────

const mainMargin = computed(() => {
  if (isRailCollapsed.value) return 'ov-main--rail'
  return 'ov-main--expanded'
})


// ─── Academic Year ────────────────────────────────────────────────────────────
const academicYears = ref<AcademicYear[]>([])
const selectedYear = ref('')
const isLoadingAcademicYears = ref(false)
const academicYearError = ref('')

const canManageCalendar = computed(
  () => props.currentUser?.permissions.includes('calendar.manage') ?? false,
)
const isCreateAcademicYearOpen = ref(false)
const isCreatingAcademicYear = ref(false)
const createAcademicYearError = ref('')
const newAcademicYearName = ref('')
const newAcademicYearStartDate = ref('')
const newAcademicYearEndDate = ref('')
const newAcademicYearIsActive = ref(true)

function openCreateAcademicYear() {
  createAcademicYearError.value = ''
  isCreateAcademicYearOpen.value = true
}

function closeCreateAcademicYear() {
  if (isCreatingAcademicYear.value) return
  isCreateAcademicYearOpen.value = false
  createAcademicYearError.value = ''
  newAcademicYearName.value = ''
  newAcademicYearStartDate.value = ''
  newAcademicYearEndDate.value = ''
  newAcademicYearIsActive.value = true
}

async function submitCreateAcademicYear() {
  const name = newAcademicYearName.value.trim()
  const startDate = newAcademicYearStartDate.value
  const endDate = newAcademicYearEndDate.value

  if (!name || name.length > 50) {
    createAcademicYearError.value = 'Enter a name between 1 and 50 characters.'
    return
  }

  if (!startDate || !endDate || startDate >= endDate) {
    createAcademicYearError.value = 'The end date must be later than the start date.'
    return
  }

  isCreatingAcademicYear.value = true
  createAcademicYearError.value = ''

  try {
    const createdYear = await createAcademicYear({
      name,
      start_date: startDate,
      end_date: endDate,
      is_active: newAcademicYearIsActive.value,
    })

    isCreateAcademicYearOpen.value = false
    newAcademicYearName.value = ''
    newAcademicYearStartDate.value = ''
    newAcademicYearEndDate.value = ''
    newAcademicYearIsActive.value = true

    try {
      academicYears.value = await listAcademicYears()
      selectedYear.value = createdYear.id
      academicYearError.value = ''
    } catch (error: unknown) {
      academicYearError.value =
        error instanceof Error
          ? `Academic year created, but the list could not be refreshed: ${error.message}`
          : 'Academic year created, but the list could not be refreshed.'
    }
  } catch (error: unknown) {
    createAcademicYearError.value =
      error instanceof Error
        ? error.message
        : 'Unable to create the academic year.'
  } finally {
    isCreatingAcademicYear.value = false
  }
}

async function loadAcademicYears() {
  isLoadingAcademicYears.value = true
  academicYearError.value = ''

  try {
    const years = await listAcademicYears()
    academicYears.value = years

    const activeYear = years.find((year) => year.is_active)
    selectedYear.value = activeYear?.id ?? years[0]?.id ?? ''

    if (years.length === 0) {
      academicYearError.value = 'No production academic years are available.'
    }
  } catch (error: unknown) {
    academicYears.value = []
    selectedYear.value = ''
    academicYearError.value =
      error instanceof Error
        ? error.message
        : 'Unable to load academic years. Please try again later.'
  } finally {
    isLoadingAcademicYears.value = false
  }
}


// ─── Live reporting ─────────────────────────────────────────────────────────
const deliveryReport = ref<DeliveryReportItem | null>(null)
const attendanceReport = ref<AttendanceReportItem | null>(null)
const engagementReport = ref<EngagementReportItem | null>(null)
const deliveryTrend = ref<DeliveryTrendItem[]>([])
const isLoadingReports = ref(false)
const reportingErrors = ref({
  delivery: '',
  attendance: '',
  engagement: '',
  trend: '',
})
let reportRequestId = 0

const selectedAcademicYear = computed(
  () => academicYears.value.find((year) => year.id === selectedYear.value) ?? null,
)

const numberFormat = new Intl.NumberFormat('en-IN')
const formatCount = (value: number | null | undefined) =>
  numberFormat.format(value ?? 0)

const reportingErrorMessages = computed(() =>
  Object.values(reportingErrors.value).filter(Boolean),
)

const reportBannerText = computed(() => {
  if (isLoadingAcademicYears.value) return 'Loading academic years…'
  if (academicYearError.value) return academicYearError.value
  if (!selectedYear.value) return 'No production academic year is configured.'
  if (isLoadingReports.value) return 'Loading live reporting data…'
  if (reportingErrorMessages.value.length) {
    return `Some reporting data could not be loaded (${reportingErrorMessages.value.length} of 4 reports).`
  }
  return 'Live reporting data • Production records only'
})

async function loadReports(yearId: string) {
  const requestId = ++reportRequestId

  reportingErrors.value = {
    delivery: '',
    attendance: '',
    engagement: '',
    trend: '',
  }
  deliveryReport.value = null
  attendanceReport.value = null
  engagementReport.value = null
  deliveryTrend.value = []

  if (!yearId) {
    isLoadingReports.value = false
    return
  }

  isLoadingReports.value = true

  const results = await Promise.allSettled([
    getDeliveryReport(yearId),
    getAttendanceReport(yearId),
    getEngagementReport(yearId),
    getDeliveryTrend(yearId),
  ])

  // Ignore responses belonging to an older year selection.
  if (requestId !== reportRequestId) return

  const [delivery, attendance, engagement, trend] = results

  if (delivery.status === 'fulfilled') {
    deliveryReport.value = delivery.value.items[0] ?? null
  } else {
    reportingErrors.value.delivery =
      delivery.reason instanceof Error
        ? delivery.reason.message
        : 'Unable to load delivery data.'
  }

  if (attendance.status === 'fulfilled') {
    attendanceReport.value = attendance.value.items[0] ?? null
  } else {
    reportingErrors.value.attendance =
      attendance.reason instanceof Error
        ? attendance.reason.message
        : 'Unable to load attendance data.'
  }

  if (engagement.status === 'fulfilled') {
    engagementReport.value = engagement.value.items[0] ?? null
  } else {
    reportingErrors.value.engagement =
      engagement.reason instanceof Error
        ? engagement.reason.message
        : 'Unable to load engagement data.'
  }

  if (trend.status === 'fulfilled') {
    deliveryTrend.value = trend.value.items
  } else {
    reportingErrors.value.trend =
      trend.reason instanceof Error
        ? trend.reason.message
        : 'Unable to load delivery trend data.'
  }

  isLoadingReports.value = false
}

watch(selectedYear, (yearId) => {
  void loadReports(yearId)
})

// ─── User initials ────────────────────────────────────────────────────────────
const userInitials = computed(() => {
  if (!props.currentUser?.full_name) return '—'
  return props.currentUser.full_name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0].toUpperCase())
    .join('')
})

const displayName = computed(() =>
  props.currentUser?.full_name || 'Signed-in user'
)

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleKeyDown)
  if (window.matchMedia) {
    darkMediaQuery.value = window.matchMedia('(prefers-color-scheme: dark)')
    darkMediaQuery.value.addEventListener('change', handleSystemThemeChange)
  }
  applyTheme(themeMode.value)
  handleResize()
  void loadAcademicYears()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleKeyDown)
  if (darkMediaQuery.value) {
    darkMediaQuery.value.removeEventListener('change', handleSystemThemeChange)
  }
  // Clean up data-ov-theme to prevent bleed
  document.documentElement.removeAttribute('data-ov-theme')
})

watch(themeMode, (mode) => applyTheme(mode))
</script>

<template>
  <div class="ov-shell" :class="[themeMode === 'dark' ? 'ov-dark' : '', isRailCollapsed ? 'ov-is-rail' : '']">
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- MOBILE DRAWER BACKDROP                                                 -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <div class="ov-backdrop" :class="isMobileDrawerOpen ? 'ov-backdrop--visible' : ''" @click="closeMobileDrawer"
      aria-hidden="true" />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- SIDEBAR                                                                 -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <ManagementSidebar :is-rail-collapsed="isRailCollapsed" :is-mobile-drawer-open="isMobileDrawerOpen"
      @toggle-collapse="toggleSidebarCollapse" @close-drawer="closeMobileDrawer" />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN CANVAS                                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <div class="ov-main" :class="mainMargin" id="ov-main-canvas">

      <ManagementHeader :is-rail-collapsed="isRailCollapsed" :selected-year="selectedYear"
        :academic-years="academicYears" :is-loading-academic-years="isLoadingAcademicYears"
        :academic-year-error="academicYearError" :can-manage-calendar="canManageCalendar" :theme-mode="themeMode"
        :display-name="displayName" :user-initials="userInitials" @open-mobile-drawer="openMobileDrawer"
        @toggle-sidebar="toggleSidebarCollapse" @update:selected-year="selectedYear = $event"
        @create-academic-year="openCreateAcademicYear" @change-theme="applyTheme" @sign-out="emit('returnToSignIn')" />

      <!-- SCROLLABLE WORKSPACE -->
      <main class="ov-workspace" id="overview">
        <section v-if="isCreateAcademicYearOpen" class="ov-create-year-panel" aria-labelledby="ov-create-year-title">
          <div class="ov-create-year-heading">
            <div>
              <h2 id="ov-create-year-title">Create academic year</h2>
              <p>Set the name and date range for a production academic year.</p>
            </div>
          </div>

          <form class="ov-create-year-form" @submit.prevent="submitCreateAcademicYear">
            <label class="ov-form-field">
              <span>Academic year name</span>
              <input v-model.trim="newAcademicYearName" type="text" maxlength="50" placeholder="e.g. 2026–27"
                required />
            </label>

            <label class="ov-form-field">
              <span>Start date</span>
              <input v-model="newAcademicYearStartDate" type="date" required />
            </label>

            <label class="ov-form-field">
              <span>End date</span>
              <input v-model="newAcademicYearEndDate" type="date" :min="newAcademicYearStartDate || undefined"
                required />
            </label>

            <label class="ov-form-checkbox">
              <input v-model="newAcademicYearIsActive" type="checkbox" />
              <span>Active academic year</span>
            </label>

            <p v-if="createAcademicYearError" class="ov-create-year-error" role="alert">
              {{ createAcademicYearError }}
            </p>

            <div class="ov-create-year-actions">
              <button type="button" class="ov-form-secondary" :disabled="isCreatingAcademicYear"
                @click="closeCreateAcademicYear">
                Cancel
              </button>
              <button type="submit" class="ov-form-primary" :disabled="isCreatingAcademicYear">
                {{ isCreatingAcademicYear ? 'Creating…' : 'Create academic year' }}
              </button>
            </div>
          </form>
        </section>
        <!-- ─── Live Reporting Status ───────────────────────────────────────── -->
        <div class="ov-preview-banner" role="status" aria-live="polite">
          <div class="ov-preview-banner-left">
            <span class="material-symbols-outlined ov-preview-icon" aria-hidden="true">
              {{ reportingErrorMessages.length || academicYearError ? 'warning' : 'info' }}
            </span>
            <span>{{ reportBannerText }}</span>
          </div>
          <span class="ov-preview-badge">
            {{
              isLoadingReports
                ? 'Loading'
                : reportingErrorMessages.length
                  ? 'Partial data'
                  : academicYearError
                    ? 'Unavailable'
                    : 'Live API'
            }}
          </span>
        </div>

        <!-- ─── KPI Cards ──────────────────────────────────────────────────── -->
        <section class="ov-kpi-grid" aria-label="Key Performance Indicators">
          <ManagementMetricCard label="Session Delivery" icon="school" icon-tone="accent"
            :value="deliveryReport ? formatCount(deliveryReport.completed_sessions) : '—'"
            :value-muted="!deliveryReport || isLoadingReports || !!reportingErrors.delivery" badge-text="Completed"
            badge-tone="accent"
            :description="isLoadingReports ? 'Loading delivery report…' : 'Production sessions in the selected academic year'"
            :footer-items="[
              { label: 'Planned', value: deliveryReport ? formatCount(deliveryReport.planned_sessions) : '—' },
              { label: 'In progress', value: deliveryReport ? formatCount(deliveryReport.in_progress_sessions) : '—' },
              { label: 'Cancelled', value: deliveryReport ? formatCount(deliveryReport.cancelled_sessions) : '—' },
            ]" />

          <ManagementMetricCard label="Attendance Records" icon="how_to_reg" icon-tone="accent"
            :value="attendanceReport ? formatCount(attendanceReport.eligible_record_count) : '—'"
            :value-muted="!attendanceReport || isLoadingReports || !!reportingErrors.attendance" badge-text="Records"
            badge-tone="neutral"
            :description="attendanceReport ? `${formatCount(attendanceReport.attendance_percentage)}% present` : 'Eligible attendance records; not student headcount'"
            :footer-items="[
              { label: 'Present', value: attendanceReport ? formatCount(attendanceReport.present_record_count) : '—', valueTone: 'green' },
              { label: 'Absent', value: attendanceReport ? formatCount(attendanceReport.absent_record_count) : '—' },
            ]" />

          <ManagementMetricCard label="Engagement Score" icon="psychology" icon-tone="terra"
            :value="engagementReport?.average_engagement == null ? '—' : engagementReport.average_engagement.toFixed(2)"
            :value-muted="engagementReport?.average_engagement == null || isLoadingReports || !!reportingErrors.engagement"
            denominator="/ 10" :badge-text="engagementReport?.average_engagement == null ? 'No scores' : 'Reported'"
            badge-tone="neutral"
            :description="engagementReport?.average_engagement == null ? 'No scored sessions for this period' : 'Average recorded engagement score'"
            :footer-items="[
              { label: 'Scored sessions', value: engagementReport ? formatCount(engagementReport.scored_session_count) : '—' },
              { label: 'Missing scores', value: engagementReport ? formatCount(engagementReport.missing_engagement_count) : '—', valueTone: 'muted' },
            ]" />

          <ManagementMetricCard label="Duration Recorded" icon="fact_check" icon-tone="accent"
            :value="deliveryReport ? formatCount(deliveryReport.completed_sessions_with_duration) : '—'"
            :value-muted="!deliveryReport || isLoadingReports || !!reportingErrors.delivery" badge-text="Recorded"
            badge-tone="neutral"
            :description="deliveryReport ? 'Completed sessions with duration entered' : 'Duration reporting unavailable'"
            :footer-items="[
              { label: 'Completed', value: deliveryReport ? formatCount(deliveryReport.completed_sessions) : '—' },
              { label: 'Teaching hours', value: deliveryReport ? formatCount(deliveryReport.teaching_hours) : '—' },
            ]" />
        </section>

        <!-- ─── Session Delivery Trajectory Chart ─────────────────────────── -->
        <DeliveryTrajectoryChart :items="deliveryTrend" :start-date="selectedAcademicYear?.start_date ?? ''"
          :end-date="selectedAcademicYear?.end_date ?? ''" :loading="isLoadingReports" :error="reportingErrors.trend" />

        <!-- ─── Operational Attention ───────────────────────────────────────── -->
        <section class="ov-attention-grid" aria-label="Operational attention">
          <ManagementAttentionPanel>
            <div class="ov-panel-header">
              <div class="ov-panel-title-wrap">
                <span class="material-symbols-outlined ov-panel-icon ov-panel-icon--amber"
                  aria-hidden="true">event_busy</span>
                <h3 class="ov-panel-title">Academic Planning Bottlenecks</h3>
              </div>
              <span class="ov-panel-badge ov-panel-badge--terra">Not connected</span>
            </div>
            <p class="ov-panel-item-desc">
              A live planning-alert feed is not connected. No bottlenecks are being asserted by this dashboard.
            </p>
          </ManagementAttentionPanel>

          <ManagementAttentionPanel>
            <div class="ov-panel-header">
              <div class="ov-panel-title-wrap">
                <span class="material-symbols-outlined ov-panel-icon ov-panel-icon--teal"
                  aria-hidden="true">biotech</span>
                <h3 class="ov-panel-title">Observations &amp; STEM Inspections</h3>
              </div>
              <span class="ov-panel-badge ov-panel-badge--accent">Not connected</span>
            </div>
            <p class="ov-panel-item-desc">
              A live observation and inspection feed is not connected. No pending sign-offs are being inferred.
            </p>
          </ManagementAttentionPanel>
        </section>

        <!-- ─── Quick Operations Navigation ──────────────────────────────── -->
        <section class="ov-shortcuts" aria-label="Quick Operations Navigation">
          <div class="ov-shortcuts-header">
            <h3 class="ov-shortcuts-title">Quick Operations Navigation</h3>
            <span class="ov-shortcuts-desc">Direct access to operational ledgers and workflows</span>
          </div>
          <div class="ov-shortcuts-grid">
            <a href="#calendar" class="ov-shortcut-card">
              <div class="ov-shortcut-top">
                <div class="ov-shortcut-icon ov-shortcut-icon--accent">
                  <span class="material-symbols-outlined" aria-hidden="true">calendar_today</span>
                </div>
                <div>
                  <h4 class="ov-shortcut-title">Academic Calendar</h4>
                  <p class="ov-shortcut-desc">Term schedules, examination slots, and holiday calendars</p>
                </div>
              </div>
              <div class="ov-shortcut-footer">
                <span>{{ selectedAcademicYear?.name ?? 'No year selected' }}</span>
                <span class="material-symbols-outlined ov-shortcut-arrow" aria-hidden="true">arrow_forward</span>
              </div>
            </a>
            <a href="#planning" class="ov-shortcut-card">
              <div class="ov-shortcut-top">
                <div class="ov-shortcut-icon ov-shortcut-icon--neutral">
                  <span class="material-symbols-outlined" aria-hidden="true">schedule</span>
                </div>
                <div>
                  <h4 class="ov-shortcut-title">Session Planning</h4>
                  <p class="ov-shortcut-desc">Review weekly lesson allocations and educator timetables</p>
                </div>
              </div>
              <div class="ov-shortcut-footer">
                <span>Planning feed not connected</span>
                <span class="material-symbols-outlined ov-shortcut-arrow" aria-hidden="true">arrow_forward</span>
              </div>
            </a>
            <a href="#reports" class="ov-shortcut-card">
              <div class="ov-shortcut-top">
                <div class="ov-shortcut-icon ov-shortcut-icon--accent">
                  <span class="material-symbols-outlined" aria-hidden="true">analytics</span>
                </div>
                <div>
                  <h4 class="ov-shortcut-title">Reports &amp; Analytics</h4>
                  <p class="ov-shortcut-desc">Export verified attendance and session compliance digests</p>
                </div>
              </div>
              <div class="ov-shortcut-footer">
                <span>Reports available via live APIs</span>
                <span class="material-symbols-outlined ov-shortcut-arrow" aria-hidden="true">arrow_forward</span>
              </div>
            </a>
            <a href="#schools" class="ov-shortcut-card">
              <div class="ov-shortcut-top">
                <div class="ov-shortcut-icon ov-shortcut-icon--terra">
                  <span class="material-symbols-outlined" aria-hidden="true">domain</span>
                </div>
                <div>
                  <h4 class="ov-shortcut-title">Schools &amp; Classes</h4>
                  <p class="ov-shortcut-desc">Manage participating STEM campuses and laboratory centers</p>
                </div>
              </div>
              <div class="ov-shortcut-footer">
                <span>School directory not connected</span>
                <span class="material-symbols-outlined ov-shortcut-arrow" aria-hidden="true">arrow_forward</span>
              </div>
            </a>
          </div>
        </section>

        <!-- ─── Discreet Footer ───────────────────────────────────────────── -->
        <footer class="ov-footer">
          <span>Project Vigyan • Academic Operations Console</span>
          <span>{{ selectedAcademicYear?.name ?? 'No academic year selected' }}</span>
        </footer>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ════════════════════════════════════════════════════════════════════════════ */
/* CSS CUSTOM PROPERTIES — Forest & Ivory Design System                        */
/* ════════════════════════════════════════════════════════════════════════════ */
.ov-shell {
  /* Light mode tokens */
  --ov-bg-page: #FCF9F0;
  --ov-bg-surface: #FFFFFF;
  --ov-bg-surface-subtle: #F0EEE5;
  --ov-bg-surface-muted: #E8E6DC;
  --ov-border: #E2DFD2;
  --ov-border-subtle: #ECE8DC;

  --ov-text-primary: #202A24;
  --ov-text-secondary: #59665D;
  --ov-text-muted: #778178;

  --ov-sidebar-bg: #193D30;
  --ov-sidebar-text: #F7F5ED;
  --ov-sidebar-muted: #A3B5AA;
  --ov-sidebar-hover: #244B3B;
  --ov-sidebar-active: #244B3B;
  --ov-sidebar-border: #315445;

  --ov-brand: #193D30;
  --ov-brand-hover: #122F24;
  --ov-terra: #C47755;
  --ov-terra-hover: #AA6245;

  --ov-tag-accent-bg: #E1EBE2;
  --ov-tag-accent-fg: #193D30;
  --ov-tag-terra-bg: #F5E5DC;
  --ov-tag-terra-fg: #9C4B27;

  --ov-chart-total: #C8B89E;
  --ov-chart-completed: #193D30;
}

/* Dark mode override */
.ov-shell.ov-dark,
:global([data-ov-theme="dark"]) .ov-shell {
  --ov-bg-page: #151E19;
  --ov-bg-surface: #1D2922;
  --ov-bg-surface-subtle: #23332A;
  --ov-bg-surface-muted: #2C3C32;
  --ov-border: #35463A;
  --ov-border-subtle: #29382E;

  --ov-text-primary: #F0F1E8;
  --ov-text-secondary: #C1CCC1;
  --ov-text-muted: #99A99B;

  --ov-sidebar-bg: #101A15;
  --ov-sidebar-text: #F7F5ED;
  --ov-sidebar-muted: #8E9F94;
  --ov-sidebar-hover: #192620;
  --ov-sidebar-active: #23372E;
  --ov-sidebar-border: #1C2B22;

  --ov-brand: #C8A856;
  --ov-brand-hover: #D8BD78;
  --ov-terra: #E0A080;
  --ov-terra-hover: #EBB69D;

  --ov-tag-accent-bg: #23382D;
  --ov-tag-accent-fg: #C8A856;
  --ov-tag-terra-bg: #38251E;
  --ov-tag-terra-fg: #F0A09A;

  --ov-chart-total: #4A5B50;
  --ov-chart-completed: #C8A856;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/* SHELL LAYOUT                                                                 */
/* ════════════════════════════════════════════════════════════════════════════ */
.ov-shell {
  display: flex;
  width: 100%;
  min-height: 100svh;
  background-color: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  overflow: hidden;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/* BACKDROP                                                                     */
/* ════════════════════════════════════════════════════════════════════════════ */
.ov-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 40;
  opacity: 0;
  pointer-events: none;
  transition: opacity 300ms ease;
}

.ov-backdrop--visible {
  opacity: 1;
  pointer-events: auto;
}

@media (min-width: 768px) {
  .ov-backdrop {
    display: none;
  }
}


/* Main canvas and responsive dashboard layout */
.ov-main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 100svh;
  width: 100%;
  margin-left: 0;
  display: flex;
  flex-direction: column;
  transition: margin-left 300ms ease;
  overflow: hidden;
}

.ov-main--expanded {
  margin-left: 248px;
}

.ov-main--rail {
  margin-left: 68px;
}

.ov-workspace {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  min-width: 0;
  padding: 24px 28px 32px;
  overflow-x: hidden;
}

@media (max-width: 1279px) {
  .ov-workspace {
    padding-inline: 20px;
  }
}

@media (max-width: 900px) {
  .ov-workspace {
    padding: 18px;
  }
}

@media (max-width: 767px) {

  .ov-main,
  .ov-main--expanded,
  .ov-main--rail {
    width: 100%;
    margin-left: 0;
  }

  .ov-workspace {
    gap: 16px;
    padding: 16px 12px 24px;
  }
}

@media (max-width: 380px) {
  .ov-workspace {
    padding-inline: 10px;
  }
}

.ov-preview-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface-subtle);
  font-size: 11px;
  font-weight: 500;
  color: var(--ov-text-secondary);
}

.ov-preview-banner-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.ov-preview-banner-left span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ov-preview-icon {
  font-size: 15px;
  color: #92650a;
  flex-shrink: 0;
}

.ov-shell.ov-dark .ov-preview-icon {
  color: #f0b94a;
}

.ov-preview-badge {
  flex-shrink: 0;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background-color: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
  display: none;
}

@media (min-width: 640px) {
  .ov-preview-badge {
    display: inline-block;
  }
}

/* ─── KPI Grid ────────────────────────────────────────────────────────────── */
.ov-kpi-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 640px) {
  .ov-kpi-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (min-width: 1280px) {
  .ov-kpi-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}



/* ─── Attention Panels ────────────────────────────────────────────────────── */
.ov-attention-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 1024px) {
  .ov-attention-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.ov-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ov-border-subtle);
}

.ov-panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ov-panel-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.ov-panel-icon--amber {
  color: #92650a;
}

.ov-panel-icon--teal {
  color: #1a7a6e;
}

.ov-shell.ov-dark .ov-panel-icon--amber {
  color: #f0b94a;
}

.ov-shell.ov-dark .ov-panel-icon--teal {
  color: #4fd5c8;
}

.ov-panel-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ov-text-primary);
  margin: 0;
}

.ov-panel-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
}

.ov-panel-badge--terra {
  background-color: var(--ov-tag-terra-bg);
  color: var(--ov-tag-terra-fg);
}

.ov-panel-badge--accent {
  background-color: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
}

.ov-panel-items {
  display: flex;
  flex-direction: column;
  margin-top: 8px;
}

.ov-panel-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--ov-border-subtle);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ov-panel-item:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

@media (min-width: 640px) {
  .ov-panel-item {
    flex-direction: row;
    align-items: flex-start;
  }
}

.ov-panel-item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ov-panel-item-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ov-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 6px;
  border-radius: 4px;
}

.ov-tag--terra {
  background-color: var(--ov-tag-terra-bg);
  color: var(--ov-tag-terra-fg);
}

.ov-tag--neutral {
  background-color: var(--ov-bg-surface-subtle);
  border: 1px solid var(--ov-border);
  color: var(--ov-text-secondary);
}

.ov-panel-item-meta {
  font-size: 11px;
  font-weight: 500;
  color: var(--ov-text-muted);
}

.ov-panel-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text-primary);
  line-height: 1.35;
}

.ov-panel-item-desc {
  font-size: 12px;
  color: var(--ov-text-secondary);
}

.ov-panel-item-date {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--ov-text-muted);
  font-variant-numeric: tabular-nums;
}

.ov-panel-item-date .material-symbols-outlined {
  font-size: 13px;
}

.ov-panel-action {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 150ms;
  align-self: flex-start;
  white-space: nowrap;
  font-family: inherit;
}

@media (min-width: 640px) {
  .ov-panel-action {
    align-self: center;
  }
}

.ov-panel-action--outline {
  background-color: var(--ov-bg-surface);
  border: 1px solid var(--ov-border);
  color: var(--ov-text-primary);
  text-decoration: none;
  display: inline-block;
}

.ov-panel-action--outline:hover {
  background-color: var(--ov-bg-surface-subtle);
}

.ov-panel-action--primary {
  background-color: var(--ov-terra);
  border: 0;
  color: #fff;
}

.ov-panel-action--primary:hover {
  background-color: var(--ov-terra-hover);
}

.ov-panel-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--ov-border-subtle);
  font-size: 12px;
  color: var(--ov-text-muted);
}

.ov-panel-link {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  color: var(--ov-brand);
  text-decoration: none;
  transition: text-decoration 150ms;
}

.ov-panel-link:hover {
  text-decoration: underline;
}

.ov-panel-link .material-symbols-outlined {
  font-size: 15px;
}

/* ─── Quick Shortcuts ─────────────────────────────────────────────────────── */
.ov-shortcuts {
  min-width: 0;
}

.ov-shortcuts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.ov-shortcuts-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ov-text-primary);
  margin: 0;
}

.ov-shortcuts-desc {
  font-size: 12px;
  color: var(--ov-text-muted);
}

.ov-shortcuts-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 640px) {
  .ov-shortcuts-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (min-width: 1280px) {
  .ov-shortcuts-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.ov-shortcut-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 12px;
  text-decoration: none;
  min-width: 0;
  box-shadow: 0 1px 2px rgba(20, 30, 24, 0.04);
  transition: border-color 150ms;
}

.ov-shortcut-card:hover {
  border-color: color-mix(in srgb, var(--ov-brand) 40%, var(--ov-border));
}

.ov-shortcut-card:hover .ov-shortcut-title {
  text-decoration: underline;
}

.ov-shortcut-card:hover .ov-shortcut-arrow {
  transform: translateX(2px);
}

.ov-shortcut-top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ov-shortcut-icon {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.ov-shortcut-icon .material-symbols-outlined {
  font-size: 19px;
}

.ov-shortcut-icon--accent {
  background-color: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
}

.ov-shortcut-icon--neutral {
  background-color: var(--ov-bg-surface-subtle);
  color: var(--ov-text-primary);
}

.ov-shortcut-icon--terra {
  background-color: var(--ov-tag-terra-bg);
  color: var(--ov-tag-terra-fg);
}

.ov-shortcut-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text-primary);
  margin: 0;
  line-height: 1.3;
}

.ov-shortcut-desc {
  font-size: 12px;
  color: var(--ov-text-secondary);
  margin: 4px 0 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ov-shortcut-footer {
  padding-top: 10px;
  border-top: 1px solid var(--ov-border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--ov-text-muted);
}

.ov-shortcut-arrow {
  font-size: 15px;
  transition: transform 200ms;
}

/* ─── Footer ──────────────────────────────────────────────────────────────── */
.ov-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--ov-border-subtle);
  font-size: 11px;
  color: var(--ov-text-muted);
  margin-top: auto;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/* REDUCED MOTION                                                               */
/* ════════════════════════════════════════════════════════════════════════════ */
@media (prefers-reduced-motion: reduce) {

  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

/* ─── Create Academic Year Form ───────────────────────────────────────────── */
.ov-create-year-panel {
  width: 100%;
  padding: 20px;
  border: 1px solid var(--ov-border);
  border-radius: 10px;
  background: var(--ov-bg-surface);
  box-shadow: 0 1px 3px rgba(20, 30, 24, 0.04);
}

.ov-create-year-heading h2 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 16px;
  font-weight: 700;
}

.ov-create-year-heading p {
  margin: 5px 0 0;
  color: var(--ov-text-secondary);
  font-size: 12px;
}

.ov-create-year-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.ov-form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  color: var(--ov-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.ov-form-field input {
  width: 100%;
  min-height: 40px;
  padding: 9px 11px;
  border: 1px solid var(--ov-border);
  border-radius: 7px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font: inherit;
  font-weight: 400;
}

.ov-form-field input:focus {
  outline: 2px solid var(--ov-brand);
  outline-offset: 1px;
}

.ov-form-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ov-text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.ov-form-checkbox input {
  width: 16px;
  height: 16px;
  accent-color: var(--ov-brand);
}

.ov-create-year-error {
  grid-column: 1 / -1;
  margin: 0;
  color: #b42318;
  font-size: 12px;
}

.ov-create-year-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}

.ov-form-secondary,
.ov-form-primary {
  min-height: 36px;
  padding: 8px 13px;
  border-radius: 7px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ov-form-secondary {
  border: 1px solid var(--ov-border);
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
}

.ov-form-primary {
  border: 1px solid var(--ov-brand);
  background: var(--ov-brand);
  color: #fff;
}

.ov-form-secondary:disabled,
.ov-form-primary:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

@media (max-width: 767px) {
  .ov-create-year-panel {
    padding: 16px;
  }

  .ov-create-year-form {
    grid-template-columns: 1fr;
    gap: 13px;
  }

  .ov-create-year-error,
  .ov-create-year-actions {
    grid-column: 1;
  }

  .ov-create-year-actions {
    flex-wrap: wrap;
  }
}
</style>
