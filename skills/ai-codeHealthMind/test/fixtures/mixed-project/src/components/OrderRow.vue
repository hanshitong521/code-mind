<template>
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
