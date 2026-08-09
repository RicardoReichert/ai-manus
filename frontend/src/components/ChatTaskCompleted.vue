<template>
  <!-- Official TaskCompleted footer (an pill + Copy; Fork / survey skipped) -->
  <div v-if="visible" class="w-full flex flex-col gap-[16px] mt-1">
    <div class="flex items-center flex-wrap gap-[12px]">
      <div
        class="rounded-full text-[var(--function-success)] text-sm w-max max-w-full flex items-center gap-[8px] pe-[8px]">
        <Check :size="16" color="var(--function-success)" class="flex-shrink-0" />
        {{ t('Task completed') }}
      </div>
      <div
        v-if="copyText.trim()"
        class="w-px h-[18px] bg-[var(--border-dark)] flex-shrink-0" />
      <div v-if="copyText.trim()" class="flex items-center gap-[4px]">
        <ChatMessageCopyButton :text="copyText" button-class="size-[28px]" />
      </div>
    </div>
    <!-- TAREFA 5.2 — follow-up suggestions, clickable chips that send as-is -->
    <div v-if="followUps.length > 0" class="flex flex-wrap items-center gap-[8px]">
      <button
        v-for="(suggestion, index) in followUps"
        :key="`${index}-${suggestion}`"
        type="button"
        data-testid="follow-up-chip"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-[var(--fill-tsp-white-main)] hover:bg-[var(--fill-tsp-white-dark)] text-[var(--text-secondary)] transition-colors clickable cursor-pointer"
        @click="emit('followUp', suggestion)">
        {{ suggestion }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { Check } from 'lucide-vue-next';
import ChatMessageCopyButton from './ChatMessageCopyButton.vue';

const props = withDefaults(defineProps<{
  visible: boolean;
  copyText: string;
  followUps?: string[] | null;
}>(), {
  followUps: () => [],
});

const emit = defineEmits<{
  (e: 'followUp', suggestion: string): void;
}>();

const { t } = useI18n();

const followUps = computed(() => (props.followUps ?? []).filter((s) => s.trim().length > 0));
</script>
