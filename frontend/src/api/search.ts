// Global search API service (TAREFA 16.1)
import { apiClient, ApiResponse } from './client';

export interface SearchResultItem {
  session_id: string;
  session_title: string | null;
  snippet: string;
  message_at: number | null;
}

export interface SearchResponse {
  results: SearchResultItem[];
}

export async function searchMessages(query: string, limit = 30): Promise<SearchResponse> {
  const response = await apiClient.get<ApiResponse<SearchResponse>>('/search', {
    params: { q: query, limit },
  });
  return response.data.data;
}
