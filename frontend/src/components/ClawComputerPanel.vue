<template>
  <!-- Trimmed adaptation of ComputerPanel.vue: live-only VNC view, no tool-history timeline -->
  <div
    ref="computerPanelRef"
    v-if="presentation === 'sidebar'"
    :class="{
      'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:min-w-[520px]': isShow,
      'h-full overflow-hidden': !isShow
    }"
    :style="{ width: isShow ? `${sideWidth}px` : '0px', opacity: isShow ? '1' : '0', transition: '0.2s ease-in-out' }">
    <div class="h-full" :style="{ width: isShow ? '100%' : '0px' }">
      <ClawComputerPanelContent
        v-if="isShow"
        presentation="sidebar"
        :sessionId="sessionId"
        @hide="hidePanel"
        @toggle-presentation="togglePresentation"
      />
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="isShow && presentation === 'dialog'"
      class="fixed inset-0 w-full z-[1100] flex items-center justify-center py-[12px] bg-[var(--background-mask-black)] backdrop-blur-[12px]"
      @click.self="hidePanel">
      <div
        class="!w-[900px] max-w-[95%] max-h-[1200px] h-full z-10"
        @click.stop>
        <ClawComputerPanelContent
          presentation="dialog"
          :sessionId="sessionId"
          @hide="hidePanel"
          @toggle-presentation="togglePresentation"
        />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ClawComputerPanelContent from './ClawComputerPanelContent.vue'
import { useResizeObserver } from '../composables/useResizeObserver'

export type ComputerPresentation = 'sidebar' | 'dialog'

const computerPanelRef = ref<HTMLElement>()
const { size: parentSize } = useResizeObserver(computerPanelRef, {
  target: 'parent',
  property: 'width'
})

const isShow = ref(false)
const presentation = ref<ComputerPresentation>('sidebar')

const sideWidth = computed(() => {
  const p = parentSize.value || 520
  return Math.min(Math.max(p / 2, Math.min(520, p)), p)
})

defineProps<{
  sessionId?: string
}>()

const showPanel = () => {
  isShow.value = true
}

const hidePanel = () => {
  isShow.value = false
  presentation.value = 'sidebar'
}

const togglePresentation = () => {
  presentation.value = presentation.value === 'sidebar' ? 'dialog' : 'sidebar'
}

defineExpose({
  showPanel,
  hidePanel,
  isShow
})
</script>
