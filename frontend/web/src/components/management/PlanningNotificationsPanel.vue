
<script setup lang="ts">
import type { PlanningNotification } from '../../services/planningNotifications'

defineProps<{
  notifications: PlanningNotification[]
  isLoading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
  close: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value))
}

function notificationTitle(type: string) {
  if (type === 'WEEKLY_PLANNING_NONCOMPLIANCE') {
    return 'Weekly planning shortfall'
  }

  if (type === 'SESSION_RESCHEDULE_REQUIRED') {
    return 'Session rescheduling required'
  }

  return 'Planning notification'
}
</script>

<template>
  <section class="planning-notifications" aria-label="Planning notifications">
    <header class="planning-notifications__header">
      <div>
        <h2>Planning notifications</h2>
        <p>Updates requiring your attention</p>
      </div>

      <div class="planning-notifications__actions">
        <button
          type="button"
          aria-label="Refresh notifications"
          title="Refresh"
          :disabled="isLoading"
          @click="emit('refresh')"
        >
          <span class="material-symbols-outlined" aria-hidden="true">refresh</span>
        </button>

        <button
          type="button"
          aria-label="Close notifications"
          title="Close"
          @click="emit('close')"
        >
          <span class="material-symbols-outlined" aria-hidden="true">close</span>
        </button>
      </div>
    </header>

    <div v-if="isLoading" class="planning-notifications__message" role="status">
      Loading planning notifications…
    </div>

    <div v-else-if="error" class="planning-notifications__message planning-notifications__message--error" role="alert">
      {{ error }}
    </div>

    <div v-else-if="notifications.length === 0" class="planning-notifications__message">
      No planning notifications.
    </div>

    <ul v-else class="planning-notifications__list">
      <li
        v-for="notification in notifications"
        :key="notification.id"
        class="planning-notifications__item"
        :class="{ 'planning-notifications__item--unread': !notification.is_read }"
      >
        <div class="planning-notifications__item-heading">
          <strong>{{ notificationTitle(notification.notification_type) }}</strong>
          <span v-if="!notification.is_read" class="planning-notifications__unread">
            Unread
          </span>
        </div>

        <p>{{ notification.message }}</p>

        <div class="planning-notifications__meta">
          <span v-if="notification.week_start_date">
            Week of {{ formatDate(notification.week_start_date) }}
          </span>
          <span>{{ formatDate(notification.created_at) }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.planning-notifications {
  width: min(390px, calc(100vw - 32px));
  max-height: min(520px, calc(100vh - 110px));
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.16);
}

.planning-notifications__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid var(--ov-border);
}

.planning-notifications__header h2 {
  margin: 0;
  font-size: 15px;
}

.planning-notifications__header p {
  margin: 4px 0 0;
  color: var(--ov-text-muted);
  font-size: 12px;
}

.planning-notifications__actions {
  display: flex;
  gap: 6px;
}

.planning-notifications__actions button {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--ov-border);
  border-radius: 7px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  cursor: pointer;
}

.planning-notifications__actions button:disabled {
  opacity: 0.5;
  cursor: wait;
}

.planning-notifications__message {
  padding: 24px 16px;
  color: var(--ov-text-secondary);
  font-size: 13px;
  text-align: center;
}

.planning-notifications__message--error {
  color: #c62828;
}

.planning-notifications__list {
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.planning-notifications__item {
  padding: 14px 16px;
  border-bottom: 1px solid var(--ov-border);
}

.planning-notifications__item--unread {
  background: var(--ov-bg-surface-subtle);
}

.planning-notifications__item-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.planning-notifications__unread {
  flex: 0 0 auto;
  color: var(--ov-text-muted);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.planning-notifications__item p {
  margin: 8px 0;
  color: var(--ov-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.planning-notifications__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px;
  color: var(--ov-text-muted);
  font-size: 10px;
}
</style>
