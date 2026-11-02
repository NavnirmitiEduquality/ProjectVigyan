<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  isSubmitting: boolean
}>()

const emit = defineEmits<{
  submit: [credentials: { email: string; password: string }]
}>()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const showValidation = ref(false)

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

function submitForm() {
  const isEmailValid = isValidEmail(email.value)
  const isPasswordValid = password.value.length > 0

  if (!isEmailValid || !isPasswordValid) {
    showValidation.value = true
    return
  }

  showValidation.value = false
  emit('submit', { email: email.value.trim(), password: password.value })
}
</script>

<template>
  <form class="sign-in-form" novalidate @submit.prevent="submitForm">
    <div class="field">
      <label for="institutional-email">Institutional Email</label>
      <span id="email-format-hint">e.g., yourname@vigyan.ac.in or institution.edu</span>
      <input
        id="institutional-email"
        v-model="email"
        name="email"
        type="email"
        autocomplete="email"
        placeholder="name@example.edu"
        aria-describedby="email-format-hint email-error"
        :aria-invalid="showValidation && !isValidEmail(email)"
        :class="{ 'has-error': showValidation && !isValidEmail(email) }"
        @input="showValidation = false"
      />
      <span v-if="showValidation && !isValidEmail(email)" id="email-error" class="field-error" role="alert">
        <span class="material-symbols-outlined" aria-hidden="true">error</span>
        Please enter a valid institutional email address.
      </span>
    </div>

    <div class="field">
      <label for="institutional-password">Password</label>
      <div class="password-control">
        <input
          id="institutional-password"
          v-model="password"
          name="password"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="current-password"
          placeholder="Enter your password"
          aria-describedby="password-error"
          :aria-invalid="showValidation && !password"
          :class="{ 'has-error': showValidation && !password }"
          @input="showValidation = false"
        />
        <button
          class="password-toggle"
          type="button"
          :aria-label="showPassword ? 'Hide password' : 'Show password'"
          @click="showPassword = !showPassword"
        >
          <span class="material-symbols-outlined" aria-hidden="true">{{ showPassword ? 'visibility_off' : 'visibility' }}</span>
        </button>
      </div>
      <span v-if="showValidation && !password" id="password-error" class="field-error" role="alert">
        <span class="material-symbols-outlined" aria-hidden="true">error</span>
        Password is required to authenticate.
      </span>
    </div>

    <button class="submit-button" type="submit" :disabled="props.isSubmitting">
      <span v-if="props.isSubmitting" class="spinner" aria-hidden="true"></span>
      {{ props.isSubmitting ? 'Signing in...' : 'Sign in' }}
    </button>
  </form>
</template>
