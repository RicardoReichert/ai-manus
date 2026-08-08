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
      class="flex items-start gap-[8px] rounded-[8px] bg-[var(--fill-tsp-white-light)] px-[10px] py-[8px]">
      <span
        class="mt-[3px] h-[8px] w-[8px] shrink-0 rounded-full"
        :class="statusDotClass(entry.status)"
        :title="statusLabel(entry.status)" />
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-[6px]">
          <span class="truncate text-[13px] font-[500] text-[var(--text-primary)]">{{ entry.name }}</span>
          <span class="shrink-0 text-[11px] text-[var(--text-tertiary)]">{{ statusLabel(entry.status) }}</span>
        </div>
        <div v-if="entry.argsSummary" class="truncate text-[12px] text-[var(--text-secondary)]">
          {{ entry.argsSummary }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { ClawToolLogEntry } from '@/api/claw';

withDefaults(defineProps<{
  toolLog: ClawToolLogEntry[];
}>(), {
  toolLog: () => [],
});

const { t } = useI18n();

const statusLabel = (status: ClawToolLogEntry['status']) => {
  const labels: Record<ClawToolLogEntry['status'], string> = {
    running: t('Running'),
    success: t('Done'),
    error: t('Error'),
  };
  return labels[status];
};

const statusDotClass = (status: ClawToolLogEntry['status']) => {
  if (status === 'running') return 'bg-yellow-500 animate-pulse';
  if (status === 'error') return 'bg-red-500';
  return 'bg-green-500';
};
</script>
