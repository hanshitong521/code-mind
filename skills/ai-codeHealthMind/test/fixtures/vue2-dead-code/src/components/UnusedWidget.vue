<template>
  <div class="unused-widget">{{ label }}</div>
</template>

<script>
export default {
  name: 'UnusedWidget',
  props: {
    label: { type: String, default: 'widget' }
  }
}
</script>
