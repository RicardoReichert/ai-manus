"""TAREFA 4.1 — non-financial usage metrics for a task.

Pure aggregation over a session's already-persisted event log and file
list. No new collection, no I/O: everything here is derived from data the
agent loop already writes (StepEvent.step.duration_ms, ToolEvent.tool_name/
status, session.files). Deliberately excludes anything credit/cost-shaped.
"""
from typing import Any, Dict, List

from app.domain.models.event import AgentEvent, StepEvent, StepStatus, ToolEvent, ToolStatus
from app.domain.models.file import FileInfo


def compute_session_usage(events: List[AgentEvent], files: List[FileInfo]) -> Dict[str, Any]:
    # Keyed by step id so a re-planned/updated step's latest duration wins
    # instead of double-counting an earlier attempt at the same step.
    step_durations: Dict[str, int] = {}
    pages_viewed = 0
    commands_run = 0
    api_calls = 0

    for event in events:
        if isinstance(event, StepEvent) and event.status in (StepStatus.COMPLETED, StepStatus.FAILED):
            if event.step.duration_ms is not None:
                step_durations[event.step.id] = event.step.duration_ms
        elif isinstance(event, ToolEvent) and event.status == ToolStatus.CALLED:
            if event.tool_name == "browser":
                pages_viewed += 1
            elif event.tool_name == "shell":
                commands_run += 1
            elif event.tool_name == "mcp":
                api_calls += 1

    return {
        "worked_ms": sum(step_durations.values()),
        "pages_viewed": pages_viewed,
        "commands_run": commands_run,
        "api_calls": api_calls,
        # session.files is already the deduped, authoritative file list (see
        # BUG-2 investigation) — includes both agent-produced files and
        # files the user uploaded as input, since the data model doesn't
        # currently distinguish origin.
        "files_created": len(files or []),
    }
