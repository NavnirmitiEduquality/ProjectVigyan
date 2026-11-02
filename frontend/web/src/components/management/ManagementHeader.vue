<script setup lang="ts">
import type { AcademicYear } from '../../services/academicCalendar'
type ThemeMode = 'light' | 'dark' | 'system'

defineProps<{
  isRailCollapsed: boolean
  selectedYear: string
  academicYears: AcademicYear[]
  isLoadingAcademicYears: boolean
  academicYearError: string
  canManageCalendar: boolean
  themeMode: ThemeMode
  displayName: string
  userInitials: string
}>()

const emit = defineEmits<{
  'open-mobile-drawer': []
  'toggle-sidebar': []
  'update:selectedYear': [yearId: string]
  'create-academic-year': []
  'change-theme': [mode: ThemeMode]
  'sign-out': []
}>()
</script>

<template>
  <header class="ov-header" role="banner">
    <div class="ov-header-left">
      <button class="ov-hamburger ov-md-hidden" aria-label="Open navigation menu" @click="emit('open-mobile-drawer')">
        <span class="material-symbols-outlined" aria-hidden="true">menu</span>
      </button>

      <button v-if="isRailCollapsed" class="ov-rail-expand ov-md-flex" aria-label="Expand sidebar"
        title="Expand sidebar" @click="emit('toggle-sidebar')">
        <span class="material-symbols-outlined" aria-hidden="true">left_panel_open</span>
      </button>

      <div class="ov-header-title">
        <h1>
          <span class="ov-title-short">Overview</span>
          <span class="ov-title-long">Management Overview</span>
        </h1>
      </div>
    </div>

    <div class="ov-header-right">
      <div class="ov-ay-select-wrap">
        <select :value="selectedYear" class="ov-ay-select" aria-label="Academic Year"
          :disabled="isLoadingAcademicYears || academicYears.length === 0"
          @change="emit('update:selectedYear', ($event.target as HTMLSelectElement).value)">
          <option v-if="isLoadingAcademicYears" value="">
            Loading academic years…
          </option>
          <option v-else-if="academicYears.length === 0" value="">
            No academic years available
          </option>
          <option v-for="year in academicYears" :key="year.id" :value="year.id">
            {{ year.name }}
          </option>
        </select>
        <span class="material-symbols-outlined ov-ay-chevron" aria-hidden="true">
          arrow_drop_down
        </span>
        <p v-if="academicYearError" class="ov-ay-error" role="alert">
          {{ academicYearError }}
        </p>
      </div>

      <button
        v-if="canManageCalendar"
        class="ov-create-year-btn"
        type="button"
        @click="emit('create-academic-year')"
      >
        <span class="material-symbols-outlined" aria-hidden="true">add</span>
        <span class="ov-create-year-label">Create Year</span>
      </button>

      <div class="ov-theme-switcher" role="group" aria-label="Theme switcher">
        <button class="ov-theme-btn" :class="themeMode === 'light' ? 'ov-theme-btn--active' : ''" title="Light mode"
          @click="emit('change-theme', 'light')">
          <span class="material-symbols-outlined" aria-hidden="true">light_mode</span>
          <span class="ov-theme-label">Light</span>
        </button>

        <button class="ov-theme-btn" :class="themeMode === 'dark' ? 'ov-theme-btn--active' : ''" title="Dark mode"
          @click="emit('change-theme', 'dark')">
          <span class="material-symbols-outlined" aria-hidden="true">dark_mode</span>
          <span class="ov-theme-label">Dark</span>
        </button>

        <button class="ov-theme-btn" :class="themeMode === 'system' ? 'ov-theme-btn--active' : ''" title="System mode"
          @click="emit('change-theme', 'system')">
          <span class="material-symbols-outlined" aria-hidden="true">desktop_windows</span>
          <span class="ov-theme-label">System</span>
        </button>
      </div>

      <div class="ov-profile" :title="displayName">
        <div class="ov-avatar" aria-hidden="true">{{ userInitials }}</div>
        <div class="ov-profile-text">
          <span class="ov-profile-name">{{ displayName }}</span>
          <span class="ov-profile-role">Academic Operations</span>
        </div>
      </div>

      <button
        class="ov-sign-out"
        type="button"
        title="Sign out"
        aria-label="Sign out"
        @click="emit('sign-out')"
      >
        <span class="material-symbols-outlined" aria-hidden="true">logout</span>
        <span class="ov-sign-out-label">Sign Out</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.ov-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 76px;
  padding: 14px 28px;
  background: var(--ov-bg-surface);
  border-bottom: 1px solid var(--ov-border);
}

.ov-header-left,
.ov-header-right {
  display: flex;
  align-items: center;
  min-width: 0;
}

.ov-ay-error {
  margin: 4px 0 0;
  color: var(--ov-text-muted);
  font-size: 11px;
}

.ov-header-left {
  gap: 14px;
  flex: 1 1 auto;
}

.ov-header-right {
  flex: 0 1 auto;
  justify-content: flex-end;
  gap: 16px;
}

.ov-header-title {
  min-width: 0;
}

.ov-header-title h1 {
  margin: 0;
  color: var(--ov-text-primary);
  font-size: 22px;
  line-height: 1.25;
  font-weight: 700;
  letter-spacing: -0.025em;
}

.ov-title-short {
  display: none;
}

.ov-title-long {
  display: inline;
}

.ov-hamburger,
.ov-rail-expand {
  align-items: center;
  justify-content: center;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
}

.ov-hamburger .material-symbols-outlined,
.ov-rail-expand .material-symbols-outlined {
  font-size: 21px;
}

.ov-ay-select-wrap {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 0;
}

.ov-ay-select {
  width: 148px;
  max-width: 100%;
  appearance: none;
  padding: 9px 30px 9px 11px;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  font-size: 12px;
  font-weight: 500;
}

.ov-ay-chevron {
  position: absolute;
  right: 7px;
  pointer-events: none;
  color: var(--ov-text-muted);
}

.ov-theme-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--ov-border);
  border-radius: 9px;
  background: var(--ov-bg-surface-subtle);
}

.ov-theme-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 30px;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--ov-text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.ov-theme-btn .material-symbols-outlined {
  font-size: 16px;
}

.ov-theme-btn--active {
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.ov-profile {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding-left: 14px;
  border-left: 1px solid var(--ov-border);
}

.ov-avatar {
  display: grid;
  place-items: center;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--ov-tag-accent-bg);
  color: var(--ov-tag-accent-fg);
  font-size: 12px;
  font-weight: 700;
}

.ov-profile-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
}

.ov-profile-name {
  max-width: 170px;
  overflow: hidden;
  color: var(--ov-text-primary);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ov-profile-role {
  color: var(--ov-text-muted);
  font-size: 11px;
  white-space: nowrap;
}

@media (max-width: 1279px) {
  .ov-header {
    gap: 14px;
    padding-inline: 20px;
  }

  .ov-header-right {
    gap: 10px;
  }

  .ov-profile {
    padding-left: 10px;
  }

  .ov-profile-name {
    max-width: 125px;
  }
}

@media (max-width: 900px) {
  .ov-header {
    align-items: flex-start;
    flex-wrap: wrap;
    padding: 14px 18px;
  }

  .ov-header-left {
    flex: 1 1 100%;
  }

  .ov-header-right {
    flex: 1 1 100%;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .ov-header-title h1 {
    font-size: 20px;
  }
}

@media (max-width: 767px) {
  .ov-header {
    position: relative;
    min-height: 0;
    gap: 12px;
    padding: 14px 16px;
  }

  .ov-header-left {
    gap: 10px;
  }

  .ov-header-title h1 {
    font-size: 18px;
  }

  .ov-title-short {
    display: inline;
  }

  .ov-title-long {
    display: none;
  }

  .ov-header-right {
    align-items: center;
    justify-content: flex-start;
    gap: 8px;
  }

  .ov-ay-select {
    width: 130px;
  }

  .ov-theme-switcher {
    gap: 1px;
  }

  .ov-theme-btn {
    padding-inline: 6px;
  }

  .ov-theme-label {
    display: none;
  }

  .ov-profile {
    padding-left: 8px;
  }

  .ov-profile-text {
    display: none;
  }
}

@media (max-width: 380px) {
  .ov-header {
    padding-inline: 12px;
  }

  .ov-header-right {
    gap: 6px;
  }

  .ov-ay-select {
    width: 118px;
  }
}

.ov-md-hidden {
  display: flex;
}

.ov-md-flex {
  display: none;
}

@media (min-width: 768px) {
  .ov-md-hidden {
    display: none;
  }

  .ov-md-flex {
    display: flex;
  }
}

.ov-sign-out {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 0 0 auto;
  min-height: 36px;
  padding: 8px 11px;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.ov-sign-out:hover {
  background: var(--ov-bg-canvas);
  border-color: var(--ov-text-muted);
}

.ov-sign-out .material-symbols-outlined {
  font-size: 17px;
}

@media (max-width: 767px) {
  .ov-sign-out {
    min-height: 34px;
    padding: 7px;
  }

  .ov-sign-out-label {
    display: none;
  }
}


.ov-create-year-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 36px;
  padding: 8px 11px;
  border: 1px solid var(--ov-border);
  border-radius: 8px;
  background: var(--ov-bg-surface);
  color: var(--ov-text-primary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.ov-create-year-btn:hover {
  background: var(--ov-bg-canvas);
  border-color: var(--ov-text-muted);
}

.ov-create-year-btn .material-symbols-outlined {
  font-size: 17px;
}

@media (max-width: 767px) {
  .ov-create-year-label {
    display: none;
  }

  .ov-create-year-btn {
    min-height: 34px;
    padding: 7px;
  }
}

</style>
