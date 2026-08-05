"""Admin API schemas for the model registry.

The credential is strictly write-only across this boundary: requests may
carry ``api_key``, responses never do — only ``api_key_hint`` (e.g. "…wxyz")
so an operator can tell which key is stored.
"""
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.domain.models.model_capabilities import ModelCapabilities
from app.domain.models.model_config import ModelConfig

# The registry id is embedded as a single URL path segment on every route but
# create (GET/PATCH/DELETE/test all key off it), so it must be one path
# segment's worth of characters. In particular no "/": a provider's real
# model name legitimately contains one (e.g. "google/gemma-4-e4b",
# OpenRouter's "anthropic/claude-3.5-sonnet") — that belongs in `model`, not
# `id` — but if it ends up in `id`, FastAPI reads it as *two* path segments
# and every follow-up action 404s despite creation having just succeeded.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_registry_id(value: str) -> str:
    if not _ID_PATTERN.match(value):
        raise ValueError(
            "must contain only letters, numbers, '.', '_', '-' (no '/' or spaces) — "
            "it becomes part of a URL. Put the provider's real model name, "
            "slashes included, in the Model field instead."
        )
    return value


class ModelCapabilitiesSchema(BaseModel):
    """Capabilities as exposed to the admin UI (same shape as the domain model)."""
    supports_native_tools: bool = True
    needs_guided_decoding: bool = False
    max_tools: Optional[int] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_parallel_tool_calls: bool = True
    strip_thinking_from_history: bool = False


class CreateModelConfigRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: Optional[str] = None
    api_key: Optional[str] = None          # write-only
    is_local: bool = False
    description: Optional[str] = None
    enabled: bool = True
    sort_order: int = 0
    # Omit to auto-fill from the built-in catalog — the normal path, so an
    # admin never has to know a model's tool-calling quirks.
    capabilities: Optional[ModelCapabilitiesSchema] = None
    tool_profile: str = "full"
    enabled_tools: List[str] = Field(default_factory=list)

    _validate_id = field_validator("id")(_validate_registry_id)


class UpdateModelConfigRequest(BaseModel):
    """All fields optional — a PATCH only changes what it sends.

    Notably, omitting ``api_key`` keeps the stored credential; clearing it
    requires the explicit ``clear_api_key`` flag, so an edit to an unrelated
    field can never silently drop a key.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=64)
    model: Optional[str] = Field(default=None, min_length=1, max_length=256)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    clear_api_key: bool = False
    is_local: Optional[bool] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None
    capabilities: Optional[ModelCapabilitiesSchema] = None
    tool_profile: Optional[str] = None
    enabled_tools: Optional[List[str]] = None


class ModelConfigResponse(BaseModel):
    """A registered model as returned to the admin UI. Never carries a key."""
    id: str
    name: str
    provider: str
    model: str
    base_url: Optional[str] = None
    is_local: bool
    description: Optional[str] = None
    enabled: bool
    sort_order: int
    capabilities: ModelCapabilitiesSchema
    capabilities_auto_detected: bool
    tool_profile: str
    enabled_tools: List[str]
    api_key_hint: str
    has_api_key: bool

    @staticmethod
    def from_domain(config: ModelConfig) -> "ModelConfigResponse":
        return ModelConfigResponse(
            id=config.id,
            name=config.name,
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            is_local=config.is_local,
            description=config.description,
            enabled=config.enabled,
            sort_order=config.sort_order,
            capabilities=ModelCapabilitiesSchema(**config.capabilities.model_dump()),
            capabilities_auto_detected=config.capabilities_auto_detected,
            tool_profile=config.tool_profile,
            enabled_tools=list(config.enabled_tools),
            api_key_hint=config.api_key_hint,
            has_api_key=config.has_api_key,
        )


class ListModelConfigsResponse(BaseModel):
    models: List[ModelConfigResponse]


class TestModelConnectionResponse(BaseModel):
    """Result of probing a model, so a broken credential is caught on save."""
    ok: bool
    error: Optional[str] = None
    latency_ms: Optional[int] = None


class ToolInfo(BaseModel):
    """One callable tool, for the per-model tool picker."""
    name: str
    toolkit: str
    description: str


class AvailableToolsResponse(BaseModel):
    tools: List[ToolInfo]
    profiles: dict  # profile name -> list of tool names


def capabilities_from_schema(schema: ModelCapabilitiesSchema) -> ModelCapabilities:
    return ModelCapabilities(**schema.model_dump())
