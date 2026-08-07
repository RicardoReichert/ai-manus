import { describe, it, expect } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { i18n } from '../useI18n'
import { useToolInfo } from '../useTool'
import type { ToolContent } from '../../types/message'
import {
  TOOL_ICON_MAP,
  TOOL_NAME_MAP,
  TOOL_FUNCTION_MAP,
  TOOL_FUNCTION_ARG_MAP,
  TOOL_COMPONENT_MAP
} from '../../constants/tool'

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return () => null
      }
    }),
    { global: { plugins: [i18n] } }
  )
  return { result, wrapper }
}

function makeTool(overrides: Partial<ToolContent> = {}): ToolContent {
  return {
    timestamp: 0,
    tool_call_id: 'call-1',
    name: 'file',
    function: 'file_read',
    args: {},
    status: 'called',
    ...overrides
  }
}

describe('useToolInfo (composables/useTool.ts)', () => {
  it('returns null for undefined tool ref argument', () => {
    const { result } = withSetup(() => useToolInfo(undefined))
    expect(result.toolInfo.value).toBeNull()
  })

  it('returns null when the ref itself holds undefined', () => {
    const { result } = withSetup(() => useToolInfo(ref(undefined)))
    expect(result.toolInfo.value).toBeNull()
  })

  describe('MCP tools (function starts with "mcp_")', () => {
    it('strips the mcp_ prefix and uses the mcp map entries', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ function: 'mcp_search', args: {} })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      const info = result.toolInfo.value

      expect(info).not.toBeNull()
      expect(info!.function).toBe('search')
      expect(info!.icon).toBe(TOOL_ICON_MAP['mcp'])
      expect(info!.name).toBe(i18n.global.t(TOOL_NAME_MAP['mcp'] ?? 'MCP Tool'))
    })

    it('uses the first arg value as functionArg when it is a short string', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ function: 'mcp_search', args: { query: 'short string' } })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      expect(result.toolInfo.value!.functionArg).toBe('short string')
    })

    it('JSON-stringifies and truncates a non-string first arg value', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ function: 'mcp_search', args: { data: { deeply: 'nested' } } })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      const expected = JSON.stringify({ deeply: 'nested' }).substring(0, 30) + '...'
      expect(result.toolInfo.value!.functionArg).toBe(expected)
    })

    it('functionArg is empty string when args is empty', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ function: 'mcp_search', args: {} })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      expect(result.toolInfo.value!.functionArg).toBe('')
    })
  })

  describe('non-MCP tools', () => {
    it('matches the real map entries for a known name/function pair (file/file_read)', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ name: 'file', function: 'file_read', args: { file: '/some/file.txt' } })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      const info = result.toolInfo.value

      expect(info).not.toBeNull()
      expect(info!.icon).toBe(TOOL_ICON_MAP['file'])
      expect(info!.name).toBe(i18n.global.t(TOOL_NAME_MAP['file']))
      expect(info!.function).toBe(i18n.global.t(TOOL_FUNCTION_MAP['file_read']))
      expect(info!.view).toBe(TOOL_COMPONENT_MAP['file'])
    })

    it('strips the leading /home/ubuntu/ from the file arg (file path-stripping branch)', () => {
      expect(TOOL_FUNCTION_ARG_MAP['file_read']).toBe('file')

      const tool = ref<ToolContent | undefined>(
        makeTool({
          name: 'file',
          function: 'file_read',
          args: { file: '/home/ubuntu/report.txt' }
        })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      expect(result.toolInfo.value!.functionArg).toBe('report.txt')
    })
  })

  describe('unknown tool name/function', () => {
    it('falls back to null icon, empty name, and raw function string', () => {
      const tool = ref<ToolContent | undefined>(
        makeTool({ name: 'nonexistent_name', function: 'nonexistent_function', args: {} })
      )
      const { result } = withSetup(() => useToolInfo(tool))
      const info = result.toolInfo.value

      expect(info).not.toBeNull()
      expect(info!.icon).toBeNull()
      expect(info!.name).toBe(i18n.global.t(''))
      expect(info!.function).toBe('nonexistent_function')
    })
  })
})
