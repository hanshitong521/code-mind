<template>
  <span class="stale-badge">{{ text }}</span>
</template>

<script>
export default {
  name: 'StaleBadge',
  props: {
    text: { type: String, default: 'stale' }
  }
}
</script>
