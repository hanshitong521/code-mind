import Vue from 'vue'
import Router from 'vue-router'
import UserView from '@/views/UserView.vue'

Vue.use(Router)

export default new Router({
  routes: [
    { path: '/users', name: 'users', component: UserView }
  ]
})
