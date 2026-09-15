<template>
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
