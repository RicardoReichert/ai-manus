from typing import List, Optional, Protocol

from app.domain.models.model_config import ModelConfig


class ModelConfigRepository(Protocol):
    """Repository interface for the admin-managed model registry."""

    async def list_all(self, enabled_only: bool = False) -> List[ModelConfig]:
        """All registered models, ordered by ``sort_order`` then name."""
        ...

    async def find_by_id(self, model_config_id: str) -> Optional[ModelConfig]:
        """Find one registered model by its registry id."""
        ...

    async def create(self, config: ModelConfig, api_key: Optional[str]) -> ModelConfig:
        """Persist a new model, encrypting ``api_key`` when provided."""
        ...

    async def update(
        self,
        model_config_id: str,
        config: ModelConfig,
        api_key: Optional[str] = None,
        clear_api_key: bool = False,
    ) -> Optional[ModelConfig]:
        """Update a model.

        ``api_key=None`` leaves the stored credential untouched (so a PATCH
        that does not resend the key does not wipe it); ``clear_api_key``
        removes it explicitly.
        """
        ...

    async def delete(self, model_config_id: str) -> bool:
        """Delete a model. Returns whether it existed."""
        ...

    async def get_api_key(self, model_config_id: str) -> Optional[str]:
        """Decrypt and return the stored credential, if any."""
        ...

    async def count(self) -> int:
        """How many models are registered (used to detect a fresh install)."""
        ...
