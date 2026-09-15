import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useAgentEvents, type AgentEventState } from '../useAgentEvents'
import type { Message, ToolContent } from '../../types/message'
import type { PlanEventData, AgentEvent } from '../../types/event'

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

function toolEvent(id: string): AgentEvent {
  return {
    event: 'terminal_update',
    data: { event_id: id, timestamp: Number(id), shell_id: 's', output: 'x' },
  } as AgentEvent
}

function messageEvent(id: string): AgentEvent {
  return {
    event: 'message',
    data: { event_id: id, timestamp: Number(id), role: 'assistant', content: `msg ${id}`, attachments: [] },
  } as AgentEvent
}

describe('useAgentEvents logs ring buffer', () => {
  it('records an entry per domain event', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(messageEvent('1'))
    handleEvent(messageEvent('2'))
    expect(state.logs!.value).toHaveLength(2)
    expect(state.logs!.value[0].id).toBe('1')
  })

  it('excludes terminal_update / file_update / status_update from the log', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    handleEvent(toolEvent('1'))
    handleEvent(messageEvent('2'))
    expect(state.logs!.value).toHaveLength(1)
    expect(state.logs!.value[0].id).toBe('2')
  })

  it('caps at 200 entries, keeping the newest', () => {
    const state = makeState()
    const { handleEvent } = useAgentEvents(state)
    for (let i = 0; i < 250; i++) {
      handleEvent(messageEvent(String(i)))
    }
    expect(state.logs!.value).toHaveLength(200)
    expect(state.logs!.value[0].id).toBe('50')
    expect(state.logs!.value[state.logs!.value.length - 1].id).toBe('249')
  })

  it('is a no-op when no logs ref is provided', () => {
    const state = makeState()
    delete (state as Partial<AgentEventState>).logs
    const { handleEvent } = useAgentEvents(state)
    expect(() => handleEvent(messageEvent('1'))).not.toThrow()
  })
})
