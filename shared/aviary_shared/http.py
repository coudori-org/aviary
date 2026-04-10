"""Reusable async HTTP client with lifecycle management."""

import logging

import httpx

logger = logging.getLogger(__name__)


class ServiceClient:
    """Base class for service-to-service HTTP clients."""

    def __init__(self, base_url: str, timeout: float = 30):
        self._base_url = base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def init(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        logger.info("%s initialized → %s", self.__class__.__name__, self._base_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"{self.__class__.__name__} not initialized — call init() first")
        return self._client
