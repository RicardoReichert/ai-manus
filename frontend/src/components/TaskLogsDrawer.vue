<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 overflow-hidden flex justify-end bg-black/40 backdrop-blur-xs transition-opacity"
    @click.self="emit('close')"
    @keydown.esc="emit('close')"
  >
    <div
      role="dialog"
      aria-modal="true"
      :aria-label="t('Task Execution Logs')"
      class="w-full max-w-md bg-[var(--background-menu-white)] h-full shadow-2xl border-l border-[var(--border-main)] flex flex-col transform transition-transform duration-200 ease-in-out"
    >
      <!-- Drawer Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-[var(--border-main)]">
        <div class="flex items-center gap-2">
          <FileText class="size-5 text-[var(--icon-primary)]" />
          <h2 class="text-base font-semibold text-[var(--text-primary)]">
            {{ t('Task Execution Logs') }}
          </h2>
        </div>
        <button
          ref="closeButtonRef"
          type="button"
          @click="emit('close')"
          class="p-1.5 rounded-lg hover:bg-[var(--fill-tsp-white-main)] text-[var(--icon-secondary)] transition-colors"
          :title="t('Close')"
        >
          <X class="size-5" />
        </button>
      </div>

      <!-- Drawer Content -->
      <div class="flex-1 overflow-y-auto p-5 space-y-6 text-sm">
        <!-- Active Model & Session Context -->
        <div class="bg-[var(--fill-tsp-white-dark)] rounded-xl p-4 border border-[var(--border-light)] space-y-2">
          <div class="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
            {{ t('Model & Execution Environment') }}
          </div>
          <div class="flex items-center justify-between">
            <span class="text-[var(--text-secondary)]">{{ t('Active Model') }}</span>
            <span class="font-medium text-[var(--text-primary)] flex items-center gap-1.5">
              {{ activeModelName || '—' }}
              <span
                v-if="isLocalModel"
                class="px-1.5 py-0.5 text-[10px] font-semibold bg-blue-500/10 text-blue-500 rounded border border-blue-500/20"
              >
                {{ t('Local') }}
              </span>
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-[var(--text-secondary)]">{{ t('Task Mode') }}</span>
            <span class="font-medium text-[var(--text-primary)] capitalize">{{ taskMode }}</span>
          </div>
        </div>

        <!-- System Execution Log Stream -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
              {{ t('Execution Timeline') }}
            </span>
          </div>

          <div class="bg-black/90 text-gray-200 font-mono text-xs p-3.5 rounded-xl max-h-72 overflow-y-auto space-y-2 border border-white/10">
            <div v-if="!props.logs.length" class="text-gray-500 italic py-2 text-center">
              {{ t('No execution logs recorded yet.') }}
            </div>
            <div v-for="entry in props.logs" :key="entry.id" class="flex flex-col gap-0.5 border-b border-white/5 pb-1.5 last:border-0 last:pb-0">
              <div class="flex items-center justify-between text-[10px] text-gray-400">
                <span class="text-blue-400 font-semibold">[{{ entry.kind.toUpperCase() }}]</span>
                <span>{{ formatTimestamp(entry.timestamp) }}</span>
              </div>
              <div class="text-gray-200 break-words">
                {{ entry.label }}
                <span v-if="entry.detail" class="text-gray-400">— {{ truncate(entry.detail) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Task Modified Files -->
        <div class="space-y-3">
          <div class="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
            {{ t('Workspace Files') }}
          </div>
          <div v-if="filesLoading" class="text-xs text-[var(--text-tertiary)] italic">
            {{ t('Loading files…') }}
          </div>
          <div v-else-if="!files.length" class="text-xs text-[var(--text-tertiary)] italic">
            {{ t('No files generated in this task.') }}
          </div>
          <div v-else class="space-y-1.5">
            <div
              v-for="file in files"
              :key="file.file_id"
              class="flex items-center gap-2.5 p-2.5 rounded-lg bg-[var(--fill-tsp-white-main)] border border-[var(--border-light)] text-xs text-[var(--text-primary)]"
            >
              <FileText class="size-4 text-[var(--icon-secondary)] shrink-0" />
              <span class="truncate flex-1 font-mono">{{ file.filename }}</span>
              <span class="text-[var(--text-tertiary)] shrink-0">{{ formatFileSize(file.size) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, X } from 'lucide-vue-next'
import type { TaskLogEntry } from '../types/taskLog'
import type { FileInfo } from '../api/file'
import { getSessionFiles } from '../api/agent'
import { formatFileSize } from '../utils/fileType'
import { useActiveModel } from '../composables/useActiveModel'

const props = withDefaults(
  defineProps<{
    open: boolean
    sessionId?: string
    taskMode?: string
    logs?: TaskLogEntry[]
  }>(),
  {
    logs: () => [],
  }
)

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t } = useI18n()
const { activeModelName, isLocalModel } = useActiveModel()

const closeButtonRef = ref<HTMLButtonElement | null>(null)
const files = ref<FileInfo[]>([])
const filesLoading = ref(false)

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    await nextTick()
    closeButtonRef.value?.focus()
    if (!props.sessionId) return
    filesLoading.value = true
    try {
      files.value = await getSessionFiles(props.sessionId)
    } catch (e) {
      console.warn('Failed to load session files:', e)
      files.value = []
    } finally {
      filesLoading.value = false
    }
  }
)

const formatTimestamp = (ts: number) => {
  const ms = ts > 1e12 ? ts : ts * 1000
  return new Date(ms).toLocaleTimeString()
}

const truncate = (text: string, max = 160) =>
  text.length > max ? `${text.slice(0, max)}…` : text
</script>
