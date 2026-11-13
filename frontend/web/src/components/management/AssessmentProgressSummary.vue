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
      baseline: item.assessment?.baseline ?? null,
      endline: item.assessment?.endline ?? null,
      longitudinal: item.assessment?.longitudinal ?? null,
    }))
    .filter(row =>
      row.baseline || row.endline || row.longitudinal,
    )
    .sort((a, b) => a.label.localeCompare(b.label)),
)

function formatPercentage(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function formatChange(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`
}
</script>

<template>
  <section class="report-card" aria-labelledby="assessment-progress-title">
    <header class="report-card__header">
      <div>
        <h3 id="assessment-progress-title">Assessment Progress</h3>
        <p>Baseline, endline and matched-student progress</p>
      </div>
      <span class="report-card__badge">Academic-year scope</span>
    </header>

    <p v-if="loading" class="report-state">Loading assessment summaries…</p>
    <p v-else-if="error" class="report-state report-state--error">{{ error }}</p>
    <p v-else-if="paraTeacherSelected" class="report-state">
      Assessment summaries are not filtered by para-teacher. Clear the
      para-teacher filter to view this comparison.
    </p>
    <p v-else-if="!rows.length" class="report-state">
      No baseline, endline or longitudinal assessment results are available
      for the active class divisions in this scope.
    </p>

    <div v-else class="assessment-list">
      <article v-for="row in rows" :key="row.id" class="assessment-row">
        <strong class="assessment-row__title">{{ row.label }}</strong>

        <div class="assessment-values">
          <div>
            <span>Baseline average</span>
            <strong>{{ formatPercentage(row.baseline?.average_percentage) }}</strong>
            <small>{{ row.baseline?.name ?? 'Not available' }}</small>
          </div>
          <div>
            <span>Endline average</span>
            <strong>{{ formatPercentage(row.endline?.average_percentage) }}</strong>
            <small>{{ row.endline?.name ?? 'Not available' }}</small>
          </div>
          <div>
            <span>Matched-student change</span>
            <strong>{{ formatChange(row.longitudinal?.average_percentage_point_change) }}</strong>
            <small>
              {{ row.longitudinal
                ? `${row.longitudinal.matched_students} matched students`
                : 'No matched comparison' }}
            </small>
          </div>
        </div>

        <p class="assessment-scope">
          Participation: not available at class-summary level.
          <template v-if="row.baseline">
            Baseline import scope:
            {{ row.baseline.assessment_import_scope === 'unknown_historical_scope'
              ? 'unknown historical scope'
              : 'recorded class-division scope' }}.
          </template>
          <template v-if="row.endline">
            Endline import scope:
            {{ row.endline.assessment_import_scope === 'unknown_historical_scope'
              ? 'unknown historical scope'
              : 'recorded class-division scope' }}.
          </template>
        </p>
      </article>
    </div>

    <p v-if="!loading && !error && !paraTeacherSelected" class="report-footnote">
      Assessment figures are based on the selected academic year, not the
      dashboard's selected date range. Longitudinal change uses students
      matched between baseline and endline who are currently assigned to
      the displayed class division. Percentage-point change is not a
      percentage growth rate.
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
.report-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
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
}
.report-card__badge {
  padding: 4px 8px;
  border-radius: 5px;
  background: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
  font-size: 10px;
  font-weight: 600;
}
.assessment-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
  margin-top: 18px;
}
.assessment-row {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--ov-border-subtle);
}
.assessment-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}
.assessment-row__title {
  display: block;
  margin-bottom: 12px;
  font-size: 12px;
}
.assessment-values {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.assessment-values div {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.assessment-values span,
.assessment-values small {
  color: var(--ov-text-muted);
  font-size: 10px;
  line-height: 1.4;
}
.assessment-values strong {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.assessment-scope,
.report-footnote {
  margin: 12px 0 0;
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
@media (max-width: 520px) {
  .assessment-values { grid-template-columns: 1fr; }
}
</style>