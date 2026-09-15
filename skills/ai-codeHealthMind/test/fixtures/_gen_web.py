"""Fixture generator: Vue2 / JS fixtures (used by ``test/fixtures/_generate.py``).

Exposed as ``WEB_FIXTURES[fixture_name][relative_path] = content`` so fixtures
that share the ``src/`` layout cannot collide with each other.
"""

from __future__ import annotations

WEB_FIXTURES: dict[str, dict[str, str]] = {
    # ======================================================================
    # vue2-clean -- healthy Vue2 SFCs + an API wrapper that normalises errors.
    # ======================================================================
    "vue2-clean": {
        "package.json": '''{
  "name": "vue2-clean-fixture",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "axios": "^0.27.2",
    "vue": "^2.7.14",
    "vue-router": "^3.6.5",
    "vuex": "^3.6.2"
  },
  "devDependencies": {
    "webpack": "^5.88.0"
  }
}
''',
        "src/main.js": '''import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'

Vue.config.productionTip = false

new Vue({
  router,
  store,
  render: (h) => h(App)
}).$mount('#app')
''',
        "src/App.vue": '''<template>
  <div class="app">
    <user-card :user="currentUser" />
    <router-view />
  </div>
</template>

<script>
import UserCard from '@/components/UserCard.vue'

export default {
  name: 'App',
  components: { UserCard },
  computed: {
    currentUser() {
      return this.$store.state.user
    }
  }
}
</script>
''',
        "src/components/UserCard.vue": '''<template>
  <div class="user-card">
    <span class="user-card__name">{{ displayName }}</span>
  </div>
</template>

<script>
export default {
  name: 'UserCard',
  props: {
    user: { type: Object, required: true }
  },
  computed: {
    displayName() {
      return this.user ? this.user.name : 'anonymous'
    }
  }
}
</script>
''',
        "src/views/UserView.vue": '''<template>
  <div class="user-view">
    <user-card :user="user" />
    <button type="button" @click="reload">reload</button>
  </div>
</template>

<script>
import UserCard from '@/components/UserCard.vue'
import { fetchUser } from '@/api/user'

export default {
  name: 'UserView',
  components: { UserCard },
  data() {
    return { user: null, userId: '1' }
  },
  methods: {
    reload() {
      return fetchUser(this.userId).then((user) => {
        this.user = user
      })
    }
  }
}
</script>
''',
        "src/api/user.js": '''import request from '@/utils/request'

export function fetchUser(id) {
  return request({
    url: '/user/' + id,
    method: 'get'
  }).then((res) => normalizeUser(res))
}

function normalizeUser(raw) {
  return { id: raw.id, name: raw.name || 'anonymous' }
}
''',
        "src/utils/request.js": '''import axios from 'axios'

const request = axios.create({ baseURL: '/api', timeout: 10000 })

request.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(normalize(error))
)

function normalize(error) {
  return {
    message: (error && error.message) || 'unknown error',
    status: (error && error.response && error.response.status) || 0
  }
}

export default request
''',
        "src/router/index.js": '''import Vue from 'vue'
import Router from 'vue-router'
import UserView from '@/views/UserView.vue'

Vue.use(Router)

export default new Router({
  routes: [
    { path: '/users', name: 'users', component: UserView }
  ]
})
''',
        "src/store/index.js": '''import Vue from 'vue'
import Vuex from 'vuex'

Vue.use(Vuex)

export default new Vuex.Store({
  state: { user: null },
  mutations: {
    setUser(state, user) {
      state.user = user
    }
  }
})
''',
    },
    # ======================================================================
    # vue2-dead-code
    # ======================================================================
    "vue2-dead-code": {
        "package.json": '''{
  "name": "vue2-dead-code-fixture",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "lodash": "^4.17.21",
    "moment": "^2.29.4",
    "vue": "^2.7.14",
    "vue-router": "^3.6.5"
  }
}
''',
        "src/main.js": '''import Vue from 'vue'
import App from './App.vue'
import router from './router'
import GlobalBanner from '@/components/GlobalBanner.vue'

Vue.config.productionTip = false
Vue.component('global-banner', GlobalBanner)

new Vue({
  router,
  render: (h) => h(App)
}).$mount('#app')
''',
        "src/App.vue": '''<template>
  <div class="app">
    <router-view />
  </div>
</template>

<script>
export default {
  name: 'App'
}
</script>
''',
        "src/views/Dashboard.vue": '''<template>
  <div class="dashboard">
    <active-tabs :items="tabs" />
    <span>{{ summary }}</span>
  </div>
</template>

<script>
import ActiveTabs from '@/components/ActiveTabs.vue'
import UnusedWidget from '@/components/UnusedWidget.vue'

export default {
  name: 'Dashboard',
  components: { ActiveTabs, UnusedWidget },
  data() {
    return { tabs: ['today', 'week'] }
  },
  computed: {
    summary() {
      return this.tabs.length + ' tabs'
    }
  }
}
</script>
''',
        "src/components/ActiveTabs.vue": '''<template>
  <ul class="active-tabs">
    <li v-for="item in items" :key="item">{{ item }}</li>
  </ul>
</template>

<script>
export default {
  name: 'ActiveTabs',
  props: {
    items: { type: Array, required: true }
  }
}
</script>
''',
        "src/components/UnusedWidget.vue": '''<template>
  <div class="unused-widget">{{ label }}</div>
</template>

<script>
export default {
  name: 'UnusedWidget',
  props: {
    label: { type: String, default: 'widget' }
  }
}
</script>
''',
        "src/components/GlobalBanner.vue": '''<template>
  <div class="global-banner">{{ text }}</div>
</template>

<script>
export default {
  name: 'GlobalBanner',
  props: {
    text: { type: String, default: 'notice' }
  }
}
</script>
''',
        "src/views/DynamicHost.vue": '''<template>
  <div class="dynamic-host">
    <component :is="current" />
  </div>
</template>

<script>
import AlphaPanel from '@/components/AlphaPanel.vue'
import BetaPanel from '@/components/BetaPanel.vue'

export default {
  name: 'DynamicHost',
  components: { AlphaPanel, BetaPanel },
  data() {
    return { current: 'AlphaPanel' }
  }
}
</script>
''',
        "src/components/AlphaPanel.vue": '''<template>
  <div class="alpha-panel">alpha</div>
</template>

<script>
export default {
  name: 'AlphaPanel'
}
</script>
''',
        "src/components/BetaPanel.vue": '''<template>
  <div class="beta-panel">beta</div>
</template>

<script>
export default {
  name: 'BetaPanel'
}
</script>
''',
        "src/views/LazyReport.vue": '''<template>
  <div class="lazy-report">{{ title }}</div>
</template>

<script>
export default {
  name: 'LazyReport',
  data() {
    return { title: 'report' }
  }
}
</script>
''',
        "src/views/ReportView.vue": '''<template>
  <div class="report-view">{{ formatted }}</div>
</template>

<script>
import { formatDate } from '@/utils/format'

export default {
  name: 'ReportView',
  data() {
    return { created: '2026-01-01' }
  },
  computed: {
    formatted() {
      return formatDate(this.created)
    }
  }
}
</script>
''',
        "src/utils/format.js": '''export function formatDate(value) {
  if (!value) {
    return ''
  }
  return value.slice(0, 10)
}

export function formatMoney(cents) {
  const units = cents / 100
  return units.toFixed(2)
}
''',
        "src/router/index.js": '''import Vue from 'vue'
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
''',
    },
    # ======================================================================
    # vue2-duplicate
    # ======================================================================
    "vue2-duplicate": {
        "package.json": '''{
  "name": "vue2-duplicate-fixture",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "vue": "^2.7.14"
  }
}
''',
        "src/main.js": '''import Vue from 'vue'
import ReportBoard from '@/views/ReportBoard.vue'

new Vue({ render: (h) => h(ReportBoard) }).$mount('#app')
''',
        "src/views/ReportBoard.vue": '''<template>
  <div class="report-board">
    <span>{{ activeUsers }}</span>
    <span>{{ activeAdmins }}</span>
  </div>
</template>

<script>
export default {
  name: 'ReportBoard',
  data() {
    return { users: [], admins: [] }
  },
  computed: {
    activeUsers() {
      const list = this.users.filter((u) => u.active)
      const sorted = list.sort((a, b) => a.name.localeCompare(b.name))
      return sorted.map((u) => u.name)
    },
    activeAdmins() {
      const list = this.users.filter((u) => u.active)
      const sorted = list.sort((a, b) => a.name.localeCompare(b.name))
      return sorted.map((u) => u.name)
    }
  }
}
</script>
''',
        "src/views/SimpleBoard.vue": '''<template>
  <div class="simple-board">
    <span>{{ label }}</span>
    <span>{{ count }}</span>
  </div>
</template>

<script>
export default {
  name: 'SimpleBoard',
  props: {
    user: { type: Object, default: null }
  },
  computed: {
    label() {
      return this.user.name
    },
    count() {
      return this.user.id
    }
  }
}
</script>
''',
    },
    # ======================================================================
    # mixed-project (Vue half + package.json; the Java half lives in
    # _gen_java.py under demo/mixed)
    # ======================================================================
    "mixed-project": {
        "package.json": '''{
  "name": "mixed-project-fixture",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "axios": "^0.27.2",
    "moment": "^2.29.4",
    "vue": "^2.7.14",
    "vue-router": "^3.6.5"
  }
}
''',
        "src/main.js": '''import Vue from 'vue'
import App from './App.vue'
import router from './router'

Vue.config.productionTip = false

new Vue({
  router,
  render: (h) => h(App)
}).$mount('#app')
''',
        "src/App.vue": '''<template>
  <div class="app">
    <order-board />
    <router-view />
  </div>
</template>

<script>
import OrderBoard from '@/views/OrderBoard.vue'

export default {
  name: 'App',
  components: { OrderBoard }
}
</script>
''',
        "src/views/OrderBoard.vue": '''<template>
  <div class="order-board">
    <order-row v-for="order in orders" :key="order.id" :order="order" />
    <stale-badge />
  </div>
</template>

<script>
import OrderRow from '@/components/OrderRow.vue'
import StaleBadge from '@/components/StaleBadge.vue'
import { fetchOrders } from '@/api/order'

export default {
  name: 'OrderBoard',
  components: { OrderRow, StaleBadge },
  data() {
    return { orders: [] }
  },
  created() {
    return fetchOrders().then((orders) => {
      this.orders = orders
    })
  }
}
</script>
''',
        "src/components/OrderRow.vue": '''<template>
  <div class="order-row">{{ order.id }}</div>
</template>

<script>
export default {
  name: 'OrderRow',
  props: {
    order: { type: Object, required: true }
  }
}
</script>
''',
        "src/components/StaleBadge.vue": '''<template>
  <span class="stale-badge">{{ text }}</span>
</template>

<script>
export default {
  name: 'StaleBadge',
  props: {
    text: { type: String, default: 'stale' }
  }
}
</script>
''',
        "src/api/order.js": '''import request from '@/utils/request'

export function fetchOrders() {
  return request({
    url: '/orders',
    method: 'get'
  }).then((res) => res.items)
}
''',
        "src/utils/request.js": '''import axios from 'axios'

const request = axios.create({ baseURL: '/api' })

export default request
''',
        "src/router/index.js": '''import Vue from 'vue'
import Router from 'vue-router'
import OrderBoard from '@/views/OrderBoard.vue'

Vue.use(Router)

export default new Router({
  routes: [{ path: '/orders', name: 'orders', component: OrderBoard }]
})
''',
    },
}

__all__ = ["WEB_FIXTURES"]
