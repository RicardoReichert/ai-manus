"""Unit tests for tool profiles.

Pure unit tests — no server, no toolkit instantiation. The important
guarantee here is non-regression: the ``full`` profile must expose exactly
what the system exposed before profiles existed.
"""
from app.domain.services.tools.profiles import (
    PROFILE_AUTO,
    PROFILE_FULL,
    PROFILE_LEAN,
    TOOL_PRIORITY,
    is_valid_profile,
    resolve_profile,
    select_tool_names,
    toolkits_for_profile,
)

# Mirrors the real toolkit shape: browser is by far the largest.
TOOLKITS = {
    "shell": ["shell_exec", "shell_view", "shell_wait", "shell_write_to_process", "shell_kill_process"],
    "browser": [
        "browser_view", "browser_navigate", "browser_restart", "browser_click",
        "browser_input", "browser_move_mouse", "browser_press_key", "browser_select_option",
        "browser_scroll_up", "browser_scroll_down", "browser_console_exec",
        "browser_console_view",
    ],
    "file": ["file_read", "file_write", "file_str_replace", "file_find_in_content", "file_find_by_name"],
    "message": ["message_notify_user", "message_ask_user"],
    "search": ["info_search_web"],
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
        for expected in ("shell_exec", "file_write", "message_ask_user", "info_search_web"):
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

    def test_auto_profile_validates(self):
        assert is_valid_profile(PROFILE_AUTO)

    def test_unknown_profile_is_rejected(self):
        assert not is_valid_profile("turbo")

    def test_unknown_profile_falls_back_to_unrestricted(self):
        """Fail open, not closed: a bad value must not silently gag the agent."""
        assert toolkits_for_profile("turbo") is None


class TestMaxToolsBudget:
    def test_budget_trims_the_full_profile(self):
        selected = select_tool_names(TOOLKITS, PROFILE_FULL, max_tools=3)
        assert len(selected) == 3

    def test_budget_keeps_the_highest_priority_tools(self):
        selected = select_tool_names(TOOLKITS, PROFILE_FULL, max_tools=2)
        assert set(selected) == {"message_notify_user", "message_ask_user"}

    def test_budget_larger_than_available_is_a_no_op(self):
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN, max_tools=1000)
        assert selected == select_tool_names(TOOLKITS, PROFILE_LEAN)

    def test_none_budget_is_unlimited(self):
        assert select_tool_names(TOOLKITS, PROFILE_FULL, max_tools=None) == \
            select_tool_names(TOOLKITS, PROFILE_FULL)

    def test_output_survives_a_tight_budget_via_priority(self):
        """Message tools rank first so a starved model can still talk to the user."""
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN, max_tools=1)
        assert selected == ["message_notify_user"]

    def test_explicit_enabled_tools_are_not_further_cut_by_max_tools(self):
        """An admin's explicit picks are respected as-is, budget or not."""
        selected = select_tool_names(
            TOOLKITS, PROFILE_FULL,
            enabled_tools=["shell_exec", "file_read", "file_write"],
            max_tools=1,
        )
        assert sorted(selected) == ["file_read", "file_write", "shell_exec"]

    def test_budget_preserves_original_relative_order(self):
        selected = select_tool_names(TOOLKITS, PROFILE_LEAN, max_tools=4)
        full_lean = select_tool_names(TOOLKITS, PROFILE_LEAN)
        assert selected == [name for name in full_lean if name in selected]

    def test_every_tool_priority_entry_is_a_real_tool(self):
        """Guards against typos in the priority list going unnoticed."""
        all_names = {name for names in TOOLKITS.values() for name in names}
        for name in TOOL_PRIORITY:
            assert name in all_names, f"{name!r} in TOOL_PRIORITY is not a real tool"


class TestResolveProfile:
    def test_explicit_full_passes_through_regardless_of_capabilities(self):
        assert resolve_profile(PROFILE_FULL, is_constrained=True) == PROFILE_FULL

    def test_explicit_lean_passes_through_regardless_of_capabilities(self):
        assert resolve_profile(PROFILE_LEAN, is_constrained=False) == PROFILE_LEAN

    def test_auto_resolves_to_lean_when_constrained(self):
        assert resolve_profile(PROFILE_AUTO, is_constrained=True) == PROFILE_LEAN

    def test_auto_resolves_to_full_when_unconstrained(self):
        assert resolve_profile(PROFILE_AUTO, is_constrained=False) == PROFILE_FULL

    def test_unrecognized_value_behaves_like_auto(self):
        """A stale/invalid stored profile fails open based on capabilities,
        not to a fixed profile — matches toolkits_for_profile's own
        fail-open-to-unrestricted behavior when unconstrained."""
        assert resolve_profile("not-a-real-profile", is_constrained=False) == PROFILE_FULL
        assert resolve_profile("not-a-real-profile", is_constrained=True) == PROFILE_LEAN
