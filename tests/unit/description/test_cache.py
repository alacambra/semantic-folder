"""Unit tests for description/cache.py — SummaryCache behaviour."""

import hashlib
from unittest.mock import MagicMock, patch

from azure.core.exceptions import ResourceNotFoundError

from semantic_folder.description.cache import (
    DEFAULT_CACHE_BLOB_PREFIX,
    DEFAULT_CACHE_CONTAINER,
    SummaryCache,
    summary_cache_from_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(
    container: str = DEFAULT_CACHE_CONTAINER,
    blob_prefix: str = DEFAULT_CACHE_BLOB_PREFIX,
) -> tuple[SummaryCache, MagicMock]:
    """Return (cache, mock_blob_service_client)."""
    with patch("semantic_folder.description.cache.BlobServiceClient") as mock_bsc_cls:
        mock_bsc = MagicMock()
        mock_bsc_cls.from_connection_string.return_value = mock_bsc
        cache = SummaryCache(
            storage_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
            container=container,
            blob_prefix=blob_prefix,
        )
    return cache, mock_bsc


# ---------------------------------------------------------------------------
# content_hash tests
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_returns_consistent_sha256_hex_digest(self) -> None:
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        assert SummaryCache.content_hash(content) == expected

    def test_returns_different_hashes_for_different_content(self) -> None:
        hash_a = SummaryCache.content_hash(b"content A")
        hash_b = SummaryCache.content_hash(b"content B")
        assert hash_a != hash_b

    def test_returns_lowercase_hex_string(self) -> None:
        result = SummaryCache.content_hash(b"test")
        assert result == result.lower()
        assert len(result) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------------------
# get tests
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_none_on_cache_miss(self) -> None:
        cache, mock_bsc = _make_cache()
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.side_effect = ResourceNotFoundError("Not found")

        result = cache.get("abc123")

        assert result is None

    def test_returns_cached_summary_on_hit(self) -> None:
        cache, mock_bsc = _make_cache()
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.return_value.readall.return_value = b"A cached summary"

        result = cache.get("abc123")

        assert result == "A cached summary"

    def test_uses_correct_blob_path(self) -> None:
        cache, mock_bsc = _make_cache(blob_prefix="my-prefix/")
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.return_value.readall.return_value = b"summary"

        cache.get("deadbeef")

        mock_container.get_blob_client.assert_called_once_with("my-prefix/deadbeef")

    def test_uses_correct_container(self) -> None:
        cache, mock_bsc = _make_cache(container="custom-container")
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.return_value.readall.return_value = b"summary"

        cache.get("abc123")

        mock_bsc.get_container_client.assert_called_once_with("custom-container")


# ---------------------------------------------------------------------------
# put tests
# ---------------------------------------------------------------------------


class TestPut:
    def test_uploads_utf8_encoded_summary(self) -> None:
        cache, mock_bsc = _make_cache()
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob

        cache.put("abc123", "A test summary")

        mock_blob.upload_blob.assert_called_once_with(b"A test summary", overwrite=True)

    def test_uses_correct_blob_path(self) -> None:
        cache, mock_bsc = _make_cache(blob_prefix="summary-cache/")
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob

        cache.put("deadbeef", "summary text")

        mock_container.get_blob_client.assert_called_once_with("summary-cache/deadbeef")

    def test_creates_container_if_not_exists(self) -> None:
        cache, mock_bsc = _make_cache()
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob

        cache.put("abc123", "summary")

        mock_container.create_container.assert_called_once()

    def test_ignores_container_already_exists_error(self) -> None:
        cache, mock_bsc = _make_cache()
        mock_container = MagicMock()
        mock_bsc.get_container_client.return_value = mock_container
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_container.create_container.side_effect = Exception("Container already exists")

        # Should not raise
        cache.put("abc123", "summary")

        mock_blob.upload_blob.assert_called_once()


# ---------------------------------------------------------------------------
# summary_cache_from_config tests
# ---------------------------------------------------------------------------


class TestSummaryCacheFromConfig:
    def test_passes_correct_config_fields(self) -> None:
        config = MagicMock()
        config.storage_connection_string = "DefaultEndpointsProtocol=https;AccountName=test"
        config.cache_container = "my-container"
        config.cache_blob_prefix = "my-prefix/"

        with patch("semantic_folder.description.cache.BlobServiceClient") as mock_bsc_cls:
            cache = summary_cache_from_config(config)

        mock_bsc_cls.from_connection_string.assert_called_once_with(
            "DefaultEndpointsProtocol=https;AccountName=test"
        )
        assert cache._container == "my-container"
        assert cache._blob_prefix == "my-prefix/"
