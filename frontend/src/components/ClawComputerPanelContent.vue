<template>
  <!-- Trimmed adaptation of ComputerPanelContent.vue: header + live VNC view only -->
  <div
    class="h-full flex flex-col bg-[var(--background-gray-main)]"
    :class="shellClass">
    <div class="flex h-[56px] items-center gap-[8px] border-b border-[var(--border-main)] px-[16px] py-[12px]">
      <div class="flex min-w-0 flex-1 flex-col justify-center">
        <h2 class="truncate text-[14px] font-[500] text-[var(--text-primary)]">
          {{ $t("{name}'s screen", { name: 'Manus Claw' }) }}
        </h2>
      </div>

      <div class="flex shrink-0 items-center gap-[2px] rounded-[8px] bg-[var(--fill-tsp-white-light)] p-[2px]">
        <button
          type="button"
          class="h-6 rounded-[6px] px-[10px] text-[12px] font-[500] transition-colors"
          :class="viewMode === 'screen'
            ? 'bg-[var(--background-gray-main)] text-[var(--text-primary)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'"
          @click="viewMode = 'screen'">
          {{ t('Screen') }}
        </button>
        <button
          type="button"
          class="h-6 rounded-[6px] px-[10px] text-[12px] font-[500] transition-colors"
          :class="viewMode === 'terminal'
            ? 'bg-[var(--background-gray-main)] text-[var(--text-primary)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'"
          @click="viewMode = 'terminal'">
          {{ t('Terminal') }}
        </button>
      </div>

      <div class="flex shrink-0 items-center gap-[4px]">
        <div
          v-if="!isMobile"
          role="button"
          tabindex="0"
          class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)] !size-[32px] !rounded-[8px]"
          :title="presentation === 'dialog' ? t('Side view') : t('Center view')"
          @click="emit('toggle-presentation')"
          @keydown.enter.prevent="emit('toggle-presentation')">
          <SideViewIcon
            v-if="presentation === 'dialog'"
            :size="18"
            color="var(--icon-secondary)"
            class="!size-[18px] text-[var(--icon-secondary)]" />
          <CenterViewIcon
            v-else
            :size="18"
            color="var(--icon-secondary)"
            class="!size-[18px] text-[var(--icon-secondary)]" />
        </div>

        <div
          role="button"
          tabindex="0"
          class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)] !size-[32px] !rounded-[8px]"
          :title="t('Close')"
          @click="hide"
          @keydown.enter.prevent="hide">
          <X :size="18" class="!size-[18px] text-[var(--icon-secondary)]" />
        </div>
      </div>
    </div>

    <div class="flex-1 min-h-0">
      <VNCViewer
        v-if="sessionId && viewMode === 'screen'"
        :sessionId="sessionId"
        :enabled="true"
        :urlResolver="getClawVncUrl" />
      <ClawTerminalView
        v-else-if="sessionId && viewMode === 'terminal'"
        :sessionId="sessionId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import { useI18n } from 'vue-i18n';
import { X } from 'lucide-vue-next';
import VNCViewer from './VNCViewer.vue';
import ClawTerminalView from './ClawTerminalView.vue';
import { getClawVncUrl } from '@/api/claw';
import CenterViewIcon from './icons/CenterViewIcon.vue';
import SideViewIcon from './icons/SideViewIcon.vue';

const props = withDefaults(defineProps<{
  sessionId?: string;
  presentation?: 'sidebar' | 'dialog';
}>(), {
  presentation: 'sidebar',
});

const { t } = useI18n();
const isMobile = useMediaQuery('(max-width: 767px)');
const viewMode = ref<'screen' | 'terminal'>('screen');

const shellClass = computed(() => {
  if (props.presentation === 'dialog') {
    return 'rounded-[12px] border border-[var(--border-main)] bg-[var(--background-gray-main)] shadow-[0_24px_24px_-12px_var(--shadow-S),_0_0_0_1px_var(--shadow-M),_0_1px_1px_-0.5px_var(--shadow-M),_0_3px_3px_-1.5px_var(--shadow-M),_0_6px_6px_-3px_var(--shadow-M),_0_12px_12px_-6px_var(--shadow-S),_0_48px_48px_-24px_var(--shadow-XS),_0_10px_20px_1px_var(--shadow-S)]';
  }
  return isMobile.value ? 'border-none' : 'border-l border-[var(--border-main)]';
});

const emit = defineEmits<{
  (e: 'hide'): void;
  (e: 'toggle-presentation'): void;
}>();

const hide = () => emit('hide');
</script>
