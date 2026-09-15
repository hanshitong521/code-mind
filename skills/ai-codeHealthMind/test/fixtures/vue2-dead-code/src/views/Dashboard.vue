<template>
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
