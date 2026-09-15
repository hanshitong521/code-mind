<template>
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
