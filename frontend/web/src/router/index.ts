import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const SESSION_STORAGE_KEY = 'vigyan_session_token'

const RoutePlaceholder = {
  render: () => null,
}

const routes: RouteRecordRaw[] = [
    {
      path: '/',
      redirect: () =>
        sessionStorage.getItem(SESSION_STORAGE_KEY) ? '/overview' : '/sign-in',
    },
    {
      path: '/sign-in',
      name: 'sign-in',
      component: RoutePlaceholder,
      meta: { requiresGuest: true },
    },
    {
      path: '/overview',
      name: 'overview',
      component: RoutePlaceholder,
      meta: { requiresAuth: true, section: 'overview' },
    },
    {
      path: '/schools',
      name: 'schools',
      component: RoutePlaceholder,
      meta: { requiresAuth: true, section: 'schools' },
    },
    {
      path: '/students',
      name: 'students',
      component: RoutePlaceholder,
      meta: { requiresAuth: true, section: 'students' },
    },
    {
      path: '/teachers',
      name: 'teachers',
      component: RoutePlaceholder,
      meta: { requiresAuth: true, section: 'teachers' },
    },
    {
      path: '/session-planning',
      name: 'session-planning',
      component: RoutePlaceholder,
      meta: {
        requiresAuth: true,
        section: 'session-planning',
      },
    },
    {
      path: '/academic-calendar',
      name: 'academic-calendar',
      component: RoutePlaceholder,
      meta: {
        requiresAuth: true,
        section: 'academic-calendar',
      },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to) => {
  const hasSession = Boolean(sessionStorage.getItem(SESSION_STORAGE_KEY))

  if (to.meta.requiresAuth && !hasSession) {
    return { name: 'sign-in' }
  }

  if (to.meta.requiresGuest && hasSession) {
    return { name: 'overview' }
  }

  return true
})

export default router
