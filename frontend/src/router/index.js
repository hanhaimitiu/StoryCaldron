import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/parse'
  },
  {
    path: '/parse',
    name: 'parse',
    component: () => import('../components/ParsePage.vue')
  },
  {
    path: '/write',
    name: 'write',
    component: () => import('../components/WritePage.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
