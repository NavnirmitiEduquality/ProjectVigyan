<script setup lang="ts">
import { ref } from 'vue'
import VigyanLogo from '../brand/VigyanLogo.vue'
import AuthAlert, { type AuthAlertState } from './AuthAlert.vue'
import SignInForm from './SignInForm.vue'
import { login, type AuthError } from '../../services/auth'

type Credentials = {
  email: string
  password: string
}

const isSubmitting = ref(false)
const alertState = ref<AuthAlertState | null>(null)
const statusMessage = ref('')
const lastCredentials = ref<Credentials | null>(null)

const props = defineProps<{
  isDark: boolean
}>()

const emit = defineEmits<{
  loginSuccess: []
}>()

async function submitCredentials(credentials: Credentials) {
  lastCredentials.value = credentials
  alertState.value = null
  statusMessage.value = ''
  isSubmitting.value = true

  try {
    await login(credentials.email, credentials.password)
    emit('loginSuccess')
  } catch (error) {
    const authError = error as AuthError

    if (authError.kind === 'invalid-credentials') {
      alertState.value = 'invalid-credentials'
    } else if (authError.kind === 'inactive') {
      alertState.value = 'inactive'
    } else {
      alertState.value = 'network-error'
    }
  } finally {
    isSubmitting.value = false
  }
}

function retryConnection() {
  if (lastCredentials.value) {
    void submitCredentials(lastCredentials.value)
  }
}
</script>

<template>
  <main class="main-content">
    <div class="auth-wrapper">
      <section class="auth-card" aria-labelledby="welcome-heading">
        <div class="sign-in-emblem-container">
          <VigyanLogo class="sign-in-emblem" variant="emblem" :theme="props.isDark ? 'dark' : 'light'" size="large" />
        </div>

        <div class="card-heading">
          <h1 id="welcome-heading">Welcome back</h1>
          <p>Sign in to your Project Vigyan workspace.</p>
        </div>

        <AuthAlert v-if="alertState" :state="alertState" @retry="retryConnection" />

        <p v-if="statusMessage" class="success-message" role="status" aria-live="polite">{{ statusMessage }}</p>

        <SignInForm :is-submitting="isSubmitting" @submit="submitCredentials" />
      </section>

      <p class="access-note">Access restricted to certified educators, administrative officers, and curriculum auditors.
      </p>
    </div>
  </main>
</template>
