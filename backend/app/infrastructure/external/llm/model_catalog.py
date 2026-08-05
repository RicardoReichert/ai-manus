"""Built-in capability catalog for known models.

An admin registering a model should not have to know whether it does native
function calling, how many tools it tolerates, or that it needs constrained
decoding. This table answers that from the model name alone, so the UI can
auto-fill capabilities and the agent can adapt without manual tuning.

Entries reflect published capabilities as of 2026-08:

* **Qwen3-4B** — top sub-7B on BFCL v4 ("high 80s"), unusually strong
  tool-calling priors, notably good at parallel calls.
* **Gemma 4 E4B** — native structured tool use, 128K context, 4.5B effective
  params. Google documents that prior thinking must be dropped when replaying
  history, *except* on tool-call turns.
* **Phi-4-Mini** — capable but the weakest of the three on BFCL ("low-to-mid
  80s"), so it gets the tightest tool budget and guided decoding.

The shared constraint for all of them is tool count, not tool *ability*:
measured degradation sets in past roughly 10-20 tools and hits small models
hardest. Hence ``max_tools`` rather than ``supports_native_tools=False``.
"""
import logging
import re
from typing import List, Optional, Tuple

from app.domain.models.model_capabilities import ModelCapabilities

logger = logging.getLogger(__name__)

# Small models: capable of native tool calling, but need a reduced tool
# surface. 8 leaves room for the shell/file/message/search core plus the
# output tool while staying under the documented degradation threshold.
_SMALL_MODEL_TOOL_BUDGET = 8

# Unknown *local* models are assumed small: someone pointing at LM Studio or
# Ollama is usually running a quantized 4-14B, and being wrong in this
# direction costs a little capability, while being wrong the other way makes
# the agent fail outright.
_UNKNOWN_LOCAL = ModelCapabilities(
    supports_native_tools=True,
    needs_guided_decoding=True,
    max_tools=_SMALL_MODEL_TOOL_BUDGET,
    context_window=32000,
    supports_parallel_tool_calls=False,
)

# (regex over the normalized model name, capabilities)
# Ordered: the first match wins, so put specific patterns before general ones.
_CATALOG: List[Tuple[re.Pattern, ModelCapabilities]] = [
    # ---- Small / on-device -------------------------------------------------
    (
        re.compile(r"^qwen3[.\-_]?4b"),
        ModelCapabilities(
            supports_native_tools=True,
            needs_guided_decoding=False,  # strongest tool-calling priors in its class
            max_tools=_SMALL_MODEL_TOOL_BUDGET,
            context_window=262144,
            supports_parallel_tool_calls=True,
        ),
    ),
    (
        re.compile(r"^gemma[.\-_]?4[.\-_]?e4b"),
        ModelCapabilities(
            supports_native_tools=True,
            needs_guided_decoding=False,  # native function-call special tokens
            max_tools=_SMALL_MODEL_TOOL_BUDGET,
            context_window=128000,
            supports_parallel_tool_calls=False,
            strip_thinking_from_history=True,
        ),
    ),
    (
        re.compile(r"^gemma[.\-_]?3n[.\-_]?e[24]b"),
        ModelCapabilities(
            supports_native_tools=False,  # 3n has no documented native tool use
            needs_guided_decoding=True,
            max_tools=_SMALL_MODEL_TOOL_BUDGET,
            context_window=32000,
            supports_parallel_tool_calls=False,
        ),
    ),
    (
        re.compile(r"^phi[.\-_]?4[.\-_]?mini"),
        ModelCapabilities(
            supports_native_tools=True,
            needs_guided_decoding=True,  # weakest BFCL of the three
            max_tools=_SMALL_MODEL_TOOL_BUDGET,
            context_window=128000,
            supports_parallel_tool_calls=False,
        ),
    ),
    # NOTE: generic parameter-size detection is handled separately in
    # _size_based_capabilities(), not as a pattern here, so that it applies
    # to the unknown-model fallback too (a local 70B must not be treated as
    # small just because it is unrecognized).
    # ---- Large / frontier --------------------------------------------------
    # Listed so the UI can say "recognized" and so the generic small-parameter
    # rule above can never accidentally capture them.
    (re.compile(r"^gpt[.\-_]?4o"), ModelCapabilities(context_window=128000)),
    (re.compile(r"^gpt[.\-_]?[45]"), ModelCapabilities(context_window=128000)),
    (re.compile(r"^o[1-4](?:[.\-_]|$)"), ModelCapabilities(context_window=200000)),
    (re.compile(r"^gemini[.\-_]?[12]\.[05]"), ModelCapabilities(context_window=1000000)),
    (re.compile(r"^gemini[.\-_]?[23]"), ModelCapabilities(context_window=1000000)),
    (re.compile(r"^claude"), ModelCapabilities(context_window=200000)),
    (re.compile(r"^deepseek"), ModelCapabilities(context_window=128000)),
    (re.compile(r"^qwen3[.\-_]?(?:32b|72b|max|plus)"), ModelCapabilities(context_window=131072)),
]


def _normalize(model: str) -> str:
    """Strip vendor prefixes and runtime tags so variants match one entry.

    ``google/gemma-4-e4b-it:latest`` and ``gemma-4-e4b-it-q4_k_m`` both need
    to resolve to the same catalog row.
    """
    name = (model or "").strip().lower()
    if "/" in name:  # OpenRouter / HuggingFace style "vendor/model"
        name = name.rsplit("/", 1)[-1]
    if ":" in name:  # Ollama style "model:tag"
        name = name.split(":", 1)[0]
    return name


def _match(model: str) -> Optional[ModelCapabilities]:
    name = _normalize(model)
    if not name:
        return None
    for pattern, caps in _CATALOG:
        if pattern.search(name):
            return caps
    return None


# Matches a parameter-count tag: "-4b", "_13b", "3.8b", "a3b" (MoE active).
_PARAM_SIZE_RE = re.compile(r"(?:^|[.\-_a-z])(\d{1,3}(?:\.\d)?)b(?:[.\-_]|$)")

# Above this many billion parameters, a model is treated as full-capability.
# Chosen between the largest models that reliably need help (~14B) and the
# smallest that reliably do not (~24-32B).
_LARGE_MODEL_THRESHOLD_B = 20.0


def _extract_param_billions(name: str) -> Optional[float]:
    """Best-effort parameter count from a model name, in billions.

    Local model names almost always carry it ("qwen3-4b", "llama-3.1-70b").
    Returns the largest match, since names often contain other numbers
    ("llama-3.1-70b" → 70, not 3.1).
    """
    sizes = [float(m) for m in _PARAM_SIZE_RE.findall(name)]
    return max(sizes) if sizes else None


def _size_based_capabilities(name: str) -> Optional[ModelCapabilities]:
    """Infer capabilities from a parameter-count tag in the name.

    Applies to models the catalog does not list explicitly, so that a local
    70B is not lumped in with a local 4B just because neither is catalogued.
    """
    size = _extract_param_billions(name)
    if size is None:
        return None
    if size >= _LARGE_MODEL_THRESHOLD_B:
        # Large enough to behave like a frontier model for tool use; still
        # give it a modest context default since we cannot know the real one.
        return ModelCapabilities(context_window=32000)
    return ModelCapabilities(
        supports_native_tools=True,
        needs_guided_decoding=True,
        max_tools=_SMALL_MODEL_TOOL_BUDGET,
        context_window=32000,
        supports_parallel_tool_calls=False,
    )


def is_known_model(model: str) -> bool:
    """Whether the catalog recognizes this model name explicitly.

    The admin UI uses this to say whether capabilities were auto-detected or
    inferred/defaulted. A model matched only by its parameter-count tag is
    *not* "known" — the number is a heuristic, not a catalog entry.
    """
    return _match(model) is not None


def lookup_capabilities(model: str, is_local: bool = False) -> ModelCapabilities:
    """Resolve capabilities for a model name.

    Resolution order:

    1. Explicit catalog entry (most precise).
    2. Parameter-count tag in the name — so an uncatalogued ``llama-3.1-70b``
       is treated as capable while ``mistral-7b`` is treated as small.
    3. Local endpoint with no size hint → conservative small profile, since
       LM Studio / Ollama usually front a quantized small model.
    4. Otherwise the permissive default, identical to the system's behavior
       before capabilities existed (no regression for hosted models).

    Returns a copy, so a caller mutating the result cannot corrupt the table.
    """
    matched = _match(model)
    if matched is not None:
        return matched.model_copy(deep=True)

    inferred = _size_based_capabilities(_normalize(model))
    if inferred is not None:
        logger.info(
            "Model %r is not catalogued; inferred capabilities from its "
            "parameter-count tag (max_tools=%s).",
            model,
            inferred.max_tools,
        )
        return inferred

    if is_local:
        logger.info(
            "Model %r is not catalogued and carries no size hint, but is "
            "local; assuming a small-model profile.",
            model,
        )
        return _UNKNOWN_LOCAL.model_copy(deep=True)

    logger.info(
        "Model %r is not in the capability catalog; assuming full capability.",
        model,
    )
    return ModelCapabilities()
