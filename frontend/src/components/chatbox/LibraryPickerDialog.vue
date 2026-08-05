<template>
  <div v-if="visible" class="absolute z-[1000] pointer-events-auto">
    <div
      class="w-full h-full bg-black/60 backdrop-blur-[4px] fixed inset-0"
      @click="emit('close')"
    />
    <div
      role="dialog"
      class="shadow-menu pointer-events-auto fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 max-w-[95%] max-h-[95%] overflow-hidden w-[520px] h-[440px] flex flex-col rounded-[20px] bg-[var(--background-menu-white)]"
      @keydown.escape.stop="emit('close')">
      <h3 class="flex items-center gap-3 border-b border-b-[var(--border-main)] pt-5 pe-3 pb-[18px] ps-5 shrink-0">
        <LibraryBig :size="18" class="shrink-0" stroke="var(--icon-secondary)" />
        <span class="flex-1 text-[16px] font-medium text-[var(--text-primary)]">{{ t('Add from Library') }}</span>
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)]"
          @click="emit('close')">
          <X class="size-5 text-[var(--icon-tertiary)]" />
        </button>
      </h3>

      <div class="flex-1 min-h-0 overflow-y-auto py-2">
        <div v-if="loading" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('Loading...') }}
        </div>
        <div v-else-if="files.length === 0" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('No files in library') }}
        </div>
        <button
          v-for="file in files"
          :key="`${file.session_id}-${file.file_id}`"
          type="button"
          class="mx-2 flex w-[calc(100%-16px)] items-center gap-3 rounded-lg px-3 py-2 text-start clickable cursor-pointer hover:bg-[var(--fill-tsp-white-light)]"
          @click="selectFile(file)">
          <component :is="getFileType(file.filename || '').icon" class="shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm text-[var(--text-primary)]">{{ file.filename || t('Untitled') }}</div>
            <div class="truncate text-xs text-[var(--text-tertiary)]">{{ file.session_title || t('Untitled task') }}</div>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, LibraryBig } from 'lucide-vue-next'
import { getLibraryFiles } from '../../api/project'
import { getFileType } from '../../utils/fileType'
import type { LibraryFileItem } from '../../types/response'
import type { FileInfo } from '../../api/file'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', file: FileInfo): void
}>()

const { t } = useI18n()
const files = ref<LibraryFileItem[]>([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await getLibraryFiles()
    files.value = res.files.filter((f) => !!f.file_id)
  } catch (e) {
    console.error('Failed to load library files', e)
    files.value = []
  } finally {
    loading.value = false
  }
}

const selectFile = (file: LibraryFileItem) => {
  if (!file.file_id) return
  emit('select', {
    file_id: file.file_id,
    filename: file.filename || file.file_path || t('Untitled'),
    content_type: file.content_type || undefined,
    size: file.size ?? undefined,
    upload_date: file.upload_date || '',
  })
}

watch(
  () => props.visible,
  (v) => {
    if (v) load()
  },
)
</script>
