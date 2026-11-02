<script setup lang="ts">
export type InitializationState = 'validating' | 'retryable-error' | 'invalid-session'

defineProps<{
  state: InitializationState
}>()

const emit = defineEmits<{
  retry: []
  returnToSignIn: []
}>()
</script>

<template>
  <main class="main-content">
    <section class="initialization-card" aria-labelledby="initialization-heading">
      <div class="initialization-icon" aria-hidden="true">
        <span class="material-symbols-outlined">{{ state === 'validating' ? 'sync' : state === 'invalid-session' ? 'lock' : 'wifi_off' }}</span>
      </div>

      <h1 id="initialization-heading">
        {{ state === 'validating' ? 'Validating your session' : state === 'invalid-session' ? 'Session no longer available' : 'Workspace validation unavailable' }}
      </h1>

      <p v-if="state === 'validating'" class="initialization-status" role="status" aria-live="polite">
        Confirming your Project Vigyan access. Please wait.
      </p>
      <p v-else-if="state === 'invalid-session'" class="initialization-status" role="alert">
        Your session is invalid or has expired. Sign in again to continue.
      </p>
      <p v-else class="initialization-status" role="alert">
        We could not validate your session right now. Your sign-in is still available to retry.
      </p>

      <span v-if="state === 'validating'" class="initialization-spinner" aria-hidden="true"></span>

      <div v-if="state !== 'validating'" class="initialization-actions">
        <button v-if="state === 'retryable-error'" class="submit-button" type="button" @click="emit('retry')">
          Retry validation
        </button>
        <button class="initialization-secondary-button" type="button" @click="emit('returnToSignIn')">
          Return to sign in
        </button>
      </div>
    </section>
  </main>
</template>
