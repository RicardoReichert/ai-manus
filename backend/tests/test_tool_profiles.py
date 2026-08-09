"""Unit tests for tool profiles.

Pure unit tests — no server, no toolkit instantiation. The important
guarantee here is non-regression: the ``full`` profile must expose exactly
what the system exposed before profiles existed.
"""
from app.domain.services.tools.profiles import (
    PROFILE_FULL,
    PROFILE_LEAN,
    is_valid_profile,
    select_tool_names,
    toolkits_for_profile,
)

# Mirrors the real toolkit shape: browser is by far the largest.
TOOLKITS = {
    "shell": ["shell_exec", "shell_view", "shell_wait", "shell_write_to_process", "shell_kill_process"],
    "browser": [
        "browser_view", "browser_navigate", "browser_click", "browser_input",
        "browser_move_mouse", "browser_press_key", "browser_select_option",
        "browser_scroll_up", "browser_scroll_down", "browser_console_exec",
        "browser_console_view", "browser_save_image",
    ],
    "file": ["file_read", "file_write", "file_str_replace", "file_find_in_content", "file_find_by_name"],
    "message": ["message_notify_user", "message_ask_user"],
    "search": ["search_web"],
    "delegation": ["browse_web"],
}


class TestFullProfile:
    def test_full_exposes_every_tool(self):
        """Non-regression guard: large models must see exactly what they did."""
        selected = select_tool_names(TOOLKITS, PROFILE_FULL)
        expected = [name for names in TOOLKITS.values() for name in names]
        assert sorted(selected) == sorted(expected)

    def test_full_has_no_toolkit_restriction(self):
        assert toolkits_for_profile(PROFILE_FULL) is None


class TestLeanProfile:
    def test_lean_excludes_the_browser_toolkit(self):
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN)
        assert not any(name.startswith("browser_") for name in selected)

    def test_lean_keeps_the_delegation_tool(self):
        """Browsing is delegated, not lost."""
        assert "browse_web" in select_tool_names(TOOLKITS, PROFILE_LEAN)

    def test_lean_keeps_core_work_tools(self):
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN)
        for expected in ("shell_exec", "file_write", "message_ask_user", "search_web"):
            assert expected in selected, expected

    def test_lean_fits_a_small_model_budget(self):
        """The whole point: stay near the ~10-tool degradation threshold.

        14 core tools + 1 delegation is a big drop from 26 and, crucially,
        removes the 12 lowest-level ones.
        """
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN)
        full = select_tool_names(TOOLKITS, PROFILE_FULL)
        assert len(selected) < len(full) / 1.5


class TestAdminOverride:
    def test_explicit_allow_list_narrows_the_profile(self):
        selected = select_tool_names(
            TOOLKITS, PROFILE_LEAN, enabled_tools=["shell_exec", "file_read"]
        )
        assert sorted(selected) == ["file_read", "shell_exec"]

    def test_empty_allow_list_means_use_the_profile(self):
        """An admin who never opens the picker still gets sane behavior."""
        assert select_tool_names(TOOLKITS, PROFILE_LEAN, enabled_tools=[]) == \
            select_tool_names(TOOLKITS, PROFILE_LEAN)

    def test_allow_list_cannot_re_add_what_the_profile_excluded(self):
        """Otherwise 'lean' would stop meaning anything."""
        selected = select_tool_names(
            TOOLKITS, PROFILE_LEAN, enabled_tools=["shell_exec", "browser_click"]
        )
        assert "browser_click" not in selected

    def test_stale_tool_names_are_ignored(self):
        """A tool deleted from the code must not linger in old configs."""
        selected = select_tool_names(
            TOOLKITS, PROFILE_FULL, enabled_tools=["shell_exec", "tool_that_no_longer_exists"]
        )
        assert selected == ["shell_exec"]


class TestValidation:
    def test_known_profiles_validate(self):
        assert is_valid_profile(PROFILE_FULL)
        assert is_valid_profile(PROFILE_LEAN)

    def test_unknown_profile_is_rejected(self):
        assert not is_valid_profile("turbo")

    def test_unknown_profile_falls_back_to_unrestricted(self):
        """Fail open, not closed: a bad value must not silently gag the agent."""
        assert toolkits_for_profile("turbo") is None
