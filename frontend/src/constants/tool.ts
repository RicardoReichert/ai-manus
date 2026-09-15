/**
 * Tool function mapping
 */
export const TOOL_FUNCTION_MAP: {[key: string]: string} = {
  // Shell tools
  "shell_exec": "Executing command",
  "shell_view": "Viewing command output",
  "shell_wait": "Waiting for command completion",
  "shell_write_to_process": "Writing data to process",
  "shell_kill_process": "Terminating process",
  
  // File tools
  "file_read": "Reading file",
  "file_write": "Writing file",
  "file_str_replace": "Replacing file content",
  "file_find_in_content": "Searching file content",
  "file_find_by_name": "Finding file",
  
  // Browser tools
  "browser_view": "Viewing webpage",
  "browser_navigate": "Navigating to webpage",
  "browser_restart": "Restarting browser",
  "browser_click": "Clicking element",
  "browser_input": "Entering text",
  "browser_move_mouse": "Moving mouse",
  "browser_press_key": "Pressing key",
  "browser_select_option": "Selecting option",
  "browser_scroll_up": "Scrolling up",
  "browser_scroll_down": "Scrolling down",
  "browser_console_exec": "Executing JS code",
  "browser_console_view": "Viewing console output",
  
  // Search tools
  "info_search_web": "Searching web",

  // Message tools
  "message_notify_user": "Sending notification",
  "message_ask_user": "Asking question",

  // Soft plan (single-loop) — timeline only; not a Computer panel tool
  "todo_write": "Updating plan",

  // Skills — progressive disclosure (L2 via tool result)
  "load_skill": "Loading skill",

  // Delegation tool (Lean tool profile — stands in for the whole browser toolkit)
  "browse_web": "Browsing web"
};

/**
 * Display name mapping for tool function parameters
 */
export const TOOL_FUNCTION_ARG_MAP: {[key: string]: string} = {
  "shell_exec": "command",
  "shell_view": "id",
  "shell_wait": "id",
  "shell_write_to_process": "input",
  "shell_kill_process": "id",
  "file_read": "file",
  "file_write": "file",
  "file_str_replace": "file",
  "file_find_in_content": "file",
  "file_find_by_name": "path",
  "browser_navigate": "url",
  "browser_restart": "url",
  "browser_click": "index",
  "browser_input": "text",
  "browser_move_mouse": "coordinate_x",
  "browser_press_key": "key",
  "browser_select_option": "option",
  "browser_scroll_up": "to_top",
  "browser_scroll_down": "to_bottom",
  "browser_console_exec": "javascript",
  "browser_console_view": "max_lines",
  "info_search_web": "query",
  "message_notify_user": "text",
  "message_ask_user": "text",
  "load_skill": "file",
  "browse_web": "task"
  // browser_view intentionally absent — the backend tool takes no parameters
};

/**
 * Tool name mapping
 */
export const TOOL_NAME_MAP: {[key: string]: string} = {
  "shell": "Terminal",
  "file": "File",
  "browser": "Browser",
  "search": "Information",
  "message": "Message",
  "mcp": "MCP Tool",
  "todo": "Plan",
  "skill": "Skill",
  // Lean tool profile: browsing delegated to a sub-agent, rendered like "browser"
  "delegation": "Browser"
};

import SearchIcon from '../components/icons/SearchIcon.vue';
import EditIcon from '../components/icons/EditIcon.vue';
import BrowserIcon from '../components/icons/BrowserIcon.vue';
import ShellIcon from '../components/icons/ShellIcon.vue';
import { ListTodo } from 'lucide-vue-next';

/**
 * Tool icon mapping
 */
export const TOOL_ICON_MAP: {[key: string]: any} = {
  "shell": ShellIcon,
  "file": EditIcon,
  "browser": BrowserIcon,
  "search": SearchIcon,
  "message": "",
  "todo": ListTodo,
  "mcp": SearchIcon,  // Reuses the search icon; no dedicated MCP icon exists yet
  "skill": EditIcon,
  "delegation": BrowserIcon
};

import ShellToolView from '@/components/toolViews/ShellToolView.vue';
import FileToolView from '@/components/toolViews/FileToolView.vue';
import SearchToolView from '@/components/toolViews/SearchToolView.vue';
import BrowserToolView from '@/components/toolViews/BrowserToolView.vue';
import McpToolView from '@/components/toolViews/McpToolView.vue';

/**
 * Mapping from tool names to components
 */
export const TOOL_COMPONENT_MAP: {[key: string]: any} = {
  "shell": ShellToolView,
  "file": FileToolView,
  "search": SearchToolView,
  "browser": BrowserToolView,
  "mcp": McpToolView,
  "skill": FileToolView,
  // The backend renders delegation's bookend events as BrowserToolContent
  // (see agent_task_runner.py), so the browser view already fits.
  "delegation": BrowserToolView
};

/**
 * Tools that can render in Manus's Computer panel.
 * Soft-plan / chat tools (todo, message) update the timeline or Plan panel
 * but must not steal the computer view — otherwise the panel shows inactive.
 */
export function isComputerPanelTool(toolName: string | undefined | null): boolean {
  if (!toolName) return false;
  return Object.prototype.hasOwnProperty.call(TOOL_COMPONENT_MAP, toolName);
}
