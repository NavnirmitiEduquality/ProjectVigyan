<script setup lang="ts">
import { computed } from 'vue'
import type { ClassMonitoringItem } from '../../services/reporting'

const props = defineProps<{
  items: ClassMonitoringItem[]
  loading: boolean
  error: string
  paraTeacherSelected: boolean
}>()

const rows = computed(() =>
  props.items
    .filter(item => item.status === 'ACTIVE')
    .map(item => ({
      id: item.class_division_id,
      label: `${item.school_code} · Class ${item.class_level} ${item.division}`,
      school: item.school_name,
      completed: item.delivery?.completed_sessions ?? null,
      total: item.delivery?.total_sessions ?? null,
      attendance: item.attendance?.attendance_percentage ?? null,
      evidence: item.evidence.completeness_percentage,
    }))
    .sort((a, b) => a.label.localeCompare(b.label)),
)

function percentage(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}%`
}
</script>

<template>
  <section class="report-card" aria-labelledby="school-class-performance-title">
    <header class="report-card__header">
      <div>
        <h3 id="school-class-performance-title">School / Class Performance</h3>
        <p>Session delivery, attendance and evidence coverage by active class</p>
      </div>
    </header>

    <p v-if="loading" class="report-state">Loading class performance…</p>
    <p v-else-if="error" class="report-state report-state--error">{{ error }}</p>
    <p v-else-if="paraTeacherSelected" class="report-state">
      Class performance is not filtered by para-teacher. Clear the para-teacher
      filter to view this comparison.
    </p>
    <p v-else-if="!rows.length" class="report-state">
      No active production class divisions are available in this scope.
    </p>

    <div v-else class="performance-list">
      <article v-for="row in rows" :key="row.id" class="performance-row">
        <div class="performance-row__heading">
          <strong>{{ row.label }}</strong>
          <span>{{ row.school }}</span>
        </div>

        <div class="performance-metrics">
          <div>
            <span>Delivery</span>
            <strong>
              {{ row.completed == null || row.total == null
                ? '—'
                : `${row.completed} / ${row.total}` }}
            </strong>
          </div>
          <div>
            <span>Attendance</span>
            <strong>{{ percentage(row.attendance) }}</strong>
          </div>
          <div>
            <span>Evidence</span>
            <strong>{{ percentage(row.evidence) }}</strong>
          </div>
        </div>

        <div class="performance-bars">
          <div class="performance-bar">
            <span>Delivery</span>
            <div class="performance-bar__track">
              <i :style="{
                width: row.completed == null || !row.total
                  ? '0%'
                  : `${Math.min(100, row.completed / row.total * 100)}%`
              }" />
            </div>
          </div>
          <div class="performance-bar">
            <span>Attendance</span>
            <div class="performance-bar__track">
              <i :style="{ width: `${Math.max(0, Math.min(100, row.attendance ?? 0))}%` }" />
            </div>
          </div>
          <div class="performance-bar">
            <span>Evidence</span>
            <div class="performance-bar__track">
              <i :style="{ width: `${Math.max(0, Math.min(100, row.evidence ?? 0))}%` }" />
            </div>
          </div>
        </div>
      </article>
    </div>

    <p v-if="!loading && !error && !paraTeacherSelected && rows.length" class="report-footnote">
      Delivery is completed sessions / total sessions. Attendance is record-weighted.
      Evidence is completed sessions with evidence / eligible completed sessions.
      A dash means the relevant denominator or value is unavailable.
    </p>
  </section>
</template>

<style scoped>
.report-card {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--ov-border);
  border-radius: 10px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
}
.report-card__header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}
.report-card__header p {
  margin: 5px 0 0;
  color: var(--ov-text-muted);
  font-size: 11px;
  line-height: 1.5;
}
.performance-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 18px;
}
.performance-row {
  min-width: 0;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--ov-border-subtle);
}
.performance-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}
.performance-row__heading {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-bottom: 10px;
}
.performance-row__heading strong {
  font-size: 12px;
}
.performance-row__heading span {
  color: var(--ov-text-muted);
  font-size: 11px;
}
.performance-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.performance-metrics div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.performance-metrics span,
.performance-bar > span {
  color: var(--ov-text-muted);
  font-size: 10px;
}
.performance-metrics strong {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.performance-bars {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.performance-bar {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.performance-bar__track {
  height: 6px;
  overflow: hidden;
  border-radius: 99px;
  background: var(--ov-bg-surface-subtle);
}
.performance-bar__track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ov-chart-completed);
}
.report-footnote {
  margin: 14px 0 0;
  color: var(--ov-text-muted);
  font-size: 10px;
  line-height: 1.5;
}
.report-state {
  color: var(--ov-text-muted);
  font-size: 12px;
  line-height: 1.5;
}
.report-state--error { color: #b42318; }
@media (max-width: 480px) {
  .performance-bars { gap: 7px; }
  .performance-row__heading { flex-direction: column; }
}
</style>