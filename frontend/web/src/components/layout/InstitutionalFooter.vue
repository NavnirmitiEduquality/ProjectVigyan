<script setup lang="ts">
defineProps<{
  academicYear?: string
}>()
</script>

<template>
  <footer class="institutional-footer">
    <div>
      <strong>Project Vigyan</strong>
      <span aria-hidden="true">•</span>
      <span>Academic Operations Platform</span>
    </div>
    <span v-if="academicYear">{{ academicYear }}</span>
    <span>© 2026 Project Vigyan. All rights reserved.</span>
  </footer>
</template>
