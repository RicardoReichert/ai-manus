export type TaskLogKind = 'message' | 'tool' | 'step' | 'plan' | 'error' | 'title' | 'wait' | 'done';

export interface TaskLogEntry {
  id: string;
  kind: TaskLogKind;
  label: string;
  detail?: string;
  timestamp: number;
}
