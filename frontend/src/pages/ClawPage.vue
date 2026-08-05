<template>
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div class="relative flex flex-col h-full flex-1 min-w-0 px-5">

      <!-- Header (only shown when claw exists) -->
      <div
        v-if="hasClaw"
        class="sm:min-w-[390px] flex flex-row items-center justify-between pt-3 pb-1 gap-1 sticky top-0 z-10 bg-[var(--background-gray-main)] flex-shrink-0">
        <div class="flex items-center flex-1"></div>
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[390px] flex w-full flex-col gap-[4px] overflow-hidden">
          <div class="text-[var(--text-primary)] text-lg font-medium w-full flex flex-row items-center justify-between flex-1 min-w-0 gap-2">
            <div class="flex flex-row items-center gap-[6px] flex-1 min-w-0">
              <ClawIcon :size="24" class="text-[var(--icon-primary)] flex-shrink-0" />
              <span class="whitespace-nowrap text-ellipsis overflow-hidden">Manus Claw</span>
              <span
                v-if="formattedCountdown != null"
                class="ml-1 text-sm font-mono px-1.5 py-0.5 rounded bg-[var(--fill-tsp-white-main)] text-[var(--text-tertiary)] whitespace-nowrap"
              >{{ formattedCountdown }}</span>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <ModelSelectorDropdown
                v-if="clawModelId !== undefined"
                :model-id="clawModelId"
                @update:model-id="handleClawModelChange"
              />
              <button
                @click="handleDeleteClaw"
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

        <!-- Create Page (no claw instance) -->
        <div v-if="!hasClaw && !isLoadingClaw" class="flex flex-col flex-1 min-h-0 overflow-y-auto">
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
                    @click="handleCreateClaw"
                    class="flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-[var(--text-primary)] text-[var(--background-gray-main)] text-sm font-medium hover:opacity-90 transition-opacity"
                  >
                    {{ t('Create') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Loading claw state -->
        <div v-else-if="isLoadingClaw" class="flex flex-1 items-center justify-center">
          <div class="flex flex-col items-center gap-3">
            <div class="w-8 h-8 border-2 border-[var(--text-tertiary)] border-t-transparent rounded-full animate-spin" />
            <span class="text-[var(--text-tertiary)] text-sm">{{ t('Loading...') }}</span>
          </div>
        </div>

        <!-- Chat Interface (claw exists) -->
        <template v-else>
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
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { Code, MessageSquarePlus, ArrowDown } from 'lucide-vue-next';
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
  getClaw, createClaw, deleteClaw, updateClawModel,
  getClawHistory, ClawWebSocket,
  type Claw, type ClawStatus, type ClawEvent,
} from '../api/claw';
import ModelSelectorDropdown from '../components/ModelSelectorDropdown.vue';
import { Message, MessageContent, AttachmentsContent, isConsecutiveAssistant } from '../types/message';
import type { FileInfo } from '../api/file';
import { showErrorToast } from '../utils/toast';

const { t } = useI18n();
const { hideFilePreviewer } = useFilePreviewer();
const { showConfirmDialog } = useDialog();

const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();

const isLoadingClaw = ref(true);
const clawData = ref<Claw | null>(null);
const clawStatus = ref<ClawStatus>('stopped');
const messages = ref<Message[]>([]);
const inputMessage = ref('');
const isWaitingResponse = ref(false);
const follow = ref(true);
const attachments = ref<FileInfo[]>([]);

let clawWS: ClawWebSocket | null = null;
let statusPollingTimer: number | null = null;
let expiryTimer: number | null = null;
const streamingAssistantIdx = ref(-1);
const remainingSeconds = ref<number | null>(null);

const formattedCountdown = computed(() => {
  const s = remainingSeconds.value;
  if (s == null || s < 0) return null;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
});

const startExpiryCountdown = (expiresAt: string) => {
  stopExpiryCountdown();
  const utcExpires = expiresAt.endsWith('Z') || expiresAt.includes('+') ? expiresAt : expiresAt + 'Z';
  const tick = () => {
    const diff = Math.floor((new Date(utcExpires).getTime() - Date.now()) / 1000);
    if (diff <= 0) {
      remainingSeconds.value = 0;
      stopExpiryCountdown();
      handleExpired();
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

const handleExpired = async () => {
  clawWS?.disconnect();
  clawWS = null;
  isWaitingResponse.value = false;
  streamingAssistantIdx.value = -1;
  stopStatusPolling();
  try {
    await deleteClaw();
  } catch {
    // The claw may already be gone once it expires; nothing to clean up
  }
  clawData.value = null;
  clawStatus.value = 'stopped';
  messages.value = [];
  remainingSeconds.value = null;
  isLoadingClaw.value = false;
};

// ------------------------------------------------------------------
// History
// ------------------------------------------------------------------

const loadHistory = async () => {
  try {
    const history = await getClawHistory();
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
    console.error('Failed to load claw history:', err);
  }
};

// ------------------------------------------------------------------
// WebSocket event stream
// ------------------------------------------------------------------

const setupWebSocket = () => {
  clawWS?.disconnect();

  clawWS = new ClawWebSocket({
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

  if (chunk.type === 'status') {
    const newStatus = chunk.status!;
    clawStatus.value = newStatus;
    if (newStatus === 'stopped' || newStatus === 'error') {
      streamingAssistantIdx.value = -1;
      isWaitingResponse.value = false;
    }
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

const hasClaw = computed(() => clawData.value !== null);
// undefined while there's no claw yet (dropdown hidden); null means "using
// the default model" once a claw exists — both are valid, distinct states.
const clawModelId = computed(() => clawData.value?.claw_model_id ?? (hasClaw.value ? null : undefined));

const handleClawModelChange = async (modelId: string) => {
  if (!clawData.value) return;
  const previous = clawData.value.claw_model_id ?? null;
  clawData.value = { ...clawData.value, claw_model_id: modelId }; // optimistic
  try {
    const updated = await updateClawModel(modelId);
    clawData.value = updated;
  } catch (err: any) {
    clawData.value = { ...clawData.value, claw_model_id: previous };
    showErrorToast(err?.response?.data?.msg || err?.message || t('Failed to update model'));
  }
};

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
// Claw lifecycle
// ------------------------------------------------------------------

const loadClaw = async () => {
  try {
    isLoadingClaw.value = true;
    const claw = await getClaw();
    clawData.value = claw;
    clawStatus.value = claw.status;

    if (claw.status === 'error' || claw.status === 'stopped') {
      if (claw.status === 'error') {
        showErrorToast(claw.error_message || t('Creation failed, please try again later'));
      }
      await deleteClaw().catch(() => {});
      clawData.value = null;
      isLoadingClaw.value = false;
      return;
    }

    if (claw.status === 'creating') {
      startStatusPolling();
      return;
    }

    await loadHistory();
    if (claw.status === 'running') {
      setupWebSocket();
      if (claw.expires_at) startExpiryCountdown(claw.expires_at);
    }
    isLoadingClaw.value = false;
    await nextTick();
    follow.value = true;
    simpleBarRef.value?.scrollToBottom();
  } catch (err: any) {
    if (err?.code === 404 || err?.code === 40400) {
      clawData.value = null;
    } else {
      console.error('Failed to load claw:', err);
    }
    isLoadingClaw.value = false;
  }
};

const startStatusPolling = () => {
  if (statusPollingTimer) return;
  if (clawStatus.value === 'running') return;

  statusPollingTimer = window.setInterval(async () => {
    try {
      const claw = await getClaw();
      clawData.value = claw;
      clawStatus.value = claw.status;
      if (claw.status === 'running') {
        stopStatusPolling();
        await loadHistory();
        setupWebSocket();
        if (claw.expires_at) startExpiryCountdown(claw.expires_at);
        isLoadingClaw.value = false;
        await nextTick();
        follow.value = true;
        simpleBarRef.value?.scrollToBottom();
      } else if (claw.status === 'error') {
        stopStatusPolling();
        showErrorToast(claw.error_message || t('Creation failed, please try again later'));
        await deleteClaw().catch(() => {});
        clawData.value = null;
        isLoadingClaw.value = false;
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

const handleCreateClaw = async () => {
  isLoadingClaw.value = true;
  try {
    const claw = await createClaw();
    clawData.value = claw;
    clawStatus.value = claw.status;
    if (claw.status === 'running') {
      await loadHistory();
      setupWebSocket();
      if (claw.expires_at) startExpiryCountdown(claw.expires_at);
      isLoadingClaw.value = false;
      await nextTick();
      follow.value = true;
      simpleBarRef.value?.scrollToBottom();
    } else if (claw.status === 'error') {
      showErrorToast(claw.error_message || t('Creation failed, please try again later'));
      await deleteClaw().catch(() => {});
      clawData.value = null;
      isLoadingClaw.value = false;
    } else {
      startStatusPolling();
    }
  } catch (err: any) {
    showErrorToast(err?.message || t('Creation failed, please try again later'));
    await deleteClaw().catch(() => {});
    clawData.value = null;
    isLoadingClaw.value = false;
  }
};

const handleDeleteClaw = () => {
  showConfirmDialog({
    title: t('Are you sure you want to delete Claw?'),
    content: t('Chat history will be cleared. The Claw instance will remain available for re-creation.'),
    confirmText: t('Delete'),
    cancelText: t('Cancel'),
    confirmType: 'danger',
    onConfirm: async () => {
      clawWS?.disconnect();
      clawWS = null;
      isWaitingResponse.value = false;
      streamingAssistantIdx.value = -1;
      stopStatusPolling();
      stopExpiryCountdown();
      try {
        await deleteClaw();
      } catch (err) {
        console.error('Failed to delete claw:', err);
      }
      clawData.value = null;
      clawStatus.value = 'stopped';
      messages.value = [];
      remainingSeconds.value = null;
      isLoadingClaw.value = false;
    },
  });
};

// ------------------------------------------------------------------
// Send message
// ------------------------------------------------------------------

const handleSubmit = async () => {
  const msg = inputMessage.value.trim();
  const files = attachments.value;
  if (!msg && files.length === 0) return;
  if (isWaitingResponse.value) return;
  if (clawStatus.value !== 'running') {
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
    clawWS.send(msgToSend, 'default', fileIds.length > 0 ? fileIds : undefined);
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
  loadClaw();
});

onUnmounted(() => {
  clawWS?.disconnect();
  stopStatusPolling();
  stopExpiryCountdown();
  hideFilePreviewer();
});
</script>
