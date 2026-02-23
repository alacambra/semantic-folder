---
document_id: IT-6-IN
version: 1.0.0
last_updated: 2026-02-23
status: Ready
purpose: Add per-file summary cache to avoid redundant LLM calls
audience: [Developers, reviewers]
dependencies: [IT-5-IN]
review_triggers:
  [
    Cache storage format changes,
    Cache key scheme changes,
    Generator interface changes,
    Config field additions,
  ]
---

# Iteration 6: Per-File Summary Cache

## Objective

Introduce a per-file summary cache backed by Azure Blob Storage that skips redundant Anthropic API calls when a file's content has not changed. The cache uses SHA-256 content hashing to detect unchanged files, storing and retrieving cached summaries without calling the LLM.

## Motivation

**Business driver:** The current system re-downloads and re-summarizes ALL files in a changed folder via the Anthropic API, even when only one file has changed. On a full reindex (deleted delta token), every file across every folder gets sent to the LLM. This is expensive -- each `summarize_file()` call consumes Anthropic API tokens. Caching eliminates redundant LLM calls for files whose content has not changed, reducing both cost and latency.

**How this iteration fulfills it:** A `SummaryCache` class backed by Azure Blob Storage stores file summaries keyed by their SHA-256 content hash. The `generate_description()` function checks the cache before calling `describer.summarize_file()`. On cache hit, the cached summary is returned immediately. On cache miss, the LLM is called and the result is stored. Folder classification (`classify_folder`) is never cached because it depends on the complete file list, which changes when files are added or removed.

## Architecture Diagram

```text
                         process_delta()
                              |
                              v
                    +-------------------+
                    | FolderProcessor   |
                    |   upload_description()
                    +-------------------+
                              |
               read_file_contents()
                    |                  \
                    v                   v
             GraphClient          generate_description()
          (download files)               |
                                         |--- classify_folder() ---> Anthropic API
                                         |    (always called)        (never cached)
                                         |
                                    for each file:
                                         |
                                         v
                              +---------------------+
                              | _get_or_generate_summary()
                              +---------------------+
                                    |
                          SHA-256(content)
                                    |
                                    v
                          +-------------------+
                          | SummaryCache.get() |
                          +-------------------+
                           /                \
                     HIT  /                  \ MISS
                         /                    \
                        v                      v
                  return cached          summarize_file()
                  summary                      |
                                               v
                                         Anthropic API
                                               |
                                               v
                                       SummaryCache.put()
                                               |
                                               v
                                        return summary


    Azure Blob Storage layout:
    +-----------------------------------------+
    | semantic-folder-state/                   |
    |   delta-token/current.txt    (existing)  |
    |   summary-cache/             (new)       |
    |     a1b2c3d4e5f6...          SHA-256 key |
    |     f7e8d9c0b1a2...          SHA-256 key |
    +-----------------------------------------+
```

## Prerequisites

- All IT-5 prerequisites remain (Azure AD credentials, `AzureWebJobsStorage`, `SF_ANTHROPIC_API_KEY`)
- Azure Storage account used for delta tokens is also used for cache blobs

## Scope

### In Scope

1. `SummaryCache` class backed by Azure Blob Storage with get/put operations keyed by SHA-256 content hash
2. Integration of cache into `generate_description()` to intercept `summarize_file()` calls
3. New config fields for cache container name and blob prefix
4. Factory function `summary_cache_from_config()` following the `*_from_config()` pattern
5. Wiring the cache into `FolderProcessor` and `folder_processor_from_config()`
6. Unit tests for all new and modified modules
7. Logging of cache hits and misses for observability

### Out of Scope

- Cache expiration / TTL -- cached summaries are valid indefinitely (content hash guarantees correctness)
- Cache invalidation beyond content changes -- if the LLM model changes, old summaries remain (acceptable for now)
- Async or batch cache operations -- synchronous only
- Cache for `classify_folder()` -- folder classification depends on the full file list
- Cache size limits or garbage collection
- Changes to the Anthropic describer itself
- Infrastructure / Terraform changes

## Deliverables

### D1: `src/semantic_folder/description/cache.py` -- New module

New module containing the `SummaryCache` class:

```python
"""Per-file summary cache backed by Azure Blob Storage."""

from __future__ import annotations

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
        self._blob_service = BlobServiceClient.from_connection_string(
            storage_connection_string
        )
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
            container_client = self._blob_service.get_container_client(
                self._container
            )
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
        container_client = self._blob_service.get_container_client(
            self._container
        )
        try:
            container_client.create_container()
        except Exception:
            pass  # Container already exists

        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(
            summary.encode("utf-8"), overwrite=True
        )
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
```

**Design notes:**
- Cache key is the SHA-256 hex digest of the raw file content bytes -- same content always produces the same key, regardless of filename
- Uses the same `BlobServiceClient` pattern as `DeltaProcessor` for consistency
- Container auto-creation follows the same pattern as `DeltaProcessor.save_delta_token()`
- Blob path: `{blob_prefix}{content_hash}` (e.g. `summary-cache/a1b2c3d4...`)
- `content_hash()` is a static method so callers can compute hashes without a cache instance

### D2: Extend `AppConfig` in `src/semantic_folder/config.py`

Add two new optional fields:

```python
# Domain constants -- defaults provided, overridable via env
cache_container: str = "semantic-folder-state"
cache_blob_prefix: str = "summary-cache/"
```

Update `load_config()`:

```python
cache_container=os.environ.get("SF_CACHE_CONTAINER", "semantic-folder-state"),
cache_blob_prefix=os.environ.get("SF_CACHE_BLOB_PREFIX", "summary-cache/"),
```

The cache reuses the same storage account and default container as the delta token storage. The blob prefix provides namespace separation within the container.

### D3: Update `generate_description()` in `src/semantic_folder/description/generator.py`

Add an optional `cache` parameter. When provided, check the cache before calling `summarize_file()`:

```python
def generate_description(
    listing: FolderListing,
    describer: AnthropicDescriber,
    file_contents: dict[str, bytes],
    cache: SummaryCache | None = None,
) -> FolderDescription:
    """Generate a folder description using AI.

    Args:
        listing: FolderListing from the folder enumeration step.
        describer: AnthropicDescriber instance for AI generation.
        file_contents: Mapping of filename to raw file content bytes.
        cache: Optional SummaryCache for skipping redundant LLM calls.

    Returns:
        FolderDescription with AI-generated content.
    """
    folder_type = describer.classify_folder(listing.folder_path, listing.files)
    files: list[FileDescription] = []
    for name in listing.files:
        content = file_contents.get(name, b"")
        summary = _get_or_generate_summary(name, content, describer, cache)
        files.append(FileDescription(filename=name, summary=summary))
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type=folder_type,
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )


def _get_or_generate_summary(
    filename: str,
    content: bytes,
    describer: AnthropicDescriber,
    cache: SummaryCache | None,
) -> str:
    """Return a cached summary or generate a new one.

    Args:
        filename: Name of the file.
        content: Raw file content bytes.
        describer: AnthropicDescriber for generating new summaries.
        cache: Optional cache to check/populate.

    Returns:
        Summary string (from cache or freshly generated).
    """
    if cache is not None and content:
        content_hash = SummaryCache.content_hash(content)
        cached = cache.get(content_hash)
        if cached is not None:
            return cached
        summary = describer.summarize_file(filename, content)
        cache.put(content_hash, summary)
        return summary
    return describer.summarize_file(filename, content)
```

**Design notes:**
- `cache` parameter is optional (`None` by default) for backward compatibility -- existing callers and tests work without modification
- Empty content (`b""`) is never cached -- it would produce a degenerate hash shared across all empty files
- `classify_folder()` is NOT cached -- it depends on the full file list which changes when files are added or removed
- Cache logic is extracted to `_get_or_generate_summary()` to keep `generate_description()` readable

### D4: Update `FolderProcessor` in `src/semantic_folder/orchestration/processor.py`

Add `cache` parameter to `__init__` and pass it to `generate_description()`:

```python
def __init__(
    self,
    delta_processor: DeltaProcessor,
    graph_client: GraphClient,
    drive_user: str,
    describer: AnthropicDescriber,
    folder_description_filename: str = "folder_description.md",
    cache: SummaryCache | None = None,
) -> None:
```

Store as `self._cache`.

Update `upload_description()`:

```python
description = generate_description(
    listing, self._describer, file_contents, self._cache
)
```

### D5: Update `folder_processor_from_config()` in `src/semantic_folder/orchestration/processor.py`

Create cache from config and pass it to FolderProcessor:

```python
def folder_processor_from_config(config: AppConfig) -> FolderProcessor:
    client = graph_client_from_config(config)
    delta = delta_processor_from_config(client, config)
    describer = anthropic_describer_from_config(config)
    cache = summary_cache_from_config(config)
    return FolderProcessor(
        delta_processor=delta,
        graph_client=client,
        drive_user=config.drive_user,
        describer=describer,
        folder_description_filename=config.folder_description_filename,
        cache=cache,
    )
```

### D6: Tests

**`tests/unit/description/test_cache.py`** (new)

- Test `SummaryCache.content_hash()` returns consistent SHA-256 hex digest
- Test `SummaryCache.content_hash()` returns different hashes for different content
- Test `SummaryCache.get()` returns None on cache miss (ResourceNotFoundError)
- Test `SummaryCache.get()` returns cached summary string on hit
- Test `SummaryCache.put()` uploads UTF-8 encoded summary to correct blob path
- Test `SummaryCache.put()` creates container if it does not exist
- Test `summary_cache_from_config()` passes correct config fields

**`tests/unit/description/test_generator.py`** (updated)

- Test `generate_description()` without cache (None) still calls `summarize_file()` for all files (backward compat)
- Test `generate_description()` with cache uses cached summary on hit, skips `summarize_file()`
- Test `generate_description()` with cache calls `summarize_file()` on miss and stores result
- Test `generate_description()` with cache does not cache empty content (b"")
- Test `classify_folder()` is always called regardless of cache (never cached)
- Test `_get_or_generate_summary()` directly for cache hit, miss, and no-cache paths

**`tests/unit/config/test_config.py`** (additions)

- Test `AppConfig.cache_container` has default `"semantic-folder-state"`
- Test `AppConfig.cache_blob_prefix` has default `"summary-cache/"`
- Test `load_config()` reads `SF_CACHE_CONTAINER` from env
- Test `load_config()` reads `SF_CACHE_BLOB_PREFIX` from env

**`tests/unit/orchestration/test_processor.py`** (updates)

- Test `FolderProcessor` accepts optional `cache` parameter
- Test `upload_description()` passes cache to `generate_description()`
- Test `folder_processor_from_config()` creates cache from config and passes it

## Acceptance Criteria

1. `make lint` passes -- ruff reports no errors in all new and modified modules
2. `make typecheck` passes -- pyright reports no type errors
3. `make test` runs and all tests pass without real Azure Storage or Anthropic credentials
4. `AppConfig` includes `cache_container` (default `"semantic-folder-state"`) and `cache_blob_prefix` (default `"summary-cache/"`)
5. `SummaryCache.content_hash()` produces consistent SHA-256 hex digests
6. `SummaryCache.get()` returns `None` on cache miss and the cached string on hit
7. `SummaryCache.put()` stores the summary as a UTF-8 blob at `{prefix}{hash}`
8. `generate_description()` skips `summarize_file()` for cache hits
9. `generate_description()` calls `summarize_file()` and stores result on cache miss
10. `generate_description()` does not cache summaries for empty content (`b""`)
11. `classify_folder()` is always called (never cached)
12. `generate_description()` works identically when `cache=None` (backward compatibility)
13. `folder_processor_from_config()` creates and wires a `SummaryCache`
14. Coverage remains at or above 90%

## Pre-Development Review

### Specification Review

**Skills loaded:** Architecture (layer responsibilities, dependency direction), Configuration Management (AppConfig pattern, factory functions), Testing (mocking patterns, coverage), Code Style (ruff, pyright, constants).

| Skill | Finding | Status |
|-------|---------|--------|
| Architecture/Layer Responsibilities | `description/cache.py` is an infrastructure adapter (Blob Storage I/O) placed in `description/` -- consistent with `description/describer.py` (Anthropic API I/O). Dependency direction: `orchestration/` -> `description/` -> Azure Storage. Generator remains pure domain logic coordinating adapters. | PASS |
| Architecture/Interface Design | `generate_description()` extended with optional `cache` parameter (default `None`) -- non-breaking backward-compatible change. `SummaryCache` injected via constructor into `FolderProcessor`, consistent with existing DI pattern. | PASS |
| Configuration Management | Two new optional fields with sensible defaults. `summary_cache_from_config()` follows `*_from_config()` pattern. Only `load_config()` reads `os.environ`. | PASS |
| Constants | `DEFAULT_CACHE_CONTAINER` and `DEFAULT_CACHE_BLOB_PREFIX` are named constants. No magic strings in cache key construction or blob paths. | PASS |
| Error Handling | `SummaryCache.get()` catches `ResourceNotFoundError` and returns `None` (graceful degradation). Container auto-creation in `put()` follows `DeltaProcessor.save_delta_token()` pattern. | PASS |
| Testing | All Blob Storage I/O mocked. Cache hit/miss/store paths tested independently. Backward compatibility tested with `cache=None`. | PASS |
| Code Style | Google-style docstrings, stdlib logging with `[function_name]` prefix, no secrets in logs. | PASS |

**Specification Review Status: APPROVED**

## Independent Validation

### Readiness Checklist

- [x] Scope clear and bounded -- cache for per-file summaries only, not folder classification
- [x] Deliverables actionable -- full code provided for all new/modified modules
- [x] Acceptance criteria testable -- each criterion maps to a verifiable test
- [x] Reference docs identified -- CLAUDE.md patterns and IT-5 predecessor
- [x] Dependencies satisfied -- IT-5 complete, Azure Storage already available

### Five Pillars

- [x] Interface Contracts defined -- `SummaryCache.get()`, `put()`, `content_hash()` signatures specified; `generate_description()` extended signature specified
- [x] Data Structures specified -- cache key is SHA-256 hex string; blob content is UTF-8 encoded summary text
- [x] Configuration Formats documented -- `SF_CACHE_CONTAINER`, `SF_CACHE_BLOB_PREFIX` env vars with defaults
- [x] Behavioral Requirements clear -- cache hit skips LLM, cache miss calls LLM and stores, empty content never cached, `classify_folder()` never cached
- [x] Quality Criteria measurable -- 14 numbered acceptance criteria, all testable

**Independent Validation Status: READY_FOR_DEV**

## Reference Documents

- `CLAUDE.md/Architecture` -- `description/cache.py` is an infrastructure adapter (external I/O to Azure Blob Storage), placed in `description/` alongside the describer adapter
- `CLAUDE.md/Configuration Management` -- Two new optional env vars (`SF_CACHE_CONTAINER`, `SF_CACHE_BLOB_PREFIX`) with defaults; factory function `summary_cache_from_config()` follows `*_from_config()` pattern
- `CLAUDE.md/Constants` -- `DEFAULT_CACHE_CONTAINER` and `DEFAULT_CACHE_BLOB_PREFIX` are named constants; no magic strings
- `CLAUDE.md/Testing` -- All Azure Blob Storage I/O mocked; cache hit/miss/store paths tested
- `CLAUDE.md/Code Style` -- Ruff rules, Pyright basic mode, Google-style docstrings, stdlib logging
- `iterations/it-5.in.md` -- Predecessor iteration establishing the AI description pipeline that IT-6 enhances with caching
