<script setup lang="ts">
import { computed } from 'vue'
import type { EngagementReportItem } from '../../services/reporting'

const props = defineProps<{
  report: EngagementReportItem | null
  loading: boolean
  error: string
}>()

const scores = computed(() =>
  Array.from({ length: 10 }, (_, index) => {
    const score = String(index + 1)
    return {
      score,
      count: props.report?.distribution?.[score] ?? 0,
    }
  }),
)

const maxCount = computed(() =>
  Math.max(1, ...scores.value.map(item => item.count)),
)
</script>

<template>
  <section class="report-card" aria-labelledby="engagement-distribution-title">
    <header class="report-card__header">
      <div>
        <h3 id="engagement-distribution-title">Engagement Distribution</h3>
        <p>Recorded session scores from 1 to 10</p>
      </div>
      <span v-if="report?.average_engagement != null" class="report-card__metric">
        {{ report.average_engagement.toFixed(2) }}<small> / 10</small>
      </span>
    </header>

    <p v-if="loading" class="report-state">Loading engagement data…</p>
    <p v-else-if="error" class="report-state report-state--error">{{ error }}</p>
    <p v-else-if="!report || !report.session_count" class="report-state">
      No production sessions in this reporting period.
    </p>
    <p v-else-if="!report.scored_session_count" class="report-state">
      No engagement scores have been recorded for these sessions.
    </p>

    <template v-else>
      <div class="score-chart" role="img"
        aria-label="Distribution of recorded engagement scores from 1 to 10">
        <div v-for="item in scores" :key="item.score" class="score-chart__column">
          <strong>{{ item.count }}</strong>
          <div class="score-chart__track">
            <span :style="{ height: `${(item.count / maxCount) * 100}%` }" />
          </div>
          <span class="score-chart__label">{{ item.score }}</span>
        </div>
      </div>

      <div class="engagement-summary">
        <div>
          <span>Scored sessions</span>
          <strong>{{ report.scored_session_count.toLocaleString('en-IN') }}</strong>
        </div>
        <div>
          <span>Missing scores</span>
          <strong>{{ report.missing_engagement_count.toLocaleString('en-IN') }}</strong>
        </div>
        <div>
          <span>Total sessions</span>
          <strong>{{ report.session_count.toLocaleString('en-IN') }}</strong>
        </div>
      </div>
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
  gap: 12px;
  margin-bottom: 18px;
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
.report-card__metric {
  color: var(--ov-brand);
  font-size: 20px;
  font-weight: 700;
  white-space: nowrap;
}
.report-card__metric small {
  font-size: 11px;
  font-weight: 500;
}
.score-chart {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 6px;
  height: 150px;
  align-items: end;
  padding-top: 10px;
}
.score-chart__column {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  height: 100%;
  min-width: 0;
}
.score-chart__column strong {
  color: var(--ov-text-secondary);
  font-size: 10px;
  font-weight: 600;
}
.score-chart__track {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
  height: 105px;
  overflow: hidden;
  border-radius: 4px 4px 0 0;
  background: var(--ov-bg-surface-subtle);
}
.score-chart__track span {
  display: block;
  width: 100%;
  min-height: 0;
  border-radius: 4px 4px 0 0;
  background: var(--ov-chart-completed);
}
.score-chart__label {
  color: var(--ov-text-muted);
  font-size: 10px;
}
.engagement-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--ov-border-subtle);
}
.engagement-summary div {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.engagement-summary span {
  color: var(--ov-text-muted);
  font-size: 10px;
}
.engagement-summary strong {
  font-size: 13px;
}
.report-state {
  color: var(--ov-text-muted);
  font-size: 12px;
}
.report-state--error { color: #b42318; }
@media (max-width: 420px) {
  .score-chart { gap: 3px; }
  .score-chart__column strong,
  .score-chart__label { font-size: 9px; }
  .engagement-summary { grid-template-columns: 1fr; }
}
</style>