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
      props: true
    },
    {
      path: '/map',
      name: 'server-map',
      component: () => import('../views/MapPage.vue')
    }
  ]
})

export default router
