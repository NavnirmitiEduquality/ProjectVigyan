<script setup lang="ts">
defineProps<{ title: string; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div class="schools-modal-backdrop" role="presentation" @click.self="emit('close')">
    <section class="schools-modal" role="dialog" aria-modal="true" :aria-label="title">
      <header class="schools-modal-header">
        <h2>{{ title }}</h2>
        <button type="button" class="schools-icon-button" aria-label="Close" :disabled="busy"
          @click="emit('close')">×</button>
      </header>
      <slot />
    </section>
  </div>
</template>

<style scoped>
.schools-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(16, 26, 21, .5);
}

.schools-modal {
  width: min(100%, 520px);
  max-height: calc(100vh - 40px);
  overflow: auto;
  padding: 24px;
  border: 1px solid var(--ov-border);
  border-radius: 12px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  box-shadow: 0 20px 60px rgba(0, 0, 0, .2);
}

.schools-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.schools-modal-header h2 {
  margin: 0;
  font-size: 20px;
}

.schools-icon-button {
  border: 0;
  background: transparent;
  color: var(--ov-text-muted);
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
}
</style>
