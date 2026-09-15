"""A selectable LLM and everything the system needs to drive it.

Replaces the former ``ModelDescriptor`` (which lived in ``core.config`` and
was parsed from models.json). Registration now happens through the admin API
and is persisted in MongoDB, so this is a real domain entity rather than a
parsed config row.

``id`` is an opaque registry key — what a session persists in
``Session.model_name`` — while ``model`` is the real model name handed to the
provider SDK. Keeping them separate lets an operator rename a model in the UI
without invalidating every session that already points at it.
"""
from datetime import datetime, UTC
from typing import List, Optional

from pydantic import BaseModel, Field

from app.domain.models.model_capabilities import ModelCapabilities


class ModelConfig(BaseModel):
    """An admin-registered model.

    The plaintext credential is deliberately **not** a field: it lives
    encrypted on the document and is decrypted on demand by the registry, so
    it cannot leak by accidentally serializing this object into a response.
    """

    id: str
    name: str
    provider: str
    model: str
    base_url: Optional[str] = None
    is_local: bool = False
    description: Optional[str] = None
    enabled: bool = True
    sort_order: int = 0

    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    capabilities_auto_detected: bool = True

    tool_profile: str = "full"
    # Explicit allow-list of tool names. Empty means "whatever tool_profile
    # implies", so an admin who never touches the checkboxes still gets the
    # profile's behavior.
    enabled_tools: List[str] = Field(default_factory=list)

    # Present only for display ("…wxyz"); never the credential itself.
    api_key_hint: str = ""
    has_api_key: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
