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
VALID_PROFILES = (PROFILE_FULL, PROFILE_LEAN)


def toolkits_for_profile(profile: str) -> Optional[Sequence[str]]:
    """Toolkit names allowed by a profile, or None for 'no restriction'."""
    if profile == PROFILE_LEAN:
        return LEAN_TOOLKITS
    return None


def is_valid_profile(profile: str) -> bool:
    return profile in VALID_PROFILES


def select_tool_names(
    all_tools_by_toolkit: Dict[str, List[str]],
    profile: str,
    enabled_tools: Optional[Sequence[str]] = None,
) -> List[str]:
    """Resolve the concrete tool names a model should be shown.

    Args:
        all_tools_by_toolkit: toolkit name -> tool names available in it.
        profile: ``full`` or ``lean``.
        enabled_tools: explicit admin allow-list. Empty/None means "use the
            profile", so an admin who never opens the tool picker still gets
            sensible behavior.

    The admin allow-list is intersected with what actually exists, so a tool
    removed from the code doesn't linger as a phantom entry in old configs.
    """
    allowed_toolkits = toolkits_for_profile(profile)

    from_profile: List[str] = []
    for toolkit_name, tool_names in all_tools_by_toolkit.items():
        if allowed_toolkits is not None and toolkit_name not in allowed_toolkits:
            continue
        from_profile.extend(tool_names)

    if not enabled_tools:
        return from_profile

    explicit = set(enabled_tools)
    return [name for name in from_profile if name in explicit]
