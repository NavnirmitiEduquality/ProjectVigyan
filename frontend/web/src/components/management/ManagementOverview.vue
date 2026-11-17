<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { CurrentUser } from '../../services/auth'
import {
  createAcademicYear,
  listAcademicYears,
} from '../../services/academicCalendar'
import {
  getAttendanceReport,
  getClassesReport,
  getDeliveryReport,
  getDeliveryTrend,
  getEngagementReport,
  getTlmReport,
} from '../../services/reporting'

import type {
  AttendanceReportItem,
  ClassMonitoringItem,
  DeliveryReportItem,
  DeliveryTrendItem,
  EngagementReportItem,
  ReportingFilters,
  TlmReportItem,
} from '../../services/reporting'
import {
  listObservations,
  listInspections,
} from '../../services/observations'

import type {
  ObservationRecord,
  InspectionRecord,
} from '../../services/observations'

import {
  listPlanningNotifications,
  type PlanningNotification,
} from '../../services/planningNotifications'

import { listHolidays } from '../../services/academicCalendar'
import type { AcademicYear } from '../../services/academicCalendar'
import { isDarkTheme, type ThemeMode } from '../../services/theme'
import ManagementSidebar from './ManagementSidebar.vue'
import ManagementHeader from './ManagementHeader.vue'
import SessionPlanning from './session-planning/SessionPlanning.vue'
import InstitutionalFooter from '../layout/InstitutionalFooter.vue'
import ManagementMetricCard from './ManagementMetricCard.vue'
import DeliveryTrajectoryChart from './DeliveryTrajectoryChart.vue'
import ManagementAttentionPanel from './ManagementAttentionPanel.vue'
import AttendanceAnalysisChart from './AttendanceAnalysisChart.vue'
import EngagementDistributionChart from './EngagementDistributionChart.vue'
import SchoolClassPerformanceChart from './SchoolClassPerformanceChart.vue'
import AssessmentProgressSummary from './AssessmentProgressSummary.vue'
import SchoolsView from './schools/SchoolsView.vue'
import AcademicCalendar from './academic-calendar/AcademicCalendar.vue'
import StudentsDirectory from './students/StudentsDirectory.vue'
import TeachersDirectory from './teachers/TeachersDirectory.vue'
import { listSchools, type School } from '../../services/schools'
import {
  listClassDivisions,
  type ClassDivision,
} from '../../services/classDivisions'
type ManagementSection =
  | 'overview'
  | 'academic-calendar'
  | 'schools'
  | 'students'
  | 'teachers'
  | 'session-planning'

// ─── Props ───────────────────────────────────────────────────────────────────
const props = defineProps<{
  currentUser: CurrentUser | null
  initialTheme: ThemeMode
}>()

const emit = defineEmits<{
  returnToSignIn: []
  changeTheme: [mode: ThemeMode]
}>()
const route = useRoute()
const router = useRouter()
const activeSection = computed<ManagementSection>(() =>
  route.meta.section === 'schools'
    ? 'schools'
    : route.meta.section === 'students'
      ? 'students'
      : route.meta.section === 'teachers'
        ? 'teachers'
        : route.meta.section === 'session-planning'
          ? 'session-planning'
          : route.meta.section === 'academic-calendar'
            ? 'academic-calendar'
            : 'overview',
)

// ─── Theme ────────────────────────────────────────────────────────────────────
const themeMode = computed(() => props.initialTheme)
const isDark = computed(() => isDarkTheme(themeMode.value))

function applyTheme(mode: ThemeMode) {
  emit('changeTheme', mode)
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
function navigate(section: ManagementSection) {
  void router.push({ name: section })
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
const activeAcademicYear = computed(
  () => academicYears.value.find((year) => year.is_active) ?? null,
)
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
const schools = ref<School[]>([])
const classDivisions = ref<ClassDivision[]>([])
const paraTeacherOptions = ref<DeliveryReportItem[]>([])

const selectedSchoolId = ref('')
const selectedClassDivisionId = ref('')
const selectedParaTeacherId = ref('')
const classMonitoringItems = ref<ClassMonitoringItem[]>([])
const classMonitoringLoaded = ref(false)
const classMonitoringError = ref('')
const filterStartDate = ref('')
const filterEndDate = ref('')

const isLoadingFilters = ref(false)
const filterOptionsError = ref('')
const dateRangeError = ref('')
const paraTeacherOptionsError = ref('')

const activeReportingFilters = computed(() => ({
  academicYearId: selectedYear.value,
  startDate: filterStartDate.value || undefined,
  endDate: filterEndDate.value || undefined,
  schoolId: selectedSchoolId.value || undefined,
  classDivisionId: selectedClassDivisionId.value || undefined,
  paraTeacherId: selectedParaTeacherId.value || undefined,
}))

const availableClassDivisions = computed(() =>
  classDivisions.value
    .filter((division) =>
      division.status === 'ACTIVE' &&
      division.data_origin === 'PRODUCTION' &&
      (!selectedSchoolId.value ||
        division.school_id === selectedSchoolId.value),
    )
    .sort((a, b) =>
      a.class_level - b.class_level ||
      a.division.localeCompare(b.division),
    ),
)

const availableParaTeachers = computed(() =>
  paraTeacherOptions.value
    .filter((teacher) => teacher.para_teacher_id)
    .sort((a, b) =>
      (a.para_teacher_name ?? '').localeCompare(
        b.para_teacher_name ?? '',
      ),
    ),
)
const activeSchoolsCount = computed(() => {
  if (selectedSchoolId.value) {
    return schools.value.some(
      school => school.id === selectedSchoolId.value,
    ) ? 1 : 0
  }

  return schools.value.length
})

const activeStudentsCount = computed(() => {
  if (!classMonitoringLoaded.value || classMonitoringError.value) {
    return null
  }

  return classMonitoringItems.value
    .filter(item => item.status === 'ACTIVE')
    .reduce(
      (total, item) => total + item.active_students,
      0,
    )
})

const evidenceCoverageStats = computed(() => {
  if (!classMonitoringLoaded.value || classMonitoringError.value) {
    return null
  }

  const eligible = classMonitoringItems.value.reduce(
    (total, item) =>
      total + item.evidence.eligible_completed_sessions,
    0,
  )

  const withEvidence = classMonitoringItems.value.reduce(
    (total, item) =>
      total + item.evidence.sessions_with_evidence,
    0,
  )

  return {
    eligible,
    withEvidence,
    percentage: eligible > 0
      ? (withEvidence / eligible) * 100
      : null,
  }
})

async function loadFilterOptions() {
  isLoadingFilters.value = true
  filterOptionsError.value = ''

  const [schoolResult, divisionResult] = await Promise.allSettled([
    listSchools(),
    listClassDivisions(),
  ])

  if (schoolResult.status === 'fulfilled') {
    schools.value = schoolResult.value.filter(
      (school) =>
        school.status === 'ACTIVE' &&
        school.data_origin === 'PRODUCTION',
    )
  } else {
    filterOptionsError.value = 'Unable to load the school filter options.'
  }

  if (divisionResult.status === 'fulfilled') {
    classDivisions.value = divisionResult.value
  } else {
    filterOptionsError.value = [
      filterOptionsError.value,
      'Unable to load class-division filter options.',
    ].filter(Boolean).join(' ')
  }

  isLoadingFilters.value = false
}

function clearOverviewFilters() {
  selectedSchoolId.value = ''
  selectedClassDivisionId.value = ''
  selectedParaTeacherId.value = ''
  filterStartDate.value = ''
  filterEndDate.value = ''
}

watch(selectedSchoolId, () => {
  selectedClassDivisionId.value = ''
  selectedParaTeacherId.value = ''
})

watch(selectedClassDivisionId, () => {
  selectedParaTeacherId.value = ''
})

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

const holidays = ref<Awaited<ReturnType<typeof listHolidays>>>([])
const holidaysError = ref('')
const isLoadingHolidays = ref(false)

const observations = ref<ObservationRecord[]>([])
const inspections = ref<InspectionRecord[]>([])

const observationsError = ref('')
const inspectionsError = ref('')

const isLoadingOperations = ref(false)

const canViewObservations = computed(
  () => props.currentUser?.permissions.includes(
    'classroom_observation.view',
  ) ?? false,
)

const canViewInspections = computed(
  () => props.currentUser?.permissions.includes(
    'stem_inspection.view',
  ) ?? false,
)

const canViewCalendar = computed(
  () => props.currentUser?.permissions.includes(
    'calendar.view',
  ) ?? false,
)

const canViewReports = computed(
  () => props.currentUser?.permissions.includes('report.view') ?? false,
)

const observationStatuses = computed(() =>
  observations.value.reduce<Record<string, number>>(
    (result, record) => {
      result[record.report_status] =
        (result[record.report_status] ?? 0) + 1
      return result
    },
    {},
  ),
)

const inspectionStatuses = computed(() =>
  inspections.value.reduce<Record<string, number>>(
    (result, record) => {
      result[record.report_status] =
        (result[record.report_status] ?? 0) + 1
      return result
    },
    {},
  ),
)

async function loadOperationalSummaries() {
  isLoadingOperations.value = true

  observationsError.value = ''
  inspectionsError.value = ''

  const requests = await Promise.allSettled([
    canViewObservations.value
      ? listObservations()
      : Promise.resolve(null),

    canViewInspections.value
      ? listInspections()
      : Promise.resolve(null),
  ])

  const [observationResult, inspectionResult] = requests

  if (observationResult.status === 'fulfilled') {
    observations.value = observationResult.value ?? []
  } else {
    observations.value = []
    observationsError.value =
      observationResult.reason instanceof Error
        ? observationResult.reason.message
        : 'Unable to load observation records.'
  }

  if (inspectionResult.status === 'fulfilled') {
    inspections.value = inspectionResult.value ?? []
  } else {
    inspections.value = []
    inspectionsError.value =
      inspectionResult.reason instanceof Error
        ? inspectionResult.reason.message
        : 'Unable to load inspection records.'
  }

  isLoadingOperations.value = false
}

async function loadHolidaySummary() {
  if (!canViewCalendar.value) return

  isLoadingHolidays.value = true
  holidaysError.value = ''

  try {
    holidays.value = await listHolidays()
  } catch (error) {
    holidays.value = []
    holidaysError.value =
      error instanceof Error
        ? error.message
        : 'Unable to load holiday information.'
  } finally {
    isLoadingHolidays.value = false
  }
}

// ─── Live reporting ─────────────────────────────────────────────────────────
const deliveryReport = ref<DeliveryReportItem | null>(null)
const attendanceReport = ref<AttendanceReportItem | null>(null)
const engagementReport = ref<EngagementReportItem | null>(null)
const tlmReport = ref<TlmReportItem | null>(null)
const deliveryTrend = ref<DeliveryTrendItem[]>([])
const isLoadingReports = ref(false)
const reportingErrors = ref({
  delivery: '',
  attendance: '',
  engagement: '',
  trend: '',
  tlm: '',
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
    return `Some reporting data could not be loaded (${reportingErrorMessages.value.length} of 5 reports).`
  }
  return 'Live reporting data • Production records only'
})

async function loadReports() {
  const requestId = ++reportRequestId
  const filters: ReportingFilters = {
    ...activeReportingFilters.value,
  }

  reportingErrors.value = {
    delivery: '',
    attendance: '',
    engagement: '',
    trend: '',
    tlm: '',
  }

  deliveryReport.value = null
  attendanceReport.value = null
  engagementReport.value = null
  deliveryTrend.value = []
  tlmReport.value = null
  classMonitoringItems.value = []
  classMonitoringError.value = ''
  classMonitoringLoaded.value = false
  classMonitoringError.value = ''
  if (!filters.academicYearId) {
    isLoadingReports.value = false
    paraTeacherOptions.value = []
    return
  }

  if (!canViewReports.value) {
    paraTeacherOptions.value = []
    isLoadingReports.value = false
    return
  }

  if (
    filters.startDate &&
    filters.endDate &&
    filters.startDate > filters.endDate
  ) {
    dateRangeError.value = 'The end date must not be earlier than the start date.'
    isLoadingReports.value = false
    return
  }

  isLoadingReports.value = true

  // Do not constrain the option list by the currently selected para-teacher.
  const paraTeacherFilters: ReportingFilters = {
    ...filters,
    paraTeacherId: undefined,
  }

  const results = await Promise.allSettled([
    getDeliveryReport(filters),
    getAttendanceReport(filters),
    getEngagementReport(filters),
    getDeliveryTrend(filters),
    getTlmReport(filters),
    getDeliveryReport(paraTeacherFilters, 'para_teacher'),
    getClassesReport(filters),
  ])

  if (requestId !== reportRequestId) return

  const [
    delivery,
    attendance,
    engagement,
    trend,
    tlm,
    paraTeachers,
    classes,
  ] = results

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

  if (classes.status === 'fulfilled') {
    classMonitoringItems.value = classes.value.items
    classMonitoringLoaded.value = true
    classMonitoringError.value = ''
  } else {
    classMonitoringItems.value = []
    classMonitoringLoaded.value = false
    classMonitoringError.value =
      classes.reason instanceof Error
        ? classes.reason.message
        : 'Unable to load class monitoring data.'
  }

  if (trend.status === 'fulfilled') {
    deliveryTrend.value = trend.value.items
  } else {
    reportingErrors.value.trend =
      trend.reason instanceof Error
        ? trend.reason.message
        : 'Unable to load delivery trend data.'
  }

  if (paraTeachers.status === 'fulfilled') {
    paraTeacherOptions.value = paraTeachers.value.items
    paraTeacherOptionsError.value = ''
  } else {
    paraTeacherOptions.value = []
    paraTeacherOptionsError.value =
      paraTeachers.reason instanceof Error
        ? `Para-teacher options unavailable: ${paraTeachers.reason.message}`
        : 'Para-teacher options are unavailable.'
  }

  if (tlm.status === 'fulfilled') {
    tlmReport.value = tlm.value.items[0] ?? null
  } else {
    reportingErrors.value.tlm =
      tlm.reason instanceof Error
        ? tlm.reason.message
        : 'Unable to load TLM recording data.'
  }
  isLoadingReports.value = false
}

watch(
  activeReportingFilters,
  () => {
    dateRangeError.value = ''
    paraTeacherOptionsError.value = ''
    void loadReports()
  },
  { deep: true },
)

watch(canViewReports, () => {
  void loadReports()
})

// ─── Planning Notifications ──────────────────────────────────────────────────
const canViewPlanningNotifications = computed(
  () =>
    props.currentUser?.permissions.includes('planning_notification.view') ?? false,
)

const planningNotifications = ref<PlanningNotification[]>([])
const isLoadingPlanningNotifications = ref(false)
const planningNotificationsError = ref('')

const unreadPlanningNotificationCount = computed(
  () => planningNotifications.value.filter((item) => !item.is_read).length,
)

async function loadPlanningNotifications() {
  if (!canViewPlanningNotifications.value) {
    planningNotifications.value = []
    planningNotificationsError.value = ''
    return
  }

  isLoadingPlanningNotifications.value = true
  planningNotificationsError.value = ''

  try {
    planningNotifications.value = await listPlanningNotifications()
  } catch (error) {
    planningNotificationsError.value =
      error instanceof Error
        ? error.message
        : 'Unable to load planning notifications.'
  } finally {
    isLoadingPlanningNotifications.value = false
  }
}

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
  handleResize()
  void loadFilterOptions()
  void loadAcademicYears()
  void loadOperationalSummaries()
  void loadHolidaySummary()
  void loadPlanningNotifications()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <div class="ov-shell" :class="[isDark ? 'ov-dark' : '', isRailCollapsed ? 'ov-is-rail' : '']">
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- MOBILE DRAWER BACKDROP                                                 -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <div class="ov-backdrop" :class="isMobileDrawerOpen ? 'ov-backdrop--visible' : ''" @click="closeMobileDrawer"
      aria-hidden="true" />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- SIDEBAR                                                                 -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <ManagementSidebar :is-rail-collapsed="isRailCollapsed" :is-mobile-drawer-open="isMobileDrawerOpen"
      :active-section="activeSection" @toggle-collapse="toggleSidebarCollapse" @close-drawer="closeMobileDrawer"
      @navigate="navigate" />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!-- MAIN CANVAS                                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <div class="ov-main" :class="mainMargin" id="ov-main-canvas">

      <ManagementHeader :is-rail-collapsed="isRailCollapsed"
        :title="activeSection === 'schools' ? 'Schools & Classes' : activeSection === 'students' ? 'Students Directory' : activeSection === 'teachers' ? 'Teachers Directory' : activeSection === 'session-planning' ? 'Session Planning' : 'Management Overview'"
        :selected-year="selectedYear" :academic-years="academicYears"
        :is-loading-academic-years="isLoadingAcademicYears" :academic-year-error="academicYearError"
        :can-manage-calendar="canManageCalendar" :theme-mode="themeMode" :display-name="displayName"
        :user-initials="userInitials" :unread-planning-notification-count="unreadPlanningNotificationCount"
        :can-view-planning-notifications="canViewPlanningNotifications" :planning-notifications="planningNotifications"
        :is-loading-planning-notifications="isLoadingPlanningNotifications"
        :planning-notifications-error="planningNotificationsError" @open-mobile-drawer="openMobileDrawer"
        @toggle-sidebar="toggleSidebarCollapse" @update:selected-year="selectedYear = $event"
        @create-academic-year="openCreateAcademicYear" @change-theme="applyTheme" @sign-out="emit('returnToSignIn')"
        @refresh-planning-notifications="loadPlanningNotifications" />
      <!-- SCROLLABLE WORKSPACE -->
      <main class="ov-workspace" :id="activeSection">
        <AcademicCalendar v-if="activeSection === 'academic-calendar'" :current-user="props.currentUser"
          :academic-year="activeAcademicYear" :para-teachers="availableParaTeachers" />
        <SessionPlanning v-else-if="activeSection === 'session-planning'" :current-user="props.currentUser" />
        <SchoolsView v-else-if="activeSection === 'schools'" :current-user="props.currentUser" />
        <StudentsDirectory v-else-if="activeSection === 'students'" :current-user="props.currentUser" />
        <TeachersDirectory v-else-if="activeSection === 'teachers'" :current-user="props.currentUser" />
        <template v-else>
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
          <!-- ─── Overview Filters ───────────────────────────────────────────── -->
          <section class="ov-filter-panel" aria-label="Overview filters">
            <div class="ov-filter-heading">
              <div>
                <h2>Dashboard Filters</h2>
                <p>Refine reporting by period, school and teaching assignment.</p>
              </div>

              <button type="button" class="ov-filter-clear" @click="clearOverviewFilters">
                Clear filters
              </button>
            </div>

            <div class="ov-filter-grid">
              <label class="ov-filter-field">
                <span>Start date</span>
                <input v-model="filterStartDate" type="date" :min="selectedAcademicYear?.start_date"
                  :max="filterEndDate || selectedAcademicYear?.end_date" :disabled="!selectedYear" />
              </label>

              <label class="ov-filter-field">
                <span>End date</span>
                <input v-model="filterEndDate" type="date" :min="filterStartDate || selectedAcademicYear?.start_date"
                  :max="selectedAcademicYear?.end_date" :disabled="!selectedYear" />
              </label>

              <label class="ov-filter-field">
                <span>School</span>
                <select v-model="selectedSchoolId" :disabled="isLoadingFilters">
                  <option value="">All authorized schools</option>
                  <option v-for="school in schools" :key="school.id" :value="school.id">
                    {{ school.school_name }}
                  </option>
                </select>
              </label>

              <label class="ov-filter-field">
                <span>Class / Division</span>
                <select v-model="selectedClassDivisionId" :disabled="!selectedSchoolId || isLoadingFilters">
                  <option value="">All classes</option>
                  <option v-for="division in availableClassDivisions" :key="division.id" :value="division.id">
                    Class {{ division.class_level }} – {{ division.division }}
                  </option>
                </select>
              </label>

              <label class="ov-filter-field">
                <span>Para-teacher</span>
                <select v-model="selectedParaTeacherId" :disabled="isLoadingReports || !paraTeacherOptions.length">
                  <option value="">All para-teachers</option>
                  <option v-for="teacher in availableParaTeachers" :key="teacher.para_teacher_id"
                    :value="teacher.para_teacher_id">
                    {{ teacher.para_teacher_name || teacher.para_teacher_code || 'Unnamed para-teacher' }}
                  </option>
                </select>
              </label>
            </div>
            <p v-if="selectedParaTeacherId" class="ov-filter-hint">
              Attendance figures remain scoped to the selected school and class.
              Para-teacher selection does not filter attendance records.
            </p>
            <p v-if="filterOptionsError || dateRangeError || paraTeacherOptionsError" class="ov-filter-error"
              role="alert">
              {{
                [
                  filterOptionsError,
                  dateRangeError,
                  paraTeacherOptionsError,
                ].filter(Boolean).join(' ')
              }}
            </p>
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
            <ManagementMetricCard label="Session Delivery" icon="school" icon-tone="accent" :value="deliveryReport
              ? `${formatCount(deliveryReport.completed_sessions)} / ${formatCount(deliveryReport.total_sessions)}`
              : '—'" :value-muted="!deliveryReport || isLoadingReports || !!reportingErrors.delivery"
              badge-text="Completed / Total" badge-tone="accent" :description="isLoadingReports
                ? 'Loading delivery report…'
                : 'Completed production sessions out of total production sessions'" :footer-items="[
                  { label: 'Planned', value: deliveryReport ? formatCount(deliveryReport.planned_sessions) : '—' },
                  { label: 'In progress', value: deliveryReport ? formatCount(deliveryReport.in_progress_sessions) : '—' },
                  { label: 'Cancelled', value: deliveryReport ? formatCount(deliveryReport.cancelled_sessions) : '—' },
                ]" />

            <ManagementMetricCard label="Attendance Rate" icon="how_to_reg" icon-tone="accent" :value="attendanceReport
              ? `${attendanceReport.attendance_percentage.toFixed(1)}%`
              : '—'" :value-muted="!attendanceReport || isLoadingReports || !!reportingErrors.attendance"
              badge-text="Record-weighted" badge-tone="neutral" :description="attendanceReport
                ? 'Present attendance records as a percentage of eligible records; not unique-student headcount'
                : 'Attendance reporting unavailable'" :footer-items="[
                  { label: 'Present records', value: attendanceReport ? formatCount(attendanceReport.present_record_count) : '—', valueTone: 'green' },
                  { label: 'Absent records', value: attendanceReport ? formatCount(attendanceReport.absent_record_count) : '—' },
                  { label: 'Eligible records', value: attendanceReport ? formatCount(attendanceReport.eligible_record_count) : '—' },
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

            <ManagementMetricCard label="Teaching Hours" icon="schedule" icon-tone="accent"
              :value="deliveryReport ? formatCount(deliveryReport.teaching_hours) : '—'"
              :value-muted="!deliveryReport || isLoadingReports || !!reportingErrors.delivery" denominator="hrs"
              badge-text="Recorded" badge-tone="neutral" :description="deliveryReport
                ? 'Total recorded duration of completed sessions'
                : 'Teaching-hour reporting unavailable'" :footer-items="[
                  { label: 'Completed sessions', value: deliveryReport ? formatCount(deliveryReport.completed_sessions) : '—' },
                  { label: 'Sessions with duration', value: deliveryReport ? formatCount(deliveryReport.completed_sessions_with_duration) : '—' },
                ]" />
            <ManagementMetricCard label="TLM Recording Completeness" icon="inventory_2" icon-tone="terra" :value="tlmReport
              ? `${tlmReport.recording_completeness_percentage.toFixed(1)}%`
              : '—'" :value-muted="!tlmReport || isLoadingReports || !!reportingErrors.tlm" badge-text="Recorded / N/A"
              badge-tone="neutral" :description="tlmReport
                ? 'Eligible sessions with TLM recorded or explicitly marked not applicable'
                : 'TLM recording data unavailable'" :footer-items="[
                  {
                    label: 'Sessions with TLM',
                    value: tlmReport ? formatCount(tlmReport.sessions_with_tlm) : '—',
                  },
                  {
                    label: 'Explicit N/A',
                    value: tlmReport ? formatCount(tlmReport.explicit_na_sessions) : '—',
                  },
                  {
                    label: 'Missing recording',
                    value: tlmReport ? formatCount(tlmReport.missing_tlm_sessions) : '—',
                    valueTone: 'muted',
                  },
                  {
                    label: 'Eligible sessions',
                    value: tlmReport ? formatCount(tlmReport.eligible_sessions) : '—',
                  },
                ]" />
            <ManagementMetricCard label="Active Schools" icon="domain" icon-tone="accent" :value="isLoadingFilters || filterOptionsError
              ? '—'
              : formatCount(activeSchoolsCount)" :value-muted="isLoadingFilters || !!filterOptionsError"
              badge-text="Production" badge-tone="neutral"
              description="Authorized active production schools in the selected school scope" :footer-items="[
                {
                  label: 'Population metric',
                  value: 'Current',
                },
              ]" />

            <ManagementMetricCard label="Active Students" icon="groups" icon-tone="accent" :value="activeStudentsCount === null
              ? '—'
              : formatCount(activeStudentsCount)" :value-muted="activeStudentsCount === null || isLoadingReports"
              badge-text="Active divisions" badge-tone="neutral" :description="classMonitoringError
                ? 'Active student data unavailable'
                : 'Active production students in active production class divisions'" :footer-items="[
                  {
                    label: 'Scope',
                    value: selectedSchoolId ? 'Selected school' : 'Authorized schools',
                  },
                  {
                    label: 'Para-teacher filter',
                    value: 'Not applied',
                  },
                ]" />

            <ManagementMetricCard label="Evidence Coverage" icon="fact_check" icon-tone="terra" :value="evidenceCoverageStats?.percentage == null
              ? '—'
              : `${evidenceCoverageStats.percentage.toFixed(1)}%`" :value-muted="!evidenceCoverageStats ||
                evidenceCoverageStats.percentage == null ||
                isLoadingReports" badge-text="Evidence recorded" badge-tone="neutral" :description="classMonitoringError
                  ? 'Evidence coverage data unavailable'
                  : 'Completed sessions with evidence as a percentage of eligible completed sessions'" :footer-items="[
                    {
                      label: 'Sessions with evidence',
                      value: evidenceCoverageStats
                        ? formatCount(evidenceCoverageStats.withEvidence)
                        : '—',
                    },
                    {
                      label: 'Eligible completed',
                      value: evidenceCoverageStats
                        ? formatCount(evidenceCoverageStats.eligible)
                        : '—',
                    },
                    {
                      label: 'Para-teacher filter',
                      value: 'Not applied',
                    },
                  ]" />
          </section>

          <!-- ─── Session Delivery Trajectory Chart ─────────────────────────── -->
          <div id="overview-reporting" class="ov-reporting-anchor">
            <template v-if="canViewReports">
              <DeliveryTrajectoryChart :items="deliveryTrend" :start-date="selectedAcademicYear?.start_date ?? ''"
                :end-date="selectedAcademicYear?.end_date ?? ''" :filter-start-date="filterStartDate"
                :filter-end-date="filterEndDate" :loading="isLoadingReports" :error="reportingErrors.trend" />

              <section class="ov-reporting-grid" aria-label="Reporting analysis">
                <AttendanceAnalysisChart :report="attendanceReport" :loading="isLoadingReports"
                  :error="reportingErrors.attendance" />

                <EngagementDistributionChart :report="engagementReport" :loading="isLoadingReports"
                  :error="reportingErrors.engagement" />

                <SchoolClassPerformanceChart :items="classMonitoringItems" :loading="isLoadingReports"
                  :error="classMonitoringError" :para-teacher-selected="!!selectedParaTeacherId" />

                <AssessmentProgressSummary :items="classMonitoringItems" :loading="isLoadingReports"
                  :error="classMonitoringError" :para-teacher-selected="!!selectedParaTeacherId" />
              </section>
            </template>

            <section v-else class="ov-reporting-restricted" role="status">
              <h3>Reporting access restricted</h3>
              <p>
                Your account does not have permission to view management reporting.
              </p>
            </section>
          </div>

          <!-- ─── Operational Attention ───────────────────────────────────────── -->
          <section class="ov-attention-grid" aria-label="Operational attention">

            <!-- Academic Planning -->
            <ManagementAttentionPanel>
              <div class="ov-panel-header">
                <div class="ov-panel-title-wrap">
                  <span class="material-symbols-outlined ov-panel-icon ov-panel-icon--amber">
                    event_available
                  </span>
                  <h3 class="ov-panel-title">Academic Planning</h3>
                </div>
                <span class="ov-panel-badge ov-panel-badge--accent">
                  {{ canViewCalendar ? 'Calendar data' : 'Restricted' }}
                </span>
              </div>

              <template v-if="canViewCalendar">
                <p class="ov-panel-item-desc">
                  {{ selectedAcademicYear?.name ?? 'No academic year selected' }}
                </p>
                <p class="ov-panel-item-desc" v-if="isLoadingHolidays">
                  Loading holiday information…
                </p>
                <p class="ov-panel-item-desc" v-else-if="holidaysError">
                  {{ holidaysError }}
                </p>
                <p class="ov-panel-item-desc" v-else>
                  {{ holidays.length }} active holidays in the active academic year.
                </p>
                <p class="ov-panel-item-desc">
                  Planning bottleneck alerts are not currently calculated.
                </p>
              </template>

              <p v-else class="ov-panel-item-desc">
                Calendar information is not available to your account.
              </p>
            </ManagementAttentionPanel>

            <!-- Observations and Inspections -->
            <ManagementAttentionPanel>
              <div class="ov-panel-header">
                <div class="ov-panel-title-wrap">
                  <span class="material-symbols-outlined ov-panel-icon ov-panel-icon--teal">
                    biotech
                  </span>
                  <h3 class="ov-panel-title">Observations &amp; STEM Inspections</h3>
                </div>
                <span class="ov-panel-badge ov-panel-badge--accent">
                  Live records
                </span>
              </div>

              <p v-if="isLoadingOperations" class="ov-panel-item-desc">
                Loading operational records…
              </p>

              <template v-else>
                <p class="ov-panel-item-desc" v-if="canViewObservations">
                  Classroom observations: {{ observationsError || observations.length }}
                  <span v-if="!observationsError && observations.length">
                    ({{Object.entries(observationStatuses)
                      .map(([status, count]) => `${status}: ${count}`)
                      .join(' · ')}})
                  </span>
                </p>

                <p class="ov-panel-item-desc" v-else>
                  Classroom observation access is restricted.
                </p>

                <p class="ov-panel-item-desc" v-if="canViewInspections">
                  STEM inspections: {{ inspectionsError || inspections.length }}
                  <span v-if="!inspectionsError && inspections.length">
                    ({{Object.entries(inspectionStatuses)
                      .map(([status, count]) => `${status}: ${count}`)
                      .join(' · ')}})
                  </span>
                </p>

                <p class="ov-panel-item-desc" v-else>
                  STEM inspection access is restricted.
                </p>
              </template>

              <p class="ov-panel-item-desc">
                Counts represent records visible to your account, not pending sign-offs.
                Dashboard date and school filters are not applied.
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
              <!-- Academic Calendar -->
              <button v-if="canManageCalendar" type="button" class="ov-shortcut-card ov-shortcut-card--button"
                @click="openCreateAcademicYear">
                <div class="ov-shortcut-top">
                  <div class="ov-shortcut-icon ov-shortcut-icon--accent">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      calendar_today
                    </span>
                  </div>
                  <div>
                    <h4 class="ov-shortcut-title">Academic Calendar</h4>
                    <p class="ov-shortcut-desc">
                      Manage academic-year configuration and date ranges
                    </p>
                  </div>
                </div>
                <div class="ov-shortcut-footer">
                  <span>Create academic year</span>
                  <span class="material-symbols-outlined ov-shortcut-arrow">
                    arrow_forward
                  </span>
                </div>
              </button>

              <div v-else class="ov-shortcut-card ov-shortcut-card--unavailable" aria-disabled="true">
                <div class="ov-shortcut-top">
                  <div class="ov-shortcut-icon ov-shortcut-icon--accent">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      calendar_today
                    </span>
                  </div>
                  <div>
                    <h4 class="ov-shortcut-title">Academic Calendar</h4>
                    <p class="ov-shortcut-desc">
                      Academic-year information is available in the overview.
                    </p>
                  </div>
                </div>
                <div class="ov-shortcut-footer">
                  <span>Calendar management restricted</span>
                </div>
              </div>

              <!-- Session Planning -->
              <div class="ov-shortcut-card ov-shortcut-card--unavailable" aria-disabled="true">
                <div class="ov-shortcut-top">
                  <div class="ov-shortcut-icon ov-shortcut-icon--neutral">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      schedule
                    </span>
                  </div>
                  <div>
                    <h4 class="ov-shortcut-title">Session Planning</h4>
                    <p class="ov-shortcut-desc">
                      Management-wide weekly planning workspace
                    </p>
                  </div>
                </div>
                <div class="ov-shortcut-footer">
                  <span>Workspace not available yet</span>
                </div>
              </div>

              <!-- Reports & Analytics -->
              <a href="#overview-reporting" class="ov-shortcut-card">
                <div class="ov-shortcut-top">
                  <div class="ov-shortcut-icon ov-shortcut-icon--accent">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      analytics
                    </span>
                  </div>
                  <div>
                    <h4 class="ov-shortcut-title">Reports &amp; Analytics</h4>
                    <p class="ov-shortcut-desc">
                      View live session delivery reporting and trajectory
                    </p>
                  </div>
                </div>
                <div class="ov-shortcut-footer">
                  <span>View overview reporting</span>
                  <span class="material-symbols-outlined ov-shortcut-arrow">
                    arrow_forward
                  </span>
                </div>
              </a>

              <!-- Schools & Classes -->
              <a href="#schools" class="ov-shortcut-card" @click.prevent="navigate('schools')">
                <div class="ov-shortcut-top">
                  <div class="ov-shortcut-icon ov-shortcut-icon--terra">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      domain
                    </span>
                  </div>
                  <div>
                    <h4 class="ov-shortcut-title">Schools &amp; Classes</h4>
                    <p class="ov-shortcut-desc">
                      Open the institutional school and class directory
                    </p>
                  </div>
                </div>
                <div class="ov-shortcut-footer">
                  <span>Open school directory</span>
                  <span class="material-symbols-outlined ov-shortcut-arrow">
                    arrow_forward
                  </span>
                </div>
              </a>
            </div>
          </section>

        </template>
      </main>
      <InstitutionalFooter :academic-year="selectedAcademicYear?.name ?? 'No academic year selected'" />
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
  --ov-button-primary-text: #FFFFFF;
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
  --ov-button-primary-text: #151E19;
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

.ov-reporting-anchor {
  min-width: 0;
  scroll-margin-top: 20px;
}

.ov-reporting-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
  min-width: 0;
}

.ov-reporting-grid>* {
  min-width: 0;
}

.ov-reporting-restricted {
  padding: 20px;
  border: 1px solid var(--ov-border);
  border-radius: 10px;
  background: var(--ov-bg-surface);
}

.ov-reporting-restricted h3 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 14px;
}

.ov-reporting-restricted p {
  margin: 6px 0 0;
  color: var(--ov-text-secondary);
  font-size: 12px;
}

@media (max-width: 767px) {
  .ov-reporting-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
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

.ov-shortcut-card--button {
  width: 100%;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.ov-shortcut-card--unavailable {
  cursor: default;
  opacity: 0.72;
}

.ov-shortcut-card--unavailable:hover {
  border-color: var(--ov-border);
}

.ov-shortcut-card--unavailable:hover .ov-shortcut-title {
  text-decoration: none;
}

.ov-shortcut-card--unavailable .ov-shortcut-arrow {
  display: none;
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

/* ─── Overview Filters ─────────────────────────────────────────────── */
.ov-filter-panel {
  width: 100%;
  padding: 18px 20px;
  border: 1px solid var(--ov-border);
  border-radius: 10px;
  background: var(--ov-bg-surface);
}

.ov-filter-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.ov-filter-heading h2 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 14px;
  font-weight: 700;
}

.ov-filter-heading p {
  margin: 4px 0 0;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.ov-filter-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.ov-filter-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  color: var(--ov-text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.ov-filter-field input,
.ov-filter-field select {
  width: 100%;
  min-width: 0;
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid var(--ov-border);
  border-radius: 7px;
  background: var(--ov-bg-page);
  color: var(--ov-text-primary);
  font: inherit;
  font-weight: 400;
}

.ov-filter-field input:focus,
.ov-filter-field select:focus {
  outline: 2px solid var(--ov-brand);
  outline-offset: 1px;
}

.ov-filter-field select:disabled,
.ov-filter-field input:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.ov-filter-clear {
  min-height: 34px;
  padding: 7px 12px;
  border: 1px solid var(--ov-border);
  border-radius: 7px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ov-filter-clear:hover {
  background: var(--ov-bg-surface-subtle);
}

.ov-filter-error {
  margin: 12px 0 0;
  color: #b42318;
  font-size: 12px;
}

.ov-filter-hint {
  margin: 12px 0 0;
  color: var(--ov-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 1100px) {
  .ov-filter-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .ov-filter-panel {
    padding: 15px;
  }

  .ov-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .ov-filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
