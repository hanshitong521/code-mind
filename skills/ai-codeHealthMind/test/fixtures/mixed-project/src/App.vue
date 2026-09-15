<template>
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
