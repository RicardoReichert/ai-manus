<template>
  <div class="flex items-center justify-between h-[26px] group">
    <div class="flex items-center gap-[8px] -ms-[2px] max-w-full">
      <component v-if="assistantIcon" :is="assistantIcon" :size="24" class="w-6 h-6" />
      <Bot v-else :size="24" class="w-6 h-6" />
      <span v-if="assistantName" class="text-base text-[var(--text-primary)] tracking-tight leading-none">{{ assistantName }}</span>
      <template v-else-if="!assistantIcon">
        <ManusTextIcon />
      </template>
      <span
        v-if="showLiteBadge"
        class="text-[var(--text-tertiary)] text-xs flex h-5 py-0.5 px-1.5 items-center gap-1 rounded-[6px] border border-[var(--border-dark)] flex-shrink-0 ml-[3px]">
        Lite
      </span>
      <span
        v-if="modelName"
        class="text-[var(--text-tertiary)] text-xs flex h-5 py-0.5 px-1.5 items-center gap-1 rounded-[6px] bg-[var(--fill-tsp-white-dark)] flex-shrink-0 ml-[3px] truncate max-w-[160px]"
        :title="modelName">
        {{ modelName }}
      </span>
    </div>
    <div class="flex items-center gap-[2px] invisible group-hover:visible">
      <div class="float-right transition text-[12px] text-[var(--text-tertiary)]">
        {{ relativeTime(timestamp) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue';
import { Bot } from 'lucide-vue-next';
import ManusTextIcon from './icons/ManusTextIcon.vue';
import { useRelativeTime } from '../composables/useTime';

defineProps<{
  assistantIcon?: Component;
  assistantName?: string;
  showLiteBadge?: boolean;
  /**
   * The session's currently selected model, shown as a chip next to the Lite
   * badge. This is an approximation: it reflects the model selected now, not
   * necessarily the one that produced this particular historical message —
   * per-message model attribution isn't tracked.
   */
  modelName?: string;
  timestamp: number;
}>();

const { relativeTime } = useRelativeTime();
</script>
