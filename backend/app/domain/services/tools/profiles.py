"""Tool profiles — which tools a model is shown.

Tool *count* is the dominant driver of tool-calling failure in small models:
accuracy degrades measurably past roughly 10-20 tools, and the effect is
strongest for the smallest ones. The full toolset here is ~25 tools before
MCP servers add more, which is well past that line.

Profiles cap what a given model sees:

* ``full`` — everything, exactly as before profiles existed. This is what
  every model gets unless an admin says otherwise, so large models are
  completely unaffected.
* ``lean`` — shell, file, message and search, plus a single delegation tool
  standing in for the whole browser toolkit. Browsing is not removed; it moves
  behind a sub-agent so the supervising model never holds 12 low-level browser
  tools in the same context as everything else.
* ``auto`` — not a static toolkit restriction of its own. It resolves to
  ``lean`` or ``full`` at the point the model is loaded, based on whether the
  model's capabilities mark it as constrained (see :func:`resolve_profile`).
  This is the default for newly-registered models so a fresh small-model
  registration gets a sane toolset without anyone remembering to flip a
  toggle; existing registrations keep whatever explicit value they already
  have.

An admin can override the profile's selection per model in the UI, because a
tool that causes hallucination in production needs to be switchable off
without a code change.
"""
from typing import Dict, List, Optional, Sequence

# Toolkits that make up the lean profile. Browser is deliberately absent: it
# is the largest toolkit (12 tools) and the one small models handle worst.
LEAN_TOOLKITS = ("shell", "file", "message", "search", "delegation")

PROFILE_FULL = "full"
PROFILE_LEAN = "lean"
PROFILE_AUTO = "auto"
VALID_PROFILES = (PROFILE_FULL, PROFILE_LEAN, PROFILE_AUTO)

# Retention order when a model's `max_tools` budget forces a cut below what
# its profile would otherwise show. Message tools stay first — a model that
# loses its ability to notify/ask the user degrades silently rather than
# loudly. Everything not listed here keeps its natural (dict-iteration)
# order after the ranked tools, so adding a new tool never requires touching
# this list for `full`-profile budgets to keep working.
TOOL_PRIORITY: Sequence[str] = (
    "message_notify_user",
    "message_ask_user",
    "shell_exec",
    "file_read",
    "file_write",
    "info_search_web",
    "browse_web",
    "file_str_replace",
    "shell_view",
    "file_find_by_name",
    "file_find_in_content",
    "shell_wait",
    "shell_write_to_process",
    "shell_kill_process",
    "browser_navigate",
    "browser_click",
    "browser_input",
    "browser_view",
    "browser_restart",
    "browser_scroll_down",
    "browser_scroll_up",
    "browser_press_key",
    "browser_select_option",
    "browser_move_mouse",
    "browser_console_view",
    "browser_console_exec",
)


def toolkits_for_profile(profile: str) -> Optional[Sequence[str]]:
    """Toolkit names allowed by a profile, or None for 'no restriction'."""
    if profile == PROFILE_LEAN:
        return LEAN_TOOLKITS
    return None


def is_valid_profile(profile: str) -> bool:
    return profile in VALID_PROFILES


def resolve_profile(profile: str, is_constrained: bool) -> str:
    """Resolve ``auto`` to a concrete profile using the model's capabilities.

    ``full`` and ``lean`` are explicit admin choices and always pass through
    unchanged — a human's stored decision must never be second-guessed here.
    Anything else (a stored ``auto``, an unset value, or an unrecognized
    string) resolves from ``is_constrained``
    (:attr:`~app.domain.models.model_capabilities.ModelCapabilities.is_constrained`),
    so ``auto`` behaves like a smart default rather than a third static
    profile, and a model the catalog knows nothing about still fails open to
    ``full`` (matching the pre-``auto`` behavior) rather than being silently
    starved of tools.
    """
    if profile in (PROFILE_FULL, PROFILE_LEAN):
        return profile
    return PROFILE_LEAN if is_constrained else PROFILE_FULL


def _apply_priority_budget(tool_names: List[str], max_tools: int) -> List[str]:
    """Keep the ``max_tools`` highest-priority tools, in their original order.

    Ranking comes from :data:`TOOL_PRIORITY`; any tool not listed there sorts
    after every ranked one, in the order it was encountered. The result
    preserves the *original* relative order of whatever survives the cut —
    only which tools are kept changes, not how they're ordered — so callers
    that depend on a stable ordering (schema generation, tests) aren't
    affected by the trim itself.
    """
    priority_rank = {name: rank for rank, name in enumerate(TOOL_PRIORITY)}
    order_by_rank = sorted(
        range(len(tool_names)),
        key=lambda i: (priority_rank.get(tool_names[i], len(TOOL_PRIORITY)), i),
    )
    kept_indexes = set(order_by_rank[:max_tools])
    return [name for i, name in enumerate(tool_names) if i in kept_indexes]


def select_tool_names(
    all_tools_by_toolkit: Dict[str, List[str]],
    profile: str,
    enabled_tools: Optional[Sequence[str]] = None,
    max_tools: Optional[int] = None,
) -> List[str]:
    """Resolve the concrete tool names a model should be shown.

    Args:
        all_tools_by_toolkit: toolkit name -> tool names available in it.
        profile: ``full``, ``lean``, or ``auto`` (treated as ``full`` here —
            callers resolve ``auto`` via :func:`resolve_profile` before this
            point, since only they know the model's capabilities).
        enabled_tools: explicit admin allow-list. Empty/None means "use the
            profile", so an admin who never opens the tool picker still gets
            sensible behavior. An explicit list is respected as-is and is
            *not* further cut by ``max_tools`` — the admin already made the
            call on exactly which tools to show.
        max_tools: soft cap applied only when ``enabled_tools`` is empty,
            trimming the profile's default toolset down using
            :data:`TOOL_PRIORITY`. None means no cap.

    The admin allow-list is intersected with what actually exists, so a tool
    removed from the code doesn't linger as a phantom entry in old configs.
    """
    allowed_toolkits = toolkits_for_profile(profile)

    from_profile: List[str] = []
    for toolkit_name, tool_names in all_tools_by_toolkit.items():
        if allowed_toolkits is not None and toolkit_name not in allowed_toolkits:
            continue
        from_profile.extend(tool_names)

    if enabled_tools:
        explicit = set(enabled_tools)
        return [name for name in from_profile if name in explicit]

    if max_tools is not None and len(from_profile) > max_tools:
        return _apply_priority_budget(from_profile, max_tools)

    return from_profile
