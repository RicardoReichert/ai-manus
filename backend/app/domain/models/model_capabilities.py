"""Per-model capability profile.

Drives how the agent adapts to a given LLM: how many tools it can be shown
without degrading, whether its output needs grammar-constrained decoding to
be parseable, and how much context it can hold.

These are populated automatically from the built-in catalog
(:mod:`app.infrastructure.external.llm.model_catalog`) when an admin
registers a model, so nobody has to know or type them. They stay overridable
on the stored document because a self-hosted quantization can behave quite
differently from the reference weights it is named after.

Defaults describe a large, capable frontier model — so a model the catalog
does not recognize behaves exactly as the system did before capabilities
existed, and only models we know something about get adapted behavior.
"""
from typing import Optional

from pydantic import BaseModel, Field


class ModelCapabilities(BaseModel):
    """What a model can handle, and where it needs help."""

    supports_native_tools: bool = Field(
        default=True,
        description="Model exposes real function calling. False means the agent loop cannot rely on tool_calls.",
    )
    needs_guided_decoding: bool = Field(
        default=False,
        description=(
            "Constrain generation to the JSON schema (Ollama `format`, "
            "LM Studio grammars). Costs ~30-80% generation speed, so it is "
            "reserved for models known to emit unreliable tool arguments."
        ),
    )
    max_tools: Optional[int] = Field(
        default=None,
        description=(
            "Soft cap on tools exposed at once. None = no limit. Small models "
            "degrade measurably past ~10-20 tools, which is the single "
            "biggest driver of tool-calling failure for them."
        ),
    )
    context_window: Optional[int] = Field(
        default=None,
        description="Total context in tokens; drives the agent's memory-compaction budget. None = use global default.",
    )
    max_output_tokens: Optional[int] = Field(
        default=None,
        description="Cap for a single completion. None = use the global MAX_TOKENS setting.",
    )
    supports_parallel_tool_calls: bool = Field(
        default=True,
        description="Model can emit several tool calls in one turn without degrading.",
    )
    strip_thinking_from_history: bool = Field(
        default=False,
        description=(
            "Drop prior reasoning blocks when replaying history. Gemma 4 "
            "documents this explicitly — with the exception that thinking on "
            "tool-call turns must be preserved."
        ),
    )

    def tool_budget(self, available: int) -> int:
        """How many tools may be shown, given how many exist."""
        if self.max_tools is None:
            return available
        return min(available, self.max_tools)

    @property
    def is_constrained(self) -> bool:
        """Whether this model needs any small-model accommodation at all.

        Used to decide if the agent takes the adapted path (reduced tool
        surface, sub-agent delegation) or the unchanged large-model path.
        """
        return self.max_tools is not None or self.needs_guided_decoding
