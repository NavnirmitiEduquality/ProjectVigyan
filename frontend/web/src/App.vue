<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SignInView from './components/auth/SignInView.vue'
import InitializationView, { type InitializationState } from './components/initialization/InitializationView.vue'
import InstitutionalFooter from './components/layout/InstitutionalFooter.vue'
import InstitutionalHeader from './components/layout/InstitutionalHeader.vue'
import ManagementOverview from './components/management/ManagementOverview.vue'
import { clearSession, getMe, getSessionToken, type AuthError, type CurrentUser } from './services/auth'
import {
  applyTheme,
  getSavedTheme,
  isDarkTheme,
  setTheme,
  type ThemeMode,
} from './services/theme'

type AppScreen = 'sign-in' | 'initializing' | 'authenticated'

const router = useRouter()
const screen = ref<AppScreen>('sign-in')
const themeMode = ref<ThemeMode>(getSavedTheme())
const isPreAuthDark = computed(() => isDarkTheme(themeMode.value))

function updateTheme(mode: ThemeMode) {
  themeMode.value = mode
  setTheme(mode)
}

function togglePreAuthTheme() {
  updateTheme(isPreAuthDark.value ? 'light' : 'dark')
}

const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)')

function handleSystemThemeChange() {
  if (themeMode.value === 'system') {
    applyTheme('system')
  }
}
const initializationState = ref<InitializationState>('validating')
const currentUser = ref<CurrentUser | null>(null)
const signInMessage = ref('')

async function validateSession() {
  initializationState.value = 'validating'
  screen.value = 'initializing'

  try {
    currentUser.value = await getMe()
    screen.value = 'authenticated'
    if (router.currentRoute.value.name === 'sign-in') {
      await router.replace({ name: 'overview' })
    }
  } catch (error) {
    const authError = error as AuthError

    if (authError.kind === 'invalid-credentials') {
      currentUser.value = null
      initializationState.value = 'invalid-session'
      signInMessage.value = 'Your session is invalid or has expired. Please sign in again.'
      screen.value = 'sign-in'
      await router.replace({ name: 'sign-in' })
      return
    }

    initializationState.value = 'retryable-error'
  }
}

function handleLoginSuccess() {
  signInMessage.value = ''
  void validateSession()
}

function returnToSignIn() {
  clearSession()
  currentUser.value = null
  signInMessage.value = 'Please sign in again to continue.'
  screen.value = 'sign-in'
  void router.replace({ name: 'sign-in' })
}

onMounted(() => {
  applyTheme(themeMode.value)
  systemThemeQuery.addEventListener('change', handleSystemThemeChange)

  // Restore the authenticated screen when a saved session token exists.
  if (getSessionToken()) {
    void validateSession()
  }
})

onUnmounted(() => {
  systemThemeQuery.removeEventListener('change', handleSystemThemeChange)
})
</script>

<template>
  <!-- Pre-auth wrapper: only shown on sign-in and initializing screens -->
  <template v-if="screen !== 'authenticated'">
    <div class="app-shell" :class="{ 'is-dark': isPreAuthDark }">
      <InstitutionalHeader :is-dark="isPreAuthDark" @theme-toggle="togglePreAuthTheme" />

      <p v-if="signInMessage" class="session-message" role="alert" aria-live="polite">{{ signInMessage }}</p>

      <SignInView v-if="screen === 'sign-in'" :is-dark="isPreAuthDark" @login-success="handleLoginSuccess" />
      <InitializationView v-else-if="screen === 'initializing'" :state="initializationState" @retry="validateSession"
        @return-to-sign-in="returnToSignIn" />

      <InstitutionalFooter />
    </div>
  </template>

  <!-- Authenticated: full-screen management overview (owns its own layout) -->
  <ManagementOverview v-else :current-user="currentUser" :initial-theme="themeMode"
    @change-theme="updateTheme" @return-to-sign-in="returnToSignIn" />
</template>
