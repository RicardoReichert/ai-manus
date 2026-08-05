<template>
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div class="relative flex flex-col h-full flex-1 min-w-0 px-5">

      <!-- Header (only shown when a session is active) -->
      <div
        v-if="activeSession"
        class="sm:min-w-[390px] flex flex-row items-center justify-between pt-3 pb-1 gap-1 sticky top-0 z-10 bg-[var(--background-gray-main)] flex-shrink-0">
        <div class="flex items-center flex-1"></div>
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[390px] flex w-full flex-col gap-[4px] overflow-hidden">
          <div class="text-[var(--text-primary)] text-lg font-medium w-full flex flex-row items-center justify-between flex-1 min-w-0 gap-2">
            <div class="flex flex-row items-center gap-[6px] flex-1 min-w-0 relative" ref="sessionMenuTriggerRef">
              <ClawIcon :size="24" class="text-[var(--icon-primary)] flex-shrink-0" />
              <button
                type="button"
                class="flex items-center gap-1 clickable hover:bg-[var(--fill-tsp-white-light)] rounded-[8px] px-1.5 py-0.5 -ml-1.5 min-w-0"
                @click="showSessionMenu = !showSessionMenu"
              >
                <span class="whitespace-nowrap text-ellipsis overflow-hidden truncate max-w-[160px]">{{ sessionLabel(activeSession) }}</span>
                <ChevronDown class="size-3.5 text-[var(--icon-tertiary)] shrink-0" :size="14" />
              </button>
              <span
                v-if="formattedCountdown != null"
                class="ml-1 text-sm font-mono px-1.5 py-0.5 rounded bg-[var(--fill-tsp-white-main)] text-[var(--text-tertiary)] whitespace-nowrap"
              >{{ formattedCountdown }}</span>

              <!-- Session switcher -->
              <Teleport to="body">
                <div
                  v-if="showSessionMenu"
                  ref="sessionMenuContentRef"
                  role="menu"
                  class="fixed z-50 min-w-[260px] max-w-[340px] max-h-[420px] overflow-y-auto rounded-[12px] border border-[var(--border-light)] bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S)] p-1.5 space-y-1"
                  :style="sessionMenuPositionStyle"
                >
                  <div class="px-2 py-1 text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                    {{ t('Sessions') }}
                  </div>
                  <button
                    v-for="s in sessions"
                    :key="s.id"
                    type="button"
                    class="flex w-full items-center justify-between gap-2 px-2.5 py-2 rounded-[8px] hover:bg-[var(--fill-tsp-white-main)] transition-colors cursor-pointer"
                    :class="s.id === activeSessionId ? 'bg-[var(--fill-tsp-white-main)]' : ''"
                    @click="selectSession(s.id)"
                  >
                    <span class="text-sm font-medium text-[var(--text-primary)] truncate min-w-0 flex-1 text-start">{{ sessionLabel(s) }}</span>
                    <span
                      class="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
                      :class="s.status === 'running' ? 'text-green-600 bg-green-500/10' : 'text-[var(--text-tertiary)] bg-[var(--fill-tsp-white-main)]'"
                    >{{ statusLabel(s.status) }}</span>
                    <Check v-if="s.id === activeSessionId" :size="14" class="text-[var(--icon-primary)] shrink-0" />
                  </button>
                  <div class="border-t border-[var(--border-light)] my-1"></div>
                  <button
                    type="button"
                    class="flex w-full items-center gap-2 px-2.5 py-2 rounded-[8px] hover:bg-[var(--fill-tsp-white-main)] transition-colors cursor-pointer text-[var(--text-primary)]"
                    @click="startNewSessionFlow"
                  >
                    <Plus :size="16" class="shrink-0" />
                    <span class="text-sm font-medium">{{ t('New session') }}</span>
                  </button>
                </div>
              </Teleport>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <ModelSelectorDropdown
                :model-id="activeSession.model_id"
                @update:model-id="handleModelChange"
              />
              <button
                @click="handleDeleteSession"
                class="h-8 px-3 rounded-[100px] inline-flex items-center gap-1 clickable outline outline-1 outline-offset-[-1px] outline-[var(--border-btn-main)] hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)] text-sm font-medium"
              >
                {{ t('Delete') }}
              </button>
            </div>
          </div>
        </div>
        <div class="flex-1"></div>
      </div>

      <!-- Main content area -->
      <div class="mx-auto w-full max-w-full sm:max-w-[768px] sm:min-w-[390px] flex flex-col flex-1">

        <!-- Create / choose-a-model panel (no active session, or explicitly starting a new one) -->
        <div v-if="showCreatePanel" class="flex flex-col flex-1 min-h-0 overflow-y-auto">
          <div class="flex flex-col items-center justify-center flex-1 px-4 py-12 w-full">
            <div class="w-full rounded-2xl overflow-hidden bg-[#ECECEB] dark:bg-[#231a33] aspect-video mb-8 flex flex-col items-center justify-center gap-4 px-4">
              <h1 class="text-2xl sm:text-3xl font-bold tracking-tight"><span class="text-[#c0392b]">OpenClaw</span> <span class="text-[var(--text-tertiary)]">×</span> <span class="text-[#3b82f6]">Manus</span></h1>
              <img :src="openclawColorImage" alt="OpenClaw" class="w-20 h-20 sm:w-24 sm:h-24 object-contain drop-shadow-lg" />
            </div>

            <div class="w-full grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
              <div class="flex flex-col gap-3 p-4 rounded-2xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)]">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-lg bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)] flex items-center justify-center">
                    <Code class="w-4 h-4 text-[var(--text-primary)]" />
                  </div>
                  <h3 class="text-[var(--text-primary)] font-medium text-sm">{{ t('Deploy OpenClaw Instantly') }}</h3>
                </div>
                <p class="text-[var(--text-secondary)] text-xs leading-relaxed">
                  {{ t('OpenClaw is an AI assistant with unique personality and long-term memory, one-click deploy to sandbox cloud, no complex setup, 24/7 online') }}
                </p>
              </div>
              <div class="flex flex-col gap-3 p-4 rounded-2xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)]">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-lg bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)] flex items-center justify-center">
                    <MessageSquarePlus class="w-4 h-4 text-[var(--text-primary)]" />
                  </div>
                  <h3 class="text-[var(--text-primary)] font-medium text-sm">{{ t('Chat Freely via Manus') }}</h3>
                </div>
                <p class="text-[var(--text-secondary)] text-xs leading-relaxed">
                  {{ t('Auto-configured with powerful LLMs and skill libraries, supports multiple chat tools, proactively completes various tasks') }}
                </p>
              </div>
            </div>

            <div class="w-full">
              <div class="flex items-center justify-between mb-4">
                <h2 class="text-[var(--text-primary)] font-semibold text-lg">{{ t('Get Started') }}</h2>
                <button
                  v-if="sessions.length > 0"
                  type="button"
                  class="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] clickable"
                  @click="cancelNewSessionFlow"
                >
                  {{ t('Cancel') }}
                </button>
              </div>

              <!-- Model is mandatory before creation is allowed -->
              <div class="mb-4 space-y-2">
                <p class="text-[13px] text-[var(--text-secondary)]">{{ t('Choose a model') }}</p>
                <div v-if="isLoadingModels" class="text-[13px] text-[var(--text-tertiary)] py-2">{{ t('Loading...') }}</div>
                <div v-else class="flex flex-col gap-1.5">
                  <button
                    v-for="m in availableModels"
                    :key="m.id"
                    type="button"
                    class="flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-xl border text-start clickable transition-colors"
                    :class="pendingModelId === m.id
                      ? 'border-[var(--Button-black)] bg-[var(--fill-tsp-white-main)]'
                      : 'border-[var(--border-main)] hover:bg-[var(--fill-tsp-white-light)]'"
                    @click="pendingModelId = m.id"
                  >
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5">
                        <span class="text-sm font-medium text-[var(--text-primary)] truncate">{{ m.name }}</span>
                        <span v-if="m.is_local" class="text-[10px] font-semibold text-blue-500 bg-blue-500/10 px-1 rounded shrink-0">{{ t('Local') }}</span>
                      </div>
                      <p v-if="m.description" class="text-[11px] text-[var(--text-tertiary)] truncate">{{ m.description }}</p>
                    </div>
                    <Check v-if="pendingModelId === m.id" :size="16" class="text-[var(--icon-primary)] shrink-0" />
                  </button>
                  <p v-if="availableModels.length === 0" class="text-[13px] text-[var(--text-tertiary)] py-2">
                    {{ t('No models configured — add the first one.') }}
                  </p>
                </div>
              </div>

              <div class="flex flex-col gap-3">
                <div class="flex items-center justify-between p-4 rounded-2xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)]">
                  <div class="flex items-center gap-3">
                    <img :src="openclawColorImage" alt="OpenClaw" class="w-10 h-10 rounded-full object-cover flex-shrink-0" />
                    <div>
                      <h4 class="text-[var(--text-primary)] font-medium text-sm">{{ t('Create Manus Claw') }}</h4>
                      <p class="text-[var(--text-tertiary)] text-xs">{{ t('One-click OpenClaw deployment by Manus') }}</p>
                    </div>
                  </div>
                  <button
                    @click="handleCreateSession"
                    :disabled="!pendingModelId || isCreating"
                    class="flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-[var(--text-primary)] text-[var(--background-gray-main)] text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                  >
                    {{ isCreating ? t('Loading...') : t('Create') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Loading active session -->
        <div v-else-if="isLoadingSession" class="flex flex-1 items-center justify-center">
          <div class="flex flex-col items-center gap-3">
            <div class="w-8 h-8 border-2 border-[var(--text-tertiary)] border-t-transparent rounded-full animate-spin" />
            <span class="text-[var(--text-tertiary)] text-sm">{{ t('Loading...') }}</span>
          </div>
        </div>

        <!-- Session stopped/error: offer to restart instead of auto-deleting
             (sessions persist by design; only explicit delete removes them) -->
        <div v-else-if="activeSession && activeSession.status !== 'running' && activeSession.status !== 'creating'" class="flex flex-1 items-center justify-center px-4">
          <div class="flex flex-col items-center gap-3 text-center max-w-[360px]">
            <span class="text-[var(--text-tertiary)] text-sm">
              {{ activeSession.status === 'error'
                ? (activeSession.error_message || t('Creation failed, please try again later'))
                : t('This session’s container stopped. Its memory is preserved — restart to continue.') }}
            </span>
            <button
              type="button"
              class="px-4 py-1.5 rounded-full bg-[var(--text-primary)] text-[var(--background-gray-main)] text-sm font-medium hover:opacity-90 transition-opacity"
              @click="handleModelChange(activeSession.model_id)"
            >
              {{ t('Restart') }}
            </button>
          </div>
        </div>

        <!-- Chat Interface -->
        <template v-else-if="activeSession">
          <!-- Messages -->
          <div class="flex flex-col w-full gap-[12px] pb-[80px] pt-[12px] flex-1 overflow-y-auto">
            <ChatMessage
              v-for="(msg, index) in messages"
              :key="messageKey(msg, index)"
              :message="msg"
              :hideHeader="isConsecutiveAssistant(messages, index)"
              :assistantIcon="ClawIcon"
              assistantName="Claw"
              :hideAllFilesButton="true"
            />

            <!-- Loading indicator while waiting for response -->
            <LoadingIndicator v-if="isWaitingResponse && !hasStreamingContent" :text="$t('{name} is thinking', { name: 'Manus' })" />

          </div>

          <!-- Input Area -->
          <div class="flex flex-col bg-[var(--background-gray-main)] sticky bottom-0">
            <button
              v-if="!follow"
              @click="handleFollow"
              class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute -top-20 left-1/2 -translate-x-1/2"
            >
              <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
            </button>
            <ChatBox
              v-model="inputMessage"
              v-model:attachments="attachments"
              :rows="1"
              dense
              :placeholder="t('Send message to Manus')"
              :isRunning="false"
              :hideStopButton="true"
              :allowSendFilesOnly="true"
              @submit="handleSubmit"
            />
          </div>
        </template>

      </div>
    </div>
  </SimpleBar>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { Code, MessageSquarePlus, ArrowDown, ChevronDown, Check, Plus } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import SimpleBar from '../components/SimpleBar.vue';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import LoadingIndicator from '../components/ui/LoadingIndicator.vue';
import ClawIcon from '../components/icons/ClawIcon.vue';
import openclawColorImage from '../assets/openclaw-color.png';
import { useFilePreviewer } from '../composables/useFilePreviewer';
import { useDialog } from '../composables/useDialog';
import {
  listClawSessions, createClawSession, getClawSession, restartClawSession, deleteClawSession,
  getClawSessionHistory, ClawWebSocket,
  type ClawSession, type ClawStatus, type ClawEvent,
} from '../api/claw';
import { getAvailableModels, type ModelDescriptor } from '../api/model';
import ModelSelectorDropdown from '../components/ModelSelectorDropdown.vue';
import { Message, MessageContent, AttachmentsContent, isConsecutiveAssistant } from '../types/message';
import type { FileInfo } from '../api/file';
import { showErrorToast, showSuccessToast } from '../utils/toast';

const { t } = useI18n();
const { hideFilePreviewer } = useFilePreviewer();
const { showConfirmDialog } = useDialog();

const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();

const sessions = ref<ClawSession[]>([]);
const activeSessionId = ref<string | null>(null);
const isLoadingSession = ref(true);
const messages = ref<Message[]>([]);
const inputMessage = ref('');
const isWaitingResponse = ref(false);
const follow = ref(true);
const attachments = ref<FileInfo[]>([]);

const showSessionMenu = ref(false);
const sessionMenuTriggerRef = ref<HTMLElement | null>(null);
const sessionMenuContentRef = ref<HTMLElement | null>(null);
const sessionMenuPosition = reactive({ top: 0, left: 0 });
const sessionMenuPositionStyle = computed(() => ({
  top: `${sessionMenuPosition.top}px`,
  left: `${sessionMenuPosition.left}px`,
}));

// Explicitly starting a new session even though others already exist — kept
// separate from "no sessions at all" so the create panel's Cancel button
// only shows in the former case.
const startingNewSession = ref(false);
const availableModels = ref<ModelDescriptor[]>([]);
const isLoadingModels = ref(false);
const pendingModelId = ref<string | null>(null);
const isCreating = ref(false);

let clawWS: ClawWebSocket | null = null;
let statusPollingTimer: number | null = null;
let expiryTimer: number | null = null;
const streamingAssistantIdx = ref(-1);
const remainingSeconds = ref<number | null>(null);

const activeSession = computed(() =>
  sessions.value.find((s) => s.id === activeSessionId.value) ?? null,
);
const showCreatePanel = computed(() =>
  !isLoadingSession.value && (sessions.value.length === 0 || startingNewSession.value),
);

const sessionLabel = (s: ClawSession) => s.name || t('Session {n}', { n: s.id.slice(0, 8) });
const statusLabel = (status: ClawStatus) => {
  const labels: Record<ClawStatus, string> = {
    running: t('Running'),
    creating: t('Loading...'),
    stopped: t('Stopped'),
    error: t('Error'),
  };
  return labels[status] ?? status;
};

const formattedCountdown = computed(() => {
  const s = remainingSeconds.value;
  if (s == null || s < 0) return null;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
});

// ------------------------------------------------------------------
// Session switcher menu (teleported — see ModelSelectorDropdown for why:
// SimpleBar's overflow:hidden-scroll wrapper clips position:absolute
// dropdowns that try to render outside its own box).
// ------------------------------------------------------------------

function updateSessionMenuPosition() {
  const trigger = sessionMenuTriggerRef.value;
  if (!trigger) return;
  const rect = trigger.getBoundingClientRect();
  sessionMenuPosition.top = rect.bottom + 6;
  sessionMenuPosition.left = rect.left;
}

watch(showSessionMenu, (open) => {
  if (open) updateSessionMenuPosition();
});

const handleSessionMenuOutsideClick = (e: MouseEvent) => {
  const target = e.target as Node;
  const insideTrigger = sessionMenuTriggerRef.value?.contains(target);
  const insideMenu = sessionMenuContentRef.value?.contains(target);
  if (!insideTrigger && !insideMenu) {
    showSessionMenu.value = false;
  }
};

const handleSessionMenuReposition = () => {
  if (showSessionMenu.value) updateSessionMenuPosition();
};

const startExpiryCountdown = (expiresAt: string) => {
  stopExpiryCountdown();
  const utcExpires = expiresAt.endsWith('Z') || expiresAt.includes('+') ? expiresAt : expiresAt + 'Z';
  const tick = () => {
    const diff = Math.floor((new Date(utcExpires).getTime() - Date.now()) / 1000);
    if (diff <= 0) {
      remainingSeconds.value = 0;
      stopExpiryCountdown();
      // The container's TTL is up — the backend stops it but keeps the
      // session/volume, so just refresh state instead of deleting anything.
      refreshActiveSession();
      return;
    }
    remainingSeconds.value = diff;
  };
  tick();
  expiryTimer = window.setInterval(tick, 1000);
};

const stopExpiryCountdown = () => {
  if (expiryTimer) {
    clearInterval(expiryTimer);
    expiryTimer = null;
  }
};

// ------------------------------------------------------------------
// History
// ------------------------------------------------------------------

const loadHistory = async (sessionId: string) => {
  try {
    const history = await getClawSessionHistory(sessionId);
    const loaded: Message[] = [];
    for (const m of history) {
      if (m.role === 'attachments' && m.attachments?.length) {
        const attRole = (m.content === 'user' ? 'user' : 'assistant') as 'user' | 'assistant';
        loaded.push({
          type: 'attachments',
          content: {
            role: attRole,
            attachments: m.attachments.map(a => ({
              file_id: a.file_id,
              filename: a.filename,
              content_type: a.content_type,
              size: a.size,
              upload_date: '',
              file_url: a.file_url,
            })),
            timestamp: m.timestamp,
          } as AttachmentsContent,
        });
      } else {
        let text = m.content || '';
        if (text.startsWith('i18n:')) {
          text = t(text.slice(5));
        }
        loaded.push({
          type: m.role as 'user' | 'assistant',
          content: {
            content: text,
            timestamp: m.timestamp,
          } as MessageContent,
        });
      }
    }
    messages.value = loaded;
  } catch (err) {
    console.error('Failed to load claw session history:', err);
  }
};

// ------------------------------------------------------------------
// WebSocket event stream
// ------------------------------------------------------------------

const setupWebSocket = (sessionId: string) => {
  clawWS?.disconnect();

  clawWS = new ClawWebSocket(sessionId, {
    onEvent: (event: ClawEvent) => handleWSEvent(event),
  });
};

const handleWSEvent = (chunk: ClawEvent) => {
  if (chunk.type === 'catchup') {
    // Reconnected while a response was in progress
    if (streamingAssistantIdx.value < 0) {
      streamingAssistantIdx.value = messages.value.length;
      messages.value.push({
        type: 'assistant',
        content: { content: '', timestamp: Math.floor(Date.now() / 1000) } as MessageContent,
      });
      isWaitingResponse.value = true;
    }
    if (chunk.content && streamingAssistantIdx.value >= 0) {
      (messages.value[streamingAssistantIdx.value].content as MessageContent).content = chunk.content;
    }
    return;
  }

  if (chunk.type === 'text') {
    if (streamingAssistantIdx.value < 0) {
      streamingAssistantIdx.value = messages.value.length;
      messages.value.push({
        type: 'assistant',
        content: { content: '', timestamp: Math.floor(Date.now() / 1000) } as MessageContent,
      });
    }
    if (chunk.content && streamingAssistantIdx.value >= 0) {
      (messages.value[streamingAssistantIdx.value].content as MessageContent).content += chunk.content;
    }
    return;
  }

  if (chunk.type === 'file' && chunk.file_id) {
    const fileInfo: FileInfo = {
      file_id: chunk.file_id,
      filename: chunk.filename || chunk.file_id,
      content_type: chunk.content_type,
      size: chunk.size ?? 0,
      upload_date: chunk.upload_date || new Date().toISOString(),
      file_url: chunk.file_url,
    };
    messages.value.push({
      type: 'attachments',
      content: {
        role: 'assistant',
        attachments: [fileInfo],
        timestamp: Math.floor(Date.now() / 1000),
      } as AttachmentsContent,
    });
    return;
  }

  if (chunk.type === 'done') {
    streamingAssistantIdx.value = -1;
    isWaitingResponse.value = false;
    return;
  }

  if (chunk.type === 'error') {
    if (streamingAssistantIdx.value >= 0) {
      (messages.value[streamingAssistantIdx.value].content as MessageContent).content
        += `\n⚠️ ${chunk.error || t('An error occurred')}`;
    } else {
      messages.value.push({
        type: 'assistant',
        content: { content: `⚠️ ${chunk.error || t('An error occurred')}`, timestamp: Math.floor(Date.now() / 1000) } as MessageContent,
      });
    }
    streamingAssistantIdx.value = -1;
    isWaitingResponse.value = false;
  }
};

// ------------------------------------------------------------------
// UI helpers
// ------------------------------------------------------------------

const messageKey = (msg: Message, index: number): string => {
  if (msg.type === 'attachments') {
    const ac = msg.content as AttachmentsContent;
    const ids = ac.attachments?.map(a => a.file_id).join(',') || '';
    return `att-${ac.role}-${ac.timestamp}-${ids}`;
  }
  const mc = msg.content as MessageContent;
  const prefix = (mc.content || '').slice(0, 40);
  return `${msg.type}-${mc.timestamp}-${index}-${prefix}`;
};

const hasStreamingContent = computed(() => {
  if (streamingAssistantIdx.value < 0) return false;
  const msg = messages.value[streamingAssistantIdx.value];
  return msg && (msg.content as MessageContent).content.length > 0;
});

const handleScroll = () => {
  follow.value = simpleBarRef.value?.isScrolledToBottom() ?? false;
};

const handleFollow = () => {
  follow.value = true;
  simpleBarRef.value?.scrollToBottom();
};

watch(messages, async () => {
  await nextTick();
  if (follow.value) {
    simpleBarRef.value?.scrollToBottom();
  }
}, { deep: true });

// ------------------------------------------------------------------
// Session list / switching
// ------------------------------------------------------------------

const teardownActiveSession = () => {
  clawWS?.disconnect();
  clawWS = null;
  isWaitingResponse.value = false;
  streamingAssistantIdx.value = -1;
  stopStatusPolling();
  stopExpiryCountdown();
  remainingSeconds.value = null;
  messages.value = [];
};

const enterSession = async (session: ClawSession) => {
  teardownActiveSession();
  activeSessionId.value = session.id;
  startingNewSession.value = false;

  if (session.status === 'creating') {
    startStatusPolling(session.id);
    return;
  }
  if (session.status !== 'running') {
    return; // stopped/error panel handles its own "Restart" action
  }

  await loadHistory(session.id);
  setupWebSocket(session.id);
  if (session.expires_at) startExpiryCountdown(session.expires_at);
  await nextTick();
  follow.value = true;
  simpleBarRef.value?.scrollToBottom();
};

const selectSession = async (sessionId: string) => {
  showSessionMenu.value = false;
  const session = sessions.value.find((s) => s.id === sessionId);
  if (session) await enterSession(session);
};

const refreshActiveSession = async () => {
  if (!activeSessionId.value) return;
  try {
    const updated = await getClawSession(activeSessionId.value);
    const idx = sessions.value.findIndex((s) => s.id === updated.id);
    if (idx >= 0) sessions.value[idx] = updated;
    else sessions.value.unshift(updated);
  } catch {
    // session may have been deleted elsewhere; leave the list as-is
  }
};

const loadModelsForCreation = async () => {
  isLoadingModels.value = true;
  try {
    availableModels.value = await getAvailableModels();
    if (!pendingModelId.value && availableModels.value.length > 0) {
      pendingModelId.value = availableModels.value[0].id;
    }
  } catch (err) {
    console.error('Failed to load models:', err);
  } finally {
    isLoadingModels.value = false;
  }
};

const startNewSessionFlow = () => {
  showSessionMenu.value = false;
  startingNewSession.value = true;
  pendingModelId.value = availableModels.value[0]?.id ?? null;
};

const cancelNewSessionFlow = () => {
  startingNewSession.value = false;
};

// ------------------------------------------------------------------
// Claw lifecycle
// ------------------------------------------------------------------

const loadSessions = async () => {
  isLoadingSession.value = true;
  try {
    sessions.value = await listClawSessions();
    await loadModelsForCreation();
    if (sessions.value.length === 0) {
      isLoadingSession.value = false;
      return;
    }
    const mostRecent = sessions.value[0];
    isLoadingSession.value = false;
    await enterSession(mostRecent);
  } catch (err) {
    console.error('Failed to load claw sessions:', err);
    isLoadingSession.value = false;
  }
};

const startStatusPolling = (sessionId: string) => {
  if (statusPollingTimer) return;

  statusPollingTimer = window.setInterval(async () => {
    try {
      const session = await getClawSession(sessionId);
      const idx = sessions.value.findIndex((s) => s.id === sessionId);
      if (idx >= 0) sessions.value[idx] = session;

      if (session.status === 'running') {
        stopStatusPolling();
        await loadHistory(sessionId);
        setupWebSocket(sessionId);
        if (session.expires_at) startExpiryCountdown(session.expires_at);
        await nextTick();
        follow.value = true;
        simpleBarRef.value?.scrollToBottom();
      } else if (session.status === 'error') {
        stopStatusPolling();
        showErrorToast(session.error_message || t('Creation failed, please try again later'));
      }
    } catch {
      stopStatusPolling();
    }
  }, 3000);
};

const stopStatusPolling = () => {
  if (statusPollingTimer) {
    clearInterval(statusPollingTimer);
    statusPollingTimer = null;
  }
};

const handleCreateSession = async () => {
  if (!pendingModelId.value) return;
  isCreating.value = true;
  try {
    const session = await createClawSession(pendingModelId.value);
    sessions.value.unshift(session);
    startingNewSession.value = false;
    await enterSession(session);
  } catch (err: any) {
    showErrorToast(err?.response?.data?.msg || err?.message || t('Creation failed, please try again later'));
  } finally {
    isCreating.value = false;
  }
};

/**
 * Switching models is always a restart: kill the current container, start a
 * fresh one on the chosen model. The session's volume is untouched, so
 * OpenClaw's native memory survives — this is not the destructive action it
 * might look like.
 */
const handleModelChange = async (modelId: string) => {
  const session = activeSession.value;
  if (!session) return;
  teardownActiveSession();
  try {
    const updated = await restartClawSession(session.id, modelId);
    const idx = sessions.value.findIndex((s) => s.id === updated.id);
    if (idx >= 0) sessions.value[idx] = updated;
    showSuccessToast(t('Restarting with the new model — your conversation history is preserved.'));
    await enterSession(updated);
  } catch (err: any) {
    showErrorToast(err?.response?.data?.msg || err?.message || t('Failed to update model'));
  }
};

const handleDeleteSession = () => {
  const session = activeSession.value;
  if (!session) return;
  showConfirmDialog({
    title: t('Are you sure you want to delete this session?'),
    content: t('This permanently deletes its memory and cannot be undone. To just switch models, use the model dropdown instead — it restarts without losing history.'),
    confirmText: t('Delete'),
    cancelText: t('Cancel'),
    confirmType: 'danger',
    onConfirm: async () => {
      teardownActiveSession();
      try {
        await deleteClawSession(session.id);
      } catch (err) {
        console.error('Failed to delete claw session:', err);
      }
      sessions.value = sessions.value.filter((s) => s.id !== session.id);
      activeSessionId.value = null;
      if (sessions.value.length > 0) {
        await enterSession(sessions.value[0]);
      } else {
        await loadModelsForCreation();
      }
    },
  });
};

// ------------------------------------------------------------------
// Send message
// ------------------------------------------------------------------

const handleSubmit = async () => {
  const session = activeSession.value;
  const msg = inputMessage.value.trim();
  const files = attachments.value;
  if (!msg && files.length === 0) return;
  if (isWaitingResponse.value) return;
  if (!session || session.status !== 'running') {
    return;
  }

  const successFiles = files.filter((f: FileInfo) => !('status' in f) || (f as FileInfo & { status?: string }).status === 'success');
  const msgToSend = msg || (successFiles.length > 0 ? t('Please check {count} attachment(s) I sent', { count: successFiles.length }) : '');

  if (msgToSend || successFiles.length > 0) {
    messages.value.push({
      type: 'user',
      content: {
        content: msgToSend,
        timestamp: Math.floor(Date.now() / 1000),
        attachments: successFiles.length > 0 ? successFiles : undefined,
      } as MessageContent,
    });
  }

  if (successFiles.length > 0) {
    attachments.value.length = 0;
  }

  inputMessage.value = '';
  follow.value = true;
  isWaitingResponse.value = true;

  const fileIds = successFiles.map((f: FileInfo) => f.file_id).filter(Boolean);
  if (clawWS?.isConnected) {
    clawWS.send(msgToSend, fileIds.length > 0 ? fileIds : undefined);
  } else {
    isWaitingResponse.value = false;
    messages.value.push({
      type: 'assistant',
      content: { content: `⚠️ ${t('WebSocket not connected, please try again later')}`, timestamp: Math.floor(Date.now() / 1000) } as MessageContent,
    });
  }
};

// ------------------------------------------------------------------
// Lifecycle
// ------------------------------------------------------------------

onMounted(() => {
  loadSessions();
  document.addEventListener('mousedown', handleSessionMenuOutsideClick);
  window.addEventListener('scroll', handleSessionMenuReposition, true);
  window.addEventListener('resize', handleSessionMenuReposition);
});

onUnmounted(() => {
  teardownActiveSession();
  hideFilePreviewer();
  document.removeEventListener('mousedown', handleSessionMenuOutsideClick);
  window.removeEventListener('scroll', handleSessionMenuReposition, true);
  window.removeEventListener('resize', handleSessionMenuReposition);
});
</script>
