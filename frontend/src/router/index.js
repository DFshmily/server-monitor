import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('../views/Overview.vue')
    },
    {
      path: '/server/:name',
      name: 'server-detail',
      component: () => import('../views/ServerDetail.vue'),
      props: true,
      meta: { requiresAuth: true }
    },
    {
      path: '/map',
      name: 'server-map',
      component: () => import('../views/MapPage.vue')
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
      meta: { guestOnly: true }
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/Admin.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    }
  ]
})

// 全局守卫:详情/管理页需登录,管理页需管理员
router.beforeEach((to) => {
  const token = localStorage.getItem('monitor_token')
  let user = null
  try {
    user = JSON.parse(localStorage.getItem('monitor_user') || 'null')
  } catch (e) {
    user = null
  }

  if (to.meta.requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && (!token || user?.role !== 'admin')) {
    return { path: '/' }
  }
  if (to.meta.guestOnly && token) {
    return { path: '/' }
  }
  return true
})

export default router
