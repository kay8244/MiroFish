import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Process from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import ReportView from '../views/ReportView.vue'
import InteractionView from '../views/InteractionView.vue'
import PipelineView from '../views/PipelineView.vue'
import LoginView from '../views/LoginView.vue'
import { authState, initAuth } from '../store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true
  },
  {
    path: '/pipeline',
    name: 'Pipeline',
    component: PipelineView
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 전역 인증 가드: 앱 부팅 시 1회 initAuth 로 세션 복원, 그 후 미인증 접근은 /login 으로.
// 이미 인증된 상태로 /login 에 진입하면 (DEV_BYPASS_AUTH 자동 로그인 등) 즉시 next 로 점프.
router.beforeEach(async (to, from) => {
  if (!authState.initialized) {
    await initAuth()
  }
  if (to.name === 'Login' && authState.user) {
    const next = (to.query.next && decodeURIComponent(to.query.next)) || '/'
    return next
  }
  if (to.meta && to.meta.public) return true
  if (!authState.user) {
    return {
      path: '/login',
      query: { next: to.fullPath }
    }
  }
  return true
})

export default router
