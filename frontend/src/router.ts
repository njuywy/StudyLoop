import { watch } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import ComingSoonView from './views/ComingSoonView.vue'
import RegisterView from './views/RegisterView.vue'
import VerifyEmailView from './views/VerifyEmailView.vue'
import LoginView from './views/LoginView.vue'
import ProtectedView from './views/ProtectedView.vue'
import { sessionExpired, token } from './session'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView },
    { path: '/register', component: RegisterView },
    { path: '/verify-email', component: VerifyEmailView },
    { path: '/login', component: LoginView },
    { path: '/profile', component: ProtectedView, meta: { requiresAuth: true } },
    { path: '/review', component: ProtectedView, meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', component: ComingSoonView, meta: { title: '页面暂不可用', label: '返回首页' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(to => {
  if (to.meta.requiresAuth && !token.value) {
    return { path: '/login', query: { redirect: to.fullPath, ...(sessionExpired.value ? { expired: '1' } : {}) } }
  }
})

watch(sessionExpired, expired => {
  const current = router.currentRoute.value
  if (expired && current.meta.requiresAuth) {
    void router.replace({ path: '/login', query: { redirect: current.fullPath, expired: '1' } })
  }
})

export default router
