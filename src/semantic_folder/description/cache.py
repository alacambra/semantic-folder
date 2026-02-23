"""Per-file summary cache backed by Azure Blob Storage."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from typing import TYPE_CHECKING

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)

# Named constants for cache configuration defaults
DEFAULT_CACHE_CONTAINER = "semantic-folder-state"
DEFAULT_CACHE_BLOB_PREFIX = "summary-cache/"


class SummaryCache:
    """Per-file summary cache backed by Azure Blob Storage.

    Summaries are stored as UTF-8 text blobs keyed by the SHA-256 hash
    of the file's raw content. This ensures that identical file content
    always maps to the same cache key, regardless of filename or path.
    """

    def __init__(
        self,
        storage_connection_string: str,
        container: str = DEFAULT_CACHE_CONTAINER,
        blob_prefix: str = DEFAULT_CACHE_BLOB_PREFIX,
    ) -> None:
        """Initialise the summary cache.

        Args:
            storage_connection_string: Azure Storage connection string.
            container: Blob container name for cache storage.
            blob_prefix: Prefix for cache blob paths (e.g. "summary-cache/").
        """
        self._blob_service = BlobServiceClient.from_connection_string(storage_connection_string)
        self._container = container
        self._blob_prefix = blob_prefix

    @staticmethod
    def content_hash(content: bytes) -> str:
        """Compute the SHA-256 hex digest of file content.

        Args:
            content: Raw file content bytes.

        Returns:
            Lowercase hex string of the SHA-256 hash.
        """
        return hashlib.sha256(content).hexdigest()

    def get(self, content_hash: str) -> str | None:
        """Retrieve a cached summary by content hash.

        Args:
            content_hash: SHA-256 hex digest of the file content.

        Returns:
            Cached summary string, or None if not found.
        """
        blob_path = f"{self._blob_prefix}{content_hash}"
        try:
            container_client = self._blob_service.get_container_client(self._container)
            blob_client = container_client.get_blob_client(blob_path)
            data = blob_client.download_blob().readall()
            logger.info(
                "[summary_cache] cache hit; hash:%s",
                content_hash,
            )
            return data.decode("utf-8")
        except ResourceNotFoundError:
            logger.info(
                "[summary_cache] cache miss; hash:%s",
                content_hash,
            )
            return None

    def put(self, content_hash: str, summary: str) -> None:
        """Store a summary in the cache.

        Creates the container if it does not exist.

        Args:
            content_hash: SHA-256 hex digest of the file content.
            summary: Summary text to cache.
        """
        blob_path = f"{self._blob_prefix}{content_hash}"
        container_client = self._blob_service.get_container_client(self._container)
        with contextlib.suppress(Exception):
            container_client.create_container()

        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(summary.encode("utf-8"), overwrite=True)
        logger.info(
            "[summary_cache] stored; hash:%s",
            content_hash,
        )


def summary_cache_from_config(config: AppConfig) -> SummaryCache:
    """Construct a SummaryCache from application configuration.

    Args:
        config: Application configuration instance.

    Returns:
        Configured SummaryCache instance.
    """
    return SummaryCache(
        storage_connection_string=config.storage_connection_string,
        container=config.cache_container,
        blob_prefix=config.cache_blob_prefix,
    )
