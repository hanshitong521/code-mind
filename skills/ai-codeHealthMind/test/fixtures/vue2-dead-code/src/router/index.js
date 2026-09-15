import Vue from 'vue'
import Router from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import DynamicHost from '@/views/DynamicHost.vue'
import ReportView from '@/views/ReportView.vue'

Vue.use(Router)

export default new Router({
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/dynamic', name: 'dynamic', component: DynamicHost },
    { path: '/reports', name: 'reports', component: ReportView },
    { path: '/lazy', name: 'lazy', component: () => import('@/views/LazyReport.vue') }
  ]
})
