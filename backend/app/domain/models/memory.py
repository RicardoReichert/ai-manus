import json
import logging
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.domain.models.message import LLMMessage, Role

logger = logging.getLogger(__name__)

# Rough chars-per-token ratio; conservative for mixed prose/code/JSON.
_CHARS_PER_TOKEN = 4

# Placeholder written over elided tool results. Kept as a ToolResult-shaped
# JSON string so downstream consumers can still parse the content.
_ELIDED_CONTENT = json.dumps(
    {"success": True, "message": "(result elided to save context)", "data": None}
)

# Placeholder for a superseded tagged message (e.g. an old plan-JSON dump —
# see `_elide_superseded_tagged_messages`). Plain text, not ToolResult-shaped,
# since these are USER-role messages, not tool results.
_ELIDED_TAGGED_CONTENT = "(superseded — see the latest snapshot below instead)"

# How much of an old assistant turn's own prose to keep once it's eligible
# for the (budget-gated) truncation pass. Chosen to keep enough for the
# model to recognize what it previously said without keeping full essays.
_ASSISTANT_KEEP_CHARS = 400
_ASSISTANT_TRUNCATION_SUFFIX = " … [earlier reasoning elided to save context]"


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate for context budgeting."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


class Memory(BaseModel):
    """Agent conversation memory with token-aware compaction.

    Messages are stored append-only; :meth:`compact` reclaims context budget
    in three passes over messages older than the ``keep_recent`` window,
    stopping as soon as the budget is met:

    1. Elide old tool results (oldest first) — always runs, even with no
       budget given, matching the historical unconditional per-step cleanup.
       Only ever shrinks content to a fixed placeholder, so it is always
       safe regardless of the model's context size.
    2. Elide all but the most recent message sharing a compaction ``tag``
       (see :attr:`app.domain.models.message.LLMMessage.tag`) — also always
       runs. A tagged message is understood to fully supersede every earlier
       message with the same tag (e.g. the planner's full plan-JSON dump),
       so this is lossless: nothing a model still needs is discarded.
    3. Truncate old assistant turns' own prose — the dominant context
       consumer once tool results are already elided, especially for a
       small model that narrates each step in the chat instead of writing
       long output to a file. This pass *does* discard information (older
       reasoning), so unlike passes 1-2 it only runs when there is an
       actual token budget to reclaim (``max_tokens`` given and still
       exceeded) — a large-context model's own prior reasoning is never
       truncated just because a step boundary was reached.

    None of the three passes ever touches ``tool_calls``, so tool-call/tool
    pairing required by LLM APIs is never broken, and the last
    ``keep_recent`` messages are never touched by any pass, preserving the
    model's most recent working context.
    """
    messages: List[LLMMessage] = []

    def add_message(self, message: LLMMessage) -> None:
        """Add message to memory"""
        self.messages.append(message)

    def add_messages(self, messages: List[LLMMessage]) -> None:
        """Add messages to memory"""
        self.messages.extend(messages)

    def get_messages(self) -> List[LLMMessage]:
        """Get all message history"""
        return self.messages

    def get_last_message(self) -> Optional[LLMMessage]:
        """Get the last message"""
        if len(self.messages) > 0:
            return self.messages[-1]
        return None

    def roll_back(self) -> None:
        """Roll back memory"""
        self.messages = self.messages[:-1]

    def estimate_tokens(self) -> int:
        """Estimate the total token footprint of the stored messages."""
        total = 0
        for message in self.messages:
            total += estimate_tokens(message.content)
            for tool_call in message.tool_calls:
                total += estimate_tokens(tool_call.name)
                total += estimate_tokens(json.dumps(tool_call.args, default=str))
        return total

    def _elide_old_tool_results(self, cutoff: int, max_tokens: int) -> None:
        for message in self.messages[:cutoff]:
            if message.role != Role.TOOL:
                continue
            if message.content == _ELIDED_CONTENT:
                continue
            message.content = _ELIDED_CONTENT
            logger.debug(f"Elided old tool result from memory: {message.name}")
            if max_tokens and self.estimate_tokens() <= max_tokens:
                return

    def _elide_superseded_tagged_messages(self, cutoff: int) -> None:
        """Keep only the most recent message for each compaction tag.

        Safe regardless of token budget: a tag marks a message as one that
        fully supersedes every earlier message carrying the same tag, so
        every earlier one is, by construction, redundant.
        """
        latest_index_by_tag: Dict[str, int] = {}
        for i, message in enumerate(self.messages[:cutoff]):
            if message.tag:
                latest_index_by_tag[message.tag] = i

        for i, message in enumerate(self.messages[:cutoff]):
            if not message.tag or i == latest_index_by_tag[message.tag]:
                continue
            if message.content == _ELIDED_TAGGED_CONTENT:
                continue
            message.content = _ELIDED_TAGGED_CONTENT
            logger.debug(f"Elided superseded '{message.tag}'-tagged message from memory")

    def _truncate_old_assistant_turns(self, cutoff: int, max_tokens: int) -> None:
        for message in self.messages[:cutoff]:
            if message.role != Role.ASSISTANT:
                continue
            if len(message.content) <= _ASSISTANT_KEEP_CHARS:
                continue
            if message.content.endswith(_ASSISTANT_TRUNCATION_SUFFIX):
                continue
            message.content = message.content[:_ASSISTANT_KEEP_CHARS] + _ASSISTANT_TRUNCATION_SUFFIX
            logger.debug("Truncated an old assistant turn's prose to save context")
            if self.estimate_tokens() <= max_tokens:
                return

    def compact(self, max_tokens: int = 0, keep_recent: int = 10) -> None:
        """Reclaim context budget from old messages. See the class docstring
        for the three-pass strategy.

        Args:
            max_tokens: Target context budget. ``0`` means "run the
                lossless passes (1-2) unconditionally, skip the lossy one
                (3)" — the unconditional per-step cleanup behavior.
            keep_recent: Number of most recent messages that are never
                touched, so the model keeps its working context.
        """
        if max_tokens and self.estimate_tokens() <= max_tokens:
            return

        cutoff = max(0, len(self.messages) - keep_recent)

        self._elide_old_tool_results(cutoff, max_tokens)
        self._elide_superseded_tagged_messages(cutoff)
        if max_tokens and self.estimate_tokens() <= max_tokens:
            return

        if max_tokens:
            self._truncate_old_assistant_turns(cutoff, max_tokens)

    @property
    def empty(self) -> bool:
        """Check if memory is empty"""
        return len(self.messages) == 0
