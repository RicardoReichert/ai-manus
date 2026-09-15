"""Unit tests for TAREFA 4.1 — compute_session_usage() pure aggregation.

No running server needed — this hits the domain function directly with
synthetic events, not the API. See test_session_rating.py for the
integration-level rating/usage-endpoint tests.
"""
from datetime import datetime, timedelta, timezone

from app.domain.models.event import StepEvent, StepStatus, ToolEvent, ToolStatus
from app.domain.models.plan import Step, ExecutionStatus
from app.domain.models.file import FileInfo
from app.domain.services.session_usage import compute_session_usage


def make_step(step_id: str, started_ago_ms: int, duration_ms: int) -> Step:
    now = datetime.now(timezone.utc)
    started = now - timedelta(milliseconds=started_ago_ms)
    return Step(
        id=step_id,
        description="do something",
        status=ExecutionStatus.COMPLETED,
        started_at=started,
        finished_at=started + timedelta(milliseconds=duration_ms),
    )


def tool_event(tool_name: str, status: ToolStatus = ToolStatus.CALLED) -> ToolEvent:
    return ToolEvent(
        tool_call_id="call-1",
        tool_name=tool_name,
        function_name=f"{tool_name}_action",
        function_args={},
        status=status,
    )


class TestComputeSessionUsage:
    def test_empty_session_is_all_zeros(self):
        result = compute_session_usage(events=[], files=[])
        assert result == {
            "worked_ms": 0,
            "pages_viewed": 0,
            "commands_run": 0,
            "api_calls": 0,
            "files_created": 0,
        }

    def test_sums_completed_step_durations(self):
        events = [
            StepEvent(status=StepStatus.COMPLETED, step=make_step("1", 5000, 3000)),
            StepEvent(status=StepStatus.COMPLETED, step=make_step("2", 2000, 1500)),
        ]
        result = compute_session_usage(events, files=[])
        assert result["worked_ms"] == 4500

    def test_failed_step_still_counts_its_duration(self):
        step = make_step("1", 1000, 900)
        step.status = ExecutionStatus.FAILED
        events = [StepEvent(status=StepStatus.FAILED, step=step)]
        result = compute_session_usage(events, files=[])
        assert result["worked_ms"] == 900

    def test_started_only_step_contributes_nothing_yet(self):
        step = Step(id="1", description="x", status=ExecutionStatus.RUNNING)
        events = [StepEvent(status=StepStatus.STARTED, step=step)]
        result = compute_session_usage(events, files=[])
        assert result["worked_ms"] == 0

    def test_replanned_step_counts_once_using_latest_duration(self):
        """Same step id completed twice (re-planned) — must not double count."""
        events = [
            StepEvent(status=StepStatus.COMPLETED, step=make_step("1", 5000, 1000)),
            StepEvent(status=StepStatus.COMPLETED, step=make_step("1", 2000, 1800)),
        ]
        result = compute_session_usage(events, files=[])
        assert result["worked_ms"] == 1800

    def test_counts_tool_calls_by_kind(self):
        events = [
            tool_event("browser"),
            tool_event("browser"),
            tool_event("shell"),
            tool_event("mcp"),
            tool_event("file"),  # not counted in any of the three buckets
            tool_event("message"),  # not counted
        ]
        result = compute_session_usage(events, files=[])
        assert result["pages_viewed"] == 2
        assert result["commands_run"] == 1
        assert result["api_calls"] == 1

    def test_only_called_status_counts_not_calling(self):
        events = [tool_event("shell", status=ToolStatus.CALLING)]
        result = compute_session_usage(events, files=[])
        assert result["commands_run"] == 0

    def test_files_created_is_session_files_count(self):
        files = [
            FileInfo(file_id="a", filename="report.md"),
            FileInfo(file_id="b", filename="chart.png"),
        ]
        result = compute_session_usage(events=[], files=files)
        assert result["files_created"] == 2

    def test_no_credit_shaped_keys_anywhere_in_the_result(self):
        result = compute_session_usage(events=[], files=[])
        assert not any("credit" in key.lower() for key in result)
