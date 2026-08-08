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
        <div class="mt-[1px] flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-[6px] bg-[var(--fill-tsp-white-main)]">
          <component :is="toolIcon(entry.name)" :size="12" class="text-[var(--icon-tertiary)]" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-[6px]">
            <span class="truncate text-[13px] font-[500] text-[var(--text-primary)]">{{ entry.name }}</span>
            <span
              class="shrink-0 inline-flex items-center gap-[3px] text-[11px]"
              :class="entry.status === 'error' ? 'text-[var(--function-error)]' : 'text-[var(--text-tertiary)]'">
              <span
                class="h-[6px] w-[6px] rounded-full"
                :class="statusDotClass(entry.status)" />
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
        <div v-if="entry.truncated" class="text-[11px] text-[var(--text-tertiary)] italic">
          {{ t('Output truncated') }}
        </div>
        <ClawToolDetailView
          :name="entry.name"
          :args="entry.args"
          :result="entry.result"
          :is-error="entry.status === 'error'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronDown } from 'lucide-vue-next';
import { type ClawToolLogEntry } from '@/api/claw';
import { resolveClawToolKind, CLAW_TOOL_ICON_MAP } from '@/constants/clawTool';
import ClawToolDetailView from './ClawToolDetailView.vue';

withDefaults(defineProps<{
  toolLog: ClawToolLogEntry[];
}>(), {
  toolLog: () => [],
});

const { t } = useI18n();

const expandedIds = ref<Set<string>>(new Set());

const hasResult = (entry: ClawToolLogEntry) => entry.result !== undefined && entry.result !== '';
const hasArgs = (entry: ClawToolLogEntry) => !!entry.args && Object.keys(entry.args).length > 0;
const hasDetails = (entry: ClawToolLogEntry) => hasArgs(entry) || hasResult(entry);
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

const toolIcon = (name: string) => CLAW_TOOL_ICON_MAP[resolveClawToolKind(name)];

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
