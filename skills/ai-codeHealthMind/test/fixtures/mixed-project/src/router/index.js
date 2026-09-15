import Vue from 'vue'
import Router from 'vue-router'
import OrderBoard from '@/views/OrderBoard.vue'

Vue.use(Router)

export default new Router({
  routes: [{ path: '/orders', name: 'orders', component: OrderBoard }]
})
