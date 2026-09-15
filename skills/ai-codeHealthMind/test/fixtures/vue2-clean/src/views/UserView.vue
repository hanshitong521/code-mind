<template>
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
