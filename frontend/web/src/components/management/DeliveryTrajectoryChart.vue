<template>
  <section class="ov-chart-card" aria-label="Session Delivery Trajectory">
    <div class="ov-chart-header">
      <div>
        <h2 class="ov-chart-title">Session Delivery Trajectory</h2>
        <p class="ov-chart-subtitle">Monthly total sessions versus completed sessions</p>
      </div>
      <div class="ov-chart-legend" aria-label="Chart legend">
        <div class="ov-legend-item">
          <span class="ov-legend-dot ov-legend-dot--total" aria-hidden="true"></span>
          <span>Total Sessions</span>
        </div>
        <div class="ov-legend-item">
          <span class="ov-legend-dot ov-legend-dot--completed" aria-hidden="true"></span>
          <span>Completed Sessions</span>
        </div>
      </div>
    </div>

    <p v-if="loading" class="ov-chart-subtitle" role="status">Loading delivery trend…</p>
    <p v-else-if="error" class="ov-chart-subtitle" role="status">
      The chart is unavailable until the reporting request succeeds.
    </p>
    <p v-else-if="!startDate || !endDate" class="ov-chart-subtitle" role="status">
      Select a production academic year to view its delivery trend.
    </p>
    <p v-else-if="months.length === 0 || !hasActivity" class="ov-chart-subtitle" role="status">
      No production session activity is recorded for this academic year.
    </p>

    <div v-if="!loading && !error && months.length && hasActivity" class="ov-chart-body">
      <div class="ov-y-axis" aria-hidden="true">
        <span>{{ axisMax }}</span>
        <span>{{ Math.round(axisMax * 0.75) }}</span>
        <span>{{ Math.round(axisMax * 0.5) }}</span>
        <span>{{ Math.round(axisMax * 0.25) }}</span>
        <span>0</span>
      </div>
      <div class="ov-chart-plot">
        <div class="ov-grid-lines" aria-hidden="true">
          <div v-for="line in 5" :key="line" class="ov-grid-line" :class="{ 'ov-grid-line--solid': line === 5 }"></div>
        </div>
        <div class="ov-bars" :style="{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }">
          <div v-for="month in months" :key="month.key" class="ov-bar-group">
            <div class="ov-bar-pair">
              <div
                class="ov-bar ov-bar--total"
                :style="{ height: `${month.total / axisMax * 100}%` }"
                :title="`Total sessions: ${month.total}`"
              ></div>
              <div
                class="ov-bar ov-bar--completed"
                :style="{ height: `${month.completed / axisMax * 100}%` }"
                :title="`Completed sessions: ${month.completed}`"
              ></div>
            </div>
            <div class="ov-bar-label">
              <span class="ov-bar-month">{{ month.label }}</span>
              <span class="ov-bar-values">{{ month.completed }} / {{ month.total }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DeliveryTrendItem } from '../../services/reporting'

const props = defineProps<{
  items: DeliveryTrendItem[]
  startDate: string
  endDate: string
  loading: boolean
  error: string
}>()

const months = computed(() => {
  if (!props.startDate || !props.endDate) return []

  // Parse date-only values as local calendar dates to avoid UTC month shifts.
  const start = new Date(`${props.startDate.slice(0, 10)}T12:00:00`)
  const end = new Date(`${props.endDate.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return []

  const byMonth = new Map<string, DeliveryTrendItem>()
  for (const item of props.items) {
    const date = new Date(item.month)
    if (Number.isNaN(date.getTime())) continue
    const key = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
    byMonth.set(key, item)
  }

  const result: { key: string; label: string; total: number; completed: number }[] = []
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1, 12)
  const last = new Date(end.getFullYear(), end.getMonth(), 1, 12)
  while (cursor <= last) {
    const key = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`
    const item = byMonth.get(key)
    result.push({
      key,
      label: cursor.toLocaleDateString(undefined, { month: 'short' }),
      total: item?.session_count ?? 0,
      completed: item?.completed_sessions ?? 0,
    })
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return result
})

const axisMax = computed(() => {
  const highest = Math.max(0, ...months.value.map((month) => month.total))
  if (highest === 0) return 1
  return Math.ceil(highest / 5) * 5
})
const hasActivity = computed(() => months.value.some((month) => month.total > 0))
</script>


<style scoped>
/* ─── Chart Card ──────────────────────────────────────────────────────────── */
.ov-chart-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface);
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  box-shadow: 0 1px 2px rgba(20,30,24,0.04);
  min-height: 320px;
}
@media (min-width: 640px) { .ov-chart-card { padding: 20px; } }

.ov-chart-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ov-border-subtle);
  flex-shrink: 0;
}
@media (min-width: 640px) {
  .ov-chart-header { flex-direction: row; align-items: center; justify-content: space-between; }
}

.ov-chart-title { font-size: 15px; font-weight: 700; letter-spacing: -0.02em; color: var(--ov-text-primary); margin: 0; }
.ov-chart-subtitle { font-size: 12px; color: var(--ov-text-secondary); margin: 2px 0 0; }
.ov-chart-legend { display: flex; align-items: center; gap: 16px; font-size: 12px; flex-shrink: 0; flex-wrap: wrap; }
.ov-legend-item { display: flex; align-items: center; gap: 6px; color: var(--ov-text-secondary); }
.ov-legend-item:last-child { color: var(--ov-text-primary); font-weight: 500; }
.ov-legend-dot { display: inline-block; width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }
.ov-legend-dot--total { background-color: var(--ov-chart-total); }
.ov-legend-dot--completed { background-color: var(--ov-chart-completed); }

/* Chart body */
.ov-chart-body {
  display: flex;
  flex: 1;
  padding-top: 20px;
  min-height: 230px;
}

/* Y-Axis */
.ov-y-axis {
  width: 32px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  text-align: right;
  padding-right: 8px;
  padding-bottom: 24px;
  font-size: 11px;
  font-family: monospace;
  font-variant-numeric: tabular-nums;
  color: var(--ov-text-muted);
  border-right: 1px solid var(--ov-border-subtle);
}
.ov-y-mid { display: none; }
.ov-y-250 { display: block; }
@media (min-width: 640px) {
  .ov-y-mid { display: block; }
  .ov-y-250 { display: none; }
}

/* Chart plot */
.ov-chart-plot {
  position: relative;
  flex: 1;
  padding-left: 12px;
  padding-right: 8px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ov-grid-lines {
  position: absolute;
  inset: 0;
  padding-left: 12px;
  padding-right: 8px;
  padding-bottom: 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: none;
  z-index: 0;
}
.ov-grid-line {
  width: 100%;
  border-bottom: 1px dashed var(--ov-border-subtle);
}
.ov-grid-line--solid { border-bottom-style: solid; }

/* Bars */
.ov-bars {
  position: relative;
  z-index: 10;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 6px;
  height: 100%;
  align-items: end;
  padding-bottom: 0;
}
@media (min-width: 640px) { .ov-bars { gap: 16px; } }
@media (min-width: 768px) { .ov-bars { gap: 24px; } }

.ov-bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
  justify-content: flex-end;
  min-width: 0;
}

.ov-bar-pair {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  width: 100%;
  height: 165px;
}
@media (min-width: 640px) { .ov-bar-pair { gap: 4px; } }

.ov-bar {
  border-radius: 2px 2px 0 0;
  transition: opacity 150ms;
  min-width: 0;
  flex-shrink: 0;
}
.ov-bar--total { background-color: var(--ov-chart-total); width: 10px; }
.ov-bar--completed { background-color: var(--ov-chart-completed); width: 10px; }
@media (min-width: 640px) {
  .ov-bar--total, .ov-bar--completed { width: 16px; }
}
@media (min-width: 768px) {
  .ov-bar--total, .ov-bar--completed { width: 22px; }
}
.ov-bar:hover { opacity: 0.8; }

.ov-bar-label {
  text-align: center;
  width: 100%;
  min-width: 0;
  padding-bottom: 4px;
}
.ov-bar-month {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--ov-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (min-width: 640px) { .ov-bar-month { font-size: 12px; } }
.ov-bar-month--current { color: var(--ov-brand); }
.ov-bar-month-suffix { display: none; }
@media (min-width: 640px) { .ov-bar-month-suffix { display: inline; } }
.ov-bar-values {
  display: none;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--ov-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (min-width: 640px) { .ov-bar-values { display: block; } }
.ov-bar-values--current { color: var(--ov-brand); font-weight: 500; }
</style>
