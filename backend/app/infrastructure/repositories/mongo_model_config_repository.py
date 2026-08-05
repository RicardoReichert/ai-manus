import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.domain.models.model_capabilities import ModelCapabilities
from app.domain.models.model_config import ModelConfig
from app.domain.repositories.model_config_repository import ModelConfigRepository
from app.infrastructure.models.documents import ModelConfigDocument
from app.infrastructure.security import secret_box

logger = logging.getLogger(__name__)


class MongoModelConfigRepository(ModelConfigRepository):
    """MongoDB implementation of the model registry.

    Credentials are encrypted on write and only decrypted through the
    explicit :meth:`get_api_key` call, so the domain objects this returns can
    be serialized into API responses without risk of leaking a key.
    """

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(doc: ModelConfigDocument) -> ModelConfig:
        try:
            capabilities = ModelCapabilities(**(doc.capabilities or {}))
        except Exception as e:
            # A capability set written by a newer/older version must not make
            # the whole model unusable — fall back to permissive defaults.
            logger.warning(
                "Model %s has unreadable capabilities (%s); using defaults",
                doc.model_config_id, e,
            )
            capabilities = ModelCapabilities()

        return ModelConfig(
            id=doc.model_config_id,
            name=doc.name,
            provider=doc.provider,
            model=doc.model,
            base_url=doc.base_url,
            is_local=doc.is_local,
            description=doc.description,
            enabled=doc.enabled,
            sort_order=doc.sort_order,
            capabilities=capabilities,
            capabilities_auto_detected=doc.capabilities_auto_detected,
            tool_profile=doc.tool_profile,
            enabled_tools=list(doc.enabled_tools or []),
            api_key_hint=doc.api_key_hint or "",
            has_api_key=doc.api_key_encrypted is not None,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    @staticmethod
    def _apply_to_doc(doc: ModelConfigDocument, config: ModelConfig) -> None:
        doc.name = config.name
        doc.provider = config.provider
        doc.model = config.model
        doc.base_url = config.base_url
        doc.is_local = config.is_local
        doc.description = config.description
        doc.enabled = config.enabled
        doc.sort_order = config.sort_order
        doc.capabilities = config.capabilities.model_dump()
        doc.capabilities_auto_detected = config.capabilities_auto_detected
        doc.tool_profile = config.tool_profile
        doc.enabled_tools = list(config.enabled_tools or [])
        doc.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_all(self, enabled_only: bool = False) -> List[ModelConfig]:
        query = ModelConfigDocument.find(ModelConfigDocument.enabled == True) if enabled_only \
            else ModelConfigDocument.find_all()  # noqa: E712 (Beanie needs ==)
        docs = await query.sort("+sort_order", "+name").to_list()
        return [self._to_domain(d) for d in docs]

    async def find_by_id(self, model_config_id: str) -> Optional[ModelConfig]:
        doc = await ModelConfigDocument.find_one(
            ModelConfigDocument.model_config_id == model_config_id
        )
        return self._to_domain(doc) if doc else None

    async def count(self) -> int:
        return await ModelConfigDocument.find_all().count()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def create(self, config: ModelConfig, api_key: Optional[str]) -> ModelConfig:
        doc = ModelConfigDocument(
            model_config_id=config.id,
            name=config.name,
            provider=config.provider,
            model=config.model,
        )
        self._apply_to_doc(doc, config)
        doc.created_at = datetime.now(timezone.utc)
        if api_key:
            doc.api_key_encrypted = secret_box.encrypt(api_key)
            doc.api_key_hint = secret_box.build_hint(api_key)
        await doc.insert()
        logger.info("Registered model %s (%s/%s)", config.id, config.provider, config.model)
        return self._to_domain(doc)

    async def update(
        self,
        model_config_id: str,
        config: ModelConfig,
        api_key: Optional[str] = None,
        clear_api_key: bool = False,
    ) -> Optional[ModelConfig]:
        doc = await ModelConfigDocument.find_one(
            ModelConfigDocument.model_config_id == model_config_id
        )
        if not doc:
            return None

        self._apply_to_doc(doc, config)

        if clear_api_key:
            doc.api_key_encrypted = None
            doc.api_key_hint = ""
        elif api_key:
            doc.api_key_encrypted = secret_box.encrypt(api_key)
            doc.api_key_hint = secret_box.build_hint(api_key)
        # else: leave the existing credential untouched

        await doc.save()
        logger.info("Updated model %s", model_config_id)
        return self._to_domain(doc)

    async def delete(self, model_config_id: str) -> bool:
        doc = await ModelConfigDocument.find_one(
            ModelConfigDocument.model_config_id == model_config_id
        )
        if not doc:
            return False
        await doc.delete()
        logger.info("Deleted model %s", model_config_id)
        return True

    async def get_api_key(self, model_config_id: str) -> Optional[str]:
        doc = await ModelConfigDocument.find_one(
            ModelConfigDocument.model_config_id == model_config_id
        )
        if not doc or doc.api_key_encrypted is None:
            return None
        try:
            return secret_box.decrypt(doc.api_key_encrypted)
        except secret_box.SecretDecryptionError:
            # Key rotated or ciphertext corrupted. Surfacing None lets the
            # caller fall back / report a clean error instead of a 500.
            logger.error(
                "Credential for model %s could not be decrypted; "
                "re-enter it in Settings > Models.",
                model_config_id,
            )
            return None
