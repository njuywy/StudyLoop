import { watch } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import ComingSoonView from './views/ComingSoonView.vue'
import RegisterView from './views/RegisterView.vue'
import VerifyEmailView from './views/VerifyEmailView.vue'
import LoginView from './views/LoginView.vue'
import ProtectedView from './views/ProtectedView.vue'
import ReviewView from './views/ReviewView.vue'
import ForgotPasswordView from './views/ForgotPasswordView.vue'
import ResetPasswordView from './views/ResetPasswordView.vue'
import AdminView from './views/AdminView.vue'
import { sessionEndReason, token } from './session'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView },
    { path: '/register', component: RegisterView },
    { path: '/verify-email', component: VerifyEmailView },
    { path: '/login', component: LoginView },
    { path: '/forgot-password', component: ForgotPasswordView },
    { path: '/reset-password', component: ResetPasswordView },
    { path: '/profile', component: ProtectedView, meta: { requiresAuth: true } },
    { path: '/review', component: ReviewView, meta: { requiresAuth: true } },
    { path: '/admin/users', component: AdminView, meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', component: ComingSoonView, meta: { title: '页面暂不可用', label: '返回首页' } },
  ],
  scrollBehavior: to => to.path === '/review' ? false : { top: 0 },
})

router.beforeEach(to => {
  if (to.meta.requiresAuth && !token.value) {
    return { path: '/login', query: { redirect: to.fullPath, ...(sessionEndReason.value === 'expired' ? { expired: '1' } : {}) } }
  }
})

watch(sessionEndReason, reason => {
  const current = router.currentRoute.value
  if (reason === 'password-changed') {
    void router.replace({ path: '/login', query: { changed: '1' } })
  } else if (reason === 'expired' && current.meta.requiresAuth) {
    void router.replace({ path: '/login', query: { redirect: current.fullPath, expired: '1' } })
  }
})

export default router
