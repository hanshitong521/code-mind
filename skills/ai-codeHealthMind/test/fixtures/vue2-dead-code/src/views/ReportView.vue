<template>
  <div class="report-view">{{ formatted }}</div>
</template>

<script>
import { formatDate } from '@/utils/format'

export default {
  name: 'ReportView',
  data() {
    return { created: '2026-01-01' }
  },
  computed: {
    formatted() {
      return formatDate(this.created)
    }
  }
}
</script>
