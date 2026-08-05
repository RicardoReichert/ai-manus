<template>
  <div class="flex size-full min-h-0 min-w-0 flex-1 flex-col bg-[var(--background-gray-main)]">
    <div class="flex h-[56px] w-full shrink-0 items-center justify-between py-[12px] ps-[14px] pe-[20px] md:px-[24px] gap-[8px]">
      <div class="flex-1 text-lg font-[500] leading-[28px] text-[var(--text-primary)]">
        {{ t('Data Controls') }}
      </div>
    </div>

    <div class="w-full flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-[720px] mx-auto w-full px-5 md:px-6 pb-10">
        <!-- Tabs -->
        <div class="flex flex-wrap gap-[8px] pb-[16px] sticky top-0 z-[3] bg-[var(--background-gray-main)] pt-2">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            class="clickable h-8 px-3 rounded-full text-[13px] font-medium border transition-colors"
            :class="activeTab === tab.key
              ? 'border-[var(--Button-border-secondary)] bg-[var(--fill-blue)] text-[var(--text-blue)]'
              : 'border-[var(--Button-border-secondary)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-main)]'"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- Shared / Archived: real session lists -->
        <template v-if="activeTab === 'shared' || activeTab === 'archived'">
          <div v-if="loading" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
            {{ t('Loading...') }}
          </div>
          <div v-else-if="sessions.length === 0" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
            {{ activeTab === 'shared' ? t('No shared tasks') : t('No archived tasks') }}
          </div>
          <div v-else class="flex flex-col gap-1">
            <div
              v-for="session in sessions"
              :key="session.session_id"
              class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[var(--fill-tsp-white-light)] group"
            >
              <FileText :size="18" class="shrink-0 text-[var(--icon-tertiary)]" />
              <button
                type="button"
                class="min-w-0 flex-1 text-start clickable cursor-pointer"
                @click="openSession(session.session_id)"
              >
                <div class="truncate text-sm text-[var(--text-primary)]">{{ session.title || t('Untitled task') }}</div>
                <div v-if="session.latest_message_at" class="truncate text-xs text-[var(--text-tertiary)]">
                  {{ formatCustomTime(session.latest_message_at, t, locale) }}
                </div>
              </button>
              <button
                v-if="activeTab === 'shared'"
                type="button"
                class="shrink-0 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-md px-2 py-1 hover:bg-[var(--fill-tsp-white-main)] opacity-0 group-hover:opacity-100"
                @click="handleUnshare(session.session_id)"
              >
                {{ t('Unshare') }}
              </button>
              <button
                v-else
                type="button"
                class="shrink-0 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-md px-2 py-1 hover:bg-[var(--fill-tsp-white-main)] opacity-0 group-hover:opacity-100"
                @click="handleUnarchive(session.session_id)"
              >
                {{ t('Restore') }}
              </button>
            </div>
          </div>
        </template>

        <!-- Sites / Apps / Domains: no supporting infra yet -->
        <div v-else class="py-16 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('Not available yet') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { FileText } from 'lucide-vue-next'
import { getSessions, unshareSession, unarchiveSession } from '../api/agent'
import type { ListSessionItem } from '../types/response'
import { formatCustomTime } from '../utils/time'
import { showSuccessToast, showErrorToast } from '../utils/toast'

type TabKey = 'shared' | 'archived' | 'sites' | 'apps' | 'domains'

const { t, locale } = useI18n()
const router = useRouter()

const tabs = computed(() => [
  { key: 'shared' as TabKey, label: t('Shared') },
  { key: 'archived' as TabKey, label: t('Archived') },
  { key: 'sites' as TabKey, label: t('Sites') },
  { key: 'apps' as TabKey, label: t('Apps') },
  { key: 'domains' as TabKey, label: t('Purchased domains') },
])

const activeTab = ref<TabKey>('shared')
const sessions = ref<ListSessionItem[]>([])
const loading = ref(false)

const load = async () => {
  if (activeTab.value !== 'shared' && activeTab.value !== 'archived') return
  loading.value = true
  try {
    const filters = activeTab.value === 'shared'
      ? { shared: true }
      : { archived: true }
    const res = await getSessions(filters)
    sessions.value = res.sessions
  } catch (e) {
    console.error('Failed to load sessions', e)
    sessions.value = []
  } finally {
    loading.value = false
  }
}

watch(activeTab, load)
onMounted(load)

const openSession = (sessionId: string) => {
  router.push(`/chat/${sessionId}`)
}

const handleUnshare = async (sessionId: string) => {
  try {
    await unshareSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    showSuccessToast(t('Link unshared'))
  } catch {
    showErrorToast(t('Failed to unshare session'))
  }
}

const handleUnarchive = async (sessionId: string) => {
  try {
    await unarchiveSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    showSuccessToast(t('Task restored'))
  } catch {
    showErrorToast(t('Failed to archive task'))
  }
}
</script>
