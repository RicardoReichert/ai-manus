import { apiClient, ApiResponse } from './client'

export interface ModelDescriptor {
  id: string
  name: string
  provider: string
  is_local?: boolean
  description?: string | null
}

export async function getAvailableModels(): Promise<ModelDescriptor[]> {
  const response = await apiClient.get<ApiResponse<ModelDescriptor[]>>('/models')
  return response.data.data || []
}
