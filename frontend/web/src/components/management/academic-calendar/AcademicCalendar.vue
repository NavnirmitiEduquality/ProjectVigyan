<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { CurrentUser } from '../../../services/auth'
import {
    getCalendar,
    listHolidays,
    createHoliday,
    updateHoliday,
    deactivateHoliday,
    type AcademicHoliday,
} from '../../../services/academicCalendar'
import type {
    AcademicYear,
    CalendarDay,
    CalendarSession,
    CreateAcademicHolidayPayload,
    UpdateAcademicHolidayPayload,
} from '../../../services/academicCalendar'
import { listClassDivisions, type ClassDivision } from '../../../services/classDivisions'
import { listSchools, type School } from '../../../services/schools'
import type { DeliveryReportItem } from '../../../services/reporting'
type CalendarView = 'month' | 'week' | 'agenda'

const viewMode = ref<CalendarView>('month')
const props = defineProps<{
    currentUser: CurrentUser | null
    academicYear: AcademicYear | null
    paraTeachers: DeliveryReportItem[]
}>()

const canView = computed(
    () => props.currentUser?.permissions.includes('calendar.view') ?? false,
)

const canViewAll = computed(
    () => props.currentUser?.permissions.includes('session_plan.view_all') ?? false,
)
const router = useRouter()
const selectedTeacherId = ref('')
const visibleMonth = ref(new Date())
const calendarDays = ref<CalendarDay[]>([])
const selectedSession = ref<CalendarSession | null>(null)
const selectedDate = ref('')
const isLoading = ref(false)
const loadError = ref('')

const canViewClasses = computed(
    () => props.currentUser?.permissions.includes('class.view') ?? false,
)

const divisions = ref<ClassDivision[]>([])
const schools = ref<School[]>([])
const metadataError = ref('')

const selectedSchoolId = ref('')
const selectedDivisionId = ref('')
const selectedStatus = ref('')
const selectedDayType = ref('')

const availableDivisions = computed(() =>
    divisions.value
        .filter(item => item.status === 'ACTIVE' && item.data_origin === 'PRODUCTION')
        .filter(item => !selectedSchoolId.value || item.school_id === selectedSchoolId.value)
        .sort((a, b) =>
            a.class_level - b.class_level || a.division.localeCompare(b.division),
        ),
)

const availableSchools = computed(() => {
    const usedSchoolIds = new Set(
        divisions.value
            .filter(item => item.status === 'ACTIVE' && item.data_origin === 'PRODUCTION')
            .map(item => item.school_id),
    )

    return schools.value
        .filter(item =>
            item.status === 'ACTIVE'
            && item.data_origin === 'PRODUCTION'
            && usedSchoolIds.has(item.id),
        )
        .sort((a, b) => a.school_name.localeCompare(b.school_name))
})

const divisionById = computed(() =>
    new Map(divisions.value.map(item => [item.id, item])),
)

const monthLabel = computed(() =>
    visibleMonth.value.toLocaleDateString('en-IN', {
        month: 'long',
        year: 'numeric',
    }),
)

const viewLabel = computed(() => {
    if (viewMode.value === 'month') return monthLabel.value

    const start = viewRange.value.start
    const end = viewRange.value.end

    if (viewMode.value === 'week') {
        return `${parseDate(start).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
        })} – ${parseDate(end).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        })}`
    }

    return monthLabel.value
})

const viewRange = computed(() => {
    const anchor = visibleMonth.value
    let start: Date
    let end: Date

    if (viewMode.value === 'week') {
        const mondayOffset = (anchor.getDay() + 6) % 7
        start = new Date(
            anchor.getFullYear(),
            anchor.getMonth(),
            anchor.getDate() - mondayOffset,
        )
        end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6)
    } else {
        start = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
        end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
    }

    const academicStart = parseDate(props.academicYear?.start_date ?? dateKey(start))
    const academicEnd = parseDate(props.academicYear?.end_date ?? dateKey(end))

    if (start < academicStart) start = academicStart
    if (end > academicEnd) end = academicEnd

    return {
        start: dateKey(start),
        end: dateKey(end),
    }
})

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const canManageHolidays = computed(
    () => props.currentUser?.permissions.includes('calendar.manage') ?? false,
)

const holidayModalOpen = ref(false)
const holidayList = ref<AcademicHoliday[]>([])
const holidayLoading = ref(false)
const holidaySaving = ref(false)
const holidayError = ref('')
const holidaySuccess = ref('')
const editingHolidayId = ref<string | null>(null)

const holidayForm = ref({
    holiday_date: '',
    name: '',
    type: '',
    description: '',
})

function resetHolidayForm() {
    editingHolidayId.value = null
    holidayForm.value = {
        holiday_date: '',
        name: '',
        type: '',
        description: '',
    }
    holidayError.value = ''
    holidaySuccess.value = ''
}

function closeHolidayModal() {
    if (holidaySaving.value) return
    holidayModalOpen.value = false
    resetHolidayForm()
}

async function openHolidayModal() {
    holidayModalOpen.value = true
    resetHolidayForm()
    await loadHolidayList()
}

async function loadHolidayList() {
    holidayLoading.value = true
    holidayError.value = ''

    try {
        holidayList.value = await listHolidays()
    } catch (error) {
        holidayError.value = error instanceof Error
            ? error.message
            : 'Unable to load holidays.'
    } finally {
        holidayLoading.value = false
    }
}

function openSessionInPlanning(session: CalendarSession) {
    if (!selectedDate.value) return

    const date = new Date(`${selectedDate.value}T00:00:00`)
    const day = date.getDay()
    date.setDate(date.getDate() - ((day + 6) % 7))

    const weekStart = [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, '0'),
        String(date.getDate()).padStart(2, '0'),
    ].join('-')

    void router.push({
        name: 'session-planning',
        query: {
            item_id: session.session_plan_item_id,
            teacher_id: session.para_teacher_id,
            week_start: weekStart,
        },
    })
}

function editHoliday(holiday: AcademicHoliday) {
    editingHolidayId.value = holiday.id
    holidayForm.value = {
        holiday_date: holiday.holiday_date,
        name: holiday.name,
        type: holiday.type,
        description: holiday.description ?? '',
    }
    holidayError.value = ''
    holidaySuccess.value = ''
}

async function saveHoliday() {
    holidayError.value = ''
    holidaySuccess.value = ''

    const payload: CreateAcademicHolidayPayload = {
        holiday_date: holidayForm.value.holiday_date,
        name: holidayForm.value.name.trim(),
        type: holidayForm.value.type.trim(),
        description: holidayForm.value.description.trim() || null,
    }

    if (!payload.holiday_date || !payload.name || !payload.type) {
        holidayError.value = 'Date, holiday name and type are required.'
        return
    }

    if (
        props.academicYear
        && (
            payload.holiday_date < props.academicYear.start_date
            || payload.holiday_date > props.academicYear.end_date
        )
    ) {
        holidayError.value = 'The holiday date must fall within the active academic year.'
        return
    }

    holidaySaving.value = true

    try {
        if (editingHolidayId.value) {
            const updatePayload: UpdateAcademicHolidayPayload = payload
            await updateHoliday(editingHolidayId.value, updatePayload)
            holidaySuccess.value = 'Holiday updated successfully.'
        } else {
            await createHoliday(payload)
            holidaySuccess.value = 'Holiday added successfully.'
        }

        resetHolidayForm()
        await loadHolidayList()
        await loadCalendar()
    } catch (error) {
        holidayError.value = error instanceof Error
            ? error.message
            : 'Unable to save the holiday.'
    } finally {
        holidaySaving.value = false
    }
}

async function removeHoliday(holiday: AcademicHoliday) {
    const confirmed = window.confirm(
        `Deactivate "${holiday.name}" on ${holiday.holiday_date}?`,
    )

    if (!confirmed) return

    holidayError.value = ''
    holidaySuccess.value = ''

    try {
        await deactivateHoliday(holiday.id)
        holidaySuccess.value = 'Holiday deactivated successfully.'

        if (editingHolidayId.value === holiday.id) {
            resetHolidayForm()
        }

        await loadHolidayList()
        await loadCalendar()
    } catch (error) {
        holidayError.value = error instanceof Error
            ? error.message
            : 'Unable to deactivate the holiday.'
    }
}

function clearCalendarFilters() {
    selectedSchoolId.value = ''
    selectedDivisionId.value = ''
    selectedStatus.value = ''
    selectedDayType.value = ''
}

function dateKey(date: Date): string {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
}

function parseDate(value: string): Date {
    const [year, month, day] = value.split('-').map(Number)
    return new Date(year, month - 1, day)
}

function isSaturday(value: string): boolean {
    return parseDate(value).getDay() === 6
}

function isSunday(value: string): boolean {
    return parseDate(value).getDay() === 0
}

function shiftPeriod(amount: number) {
    if (viewMode.value === 'week') {
        visibleMonth.value = new Date(
            visibleMonth.value.getFullYear(),
            visibleMonth.value.getMonth(),
            visibleMonth.value.getDate() + amount * 7,
        )
    } else {
        visibleMonth.value = new Date(
            visibleMonth.value.getFullYear(),
            visibleMonth.value.getMonth() + amount,
            1,
        )
    }

    selectedSession.value = null
    selectedDate.value = ''
}

function goToToday() {
    const today = new Date()

    visibleMonth.value = today
    selectedDate.value = dateKey(today)
    selectedSession.value = null
}

const monthCells = computed(() => {
    const year = visibleMonth.value.getFullYear()
    const month = visibleMonth.value.getMonth()
    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)

    // Monday-first calendar grid.
    const leadingDays = (firstDay.getDay() + 6) % 7
    const totalCells = Math.ceil((leadingDays + lastDay.getDate()) / 7) * 7

    return Array.from({ length: totalCells }, (_, index) => {
        const date = new Date(year, month, index - leadingDays + 1)
        const weekday = date.getDay()

        return {
            date,
            key: dateKey(date),
            inMonth: date.getMonth() === month,
            isSaturday: weekday === 6,
            isSunday: weekday === 0,
            isWeekend: weekday === 0 || weekday === 6,
        }
    })
})

const calendarByDate = computed(() =>
    new Map(calendarDays.value.map((day) => [day.calendar_date, day])),
)

const visibleCalendarDays = computed(() =>
    calendarDays.value.filter(
        (day) =>
            day.calendar_date >= viewRange.value.start
            && day.calendar_date <= viewRange.value.end,
    ),
)

function dayType(day: CalendarDay): string {
    if (day.is_holiday) return 'HOLIDAY'
    if (isSaturday(day.calendar_date)) return 'PLANNING_DAY'
    if (isSunday(day.calendar_date)) return 'REST_DAY'
    return 'WORKING_DAY'
}

const filteredCalendarDays = computed(() =>
    visibleCalendarDays.value.map(day => ({
        ...day,
        sessions: day.sessions.filter(session => {
            if (
                selectedSchoolId.value
                && divisionById.value.get(session.class_division_id)?.school_id
                !== selectedSchoolId.value
            ) return false

            if (
                selectedDivisionId.value
                && session.class_division_id !== selectedDivisionId.value
            ) return false

            if (
                selectedStatus.value
                && session.derived_status !== selectedStatus.value
            ) return false

            if (
                selectedDayType.value
                && dayType(day) !== selectedDayType.value
            ) return false

            return true
        }),
    })),
)

const filteredCalendarByDate = computed(() =>
    new Map(filteredCalendarDays.value.map(day => [day.calendar_date, day])),
)

const agendaDays = computed(() => filteredCalendarDays.value)

const filteredSessions = computed(() =>
    filteredCalendarDays.value.flatMap(day => day.sessions),
)

const totalSessions = computed(() => filteredSessions.value.length)

const completedSessions = computed(() =>
    filteredSessions.value.filter(session => session.derived_status === 'COMPLETED').length,
)

const rescheduleRequired = computed(() =>
    filteredSessions.value.filter(session =>
        session.derived_status === 'RESCHEDULE_REQUIRED',
    ).length,
)

const plannedSessions = computed(() =>
    filteredSessions.value.filter(session => session.derived_status === 'PLANNED').length,
)

const holidayCount = computed(() =>
    visibleCalendarDays.value.filter(day => day.is_holiday).length,
)

const planningDayCount = computed(() =>
    visibleCalendarDays.value.filter(day =>
        isSaturday(day.calendar_date),
    ).length,
)

const selectedDay = computed(() =>
    selectedDate.value
        ? filteredCalendarByDate.value.get(selectedDate.value) ?? null
        : null,
)

function formatTime(value: string | null): string {
    if (!value) return 'Time not set'
    return value.slice(0, 5)
}

function sessionStatusLabel(session: CalendarSession): string {
    if (session.derived_status === 'COMPLETED') return 'Completed'
    if (session.derived_status === 'RESCHEDULE_REQUIRED') return 'Reschedule required'
    return 'Planned'
}

function selectDay(key: string) {
    selectedDate.value = key
    selectedSession.value = null
}

function selectSession(session: CalendarSession) {
    selectedDate.value = calendarDays.value.find(
        (day) => day.sessions.some(
            (item) => item.session_plan_item_id === session.session_plan_item_id,
        ),
    )?.calendar_date ?? ''
    selectedSession.value = session
}

async function loadFilterMetadata() {
    if (!canViewClasses.value) return

    metadataError.value = ''

    const results = await Promise.allSettled([
        listClassDivisions(),
        listSchools(),
    ])

    if (results[0].status === 'fulfilled') {
        divisions.value = results[0].value
    } else {
        metadataError.value = 'Class/division filters are unavailable.'
    }

    if (results[1].status === 'fulfilled') {
        schools.value = results[1].value
    } else {
        metadataError.value = 'School filters are unavailable.'
    }
}

async function loadCalendar() {
    if (!props.academicYear || !canView.value) {
        calendarDays.value = []
        return
    }

    const { start, end } = viewRange.value

    if (start > end) {
        calendarDays.value = []
        loadError.value = ''
        selectedDate.value = ''
        selectedSession.value = null
        return
    }

    isLoading.value = true
    loadError.value = ''

    try {
        calendarDays.value = await getCalendar({
            startDate: start,
            endDate: end,
            ...(canViewAll.value && selectedTeacherId.value
                ? { paraTeacherId: selectedTeacherId.value }
                : {}),
        })
    } catch (error) {
        calendarDays.value = []
        loadError.value = error instanceof Error
            ? error.message
            : 'Unable to load the academic calendar.'
    } finally {
        isLoading.value = false
    }
}

watch(
    [
        viewRange,
        selectedTeacherId,
        () => props.academicYear?.id,
        canView,
    ],
    () => {
        void loadCalendar()
    },
)

onMounted(() => {
    void loadCalendar()
    void loadFilterMetadata()
})
</script>

<template>
    <section class="academic-calendar">
        <header class="calendar-heading">
            <div>
                <p class="calendar-eyebrow">PROJECT VIGYAN · ACADEMIC OPERATIONS</p>
                <h2>Academic Calendar</h2>
                <p class="calendar-subtitle">
                    View planned sessions, completed delivery and holidays.
                </p>
            </div>

            <div class="calendar-controls">
                <button v-if="canManageHolidays" type="button" class="calendar-manage-holidays-button"
                    @click="openHolidayModal">
                    Manage Holidays
                </button>
                <div class="calendar-view-controls">
                    <div class="calendar-view-switch" role="group" aria-label="Calendar view">
                        <button v-for="view in [
                            { value: 'month', label: 'Month' },
                            { value: 'week', label: 'Week' },
                            { value: 'agenda', label: 'Agenda' },
                        ]" :key="view.value" type="button"
                            :class="{ 'calendar-view-button--active': viewMode === view.value }"
                            @click="viewMode = view.value as CalendarView">
                            {{ view.label }}
                        </button>
                    </div>

                    <div class="calendar-month-navigation">
                        <button type="button" aria-label="Previous period" @click="shiftPeriod(-1)">
                            ‹
                        </button>
                        <strong>{{ viewLabel }}</strong>
                        <button type="button" aria-label="Next period" @click="shiftPeriod(1)">
                            ›
                        </button>
                    </div>

                    <button type="button" class="calendar-today-button" @click="goToToday">
                        Today
                    </button>
                </div>
            </div>
        </header>

        <div v-if="canView" class="calendar-filters">
            <label v-if="canViewAll" class="calendar-filter">
                <span>Para Teacher</span>
                <select v-model="selectedTeacherId">
                    <option value="">My calendar</option>
                    <option v-for="teacher in paraTeachers" :key="teacher.para_teacher_id"
                        :value="teacher.para_teacher_id">
                        {{ teacher.para_teacher_name || teacher.para_teacher_code }}
                    </option>
                </select>
            </label>

            <template v-if="canViewClasses">
                <label class="calendar-filter">
                    <span>School</span>
                    <select v-model="selectedSchoolId" @change="selectedDivisionId = ''">
                        <option value="">All schools</option>
                        <option v-for="school in availableSchools" :key="school.id" :value="school.id">
                            {{ school.school_name }}
                        </option>
                    </select>
                </label>

                <label class="calendar-filter">
                    <span>Class / Division</span>
                    <select v-model="selectedDivisionId">
                        <option value="">All classes</option>
                        <option v-for="division in availableDivisions" :key="division.id" :value="division.id">
                            Class {{ division.class_level }} · {{ division.division }}
                        </option>
                    </select>
                </label>
            </template>

            <label class="calendar-filter">
                <span>Session status</span>
                <select v-model="selectedStatus">
                    <option value="">All statuses</option>
                    <option value="PLANNED">Planned</option>
                    <option value="COMPLETED">Completed</option>
                    <option value="RESCHEDULE_REQUIRED">Reschedule required</option>
                </select>
            </label>

            <label class="calendar-filter">
                <span>Day type</span>
                <select v-model="selectedDayType">
                    <option value="">All days</option>
                    <option value="WORKING_DAY">Working day</option>
                    <option value="PLANNING_DAY">Saturday · Planning day</option>
                    <option value="REST_DAY">Sunday · Weekly rest</option>
                    <option value="HOLIDAY">Holiday</option>
                </select>
            </label>

            <button v-if="selectedSchoolId || selectedDivisionId || selectedStatus || selectedDayType" type="button"
                class="calendar-clear-filters" @click="clearCalendarFilters">
                Clear filters
            </button>
        </div>

        <p v-if="metadataError" class="calendar-message">
            {{ metadataError }}
        </p>

        <p v-if="!canView" class="calendar-message" role="alert">
            Your account does not have permission to view the academic calendar.
        </p>

        <p v-else-if="!academicYear" class="calendar-message">
            No active academic year is configured.
        </p>

        <p v-else-if="loadError" class="calendar-error" role="alert">
            {{ loadError }}
        </p>

        <template v-else>
            <div class="calendar-summary">
                <article class="calendar-stat">
                    <span>Total sessions</span>
                    <strong>{{ totalSessions }}</strong>
                </article>
                <article class="calendar-stat calendar-stat--planned">
                    <span>Planned</span>
                    <strong>{{ plannedSessions }}</strong>
                </article>
                <article class="calendar-stat calendar-stat--completed">
                    <span>Completed</span>
                    <strong>{{ completedSessions }}</strong>
                </article>
                <article class="calendar-stat calendar-stat--attention">
                    <span>Reschedule required</span>
                    <strong>{{ rescheduleRequired }}</strong>
                </article>
                <article class="calendar-stat">
                    <span>Holidays</span>
                    <strong>{{ holidayCount }}</strong>
                </article>
                <article class="calendar-stat">
                    <span>Planning days</span>
                    <strong>{{ planningDayCount }}</strong>
                </article>
            </div>

            <div v-if="isLoading" class="calendar-message">
                Loading calendar…
            </div>

            <div v-else class="calendar-layout">
                <div class="calendar-grid-panel">
                    <!-- MONTH VIEW: retain the existing month grid and legend here -->
                    <template v-if="viewMode === 'month'">
                        <div class="calendar-weekdays">
                            <div v-for="weekday in weekdays" :key="weekday">
                                {{ weekday }}
                            </div>
                        </div>

                        <div class="calendar-grid">
                            <button v-for="cell in monthCells" :key="cell.key" type="button" class="calendar-day"
                                :class="{
                                    'calendar-day--outside': !cell.inMonth,
                                    'calendar-day--weekend': cell.isWeekend,
                                    'calendar-day--saturday': cell.isSaturday,
                                    'calendar-day--sunday': cell.isSunday,
                                    'calendar-day--holiday': calendarByDate.get(cell.key)?.is_holiday,
                                    'calendar-day--selected': selectedDate === cell.key,
                                }" @click="selectDay(cell.key)">
                                <span class="calendar-day-number">
                                    {{ cell.date.getDate() }}
                                </span>
                                <span v-if="cell.isSaturday" class="calendar-day-marker calendar-day-marker--planning">
                                    Planning day
                                </span>
                                <span v-else-if="cell.isSunday" class="calendar-day-marker calendar-day-marker--sunday">
                                    Weekly rest
                                </span>
                                <template v-for="day in [filteredCalendarByDate.get(cell.key)]"
                                    :key="`${cell.key}-content`">
                                    <template v-if="day">
                                        <span v-if="day.is_holiday" class="calendar-holiday">
                                            {{ day.holiday_name }}
                                        </span>

                                        <span v-for="session in day.sessions.slice(0, 3)"
                                            :key="session.session_plan_item_id" class="calendar-session"
                                            :class="`calendar-session--${session.derived_status.toLowerCase()}`"
                                            @click.stop="selectSession(session)">
                                            {{ formatTime(session.planned_start_time) }}
                                            · {{ sessionStatusLabel(session) }}
                                        </span>

                                        <span v-if="day.sessions.length > 3" class="calendar-more">
                                            +{{ day.sessions.length - 3 }} more
                                        </span>
                                    </template>
                                </template>
                            </button>
                        </div>

                        <div class="calendar-legend">
                            <span><i class="legend-dot legend-dot--planned" /> Planned</span>
                            <span><i class="legend-dot legend-dot--completed" /> Completed</span>
                            <span><i class="legend-dot legend-dot--attention" /> Reschedule required</span>
                            <span><i class="legend-dot legend-dot--holiday" /> Holiday</span>
                        </div>
                    </template>

                    <!-- WEEK VIEW -->
                    <template v-else-if="viewMode === 'week'">
                        <div class="calendar-week-view">
                            <article v-for="day in filteredCalendarDays" :key="day.calendar_date"
                                class="calendar-agenda-day" :class="{
                                    'calendar-agenda-day--selected': selectedDate === day.calendar_date,
                                    'calendar-agenda-day--saturday': isSaturday(day.calendar_date),
                                    'calendar-agenda-day--sunday': isSunday(day.calendar_date),
                                    'calendar-agenda-day--holiday': day.is_holiday,
                                }">
                                <button type="button" class="calendar-agenda-date"
                                    @click="selectDay(day.calendar_date)">
                                    <strong>{{ parseDate(day.calendar_date).toLocaleDateString('en-IN', {
                                        weekday: 'short',
                                        day: 'numeric',
                                        month: 'short',
                                    }) }}</strong>
                                    <span v-if="day.is_holiday" class="calendar-holiday">
                                        {{ day.holiday_name }}
                                    </span>
                                    <span v-if="isSaturday(day.calendar_date)"
                                        class="calendar-day-marker calendar-day-marker--planning">
                                        Saturday · Planning day
                                    </span>
                                    <span v-else-if="isSunday(day.calendar_date)"
                                        class="calendar-day-marker calendar-day-marker--sunday">
                                        Sunday · Weekly rest
                                    </span>
                                </button>

                                <div class="calendar-agenda-sessions">
                                    <button v-for="session in day.sessions" :key="session.session_plan_item_id"
                                        type="button" class="calendar-inspector-session"
                                        @click="selectSession(session)">
                                        <strong>{{ formatTime(session.planned_start_time) }}</strong>
                                        <span>{{ sessionStatusLabel(session) }}</span>
                                    </button>

                                    <p v-if="day.sessions.length === 0" class="calendar-empty">
                                        {{ day.is_holiday
                                            ? 'Holiday · No sessions scheduled'
                                            : isSaturday(day.calendar_date)
                                                ? 'Weekly planning day · No sessions scheduled'
                                                : isSunday(day.calendar_date)
                                                    ? 'Weekly rest day'
                                                    : 'No sessions scheduled for this working day'
                                        }}
                                    </p>
                                </div>
                            </article>
                        </div>
                    </template>

                    <!-- AGENDA VIEW -->
                    <template v-else>
                        <div v-if="agendaDays.length === 0" class="calendar-empty">
                            No calendar dates in this period.
                        </div>

                        <div v-else class="calendar-agenda-view">
                            <article v-for="day in agendaDays" :key="day.calendar_date" class="calendar-agenda-day"
                                :class="{
                                    'calendar-agenda-day--selected': selectedDate === day.calendar_date,
                                    'calendar-agenda-day--saturday': isSaturday(day.calendar_date),
                                    'calendar-agenda-day--sunday': isSunday(day.calendar_date),
                                    'calendar-agenda-day--holiday': day.is_holiday,
                                }">
                                <button type="button" class="calendar-agenda-date"
                                    @click="selectDay(day.calendar_date)">
                                    <strong>{{ parseDate(day.calendar_date).toLocaleDateString('en-IN', {
                                        weekday: 'long',
                                        day: 'numeric',
                                        month: 'long',
                                    }) }}</strong>
                                </button>
                                <span v-if="isSaturday(day.calendar_date)"
                                    class="calendar-day-marker calendar-day-marker--planning">
                                    Saturday · Planning day
                                </span>
                                <span v-else-if="isSunday(day.calendar_date)"
                                    class="calendar-day-marker calendar-day-marker--sunday">
                                    Sunday · Weekly rest
                                </span>

                                <p v-if="day.is_holiday" class="calendar-holiday">
                                    {{ day.holiday_name }}
                                </p>

                                <button v-for="session in day.sessions" :key="session.session_plan_item_id"
                                    type="button" class="calendar-inspector-session" @click="selectSession(session)">
                                    <strong>{{ formatTime(session.planned_start_time) }}</strong>
                                    <span>{{ sessionStatusLabel(session) }}</span>
                                </button>
                            </article>
                        </div>
                    </template>
                </div>

                <aside class="calendar-inspector">
                    <template v-if="selectedSession">
                        <p class="calendar-eyebrow">SESSION DETAILS</p>
                        <h3>{{ sessionStatusLabel(selectedSession) }}</h3>
                        <dl>
                            <dt>Date</dt>
                            <dd>{{ selectedDate }}</dd>
                            <dt>Time</dt>
                            <dd>
                                {{ formatTime(selectedSession.planned_start_time) }}
                                –
                                {{ formatTime(selectedSession.planned_end_time) }}
                            </dd>
                            <dt>Sequence</dt>
                            <dd>{{ selectedSession.sequence_no }}</dd>
                            <dt>Status</dt>
                            <dd>{{ selectedSession.teaching_session_status || 'Not started' }}</dd>
                        </dl>
                        <p class="calendar-inspector-note">
                            Session details are read-only in this calendar view.
                        </p>
                        <button v-if="props.currentUser?.permissions.includes('session_plan.view')" type="button"
                            class="calendar-session-open-button" @click="openSessionInPlanning(selectedSession)">
                            <span>View in Session Planning</span>
                            <span class="calendar-session-open-icon" aria-hidden="true">→</span>
                        </button>
                    </template>

                    <template v-else-if="selectedDay">
                        <p class="calendar-eyebrow">SELECTED DATE</p>
                        <h3>{{ selectedDate }}</h3>
                        <div v-if="selectedDay.is_holiday" class="calendar-day-explanation">
                            <p class="calendar-holiday-detail">
                                {{ selectedDay.holiday_name }}
                            </p>
                            <p class="calendar-empty">
                                This is a project-wide holiday. No regular session delivery is expected.
                            </p>
                        </div>

                        <div v-else-if="isSaturday(selectedDay.calendar_date)" class="calendar-day-explanation">
                            <strong>Weekly planning day</strong>
                            <p class="calendar-empty">
                                Use Saturday to plan at least six sessions for the upcoming week.
                                Planning remains editable on Monday.
                            </p>
                        </div>

                        <div v-else-if="isSunday(selectedDay.calendar_date)" class="calendar-day-explanation">
                            <strong>Weekly rest day</strong>
                            <p class="calendar-empty">
                                Sunday is a non-working day in the academic calendar.
                            </p>
                        </div>

                        <p v-else-if="selectedDay.sessions.length === 0" class="calendar-empty">
                            No sessions scheduled for this working day.
                        </p>
                        <button v-for="session in selectedDay.sessions" :key="session.session_plan_item_id"
                            type="button" class="calendar-inspector-session" @click="selectSession(session)">
                            <strong>{{ formatTime(session.planned_start_time) }}</strong>
                            <span>{{ sessionStatusLabel(session) }}</span>
                        </button>
                    </template>

                    <template v-else>
                        <p class="calendar-eyebrow">SESSION DETAILS</p>
                        <h3>Select a date</h3>
                        <p class="calendar-empty">
                            Choose a date or session in the calendar to see its details.
                        </p>
                    </template>
                </aside>
            </div>
        </template>
        <div v-if="holidayModalOpen" class="holiday-modal-backdrop" @click.self="closeHolidayModal">
            <section class="holiday-modal" role="dialog" aria-modal="true" aria-labelledby="holiday-modal-title">
                <header class="holiday-modal-header">
                    <div>
                        <p class="calendar-eyebrow">ACADEMIC YEAR {{ academicYear?.name }}</p>
                        <h3 id="holiday-modal-title">Manage Holidays</h3>
                    </div>

                    <button type="button" class="holiday-modal-close" aria-label="Close" :disabled="holidaySaving"
                        @click="closeHolidayModal">
                        ×
                    </button>
                </header>

                <div class="holiday-modal-body">
                    <div class="holiday-list-section">
                        <div class="holiday-section-heading">
                            <h4>Active holidays</h4>
                            <button type="button" class="calendar-manage-holidays-button" @click="resetHolidayForm">
                                + Add Holiday
                            </button>
                        </div>

                        <p v-if="holidayLoading" class="calendar-empty">
                            Loading holidays…
                        </p>

                        <p v-else-if="holidayList.length === 0" class="calendar-empty">
                            No active holidays configured for this academic year.
                        </p>

                        <article v-for="holiday in holidayList" :key="holiday.id" class="holiday-list-item">
                            <div class="holiday-list-details">
                                <strong>{{ holiday.name }}</strong>
                                <span>{{ holiday.holiday_date }} · {{ holiday.type }}</span>
                                <small v-if="holiday.description">
                                    {{ holiday.description }}
                                </small>
                            </div>

                            <div class="holiday-item-actions">
                                <button type="button" @click="editHoliday(holiday)">
                                    Edit
                                </button>
                                <button type="button" class="holiday-deactivate-button" @click="removeHoliday(holiday)">
                                    Deactivate
                                </button>
                            </div>
                        </article>
                    </div>

                    <div class="holiday-form-section">
                        <h4>
                            {{ editingHolidayId ? 'Edit Holiday' : 'Add New Holiday' }}
                        </h4>

                        <form @submit.prevent="saveHoliday">
                            <label class="holiday-form-field">
                                <span>Holiday date *</span>
                                <input v-model="holidayForm.holiday_date" type="date" :min="academicYear?.start_date"
                                    :max="academicYear?.end_date" required />
                            </label>

                            <label class="holiday-form-field">
                                <span>Holiday name *</span>
                                <input v-model="holidayForm.name" type="text" maxlength="150"
                                    placeholder="e.g. Republic Day" required />
                            </label>

                            <label class="holiday-form-field">
                                <span>Holiday type *</span>
                                <input v-model="holidayForm.type" type="text" maxlength="50" placeholder="e.g. NATIONAL"
                                    required />
                            </label>

                            <label class="holiday-form-field">
                                <span>Description</span>
                                <textarea v-model="holidayForm.description" rows="3" placeholder="Optional details" />
                            </label>

                            <p v-if="holidayError" class="calendar-error" role="alert">
                                {{ holidayError }}
                            </p>

                            <p v-if="holidaySuccess" class="holiday-success" role="status">
                                {{ holidaySuccess }}
                            </p>

                            <div class="holiday-form-actions">
                                <button v-if="editingHolidayId" type="button" :disabled="holidaySaving"
                                    @click="resetHolidayForm">
                                    Cancel edit
                                </button>

                                <button type="submit" class="calendar-manage-holidays-button" :disabled="holidaySaving">
                                    {{ holidaySaving
                                        ? 'Saving…'
                                        : editingHolidayId
                                            ? 'Save Changes'
                                            : 'Add Holiday'
                                    }}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </section>
        </div>
    </section>
</template>

<style scoped>
.calendar-view-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.calendar-view-switch {
    display: flex;
    gap: 3px;
    padding: 3px;
    border: 1px solid var(--ov-border);
    border-radius: 9px;
    background: var(--ov-bg-surface);
}

.calendar-view-switch button {
    padding: 7px 11px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--ov-text-muted);
    cursor: pointer;
}

.calendar-view-switch .calendar-view-button--active {
    background: var(--ov-brand);
    color: white;
}

.calendar-week-view,
.calendar-agenda-view {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.calendar-agenda-day {
    display: grid;
    grid-template-columns: minmax(130px, 190px) minmax(0, 1fr);
    gap: 14px;
    padding: 12px;
    border-bottom: 1px solid var(--ov-border);
}

.calendar-agenda-day--selected {
    background: color-mix(in srgb, var(--ov-brand) 7%, transparent);
    border-radius: 8px;
}

.calendar-agenda-date {
    align-self: start;
    padding: 4px;
    border: 0;
    background: transparent;
    color: var(--ov-text-primary);
    text-align: left;
    cursor: pointer;
}

.calendar-agenda-sessions {
    min-width: 0;
}

@media (max-width: 700px) {
    .calendar-agenda-day {
        grid-template-columns: 1fr;
        gap: 6px;
    }

    .calendar-view-controls {
        width: 100%;
    }
}

.academic-calendar {
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 24px;
    color: var(--ov-text-primary);
}

.calendar-heading,
.calendar-controls,
.calendar-month-navigation,
.calendar-legend {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.calendar-heading {
    flex-wrap: wrap;
}

.calendar-eyebrow {
    margin: 0 0 6px;
    color: var(--ov-text-muted);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
}

.calendar-heading h2 {
    margin: 0;
    font-size: 1.65rem;
}

.calendar-subtitle {
    margin: 6px 0 0;
    color: var(--ov-text-muted);
}

.calendar-controls {
    flex-wrap: wrap;
}

.calendar-teacher-filter {
    display: grid;
    gap: 5px;
    color: var(--ov-text-muted);
    font-size: 0.78rem;
}

.calendar-teacher-filter select,
.calendar-month-navigation button,
.calendar-today-button {
    min-height: 38px;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    background: var(--ov-bg-surface);
    color: var(--ov-text-primary);
    padding: 7px 12px;
}

.calendar-month-navigation {
    border: 1px solid var(--ov-border);
    border-radius: 9px;
    padding: 3px 7px;
}

.calendar-month-navigation button {
    min-width: 32px;
    border: 0;
    font-size: 1.3rem;
    padding: 2px 7px;
}

.calendar-today-button {
    font-weight: 650;
}

.calendar-summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
}

.calendar-stat {
    display: grid;
    gap: 8px;
    padding: 16px;
    border: 1px solid var(--ov-border);
    border-radius: 12px;
    background: var(--ov-bg-surface);
}

.calendar-stat span {
    color: var(--ov-text-muted);
    font-size: 0.8rem;
}

.calendar-stat strong {
    font-size: 1.6rem;
}

.calendar-stat--planned strong {
    color: #3479bd;
}

.calendar-stat--completed strong {
    color: #26835c;
}

.calendar-stat--attention strong {
    color: #bd7a27;
}

.calendar-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 270px;
    gap: 16px;
    align-items: start;
}

.calendar-grid-panel,
.calendar-inspector {
    min-width: 0;
    border: 1px solid var(--ov-border);
    border-radius: 12px;
    background: var(--ov-bg-surface);
}

.calendar-grid-panel {
    padding: 12px;
}

.calendar-weekdays,
.calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
}

.calendar-weekdays>div {
    padding: 10px 4px;
    color: var(--ov-text-muted);
    text-align: center;
    font-size: 0.75rem;
    font-weight: 700;
}

.calendar-day {
    display: flex;
    min-width: 0;
    min-height: 112px;
    flex-direction: column;
    align-items: stretch;
    gap: 5px;
    overflow: hidden;
    padding: 8px;
    border: 1px solid var(--ov-border);
    background: transparent;
    color: var(--ov-text-primary);
    text-align: left;
    cursor: pointer;
}

.calendar-day--outside {
    opacity: 0.42;
}

.calendar-day--weekend {
    background: color-mix(in srgb, var(--ov-bg-surface) 80%, var(--ov-text-muted) 8%);
}

.calendar-day--selected {
    outline: 2px solid var(--ov-brand);
    outline-offset: -2px;
}

.calendar-day-number {
    font-size: 0.8rem;
    font-weight: 700;
}

.calendar-session,
.calendar-holiday {
    display: block;
    overflow: hidden;
    border-radius: 5px;
    padding: 4px 5px;
    font-size: 0.67rem;
    line-height: 1.3;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.calendar-session--planned {
    background: #e5effb;
    color: #245c91;
}

.calendar-session--completed {
    background: #e1f2e9;
    color: #216b49;
}

.calendar-session--reschedule_required {
    background: #fff0d9;
    color: #895616;
}

.calendar-holiday {
    background: #f7edcf;
    color: #765b17;
}

.calendar-more {
    color: var(--ov-text-muted);
    font-size: 0.68rem;
}

.calendar-legend {
    justify-content: flex-start;
    flex-wrap: wrap;
    padding: 14px 4px 2px;
    color: var(--ov-text-muted);
    font-size: 0.72rem;
}

.calendar-session-open-button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    min-height: 44px;
    margin-top: 18px;
    padding: 11px 16px;

    border: 1px solid var(--ov-brand);
    border-radius: 9px;

    background: var(--ov-brand);
    color: #ffffff;

    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 650;
    letter-spacing: 0.01em;

    cursor: pointer;
    transition:
        background 180ms ease,
        border-color 180ms ease,
        box-shadow 180ms ease,
        transform 180ms ease;
}

.calendar-session-open-button:hover {
    background: var(--ov-brand-hover, var(--ov-brand));
    border-color: var(--ov-brand-hover, var(--ov-brand));
    box-shadow: 0 4px 12px rgb(0 0 0 / 13%);
    transform: translateY(-1px);
}

.calendar-session-open-button:active {
    transform: translateY(0);
    box-shadow: none;
}

.calendar-session-open-button:focus-visible {
    outline: 3px solid var(--ov-brand);
    outline-offset: 3px;
}

.calendar-session-open-icon {
    font-size: 1.15rem;
    line-height: 1;
    transition: transform 180ms ease;
}

.calendar-session-open-button:hover .calendar-session-open-icon {
    transform: translateX(3px);
}

.calendar-legend span {
    display: flex;
    align-items: center;
    gap: 5px;
}

.legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.legend-dot--planned {
    background: #3479bd;
}

.legend-dot--completed {
    background: #26835c;
}

.legend-dot--attention {
    background: #bd7a27;
}

.legend-dot--holiday {
    background: #c6a342;
}

.calendar-inspector {
    padding: 18px;
}

.calendar-inspector h3 {
    margin: 0 0 16px;
    font-size: 1.05rem;
}

.calendar-inspector dl {
    display: grid;
    grid-template-columns: 90px minmax(0, 1fr);
    gap: 10px;
    font-size: 0.8rem;
}

.calendar-inspector dt {
    color: var(--ov-text-muted);
}

.calendar-inspector dd {
    margin: 0;
    overflow-wrap: anywhere;
}

.calendar-inspector-note,
.calendar-empty,
.calendar-message {
    color: var(--ov-text-muted);
    font-size: 0.85rem;
    line-height: 1.5;
}

.calendar-inspector-session {
    display: flex;
    width: 100%;
    justify-content: space-between;
    gap: 8px;
    margin: 7px 0;
    padding: 10px;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    background: transparent;
    color: var(--ov-text-primary);
    text-align: left;
    cursor: pointer;
}

.calendar-error {
    color: #b33c32;
}

.calendar-filters {
    display: flex;
    align-items: end;
    flex-wrap: wrap;
    gap: 12px;
    margin: 16px 0;
}

.calendar-filter {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 155px;
    color: var(--ov-text-muted);
    font-size: 0.8rem;
}

.calendar-filter select {
    min-height: 38px;
    padding: 7px 10px;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    background: var(--ov-bg-surface);
    color: var(--ov-text-primary);
    font: inherit;
}

.calendar-clear-filters {
    min-height: 38px;
    padding: 7px 12px;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    background: transparent;
    color: var(--ov-brand);
    cursor: pointer;
}

.calendar-summary {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
}

.calendar-day-explanation {
    margin: 10px 0;
}

.calendar-day-explanation>strong {
    color: var(--ov-text-primary);
}

.calendar-day-explanation .calendar-empty {
    margin-top: 5px;
}

@media (max-width: 1050px) {
    .calendar-layout {
        grid-template-columns: 1fr;
    }

    .calendar-inspector {
        min-height: 150px;
    }
}

@media (max-width: 700px) {
    .academic-calendar {
        padding: 14px;
    }

    .calendar-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .calendar-day {
        min-height: 82px;
        padding: 4px;
    }

    .calendar-session,
    .calendar-holiday {
        font-size: 0.58rem;
    }

    .calendar-controls {
        width: 100%;
        justify-content: flex-start;
    }

    .calendar-session-open-button {
        min-height: 46px;
        margin-top: 14px;
    }
}

.calendar-manage-holidays-button {
    border: 1px solid var(--ov-brand);
    border-radius: 8px;
    padding: 9px 14px;
    background: var(--ov-brand);
    color: white;
    cursor: pointer;
    font: inherit;
    font-weight: 600;
}

.calendar-manage-holidays-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.holiday-modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: rgb(0 0 0 / 45%);
}

.holiday-modal {
    width: min(760px, 100%);
    max-height: 90vh;
    overflow-y: auto;
    padding: 24px;
    border: 1px solid var(--ov-border);
    border-radius: 14px;
    background: var(--ov-bg-surface);
    color: var(--ov-text-primary);
    box-shadow: 0 20px 60px rgb(0 0 0 / 20%);
}

.holiday-modal-header,
.holiday-section-heading,
.holiday-list-item,
.holiday-item-actions,
.holiday-form-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.holiday-modal-header {
    margin-bottom: 20px;
}

.holiday-modal-header h3 {
    margin: 4px 0 0;
}

.holiday-modal-close {
    border: 0;
    background: transparent;
    color: var(--ov-text-primary);
    font-size: 26px;
    cursor: pointer;
}

.holiday-modal-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}

.holiday-list-section,
.holiday-form-section {
    min-width: 0;
}

.holiday-list-section h4,
.holiday-form-section h4 {
    margin: 0 0 14px;
}

.holiday-list-item {
    align-items: flex-start;
    padding: 12px 0;
    border-bottom: 1px solid var(--ov-border);
}

.holiday-list-details {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
}

.holiday-list-details span,
.holiday-list-details small {
    color: var(--ov-text-muted);
    font-size: 0.8rem;
}

.holiday-item-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
}

.holiday-item-actions button,
.holiday-form-actions button {
    border: 1px solid var(--ov-border);
    border-radius: 7px;
    padding: 7px 10px;
    background: transparent;
    color: var(--ov-text-primary);
    cursor: pointer;
}

.holiday-item-actions .holiday-deactivate-button {
    color: #b45309;
}

.holiday-form-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
    color: var(--ov-text-muted);
    font-size: 0.85rem;
}

.holiday-form-field input,
.holiday-form-field textarea {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid var(--ov-border);
    border-radius: 8px;
    padding: 10px;
    background: var(--ov-bg-surface);
    color: var(--ov-text-primary);
    font: inherit;
}

.holiday-form-actions {
    justify-content: flex-end;
    margin-top: 16px;
}

.holiday-success {
    color: #15803d;
    font-size: 0.85rem;
}

@media (max-width: 650px) {
    .holiday-modal-body {
        grid-template-columns: 1fr;
    }

    .holiday-modal {
        padding: 16px;
    }

    .holiday-list-item {
        flex-direction: column;
    }

    .holiday-item-actions {
        justify-content: flex-start;
    }
}

/* Saturday, Sunday and holiday distinctions */

.calendar-day--saturday,
.calendar-agenda-day--saturday {
    background: color-mix(in srgb, #dceee4 55%, var(--ov-bg-surface));
}

.calendar-day--sunday,
.calendar-agenda-day--sunday {
    background: color-mix(in srgb, #e9ebef 65%, var(--ov-bg-surface));
}

.calendar-day--holiday,
.calendar-agenda-day--holiday {
    border-color: #dfc47d;
}

.calendar-day--holiday {
    background: #fff8e8;
}

.calendar-day-marker {
    display: inline-block;
    align-self: flex-start;
    width: fit-content;
    max-width: 100%;
    padding: 3px 5px;
    border-radius: 4px;
    font-size: 0.62rem;
    font-weight: 650;
    line-height: 1.3;
}

.calendar-day-marker--planning {
    background: #dceee4;
    color: #185a3a;
}

.calendar-day-marker--sunday {
    background: #e9ebef;
    color: #596273;
}

.calendar-agenda-day--holiday {
    background: #fff8e8;
}

.calendar-holiday {
    background: #f7edcf;
    color: #765b17;
}

/* Responsive calendar layout */

@media (max-width: 900px) {
    .academic-calendar {
        padding: 16px;
    }

    .calendar-layout {
        grid-template-columns: minmax(0, 1fr);
    }

    .calendar-inspector {
        width: 100%;
    }

    .calendar-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .calendar-controls {
        width: 100%;
        align-items: stretch;
    }

    .calendar-view-controls {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
    }
}

@media (max-width: 600px) {
    .academic-calendar {
        padding: 12px;
        gap: 14px;
    }

    .calendar-heading {
        align-items: flex-start;
        flex-direction: column;
    }

    .calendar-heading h2 {
        font-size: 1.35rem;
    }

    .calendar-controls {
        flex-direction: column;
        align-items: stretch;
    }

    .calendar-teacher-filter,
    .calendar-teacher-filter select {
        width: 100%;
    }

    .calendar-view-controls {
        display: grid;
        grid-template-columns: 1fr;
        width: 100%;
    }

    .calendar-view-switch {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        width: 100%;
    }

    .calendar-view-switch button {
        padding: 9px 5px;
    }

    .calendar-month-navigation {
        justify-content: space-between;
        width: 100%;
    }

    .calendar-month-navigation strong {
        font-size: 0.85rem;
        text-align: center;
    }

    .calendar-today-button {
        width: 100%;
    }

    .calendar-summary {
        gap: 8px;
    }

    .calendar-stat {
        padding: 12px;
    }

    .calendar-stat strong {
        font-size: 1.35rem;
    }

    .calendar-grid-panel {
        padding: 6px;
        overflow-x: auto;
    }

    .calendar-weekdays,
    .calendar-grid {
        min-width: 420px;
    }

    .calendar-weekdays>div {
        padding: 8px 2px;
        font-size: 0.68rem;
    }

    .calendar-day {
        min-height: 82px;
        padding: 5px 3px;
        gap: 3px;
    }

    .calendar-day-number {
        font-size: 0.72rem;
    }

    .calendar-day-marker {
        font-size: 0.52rem;
        padding: 2px 3px;
    }

    .calendar-session,
    .calendar-holiday {
        font-size: 0.57rem;
        padding: 3px;
    }

    .calendar-more {
        font-size: 0.58rem;
    }

    .calendar-legend {
        gap: 8px;
        font-size: 0.65rem;
    }

    .calendar-agenda-day {
        grid-template-columns: 1fr;
        gap: 6px;
        padding: 10px 6px;
    }
}
</style>
