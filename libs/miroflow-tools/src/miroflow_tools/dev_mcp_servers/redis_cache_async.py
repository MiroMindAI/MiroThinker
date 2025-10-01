import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional, Union

import redis.asyncio as redis  # type: ignore
from redis.exceptions import ConnectionError, RedisError, TimeoutError

logger = logging.getLogger(__name__)


class AsyncRedisCache:
    """Redis缓存管理类（异步版），支持火山云Redis服务。

    说明：
    - 使用 redis-py 的 asyncio 客户端（`redis.asyncio`）。
    - 采用惰性初始化：首次调用时才尝试建立连接与 `PING`，避免在模块导入阶段阻塞或缺少事件循环。
    - 接口与同步版本基本一致，但 `get`、`set`、`health_check` 为异步方法。
    """

    def __init__(self) -> None:
        self.client: Optional[redis.Redis] = None
        self.enabled: bool = False

        # 读取环境变量配置（同步读取即可）
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
        """惰性初始化 Redis 客户端并执行一次 PING 健康检查。"""
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

            # 测试连接
            await self.client.ping()
            self.enabled = True
            logger.info(
                f"Async Redis cache initialized successfully, host: {self._redis_host}:{self._redis_port}, db: {self._redis_db}, ssl: {self._redis_ssl}"
            )
        except Exception as e:  # noqa: BLE001 - 记录详细错误
            logger.error(f"Failed to initialize async Redis cache: {str(e)}")
            self.client = None
            self.enabled = False

    def _generate_cache_key(self, prefix: str, data: Union[str, Dict[str, Any]]) -> str:
        """生成缓存键。

        Args:
            prefix: 前缀，例如 "google_search"、"jina_complete"。
            data: 用于生成哈希的内容，支持字符串或字典（字典会进行排序后序列化）。

        Returns:
            形如 "{prefix}:{hash16}" 的键名。
        """
        if isinstance(data, dict):
            data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            data_str = str(data)

        hash_obj = hashlib.sha256(data_str.encode("utf-8"))
        hash_str = hash_obj.hexdigest()[:16]
        return f"{prefix}:{hash_str}"

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存中获取数据。

        Args:
            cache_key: 缓存键。

        Returns:
            反序列化后的字典，若未命中或出错返回 None。
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
        """将数据存储到缓存中。

        Args:
            cache_key: 缓存键。
            data: 将被 JSON 序列化后写入。
            ttl_seconds: 过期时间（秒），默认 3600。

        Returns:
            成功写入返回 True，否则 False。
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
        """为 google_search 搜索生成缓存键。"""
        return self._generate_cache_key("google_search", search_params)

    def generate_scrape_and_extract_info_cache_key(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """为 Jina 完整流程生成缓存键。"""
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
        """为 Jina 单步网页抓取生成缓存键。"""
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
        """为 Jina 单步网页抓取生成缓存键。"""
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
        """获取 google_search 搜索缓存。"""
        cache_key = self.generate_google_search_cache_key(search_params)
        return await self.get(cache_key)

    async def set_google_search_cache(
        self,
        search_params: Dict[str, Any],
        result: Dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> bool:
        """设置 google_search 搜索缓存，默认 1 小时 TTL。"""
        cache_key = self.generate_google_search_cache_key(search_params)
        return await self.set(cache_key, result, ttl_seconds)

    async def get_scrape_and_extract_info_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取 Jina 完整流程缓存。"""
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
        """设置 Jina 完整流程缓存，默认 24 小时 TTL。"""
        cache_key = self.generate_scrape_and_extract_info_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.set(cache_key, result, ttl_seconds)

    async def get_scrape_url_with_jina_cache(
        self,
        url: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取 Jina 单步网页抓取缓存。"""
        cache_key = self.generate_scrape_url_with_jina_cache_key(url, custom_headers)
        return await self.get(cache_key)

    async def set_scrape_url_with_jina_cache(
        self,
        url: str,
        result: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None,
        ttl_seconds: int = 86400,
    ) -> bool:
        """设置 Jina 单步网页抓取缓存，默认 24 小时 TTL。"""
        cache_key = self.generate_scrape_url_with_jina_cache_key(url, custom_headers)
        return await self.set(cache_key, result, ttl_seconds)

    async def get_hierarchical_summarize_cache(
        self,
        url: str,
        info_to_extract: str,
        model: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取 Jina 单步网页抓取缓存。"""
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
        """设置 Jina 单步网页抓取缓存，默认 24 小时 TTL。"""
        cache_key = self.generate_hierarchical_summarize_cache_key(
            url, info_to_extract, model, custom_headers
        )
        return await self.set(cache_key, result, ttl_seconds)

    def is_enabled(self) -> bool:
        """检查缓存是否启用（仅反映当前已建立连接的状态）。"""
        return self.enabled and self.client is not None

    async def health_check(self) -> bool:
        """健康检查。"""
        await self._ensure_client()
        if not self.enabled or not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Async Redis health check failed: {str(e)}")
            return False


# 全局异步缓存实例
redis_cache_async = AsyncRedisCache()

__all__ = ["AsyncRedisCache", "redis_cache_async"]
