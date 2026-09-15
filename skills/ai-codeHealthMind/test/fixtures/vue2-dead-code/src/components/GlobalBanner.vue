<template>
  <div class="global-banner">{{ text }}</div>
</template>

<script>
export default {
  name: 'GlobalBanner',
  props: {
    text: { type: String, default: 'notice' }
  }
}
</script>
