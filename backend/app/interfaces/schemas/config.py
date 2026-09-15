from pydantic import BaseModel


class ClientConfigResponse(BaseModel):
    """Client runtime configuration response schema"""
    auth_provider: str
    show_github_button: bool
    github_repository_url: str
    google_analytics_id: str | None = None


class ModelSummary(BaseModel):
    """A selectable model as exposed to the client.

    Deliberately omits base_url and api_key_env: the browser has no use for
    them and shipping them would leak internal endpoint topology.
    """
    id: str
    name: str
    provider: str
    is_local: bool = False
    description: str | None = None
