<template>
  <div class="h-full flex flex-col overflow-y-auto p-[12px] gap-[6px]">
    <div
      v-if="toolLog.length === 0"
      class="flex-1 flex items-center justify-center text-[13px] text-[var(--text-tertiary)]">
      {{ t('No tool activity yet') }}
    </div>
    <div
      v-for="entry in toolLog"
      :key="entry.id"
      class="rounded-[8px] bg-[var(--fill-tsp-white-light)] overflow-hidden">
      <div
        class="flex items-start gap-[8px] px-[10px] py-[8px]"
        :class="hasDetails(entry) ? 'cursor-pointer' : ''"
        role="button"
        :tabindex="hasDetails(entry) ? 0 : -1"
        :aria-expanded="isExpanded(entry.id)"
        @click="hasDetails(entry) && toggle(entry.id)"
        @keydown.enter.prevent="hasDetails(entry) && toggle(entry.id)">
        <span
          class="mt-[3px] h-[8px] w-[8px] shrink-0 rounded-full"
          :class="statusDotClass(entry.status)"
          :title="statusLabel(entry.status)" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-[6px]">
            <span class="truncate text-[13px] font-[500] text-[var(--text-primary)]">{{ entry.name }}</span>
            <span
              class="shrink-0 text-[11px]"
              :class="entry.status === 'error' ? 'text-[var(--function-error)]' : 'text-[var(--text-tertiary)]'">
              {{ statusLabel(entry.status) }}
            </span>
          </div>
          <div v-if="entry.argsSummary" class="truncate text-[12px] text-[var(--text-secondary)]">
            {{ entry.argsSummary }}
          </div>
        </div>
        <ChevronDown
          v-if="hasDetails(entry)"
          class="mt-[2px] shrink-0 text-[var(--icon-tertiary)] transition-transform duration-150"
          :class="{ 'rotate-180': isExpanded(entry.id) }"
          :size="14" />
      </div>

      <div v-if="hasDetails(entry) && isExpanded(entry.id)" class="flex flex-col gap-[8px] px-[10px] pb-[10px]">
        <div v-if="entry.argsText">
          <div class="mb-[4px] text-[11px] font-[500] text-[var(--text-tertiary)]">{{ t('Arguments') }}</div>
          <div class="relative">
            <pre class="rounded-lg bg-[var(--background-gray-main)] p-2.5 pe-9 text-[11px] font-mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-all max-h-[240px] overflow-y-auto">{{ entry.argsText }}</pre>
            <ChatMessageCopyButton :text="entry.argsText" button-class="absolute top-1 end-1" />
          </div>
        </div>
        <div v-if="entry.resultText">
          <div
            class="mb-[4px] text-[11px] font-[500]"
            :class="entry.status === 'error' ? 'text-[var(--function-error)]' : 'text-[var(--text-tertiary)]'">
            {{ entry.status === 'error' ? t('Error') : t('Result') }}
          </div>
          <div class="relative">
            <pre class="rounded-lg bg-[var(--background-gray-main)] p-2.5 pe-9 text-[11px] font-mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-all max-h-[240px] overflow-y-auto">{{ entry.resultText }}</pre>
            <ChatMessageCopyButton :text="entry.resultText" button-class="absolute top-1 end-1" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronDown } from 'lucide-vue-next';
import type { ClawToolLogEntry } from '@/api/claw';
import ChatMessageCopyButton from './ChatMessageCopyButton.vue';

withDefaults(defineProps<{
  toolLog: ClawToolLogEntry[];
}>(), {
  toolLog: () => [],
});

const { t } = useI18n();

const expandedIds = ref<Set<string>>(new Set());

const hasDetails = (entry: ClawToolLogEntry) => !!(entry.argsText || entry.resultText);
const isExpanded = (id: string) => expandedIds.value.has(id);
const toggle = (id: string) => {
  const next = new Set(expandedIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedIds.value = next;
};

const statusLabel = (status: ClawToolLogEntry['status']) => {
  const labels: Record<ClawToolLogEntry['status'], string> = {
    running: t('Running'),
    success: t('Done'),
    error: t('Error'),
  };
  return labels[status];
};

const statusDotClass = (status: ClawToolLogEntry['status']) => {
  if (status === 'running') return 'bg-[var(--function-warning)] animate-pulse';
  if (status === 'error') return 'bg-[var(--function-error)]';
  return 'bg-[var(--function-success)]';
};
</script>
