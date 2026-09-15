import Vue from 'vue'
import App from './App.vue'
import router from './router'
import GlobalBanner from '@/components/GlobalBanner.vue'

Vue.config.productionTip = false
Vue.component('global-banner', GlobalBanner)

new Vue({
  router,
  render: (h) => h(App)
}).$mount('#app')
