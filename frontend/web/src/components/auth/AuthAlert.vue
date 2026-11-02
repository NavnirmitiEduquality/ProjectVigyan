<script setup lang="ts">
export type AuthAlertState = 'invalid-credentials' | 'inactive' | 'network-error'

const props = defineProps<{
  state: AuthAlertState
}>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div class="alert" :class="props.state === 'inactive' ? 'alert-warning' : 'alert-error'" role="alert" aria-live="polite">
    <span class="material-symbols-outlined alert-icon" aria-hidden="true">
      {{ props.state === 'inactive' ? 'person_off' : props.state === 'network-error' ? 'wifi_off' : 'error' }}
    </span>
    <div>
      <strong v-if="props.state === 'invalid-credentials'">Authentication Failed</strong>
      <strong v-else-if="props.state === 'inactive'">Account Inactive</strong>
      <strong v-else>Connection Error</strong>
      <p v-if="props.state === 'invalid-credentials'">Authentication failed: Invalid credentials. Please check your email and password.</p>
      <p v-else-if="props.state === 'inactive'">Account Inactive — Access restricted. Please contact your institution's administrator or technical support.</p>
      <p v-else>Unable to reach academic authorization service. Check your connection or retry.</p>
    </div>
    <button v-if="props.state === 'network-error'" class="retry-button" type="button" @click="emit('retry')">Retry</button>
  </div>
</template>
