<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'horizontal' | 'emblem'
    theme?: 'light' | 'dark'
    size?: 'small' | 'medium' | 'large'
  }>(),
  {
    variant: 'horizontal',
    theme: 'light',
    size: 'medium',
  },
)
</script>

<template>
  <div
    class="vigyan-logo"
    :class="[
      `vigyan-logo--${variant}`,
      `vigyan-logo--${theme}`,
      `vigyan-logo--${size}`,
    ]"
    role="img"
    aria-label="Project Vigyan — Academic Operations and STEM Platform"
  >
    <img
      class="vigyan-logo__image"
      :src="variant === 'horizontal'
        ? (theme === 'dark' ? '/brand/logo-horizontal-dark.svg' : '/brand/logo-horizontal.svg')
        : '/brand/logo-emblem.svg'"
      alt=""
      draggable="false"
    />
  </div>
</template>

<style scoped>
.vigyan-logo {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  line-height: 0;
}

.vigyan-logo__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.vigyan-logo--horizontal {
  width: 280px;
  aspect-ratio: 2080 / 800;
}

.vigyan-logo--horizontal.vigyan-logo--small {
  width: 190px;
}

.vigyan-logo--horizontal.vigyan-logo--large {
  width: min(100%, 460px);
}

.vigyan-logo--emblem {
  width: 48px;
  aspect-ratio: 1;
}

.vigyan-logo--emblem.vigyan-logo--small {
  width: 32px;
}

.vigyan-logo--emblem.vigyan-logo--large {
  width: 72px;
}

.vigyan-logo--light,
.vigyan-logo--dark {
  background: transparent;
}

@media (max-width: 480px) {
  .vigyan-logo--horizontal {
    width: min(100%, 240px);
  }
}
</style>
