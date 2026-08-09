<template>
  <div class="flex-1 min-h-0 flex flex-col overflow-auto h-full px-4 py-3">
    <div class="py-3 pt-0">
      <div class="text-[var(--text-primary)] text-sm font-medium mb-2">
        {{ t('Tool') }}: {{ toolContent.function }}
      </div>

      <div v-if="toolContent.args && Object.keys(toolContent.args).length > 0" class="mb-4">
        <div class="text-[var(--text-primary)] text-sm font-medium mb-2">{{ t('Arguments') }}:</div>
        <div class="relative">
          <pre class="bg-[var(--fill-tsp-gray-main)] rounded-lg p-3 pe-9 text-xs text-[var(--text-secondary)] overflow-x-auto"><code>{{ argsJson }}</code></pre>
          <ChatMessageCopyButton :text="argsJson" button-class="absolute top-1 end-1" />
        </div>
      </div>

      <div v-if="toolContent.content?.result" class="mb-4">
        <div class="text-[var(--text-primary)] text-sm font-medium mb-2">{{ t('Result') }}:</div>
        <div class="relative">
          <div class="bg-[var(--fill-tsp-gray-main)] rounded-lg p-3 pe-9 text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
            {{ toolContent.content.result }}
          </div>
          <ChatMessageCopyButton :text="String(toolContent.content.result)" button-class="absolute top-1 end-1" />
        </div>
      </div>

      <div v-else class="text-[var(--text-tertiary)] text-sm">
        {{ toolContent.status === 'calling' ? t('Tool is executing...') : t('Waiting for result...') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ToolContent } from '@/types/message';
import ChatMessageCopyButton from '@/components/ChatMessageCopyButton.vue';

const { t } = useI18n()

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

const argsJson = computed(() => JSON.stringify(props.toolContent.args, null, 2));
</script>
