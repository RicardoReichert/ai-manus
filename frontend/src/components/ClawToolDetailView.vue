<template>
  <!-- Shell: terminal-styled command + output -->
  <div v-if="kind === 'shell'" class="flex flex-col gap-[8px]">
    <div v-if="command" class="rounded-lg bg-[var(--background-gray-main)] p-2.5 font-mono text-[12px] text-[var(--text-primary)] overflow-x-auto whitespace-pre-wrap break-all">
      <span class="text-[var(--text-blue)]">$</span> {{ command }}
    </div>
    <div v-if="exitCode !== undefined" class="flex items-center gap-[6px]">
      <span class="text-[11px] font-[500] text-[var(--text-tertiary)]">{{ t('Exit code') }}</span>
      <span
        class="rounded-full px-[8px] py-[1px] text-[11px] font-mono"
        :class="exitCode === 0 ? 'bg-[var(--function-success)]/15 text-[var(--function-success)]' : 'bg-[var(--function-error)]/15 text-[var(--function-error)]'">
        {{ exitCode }}
      </span>
    </div>
    <div v-if="outputText" class="relative">
      <div class="mb-[4px] text-[11px] font-[500] text-[var(--text-tertiary)]">{{ t('Output') }}</div>
      <pre class="rounded-lg bg-[var(--background-gray-main)] p-2.5 pe-9 text-[11px] font-mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-all max-h-[240px] overflow-y-auto">{{ outputText }}</pre>
      <ChatMessageCopyButton :text="outputText" button-class="absolute top-[26px] end-1" />
    </div>
    <ClawValueView v-else-if="!isPlainOutput" :value="result" />
  </div>

  <!-- File: filename header + content preview -->
  <div v-else-if="kind === 'file'" class="flex flex-col gap-[8px]">
    <div v-if="filePath" class="flex items-center gap-[6px] rounded-lg bg-[var(--background-gray-main)] px-2.5 py-1.5">
      <EditIcon :size="14" class="shrink-0 text-[var(--icon-tertiary)]" />
      <span class="truncate font-mono text-[12px] text-[var(--text-primary)]" :title="filePath">{{ filePath }}</span>
    </div>
    <div v-if="outputText" class="relative">
      <pre class="rounded-lg bg-[var(--background-gray-main)] p-2.5 pe-9 text-[11px] font-mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-all max-h-[280px] overflow-y-auto">{{ outputText }}</pre>
      <ChatMessageCopyButton :text="outputText" button-class="absolute top-1 end-1" />
    </div>
    <ClawValueView v-else-if="!isPlainOutput" :value="result" />
  </div>

  <!-- Browser: URL chip + result -->
  <div v-else-if="kind === 'browser'" class="flex flex-col gap-[8px]">
    <div v-if="url" class="flex items-center gap-[6px] rounded-full bg-[var(--background-gray-main)] px-2.5 py-1 w-fit max-w-full">
      <BrowserIcon :size="14" class="shrink-0 text-[var(--icon-tertiary)]" />
      <span class="truncate text-[12px] text-[var(--text-blue)]" :title="url">{{ url }}</span>
    </div>
    <ClawValueView v-if="result !== undefined" :value="result" />
  </div>

  <!-- Search: query highlight + results -->
  <div v-else-if="kind === 'search'" class="flex flex-col gap-[8px]">
    <div v-if="query" class="flex items-center gap-[6px] rounded-lg bg-[var(--background-gray-main)] px-2.5 py-1.5">
      <SearchIcon :size="14" class="shrink-0 text-[var(--icon-tertiary)]" />
      <span class="truncate font-mono text-[12px] text-[var(--text-primary)]">{{ query }}</span>
    </div>
    <ClawValueView v-if="result !== undefined" :value="result" />
  </div>

  <!-- Generic fallback: structured key/value view for both args and result -->
  <div v-else class="flex flex-col gap-[8px]">
    <div v-if="args && Object.keys(args).length > 0">
      <div class="mb-[4px] text-[11px] font-[500] text-[var(--text-tertiary)]">{{ t('Arguments') }}</div>
      <div class="rounded-lg bg-[var(--background-gray-main)] p-2.5">
        <ClawValueView :value="args" />
      </div>
    </div>
    <div v-if="result !== undefined">
      <div
        class="mb-[4px] text-[11px] font-[500]"
        :class="isError ? 'text-[var(--function-error)]' : 'text-[var(--text-tertiary)]'">
        {{ isError ? t('Error') : t('Result') }}
      </div>
      <div class="rounded-lg bg-[var(--background-gray-main)] p-2.5">
        <ClawValueView :value="result" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import EditIcon from './icons/EditIcon.vue';
import BrowserIcon from './icons/BrowserIcon.vue';
import SearchIcon from './icons/SearchIcon.vue';
import ClawValueView from './ClawValueView.vue';
import ChatMessageCopyButton from './ChatMessageCopyButton.vue';
import { resolveClawToolKind, firstArg, stripHomePrefix } from '@/constants/clawTool';

const props = defineProps<{
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  isError?: boolean;
}>();

const { t } = useI18n();

const kind = computed(() => resolveClawToolKind(props.name));

const isPlainOutput = computed(() => typeof props.result === 'string' || props.result === undefined);
const outputText = computed(() => (typeof props.result === 'string' ? props.result : undefined));

// Shell
const command = computed(() => firstArg(props.args, ['command', 'cmd', 'shell']));
const exitCode = computed(() => {
  const r = props.result;
  if (r && typeof r === 'object' && !Array.isArray(r)) {
    const v = (r as Record<string, unknown>).exit_code ?? (r as Record<string, unknown>).exitCode ?? (r as Record<string, unknown>).code;
    if (typeof v === 'number') return v;
  }
  return undefined;
});

// File
const filePath = computed(() => {
  const raw = firstArg(props.args, ['path', 'file', 'filename', 'file_path']);
  return raw ? stripHomePrefix(raw) : undefined;
});

// Browser
const url = computed(() => firstArg(props.args, ['url']));

// Search
const query = computed(() => firstArg(props.args, ['query', 'pattern', 'q']));
</script>
