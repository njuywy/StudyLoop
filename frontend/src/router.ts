import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import ComingSoonView from './views/ComingSoonView.vue'
import RegisterView from './views/RegisterView.vue'
import VerifyEmailView from './views/VerifyEmailView.vue'

export default createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView },
    { path: '/register', component: RegisterView },
    { path: '/verify-email', component: VerifyEmailView },
    { path: '/login', component: ComingSoonView, meta: { title: '登录功能准备中', label: '登录' } },
    { path: '/profile', component: ComingSoonView, meta: { title: '个人中心功能准备中', label: '个人中心' } },
    { path: '/review', component: ComingSoonView, meta: { title: '在线复习功能准备中', label: '在线复习' } },
    { path: '/:pathMatch(.*)*', component: ComingSoonView, meta: { title: '页面暂不可用', label: '返回首页' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
