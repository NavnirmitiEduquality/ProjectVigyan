<script setup lang="ts">
import { computed } from 'vue'
import type { AttendanceReportItem } from '../../services/reporting'

const props = defineProps<{
  report: AttendanceReportItem | null
  loading: boolean
  error: string
}>()

const total = computed(() =>
  props.report?.eligible_record_count ?? 0,
)

const presentWidth = computed(() =>
  total.value
    ? (props.report!.present_record_count / total.value) * 100
    : 0,
)

const absentWidth = computed(() =>
  total.value
    ? (props.report!.absent_record_count / total.value) * 100
    : 0,
)
</script>

<template>
  <section class="report-card" aria-labelledby="attendance-analysis-title">
    <header class="report-card__header">
      <div>
        <h3 id="attendance-analysis-title">Attendance Analysis</h3>
        <p>Present and absent attendance records</p>
      </div>
      <span v-if="report" class="report-card__metric">
        {{ report.attendance_percentage.toFixed(1) }}%
      </span>
    </header>

    <p v-if="loading" class="report-state">Loading attendance data…</p>
    <p v-else-if="error" class="report-state report-state--error">
      {{ error }}
    </p>
    <p v-else-if="!report || !total" class="report-state">
      No eligible attendance records in this reporting period.
    </p>

    <template v-else>
      <div class="attendance-bar" role="img"
        :aria-label="`${report.present_record_count} present records and ${report.absent_record_count} absent records`">
        <span class="attendance-bar__present" :style="{ width: `${presentWidth}%` }" />
        <span class="attendance-bar__absent" :style="{ width: `${absentWidth}%` }" />
      </div>

      <div class="report-legend">
        <div>
          <span class="legend-dot legend-dot--present" />
          <span>Present</span>
          <strong>{{ report.present_record_count.toLocaleString('en-IN') }}</strong>
        </div>
        <div>
          <span class="legend-dot legend-dot--absent" />
          <span>Absent</span>
          <strong>{{ report.absent_record_count.toLocaleString('en-IN') }}</strong>
        </div>
        <div>
          <span class="legend-dot legend-dot--total" />
          <span>Eligible records</span>
          <strong>{{ report.eligible_record_count.toLocaleString('en-IN') }}</strong>
        </div>
      </div>

      <p class="report-footnote">
        Record-weighted attendance. These figures count eligible attendance
        records, not unique students.
      </p>
    </template>
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
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 22px;
}
.report-card__header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}
.report-card__header p,
.report-footnote {
  margin: 5px 0 0;
  color: var(--ov-text-muted);
  font-size: 11px;
  line-height: 1.5;
}
.report-card__metric {
  color: var(--ov-brand);
  font-size: 20px;
  font-weight: 700;
  white-space: nowrap;
}
.attendance-bar {
  display: flex;
  width: 100%;
  height: 16px;
  overflow: hidden;
  border-radius: 99px;
  background: var(--ov-bg-surface-subtle);
}
.attendance-bar__present { background: var(--ov-chart-completed); }
.attendance-bar__absent { background: var(--ov-terra); }
.report-legend {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.report-legend > div {
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 5px 7px;
  align-items: center;
  min-width: 0;
  color: var(--ov-text-secondary);
  font-size: 11px;
}
.report-legend strong {
  grid-column: 2;
  color: var(--ov-text-primary);
  font-size: 13px;
}
.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.legend-dot--present { background: var(--ov-chart-completed); }
.legend-dot--absent { background: var(--ov-terra); }
.legend-dot--total { background: var(--ov-chart-total); }
.report-state {
  color: var(--ov-text-muted);
  font-size: 12px;
}
.report-state--error { color: #b42318; }
@media (max-width: 480px) {
  .report-legend { grid-template-columns: 1fr; }
}
</style>