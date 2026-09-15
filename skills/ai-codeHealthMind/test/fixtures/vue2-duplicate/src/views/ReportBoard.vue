<template>
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
