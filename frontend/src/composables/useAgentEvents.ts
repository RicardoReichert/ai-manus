import type { Ref } from 'vue';
import {
  Message,
  MessageContent,
  ToolContent,
  StepContent,
  AttachmentsContent,
} from '../types/message';
import {
  StepEventData,
  ToolEventData,
  MessageEventData,
  ErrorEventData,
  TitleEventData,
  PlanEventData,
  AgentEvent,
} from '../types/event';
import { isComputerPanelTool } from '../constants/tool';
import type { TaskLogEntry, TaskLogKind } from '../types/taskLog';
import { i18n } from './useI18n';

export interface AgentEventState {
  messages: Ref<Message[]>;
  title: Ref<string>;
  plan: Ref<PlanEventData | undefined>;
  lastEventId: Ref<string | undefined>;
  lastTool: Ref<ToolContent | undefined>;
  lastNoMessageTool: Ref<ToolContent | undefined>;
  /** Optional: raw event log for the Task Logs drawer. Capped, newest last. */
  logs?: Ref<TaskLogEntry[]>;
}

const MAX_LOG_ENTRIES = 200;

export interface AgentEventOptions {
  /** Called when a non-message tool is created or updated, so the page can surface it (e.g. in the tool panel). */
  onToolActivity?: (tool: ToolContent) => void;
  /** Fired when stream shows an error assistant bubble or step failed — page maps to phase. */
  onStreamError?: () => void;
}

/**
 * Shared conversion of agent stream events into the UI message list.
 * Used by both ChatPage (live chat) and SharePage (replay).
 */
export function useAgentEvents(state: AgentEventState, options: AgentEventOptions = {}) {
  const { messages, title, plan, lastEventId, lastTool, lastNoMessageTool, logs } = state;

  const getLastStep = (): StepContent | undefined => {
    return messages.value.filter(message => message.type === 'step').pop()?.content as StepContent;
  };

  const handleMessageEvent = (messageData: MessageEventData) => {
    // Skip blank assistant bubbles (e.g. empty create_plan.message from LLM)
    const text = (messageData.content ?? '').trim();
    if (messageData.role === 'assistant' && !text) {
      if (messageData.attachments && messageData.attachments.length > 0) {
        messages.value.push({
          type: 'attachments',
          content: {
            ...messageData
          } as AttachmentsContent,
        });
      }
      return;
    }

    // User turn: keep attachments on the same ChatQuestion shell (images above bubble).
    if (messageData.role === 'user') {
      messages.value.push({
        type: 'user',
        content: {
          ...messageData,
          attachments: messageData.attachments?.length ? messageData.attachments : undefined,
        } as MessageContent,
      });
      return;
    }

    messages.value.push({
      type: messageData.role,
      content: {
        ...messageData
      } as MessageContent,
    });

    if (messageData.attachments && messageData.attachments.length > 0) {
      messages.value.push({
        type: 'attachments',
        content: {
          ...messageData
        } as AttachmentsContent,
      });
    }
  };

  const handleToolEvent = (toolData: ToolEventData) => {
    // Soft-control tools are projected server-side (message bubbles / plan steps).
    if (
      toolData.name === 'todo'
      || toolData.name === 'message'
      || toolData.function === 'todo_write'
      || toolData.function === 'message_notify_user'
      || toolData.function === 'message_ask_user'
      || toolData.function === 'plan_report'
      || toolData.function === 'replan'
    ) {
      return;
    }

    const lastStep = getLastStep();
    const toolContent: ToolContent = {
      ...toolData
    };
    if (lastTool.value && lastTool.value.tool_call_id === toolContent.tool_call_id) {
      Object.assign(lastTool.value, toolContent);
    } else {
      if (lastStep?.status === 'running') {
        lastStep.tools.push(toolContent);
      } else {
        messages.value.push({
          type: 'tool',
          content: toolContent,
        });
      }
      lastTool.value = toolContent;
    }
    // Soft-plan / chat tools must not drive the Computer panel.
    if (isComputerPanelTool(toolContent.name)) {
      lastNoMessageTool.value = toolContent;
      options.onToolActivity?.(toolContent);
    }
  };

  const findStepById = (id: string): StepContent | undefined => {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const message = messages.value[i];
      if (message.type !== 'step') continue;
      const step = message.content as StepContent;
      if (step.id === id) return step;
    }
    return undefined;
  };

  const ensureStepMessage = (stepData: StepEventData) => {
    const existing = findStepById(stepData.id);
    if (existing) {
      existing.status = stepData.status;
      existing.description = stepData.description || existing.description;
      return existing;
    }
    if (stepData.status !== 'running' && stepData.status !== 'pending') {
      return undefined;
    }
    const content = {
      ...stepData,
      status: stepData.status === 'pending' ? 'running' : stepData.status,
      tools: [],
    } as StepContent;
    messages.value.push({ type: 'step', content });
    return content;
  };

  const handleStepEvent = (stepData: StepEventData) => {
    if (stepData.status === 'running') {
      ensureStepMessage(stepData);
    } else if (stepData.status === 'completed') {
      const matched = findStepById(stepData.id) ?? getLastStep();
      if (matched) {
        matched.status = stepData.status;
        if (stepData.description) matched.description = stepData.description;
        if (stepData.result) matched.result = stepData.result;
      }
    } else if (stepData.status === 'failed') {
      const matched = findStepById(stepData.id) ?? getLastStep();
      if (matched) {
        matched.status = stepData.status;
        if (stepData.description) matched.description = stepData.description;
        if (stepData.result) matched.result = stepData.result;
      }
      options.onStreamError?.();
    }
  };

  const handleErrorEvent = (errorData: ErrorEventData) => {
    options.onStreamError?.();
    messages.value.push({
      type: 'assistant',
      content: {
        content: errorData.error,
        timestamp: errorData.timestamp
      } as MessageContent,
    });
  };

  const handleTitleEvent = (titleData: TitleEventData) => {
    title.value = titleData.title;
  };

  const handlePlanEvent = (planData: PlanEventData) => {
    plan.value = planData;
    // Defense in depth: PlanEvent alone used to only feed Computer PlanPanel.
    // Official chat shows a dedicated running step row — seed/sync from plan.
    for (const step of planData.steps ?? []) {
      if (step.status === 'running') {
        ensureStepMessage(step);
      } else if (step.status === 'completed' || step.status === 'failed') {
        const matched = findStepById(step.id);
        if (matched) {
          matched.status = step.status;
        }
      }
    }
  };

  const logLabel = (event: AgentEvent): { label: string; detail?: string } => {
    const { t } = i18n.global;
    switch (event.event) {
      case 'message': {
        const d = event.data as MessageEventData;
        return { label: d.role === 'user' ? t('User message') : t('Assistant message'), detail: d.content };
      }
      case 'tool': {
        const d = event.data as ToolEventData;
        return { label: d.function || d.name, detail: JSON.stringify(d.args) };
      }
      case 'step': {
        const d = event.data as StepEventData;
        return { label: d.description, detail: d.status };
      }
      case 'plan': {
        const d = event.data as PlanEventData;
        return { label: t('Plan updated ({n} steps)', { n: d.steps.length }) };
      }
      case 'error': {
        const d = event.data as ErrorEventData;
        return { label: t('Error'), detail: d.error };
      }
      case 'title': {
        const d = event.data as TitleEventData;
        return { label: t('Title set'), detail: d.title };
      }
      case 'wait':
        return { label: t('Waiting for input') };
      case 'done':
        return { label: t('Task finished') };
      default:
        return { label: event.event };
    }
  };

  const handleEvent = (event: AgentEvent) => {
    // Control / live computer-panel events — not part of the chat message list
    // or the log stream: terminal_update in particular fires far too often to
    // keep in a capped buffer.
    if (
      event.event === 'status_update'
      || event.event === 'terminal_update'
      || event.event === 'file_update'
    ) {
      return;
    }
    if (event.event === 'message') {
      handleMessageEvent(event.data as MessageEventData);
    } else if (event.event === 'tool') {
      handleToolEvent(event.data as ToolEventData);
    } else if (event.event === 'step') {
      handleStepEvent(event.data as StepEventData);
    } else if (event.event === 'done') {
      // Loading state is cleared when the stream ends / status_update arrives
    } else if (event.event === 'wait') {
      // No-op by design: live phase (including the "waiting" state) is driven
      // solely by the WS status_update channel, not by this domain event
      // stream — see docs/superpowers/specs/2026-08-03-backend-status-channel-design.md.
      // The event is still recorded below for the Task Logs drawer.
    } else if (event.event === 'error') {
      handleErrorEvent(event.data as ErrorEventData);
    } else if (event.event === 'title') {
      handleTitleEvent(event.data as TitleEventData);
    } else if (event.event === 'plan') {
      handlePlanEvent(event.data as PlanEventData);
    }

    if (logs) {
      const { label, detail } = logLabel(event);
      const entry: TaskLogEntry = {
        id: event.data.event_id,
        kind: event.event as TaskLogKind,
        label,
        detail,
        timestamp: event.data.timestamp,
      };
      logs.value.push(entry);
      if (logs.value.length > MAX_LOG_ENTRIES) {
        logs.value.splice(0, logs.value.length - MAX_LOG_ENTRIES);
      }
    }

    lastEventId.value = event.data.event_id;
  };

  return { handleEvent };
}
