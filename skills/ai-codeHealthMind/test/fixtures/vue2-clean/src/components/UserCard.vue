<template>
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
