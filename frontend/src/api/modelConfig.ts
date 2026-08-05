// Admin API for the model registry (Settings > Models). Every call here
// requires role=admin on the backend; regular users never hit this module —
// they consume the resulting list through api/model.ts's GET /models instead.
import { apiClient, ApiResponse } from './client'

export interface ModelCapabilities {
  supports_native_tools: boolean
  needs_guided_decoding: boolean
  max_tools: number | null
  context_window: number | null
  max_output_tokens: number | null
  supports_parallel_tool_calls: boolean
  strip_thinking_from_history: boolean
}

export type ToolProfile = 'full' | 'lean'

export interface ModelConfigEntry {
  id: string
  name: string
  provider: string
  model: string
  base_url: string | null
  is_local: boolean
  description: string | null
  enabled: boolean
  sort_order: number
  capabilities: ModelCapabilities
  capabilities_auto_detected: boolean
  tool_profile: ToolProfile
  enabled_tools: string[]
  // Never the credential itself — a masked suffix like "…wxyz", or "" if none stored.
  api_key_hint: string
  has_api_key: boolean
}

export interface CreateModelConfigInput {
  id: string
  name: string
  provider: string
  model: string
  base_url?: string | null
  api_key?: string | null
  is_local?: boolean
  description?: string | null
  enabled?: boolean
  sort_order?: number
  tool_profile?: ToolProfile
  enabled_tools?: string[]
}

export interface UpdateModelConfigInput {
  name?: string
  provider?: string
  model?: string
  base_url?: string | null
  api_key?: string | null
  is_local?: boolean
  description?: string | null
  enabled?: boolean
  sort_order?: number
  tool_profile?: ToolProfile
  enabled_tools?: string[]
}

export interface TestConnectionResult {
  ok: boolean
  error?: string | null
  latency_ms?: number | null
}

export interface ToolInfo {
  name: string
  toolkit: string
  description: string
}

export interface AvailableTools {
  tools: ToolInfo[]
  // profile name -> tool names selected by that profile with no admin
  // override — what the picker starts pre-checked as.
  profiles: Record<ToolProfile, string[]>
}

export async function listModelConfigs(): Promise<ModelConfigEntry[]> {
  const response = await apiClient.get<ApiResponse<{ models: ModelConfigEntry[] }>>('/admin/models')
  return response.data.data.models
}

export async function createModelConfig(input: CreateModelConfigInput): Promise<ModelConfigEntry> {
  const response = await apiClient.post<ApiResponse<ModelConfigEntry>>('/admin/models', input)
  return response.data.data
}

export async function updateModelConfig(id: string, input: UpdateModelConfigInput): Promise<ModelConfigEntry> {
  const response = await apiClient.patch<ApiResponse<ModelConfigEntry>>(`/admin/models/${encodeURIComponent(id)}`, input)
  return response.data.data
}

export async function deleteModelConfig(id: string): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/admin/models/${encodeURIComponent(id)}`)
}

export async function testModelConnection(id: string): Promise<TestConnectionResult> {
  const response = await apiClient.post<ApiResponse<TestConnectionResult>>(`/admin/models/${encodeURIComponent(id)}/test`)
  return response.data.data
}

export async function listAvailableTools(): Promise<AvailableTools> {
  const response = await apiClient.get<ApiResponse<AvailableTools>>('/admin/models/tools')
  return response.data.data
}

// Presets pre-fill provider/base_url/is_local for the common providers named
// in the request — an admin picks one and only has to fill in the model name
// and (if hosted) the API key.
export interface ModelProviderPreset {
  id: string
  label: string
  provider: string
  base_url: string | null
  is_local: boolean
  modelPlaceholder: string
}

export const MODEL_PROVIDER_PRESETS: ModelProviderPreset[] = [
  { id: 'openai', label: 'OpenAI', provider: 'openai', base_url: null, is_local: false, modelPlaceholder: 'gpt-4o' },
  { id: 'google_genai', label: 'Google Gemini', provider: 'google_genai', base_url: null, is_local: false, modelPlaceholder: 'gemini-2.5-flash' },
  { id: 'openrouter', label: 'OpenRouter', provider: 'openai', base_url: 'https://openrouter.ai/api/v1', is_local: false, modelPlaceholder: 'anthropic/claude-3.5-sonnet' },
  { id: 'lmstudio', label: 'LM Studio', provider: 'openai', base_url: 'http://localhost:1234/v1', is_local: true, modelPlaceholder: 'qwen3-4b-instruct-2507' },
  { id: 'ollama', label: 'Ollama', provider: 'ollama', base_url: 'http://localhost:11434', is_local: true, modelPlaceholder: 'qwen3:4b' },
  { id: 'custom', label: 'Custom', provider: 'openai', base_url: null, is_local: false, modelPlaceholder: 'model-name' },
]
