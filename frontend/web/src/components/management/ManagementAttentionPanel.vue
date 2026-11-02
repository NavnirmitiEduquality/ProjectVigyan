<template>
  <article class="ov-panel">
    <slot />
  </article>
</template>

<style scoped>
.ov-panel {
  padding: 20px;
  border-radius: 10px;
  border: 1px solid var(--ov-border);
  background-color: var(--ov-bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  box-shadow: 0 1px 2px rgba(20, 30, 24, 0.04);
}
</style>
