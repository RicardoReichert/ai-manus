import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useAgentEvents, type AgentEventState } from '../useAgentEvents'
import type { Message, ToolContent, StepContent, MessageContent } from '../../types/message'
import type { PlanEventData, AgentEvent, MessageEventData, ToolEventData, StepEventData } from '../../types/event'

function makeState(): AgentEventState & { messages: ReturnType<typeof ref<Message[]>> } {
  return {
    messages: ref<Message[]>([]),
    title: ref(''),
    plan: ref<PlanEventData | undefined>(undefined),
    lastEventId: ref<string | undefined>(undefined),
    lastTool: ref<ToolContent | undefined>(undefined),
    lastNoMessageTool: ref<ToolContent | undefined>(undefined),
    logs: ref([]),
  }
}

function messageEvent(id: string, data: Partial<MessageEventData> = {}): AgentEvent {
  return {
    event: 'message',
    data: {
      event_id: id,
      timestamp: Number(id),
      role: 'assistant',
      content: `msg ${id}`,
      attachments: [],
      ...data,
    },
  } as AgentEvent
}

function toolEventData(id: string, data: Partial<ToolEventData> = {}): AgentEvent {
  return {
    event: 'tool',
    data: {
      event_id: id,
      timestamp: Number(id),
      tool_call_id: `call-${id}`,
      name: 'shell',
      status: 'calling',
      function: 'exec',
      args: {},
      ...data,
    },
  } as AgentEvent
}

function stepEvent(id: string, data: Partial<StepEventData> = {}): AgentEvent {
  return {
    event: 'step',
    data: {
      event_id: id,
      timestamp: Number(id),
      status: 'running',
      id: `step-${id}`,
      description: `step ${id}`,
      ...data,
    },
  } as AgentEvent
}

function errorEvent(id: string, error = 'boom'): AgentEvent {
  return {
    event: 'error',
    data: { event_id: id, timestamp: Number(id), error },
  } as AgentEvent
}

function titleEvent(id: string, title = 'New title'): AgentEvent {
  return {
    event: 'title',
    data: { event_id: id, timestamp: Number(id), title },
  } as AgentEvent
}

function planEvent(id: string): AgentEvent {
  return {
    event: 'plan',
    data: { event_id: id, timestamp: Number(id), steps: [] },
  } as AgentEvent
}

function waitEvent(id: string): AgentEvent {
  return {
    event: 'wait',
    data: { event_id: id, timestamp: Number(id) },
  } as AgentEvent
}

function doneEvent(id: string): AgentEvent {
  return {
    event: 'done',
    data: { event_id: id, timestamp: Number(id) },
  } as AgentEvent
}

function statusUpdateEvent(id: string): AgentEvent {
  return {
    event: 'status_update',
    data: { event_id: id, timestamp: Number(id), agent_status: 'running' },
  } as AgentEvent
}

function terminalUpdateEvent(id: string): AgentEvent {
  return {
    event: 'terminal_update',
    data: { event_id: id, timestamp: Number(id), shell_id: 's', output: 'x' },
  } as AgentEvent
}

function fileUpdateEvent(id: string): AgentEvent {
  return {
    event: 'file_update',
    data: { event_id: id, timestamp: Number(id), path: '/a', content: 'x' },
  } as AgentEvent
}

describe('useAgentEvents message events', () => {
  it('pushes an assistant bubble for non-empty trimmed content', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const event = messageEvent('1', { role: 'assistant', content: '  hello  ' })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({
      type: 'assistant',
      content: { ...(event.data as MessageEventData) },
    })
  })

  it('pushes nothing for blank assistant content with no attachments', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(messageEvent('1', { role: 'assistant', content: '   ', attachments: [] }))
    expect(state.messages.value).toHaveLength(0)
  })

  it('pushes only an attachments entry for blank assistant content with attachments', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const attachments = [{ id: 'f1' } as any]
    const event = messageEvent('1', { role: 'assistant', content: '', attachments })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({
      type: 'attachments',
      content: { ...(event.data as MessageEventData) },
    })
  })

  it('pushes a user bubble with attachments as given', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const attachments = [{ id: 'f1' } as any]
    const event = messageEvent('1', { role: 'user', content: 'hi', attachments })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({
      type: 'user',
      content: { ...(event.data as MessageEventData), attachments },
    })
  })

  it('pushes a user bubble with undefined attachments when empty', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const event = messageEvent('1', { role: 'user', content: 'hi', attachments: [] })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    const content = state.messages.value[0].content as MessageContent
    expect(content.attachments).toBeUndefined()
  })

  it('pushes two entries — primary bubble then attachments — when attachments are present', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const attachments = [{ id: 'f1' } as any]
    const event = messageEvent('1', { role: 'assistant', content: 'hello', attachments })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(2)
    expect(state.messages.value[0].type).toBe('assistant')
    expect(state.messages.value[1]).toEqual({
      type: 'attachments',
      content: { ...(event.data as MessageEventData) },
    })
  })
})

describe('useAgentEvents tool events', () => {
  it('pushes a new tool message and sets lastTool when first seen', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const event = toolEventData('1')
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({ type: 'tool', content: { ...(event.data as ToolEventData) } })
    expect(state.lastTool!.value).toEqual({ ...(event.data as ToolEventData) })
  })

  it('merges an update with the same tool_call_id onto the existing lastTool object without pushing', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(toolEventData('1', { tool_call_id: 'same', status: 'calling' }))
    expect(state.messages.value).toHaveLength(1)
    const originalObject = state.lastTool!.value
    handleEvent(toolEventData('2', { tool_call_id: 'same', status: 'called', content: 'done' }))
    expect(state.messages.value).toHaveLength(1)
    // Object identity is preserved via Object.assign
    expect(state.lastTool!.value).toBe(originalObject)
    expect(state.lastTool!.value!.status).toBe('called')
    expect(state.lastTool!.value!.content).toBe('done')
    const toolMessage = state.messages.value[0].content as ToolContent
    expect(toolMessage.status).toBe('called')
  })

  it('appends the tool to the running step tools array instead of pushing a top-level message', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(stepEvent('1', { status: 'running' }))
    expect(state.messages.value).toHaveLength(1)
    handleEvent(toolEventData('2', { tool_call_id: 'x' }))
    expect(state.messages.value).toHaveLength(1)
    const stepContent = state.messages.value[0].content as StepContent
    expect(stepContent.tools).toHaveLength(1)
    expect(stepContent.tools[0].tool_call_id).toBe('x')
  })

  it('sets lastNoMessageTool and calls onToolActivity for non-message tool names', () => {
    const state = makeState()
    const onToolActivity = vi.fn()
    const { handleEvent } = useAgentEvents(state, { onToolActivity })
    const event = toolEventData('1', { name: 'shell' })
    handleEvent(event)
    expect(state.lastNoMessageTool!.value).toEqual({ ...(event.data as ToolEventData) })
    expect(onToolActivity).toHaveBeenCalledTimes(1)
    expect(onToolActivity).toHaveBeenCalledWith(state.lastTool!.value)
  })

  it('does not set lastNoMessageTool or call onToolActivity when name === "message"', () => {
    const state = makeState()
    const onToolActivity = vi.fn()
    const { handleEvent } = useAgentEvents(state, { onToolActivity })
    handleEvent(toolEventData('1', { name: 'message' }))
    expect(state.lastNoMessageTool!.value).toBeUndefined()
    expect(onToolActivity).not.toHaveBeenCalled()
  })
})

describe('useAgentEvents step events', () => {
  it('pushes a new step message with an empty tools array when status is running', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const event = stepEvent('1', { status: 'running' })
    handleEvent(event)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({
      type: 'step',
      content: { ...(event.data as StepEventData), tools: [] },
    })
  })

  it('mutates the most recent step message status in place when completed', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(stepEvent('1', { status: 'running' }))
    handleEvent(stepEvent('2', { status: 'completed' }))
    expect(state.messages.value).toHaveLength(1)
    const content = state.messages.value[0].content as StepContent
    expect(content.status).toBe('completed')
  })

  it('calls onStreamError and does not push or mutate a step message when failed', () => {
    const state = makeState()
    const onStreamError = vi.fn()
    const { handleEvent } = useAgentEvents(state, { onStreamError })
    handleEvent(stepEvent('1', { status: 'running' }))
    handleEvent(stepEvent('2', { status: 'failed' }))
    expect(onStreamError).toHaveBeenCalledTimes(1)
    expect(state.messages.value).toHaveLength(1)
    const content = state.messages.value[0].content as StepContent
    expect(content.status).toBe('running')
  })
})

describe('useAgentEvents error/title/plan events', () => {
  it('calls onStreamError and pushes an assistant error bubble', () => {
    const state = makeState()
    const onStreamError = vi.fn()
    const { handleEvent } = useAgentEvents(state, { onStreamError })
    handleEvent(errorEvent('1', 'something broke'))
    expect(onStreamError).toHaveBeenCalledTimes(1)
    expect(state.messages.value).toHaveLength(1)
    expect(state.messages.value[0]).toEqual({
      type: 'assistant',
      content: { content: 'something broke', timestamp: 1 },
    })
  })

  it('sets state.title on a title event', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(titleEvent('1', 'A new title'))
    expect(state.title.value).toBe('A new title')
  })

  it('sets state.plan on a plan event', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    const event = planEvent('1')
    handleEvent(event)
    expect(state.plan.value).toEqual(event.data)
  })
})

describe('useAgentEvents wait/done events', () => {
  it('is a no-op on messages/title/plan but still updates lastEventId for wait', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(waitEvent('1'))
    expect(state.messages.value).toHaveLength(0)
    expect(state.title.value).toBe('')
    expect(state.plan.value).toBeUndefined()
    expect(state.lastEventId!.value).toBe('1')
  })

  it('is a no-op on messages/title/plan but still updates lastEventId for done', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(doneEvent('1'))
    expect(state.messages.value).toHaveLength(0)
    expect(state.title.value).toBe('')
    expect(state.plan.value).toBeUndefined()
    expect(state.lastEventId!.value).toBe('1')
  })
})

describe('useAgentEvents filtered events', () => {
  it('returns immediately for status_update, leaving messages and lastEventId untouched', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(statusUpdateEvent('1'))
    expect(state.messages.value).toHaveLength(0)
    expect(state.lastEventId!.value).toBeUndefined()
  })

  it('returns immediately for terminal_update, leaving messages and lastEventId untouched', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(terminalUpdateEvent('1'))
    expect(state.messages.value).toHaveLength(0)
    expect(state.lastEventId!.value).toBeUndefined()
  })

  it('returns immediately for file_update, leaving messages and lastEventId untouched', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(fileUpdateEvent('1'))
    expect(state.messages.value).toHaveLength(0)
    expect(state.lastEventId!.value).toBeUndefined()
  })
})
