<template>
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
