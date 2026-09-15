<template>
  <p v-if="tool.name === 'message' && tool.args?.text" class="text-[var(--text-secondary)] text-[14px] overflow-hidden text-ellipsis whitespace-pre-line">
    {{ tool.args.text }}
  </p>
  <!-- Official StandardToolUsed: flat icon+label row (not gray pill) -->
  <div v-else-if="toolInfo" class="flex w-full flex-col">
    <div
      class="flex w-full items-center gap-2 group"
      :class="isCalling ? '' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'">
      <div
        class="flex min-w-0 flex-1 items-center gap-[4px] overflow-hidden leading-[20px] clickable"
        @click="handleClick">
        <div class="w-[20px] inline-flex items-center flex-shrink-0 text-[var(--text-primary)]">
          <component :is="toolInfo.icon" :size="20" />
        </div>
        <div
          class="min-w-0 flex-1 truncate whitespace-nowrap"
          :class="isCalling ? 'shimmer-text-secondary' : ''"
          :title="`${toolInfo.function}${toolInfo.functionArg}`">
          <span class="text-sm">{{ toolInfo.function }}</span>
          <span
            v-if="toolInfo.functionArg"
            class="ms-[6px] font-mono text-[12px]"
            :class="isCalling ? '' : 'text-[var(--text-tertiary)]'">{{ toolInfo.functionArg }}</span>
        </div>
      </div>
      <button
        v-if="hasArgs"
        type="button"
        class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[var(--icon-tertiary)] hover:bg-[var(--fill-tsp-white-light)] hover:text-[var(--text-primary)]"
        :aria-expanded="isArgsExpanded"
        :title="isArgsExpanded ? t('Collapse') : t('Expand')"
        @click.stop="isArgsExpanded = !isArgsExpanded">
        <ChevronDown class="transition-transform duration-150" :class="{ 'rotate-180': isArgsExpanded }" :size="14" />
      </button>
      <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
        {{ relativeTime(tool.timestamp) }}
      </div>
    </div>
    <div v-if="hasArgs && isArgsExpanded" class="ms-[26px] mt-1 relative">
      <pre class="rounded-lg bg-[var(--fill-tsp-white-light)] p-2.5 pe-9 text-[11px] font-mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-all">{{ argsJson }}</pre>
      <ChatMessageCopyButton :text="argsJson" button-class="absolute top-1 end-1" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ChevronDown } from "lucide-vue-next";
import { ToolContent } from "../types/message";
import { useToolInfo } from "../composables/useTool";
import { useRelativeTime } from "../composables/useTime";
import ChatMessageCopyButton from "./ChatMessageCopyButton.vue";

const props = defineProps<{
  tool: ToolContent;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const { t } = useI18n();
const { relativeTime } = useRelativeTime();
const { toolInfo } = useToolInfo(ref(props.tool));

const isCalling = computed(() => props.tool.status === "calling");
const isArgsExpanded = ref(false);

const hasArgs = computed(() => !!props.tool.args && Object.keys(props.tool.args).length > 0);
const argsJson = computed(() => JSON.stringify(props.tool.args ?? {}, null, 2));

const handleClick = () => {
  emit("click");
};
</script>
