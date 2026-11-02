<script setup lang="ts">
import VigyanLogo from '../brand/VigyanLogo.vue'

defineProps<{
  isDark: boolean
}>()

const emit = defineEmits<{
  themeToggle: []
}>()
</script>

<template>
  <header class="institutional-header">
    <div class="header-brand">
      <VigyanLogo
        variant="horizontal"
        :theme="isDark ? 'dark' : 'light'"
        size="medium"
      />
    </div>

    <button
      class="theme-toggle"
      type="button"
      :aria-label="isDark ? 'Switch to ivory theme' : 'Switch to charcoal theme'"
      @click="emit('themeToggle')"
    >
      <span class="material-symbols-outlined" aria-hidden="true">
        {{ isDark ? 'light_mode' : 'dark_mode' }}
      </span>
    </button>
  </header>
</template>
