<script setup lang="ts">
defineProps<{
  label: string
  icon: string
  iconTone: 'accent' | 'terra'
  value: string
  valueMuted?: boolean
  denominator?: string
  badgeText: string
  badgeTone: 'accent' | 'neutral'
  description: string
  footerItems: {
    label: string
    value: string
    valueTone?: 'green' | 'muted'
  }[]
}>()
</script>

<template>
  <div class="ov-kpi-card">
    <div>
      <div class="ov-kpi-header">
        <span class="ov-kpi-label">{{ label }}</span>
        <div
          class="ov-kpi-icon"
          :class="`ov-kpi-icon--${iconTone}`"
          aria-hidden="true"
        >
          <span class="material-symbols-outlined">{{ icon }}</span>
        </div>
      </div>

      <div class="ov-kpi-value-row">
        <span
          class="ov-kpi-value"
          :class="{ 'ov-kpi-value--muted': valueMuted }"
        >
          {{ value }}<span v-if="denominator" class="ov-kpi-denom">{{ denominator }}</span>
        </span>
        <span
          class="ov-kpi-badge"
          :class="`ov-kpi-badge--${badgeTone}`"
        >
          {{ badgeText }}
        </span>
      </div>

      <p class="ov-kpi-desc">{{ description }}</p>
    </div>

    <div class="ov-kpi-footer">
      <span
        v-for="item in footerItems"
        :key="item.label"
        class="ov-kpi-pill"
      >
        {{ item.label }}:
        <strong :class="item.valueTone ? `ov-${item.valueTone}` : undefined">
          {{ item.value }}
        </strong>
      </span>
    </div>
  </div>
</template>

<style scoped>
.ov-kpi-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
  min-width: 0;
  box-shadow: 0 1px 2px rgba(20, 30, 24, 0.04);
}

.ov-kpi-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.ov-kpi-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ov-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ov-kpi-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.ov-kpi-icon .material-symbols-outlined {
  font-size: 16px;
}

.ov-kpi-icon--accent {
  background-color: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
}

.ov-kpi-icon--terra {
  background-color: var(--ov-tag-terra-bg);
  color: var(--ov-tag-terra-fg);
}

.ov-kpi-value-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.ov-kpi-value {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ov-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.ov-kpi-value--muted {
  color: var(--ov-text-muted);
}

.ov-kpi-denom {
  font-size: 16px;
  font-weight: 400;
  color: var(--ov-text-muted);
}

.ov-kpi-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.ov-kpi-badge--accent {
  background-color: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
}

.ov-kpi-badge--neutral {
  background-color: var(--ov-bg-surface-subtle);
  color: var(--ov-text-secondary);
  border: 1px solid var(--ov-border);
}

.ov-kpi-desc {
  font-size: 12px;
  color: var(--ov-text-secondary);
  margin: 2px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ov-kpi-footer {
  padding-top: 10px;
  border-top: 1px solid var(--ov-border-subtle);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--ov-text-secondary);
}

.ov-kpi-pill {
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface-subtle);
}

.ov-kpi-pill strong {
  font-weight: 600;
  color: var(--ov-text-primary);
}

.ov-green {
  color: #256d47 !important;
}

.ov-shell.ov-dark .ov-green {
  color: #5ec47e !important;
}

.ov-muted {
  color: var(--ov-text-muted) !important;
}
</style>
