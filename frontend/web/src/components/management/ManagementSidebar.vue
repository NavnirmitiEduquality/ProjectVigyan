<script setup lang="ts">
import VigyanLogo from '../brand/VigyanLogo.vue'

defineProps<{
  isRailCollapsed: boolean
  isMobileDrawerOpen: boolean
}>()

const emit = defineEmits<{
  'toggle-collapse': []
  'close-drawer': []
}>()
</script>

<template>
    <aside
      class="ov-sidebar"
      :class="[isRailCollapsed ? 'ov-sidebar--rail' : '', isMobileDrawerOpen ? 'ov-sidebar--open' : '']"
      aria-label="Main Navigation"
    >
      <div class="ov-sidebar-inner">
        <!-- Brand & Header -->
        <div class="ov-sidebar-brand">
          <div class="ov-brand-mark">
            <VigyanLogo
              variant="emblem"
              theme="dark"
              size="small"
            />
            <div class="ov-sidebar-label ov-brand-text">
              <strong>Project Vigyan</strong>
              <span>Academic Operations</span>
            </div>
          </div>
          <!-- Mobile close X -->
          <button
            class="ov-mobile-close ov-md-hidden"
            aria-label="Close navigation drawer"
            @click="emit('close-drawer')"
          >
            <span class="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
          <!-- Desktop rail toggle -->
          <button
            class="ov-rail-toggle ov-md-flex"
            :aria-label="isRailCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
            :title="isRailCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
            @click="emit('toggle-collapse')"
          >
            <span class="material-symbols-outlined" aria-hidden="true">{{ isRailCollapsed ? 'left_panel_open' : 'left_panel_close' }}</span>
          </button>
        </div>

        <!-- New Assessment CTA -->
        <div class="ov-sidebar-cta">
          <button class="ov-cta-btn" title="New Assessment">
            <span class="material-symbols-outlined" aria-hidden="true">add</span>
            <span class="ov-sidebar-label">New Assessment</span>
          </button>
        </div>

        <!-- Navigation -->
        <nav class="ov-nav" aria-label="Application sections">
          <a href="#overview" @click="emit('close-drawer')" class="ov-nav-item ov-nav-item--active" title="Overview">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">dashboard</span>
            <span class="ov-sidebar-label ov-nav-label">Overview</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Overview</span>
          </a>
          <a href="#calendar" @click="emit('close-drawer')" class="ov-nav-item" title="Academic Calendar">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">calendar_month</span>
            <span class="ov-sidebar-label ov-nav-label">Academic Calendar</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Academic Calendar</span>
          </a>
          <a href="#planning" @click="emit('close-drawer')" class="ov-nav-item" title="Session Planning">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">schedule</span>
            <span class="ov-sidebar-label ov-nav-label">Session Planning</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Session Planning</span>
          </a>
          <a href="#schools" @click="emit('close-drawer')" class="ov-nav-item" title="Schools &amp; Classes">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">domain</span>
            <span class="ov-sidebar-label ov-nav-label">Schools &amp; Classes</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Schools &amp; Classes</span>
          </a>
          <a href="#teachers" @click="emit('close-drawer')" class="ov-nav-item" title="Teachers">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">group</span>
            <span class="ov-sidebar-label ov-nav-label">Teachers</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Teachers</span>
          </a>
          <a href="#assessments" @click="emit('close-drawer')" class="ov-nav-item" title="Assessments">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">assignment</span>
            <span class="ov-sidebar-label ov-nav-label">Assessments</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Assessments</span>
          </a>
          <a href="#reports" @click="emit('close-drawer')" class="ov-nav-item" title="Reports &amp; Analytics">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">monitoring</span>
            <span class="ov-sidebar-label ov-nav-label">Reports &amp; Analytics</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Reports &amp; Analytics</span>
          </a>
          <a href="#observations" @click="emit('close-drawer')" class="ov-nav-item" title="Observations">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">visibility</span>
            <span class="ov-sidebar-label ov-nav-label">Observations</span>
            <span class="ov-nav-tooltip" aria-hidden="true">Observations</span>
          </a>
          <a href="#inspections" @click="emit('close-drawer')" class="ov-nav-item" title="STEM Inspections">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">biotech</span>
            <span class="ov-sidebar-label ov-nav-label">STEM Inspections</span>
            <span class="ov-nav-tooltip" aria-hidden="true">STEM Inspections</span>
          </a>
          <a href="#admin" @click="emit('close-drawer')" class="ov-nav-item" title="Administration">
            <span class="material-symbols-outlined ov-nav-icon" aria-hidden="true">settings</span>
            <span class="ov-sidebar-label ov-nav-label-row">
              <span class="ov-nav-label-text">Administration</span>
              <span class="ov-admin-badge">Admin</span>
            </span>
            <span class="ov-nav-tooltip" aria-hidden="true">Administration</span>
          </a>
        </nav>
      </div>
    </aside>
</template>

<style scoped>
/* SIDEBAR                                                                      */
/* ════════════════════════════════════════════════════════════════════════════ */
.ov-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 248px;
  height: 100svh;
  display: flex;
  flex-direction: column;
  z-index: 50;
  transition: width 300ms ease, transform 300ms ease;
  background-color: var(--ov-sidebar-bg);
  border-right: 1px solid var(--ov-sidebar-border);
  color: var(--ov-sidebar-text);
  /* Mobile: off-screen by default */
  transform: translateX(-100%);
}
@media (min-width: 768px) {
  .ov-sidebar { transform: translateX(0); }
}
.ov-sidebar--open { transform: translateX(0) !important; box-shadow: 0 12px 32px -4px rgba(21,30,25,0.4); }
.ov-sidebar--rail { width: 68px; }

.ov-sidebar-inner {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 12px;
  overflow: hidden;
}

/* Brand header */
.ov-sidebar-brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ov-sidebar-border);
  flex-shrink: 0;
  padding-inline: 4px;
}
.ov-brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
  overflow: hidden;
  min-width: 0;
}
.ov-brand-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  background: rgba(255,255,255,0.08);
  border-radius: 8px;
  font-size: 20px;
  color: #C8A856;
}
.ov-brand-text { display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.ov-brand-text strong { font-size: 13px; font-weight: 700; letter-spacing: -0.02em; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ov-brand-text span { font-size: 10px; color: var(--ov-sidebar-muted); letter-spacing: 0.02em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.ov-mobile-close,
.ov-rail-toggle {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: transparent;
  border: 0;
  color: #a3b5aa;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 150ms;
}
.ov-mobile-close:hover, .ov-rail-toggle:hover { background: rgba(255,255,255,0.1); }
.ov-mobile-close .material-symbols-outlined,
.ov-rail-toggle .material-symbols-outlined { font-size: 19px; }


/* CTA Button */
.ov-sidebar-cta { flex-shrink: 0; }
.ov-cta-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 0;
  background-color: #193D30;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 150ms;
  overflow: hidden;
}
.ov-cta-btn:hover { background-color: #244B3B; }
.ov-cta-btn .material-symbols-outlined { font-size: 18px; flex-shrink: 0; }

/* Navigation */
.ov-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  font-size: 13px;
  padding-right: 2px;
}
.ov-nav::-webkit-scrollbar { width: 4px; }
.ov-nav::-webkit-scrollbar-thumb { background: var(--ov-sidebar-border); border-radius: 999px; }

.ov-nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  text-decoration: none;
  color: var(--ov-sidebar-muted);
  font-weight: 400;
  transition: background-color 150ms, color 150ms;
  white-space: nowrap;
}
.ov-nav-item:hover { background-color: rgba(255,255,255,0.05); color: #fff; }
.ov-nav-item--active { background-color: var(--ov-sidebar-active); color: #fff; font-weight: 500; }
.ov-nav-icon { font-size: 20px; flex-shrink: 0; }
.ov-nav-item--active .ov-nav-icon { color: #C8A856; }
.ov-nav-label { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.ov-nav-label-row { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 6px; overflow: hidden; min-width: 0; padding-right: 4px; }
.ov-nav-label-text { overflow: hidden; text-overflow: ellipsis; }
.ov-admin-badge {
  font-size: 9px;
  padding: 2px 5px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  background: rgba(255,255,255,0.08);
  color: var(--ov-sidebar-muted);
  flex-shrink: 0;
}

/* Rail tooltip */
.ov-nav-tooltip {
  display: none;
  position: absolute;
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%);
  background: #101A15;
  color: #F7F5ED;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 10px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 14px rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.12);
  z-index: 99;
  visibility: hidden;
  opacity: 0;
  transition: opacity 150ms, visibility 150ms;
}
.ov-sidebar.ov-sidebar--rail .ov-nav-tooltip { display: block; }
.ov-sidebar.ov-sidebar--rail .ov-nav-item:hover .ov-nav-tooltip { visibility: visible; opacity: 1; }
.ov-sidebar:not(.ov-sidebar--rail) .ov-nav-tooltip { display: none !important; }

/* Hide sidebar labels in rail mode */
.ov-sidebar.ov-sidebar--rail .ov-sidebar-label { display: none; }

/* ════════════════════════════════════════════════════════════════════════════ */

</style>
