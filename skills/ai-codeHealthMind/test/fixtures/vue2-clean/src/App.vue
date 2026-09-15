<template>
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
