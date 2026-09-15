<template>
  <div class="dynamic-host">
    <component :is="current" />
  </div>
</template>

<script>
import AlphaPanel from '@/components/AlphaPanel.vue'
import BetaPanel from '@/components/BetaPanel.vue'

export default {
  name: 'DynamicHost',
  components: { AlphaPanel, BetaPanel },
  data() {
    return { current: 'AlphaPanel' }
  }
}
</script>
