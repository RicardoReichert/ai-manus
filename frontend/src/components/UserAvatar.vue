<template>
  <div
    class="relative flex items-center justify-center font-bold flex-shrink-0 rounded-full overflow-hidden"
    :style="circleStyle"
  >
    <img
      v-if="avatarUrl && !imageFailed"
      :src="avatarUrl"
      :alt="fallbackLetter"
      class="w-full h-full object-cover"
      @error="imageFailed = true"
    >
    <template v-else>{{ fallbackLetter }}</template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

const props = defineProps<{
  avatarUrl?: string | null;
  fallbackLetter: string;
  size: number;
}>();

// Reset the failed-image fallback whenever the URL itself changes (e.g. the
// user uploads a new photo after a previous one 404'd for some reason).
const imageFailed = ref(false);
watch(() => props.avatarUrl, () => { imageFailed.value = false; });

const circleStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.round(props.size / 2)}px`,
  color: 'rgba(255, 255, 255, 0.9)',
  backgroundColor: 'rgb(59, 130, 246)',
}));
</script>
