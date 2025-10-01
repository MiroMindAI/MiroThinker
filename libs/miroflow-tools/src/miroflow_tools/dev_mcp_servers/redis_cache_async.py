import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional, Union

import redis.asyncio as redis  # type: ignore
from redis.exceptions import ConnectionError, RedisError, TimeoutError

logger = logging.getLogger(__name__)


class AsyncRedisCache:
    """Async Redis cache manager class, supporting Volcengine Redis service.

    Notes:
    - Uses redis-py asyncio client (`redis.asyncio`).
    - Lazy initialization: connection and `PING` are attempted only on first call,
      to avoid blocking or missing event loop at import stage.
    - The interface is basically the same as the sync version,
      but `get`, `set`, and `health_check` are async methods.
    """

    def __init__(self) -> None:
        self.client: Optional[redis.Redis] = None
        self.enabled: bool = False

        # Read environment variable configuration (synchronously is fine)
        self._cache_enabled: bool = (
            os.getenv("REDIS_CACHE_ENABLED", "false").lower() == "true"
        )
        self._redis_host: Optional[str] = os.getenv("VOLCENGINE_REDIS_HOST")
        self._redis_port: int = int(os.getenv("VOLCENGINE_REDIS_PORT", "6379"))
        self._redis_password: Optional[str] = os.getenv("VOLCENGINE_REDIS_PASSWORD")
        self._redis_db: int = int(os.getenv("VOLCENGINE_REDIS_DB", "0"))
        self._redis_ssl: bool = (
            os.getenv("VOLCENGINE_REDIS_SSL", "false").lower() == "true"
        )

    async def _ensure_client(self) -> None:
        """Lazy initialize Redis client and perform a PING health check once."""
        if self.client is not None:
            return

        if not self._cache_enabled:
            logger.info(
                "Redis cache is disabled via REDIS_CACHE_ENABLED environment variable"
            )
            self.enabled = False
            return

        if not self._redis_host:
            logger.warning(
                "VOLCENGINE_REDIS_HOST environment variable not set, Redis cache disabled"
            )
            self.enabled = False
            return

        if not self._redis_password:
            logger.warning(
                "VOLCENGINE_REDIS_PASSWORD environment variable not set, Redis cache disabled"
            )
            self.enabled = False
            return

        try:
            self.client = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                password=self._redis_password,
                db=self._redis_db,
                ssl=self._redis_ssl,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                decode_responses=True,
            )

            # Test connection
            await self.client.ping()
            self.enabled = True
            logger.info(
                f"Async Redis cache initialized successfully, host: {self._redis_host}:{self._redis_port}, db: {self._redis_db}, ssl: {self._redis_ssl}"
            )
        except Exception as e:  # noqa: BLE001 - log detailed error
            logger.error(f"Failed to initialize async Redis cache: {str(e)}")
            self.client = None
            self.enabled = False

    def _generate_cache_key(self, prefix: str, data: Union[str, Dict[str, Any]]) -> str:
        """Generate cache key.

        Args:
            prefix: Key prefix, e.g., "google_search", "jina_complete".
            data: Content used for hash generation, supports string or dict
                  (dict will be sorted and serialized).

        Returns:
            Key string in the form "{prefix}:{hash16}".
        """
        if isinstance(data, dict):
            data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            data_str = str(data)

        hash_obj = hashlib.sha256(data_str.encode("utf-8"))
        hash_str = hash_obj.hexdigest()[:16]
        return f"{prefix}:{hash_str}"

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve data from cache.

        Args:
            cache_key: Cache key.

        Returns:
            Deserialized dictionary, or None if not found or error occurred.
        """
        await self._ensure_client()
        if not self.enabled or not self.client:
            return None

        try:
            cached_data = await self.client.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit: {cache_key}")
                return json.loads(cached_data)
            logger.info(f"Cache miss: {cache_key}")
            return None
        except (RedisError, json.JSONDecodeError, ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis cache get error for key {cache_key}: {str(e)}")
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Unexpected error in Redis cache get for key {cache_key}: {str(e)}"
            )
            return None

    async def set(
        self, cache_key: str, data: Dict[str, Any], ttl_seconds: int = 3600
    ) -> bool:
        """Store data in cache.

        Args:
            cache_key: Cache key.
            data: Data to be serialized to JSON and stored.
            ttl_seconds: Expiration time in seconds, default 3600.

        Returns:
            True if successfully written, otherwise False.
        """
        await self._ensure_client()
        if not self.enabled or not self.client:
            return False

        try:
            serialized_data = json.dumps(data, ensure_ascii=False)
            result = await self.client.setex(cache_key, ttl_seconds, serialized_data)
            if result:
                logger.info(f"Cache set: {cache_key}, TTL: {ttl_seconds}s")
                return True
            logger.warning(f"Failed to set cache: {cache_key}")
            return False
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis cache set error for key {cache_key}: {str(e)}")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Unexpected error in Redis cache set for key {cache_key}: {str(e)}"
            )
            return False

    def generate_google_search_cache_key(self, search_params: Dict[str, Any]) -> str:
        """Generate cache key for google_search."""
        return self._generate_cache_key("google_search", search_params)

    def generate_scrape_and_extract_info_cache_key(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate cache key for Jina full pipeline."""
        cache_data: Dict[str, Any] = {
            "url": url,
            "info_to_extract": info_to_extract,
            "model": model,
            "custom_headers": custom_headers or {},
        }
        return self._generate_cache_key("scrape_and_extract_info", cache_data)

    def generate_scrape_url_with_jina_cache_key(
        self,
        url: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate cache key for Jina single-step scraping."""
        cache_data: Dict[str, Any] = {
            "url": url,
            "custom_headers": custom_headers or {},
        }
        return self._generate_cache_key("scrape_url_with_jina", cache_data)

    def generate_hierarchical_summarize_cache_key(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate cache key for hierarchical summarize (Jina single-step scraping)."""
        cache_data: Dict[str, Any] = {
            "url": url,
            "info_to_extract": info_to_extract,
            "model": model,
            "custom_headers": custom_headers or {},
        }
        return self._generate_cache_key("hierarchical_summarize", cache_data)

    async def get_google_search_cache(
        self, search_params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get google_search cache."""
        cache_key = self.generate_google_search_cache_key(search_params)
        return await self.get(cache_key)

    async def set_google_search_cache(
        self,
        search_params: Dict[str, Any],
        result: Dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> bool:
        """Set google_search cache, default TTL 1 hour."""
        cache_key = self.generate_google_search_cache_key(search_params)
        return await self.set(cache_key, result, ttl_seconds)

    async def get_scrape_and_extract_info_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get Jina full pipeline cache."""
        cache_key = self.generate_scrape_and_extract_info_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.get(cache_key)

    async def set_scrape_and_extract_info_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        result: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None,
        ttl_seconds: int = 86400,
    ) -> bool:
        """Set Jina full pipeline cache, default TTL 24 hours."""
        cache_key = self.generate_scrape_and_extract_info_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.set(cache_key, result, ttl_seconds)

    async def get_scrape_url_with_jina_cache(
        self,
        url: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get Jina single-step scraping cache."""
        cache_key = self.generate_scrape_url_with_jina_cache_key(url, custom_headers)
        return await self.get(cache_key)

    async def set_scrape_url_with_jina_cache(
        self,
        url: str,
        result: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None,
        ttl_seconds: int = 86400,
    ) -> bool:
        """Set Jina single-step scraping cache, default TTL 24 hours."""
        cache_key = self.generate_scrape_url_with_jina_cache_key(url, custom_headers)
        return await self.set(cache_key, result, ttl_seconds)

    async def get_hierarchical_summarize_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get hierarchical summarize (Jina single-step scraping) cache."""
        cache_key = self.generate_hierarchical_summarize_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.get(cache_key)

    async def set_hierarchical_summarize_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        result: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None,
        ttl_seconds: int = 86400,
    ) -> bool:
        """Set hierarchical summarize (Jina single-step scraping) cache, default TTL 24 hours."""
        cache_key = self.generate_hierarchical_summarize_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.set(cache_key, result, ttl_seconds)

    def is_enabled(self) -> bool:
        """Check if cache is enabled (only reflects currently established connection state)."""
        return self.enabled and self.client is not None

    async def health_check(self) -> bool:
        """Health check."""
        await self._ensure_client()
        if not self.enabled or not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Async Redis health check failed: {str(e)}")
            return False


# Global async cache instance
redis_cache_async = AsyncRedisCache()

__all__ = ["AsyncRedisCache", "redis_cache_async"]
