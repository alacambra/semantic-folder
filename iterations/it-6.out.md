---
document_id: IT-6-OUT
version: 1.0.0
last_updated: 2026-02-23
status: Complete
iteration_ref: IT-6-IN
---

# Iteration 6 -- Completion Report: Per-File Summary Cache

## Summary

IT-6 introduced a per-file summary cache backed by Azure Blob Storage that skips redundant Anthropic API calls when a file's content has not changed. The cache uses SHA-256 content hashing as the cache key, ensuring identical file content always maps to the same cached summary regardless of filename or path. The `generate_description()` function checks the cache before calling `summarize_file()` -- on a hit, the cached summary is returned immediately; on a miss, the LLM is called and the result is stored. Folder classification (`classify_folder`) is never cached because it depends on the complete file list.

All 14 acceptance criteria pass. `make lint`, `make typecheck`, and `make test` are all clean (164 passed, 3 skipped, 93% coverage).

## Deliverables Completed

| Deliverable | Spec ref | Status |
|-------------|----------|--------|
| `src/semantic_folder/description/cache.py` -- `SummaryCache` class with get/put/content_hash | D1 | Complete |
| `src/semantic_folder/config.py` -- `cache_container` + `cache_blob_prefix` fields | D2 | Complete |
| `src/semantic_folder/description/generator.py` -- cache-aware `generate_description()` + `_get_or_generate_summary()` | D3 | Complete |
| `src/semantic_folder/orchestration/processor.py` -- `FolderProcessor` accepts optional `cache` parameter | D4 | Complete |
| `src/semantic_folder/orchestration/processor.py` -- `folder_processor_from_config()` creates and wires `SummaryCache` | D5 | Complete |
| Tests (unit) -- all new and updated test modules | D6 | Complete |

## Files Created / Modified

| File | Status | Lines |
|------|--------|-------|
| `src/semantic_folder/description/cache.py` | Created | 121 |
| `src/semantic_folder/config.py` | Modified | 73 |
| `src/semantic_folder/description/generator.py` | Modified | 72 |
| `src/semantic_folder/orchestration/processor.py` | Modified | 224 |
| `tests/unit/description/test_cache.py` | Created | 185 |
| `tests/unit/description/test_generator.py` | Modified | 284 |
| `tests/unit/config/test_config.py` | Modified | 136 |
| `tests/unit/orchestration/test_processor.py` | Modified | 746 |
| `CLAUDE.md` | Modified | 94 |
| `iterations/it-6.in.md` | Modified | (diagram added) |

## Validation Results

| Check | Command | Result |
|-------|---------|--------|
| Lint | `make lint` | PASS -- 0 ruff errors, 37 files formatted |
| Type check | `make typecheck` | PASS -- 0 pyright errors, 0 warnings |
| Tests | `make test` | PASS -- 164 passed, 3 skipped, 93% coverage |

Integration tests skipped: `SF_CLIENT_ID` and `SF_ANTHROPIC_API_KEY` not set in CI environment -- correct and expected.

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `make lint` passes -- ruff reports no errors in all new and modified modules | PASS |
| 2 | `make typecheck` passes -- pyright reports no type errors | PASS |
| 3 | `make test` runs and all tests pass without real Azure Storage or Anthropic credentials | PASS |
| 4 | `AppConfig` includes `cache_container` (default `"semantic-folder-state"`) and `cache_blob_prefix` (default `"summary-cache/"`) | PASS |
| 5 | `SummaryCache.content_hash()` produces consistent SHA-256 hex digests | PASS |
| 6 | `SummaryCache.get()` returns `None` on cache miss and the cached string on hit | PASS |
| 7 | `SummaryCache.put()` stores the summary as a UTF-8 blob at `{prefix}{hash}` | PASS |
| 8 | `generate_description()` skips `summarize_file()` for cache hits | PASS |
| 9 | `generate_description()` calls `summarize_file()` and stores result on cache miss | PASS |
| 10 | `generate_description()` does not cache summaries for empty content (`b""`) | PASS |
| 11 | `classify_folder()` is always called (never cached) | PASS |
| 12 | `generate_description()` works identically when `cache=None` (backward compatibility) | PASS |
| 13 | `folder_processor_from_config()` creates and wires a `SummaryCache` | PASS |
| 14 | Coverage remains at or above 90% | PASS (93%) |

## Reference Documentation Review

### CLAUDE.md/Architecture

- `description/cache.py` is an infrastructure adapter (external I/O to Azure Blob Storage), placed in `description/` alongside `describer.py` (Anthropic API I/O). Both are adapters coordinated by the generator.
- `description/generator.py` remains domain logic that coordinates adapters -- it takes both `describer` and `cache` as dependency parameters, keeping it testable with mocks.
- `orchestration/processor.py` wires the cache into the pipeline via `folder_processor_from_config()`.
- Dependency direction: `functions/` -> `orchestration/` -> `description/` -> Azure Storage. Correct inward direction. **PASS**

### CLAUDE.md/Configuration Management

- Two new optional environment variables: `SF_CACHE_CONTAINER` (default `"semantic-folder-state"`), `SF_CACHE_BLOB_PREFIX` (default `"summary-cache/"`).
- `load_config()` is the only module reading `os.environ` -- all other modules receive config via constructor injection.
- Factory function `summary_cache_from_config()` follows the established `*_from_config(config: AppConfig)` pattern. **PASS**

### CLAUDE.md/Constants

- `DEFAULT_CACHE_CONTAINER` and `DEFAULT_CACHE_BLOB_PREFIX` are named constants in `cache.py`.
- Blob path construction uses `f"{self._blob_prefix}{content_hash}"` -- no magic strings.
- Config fields `cache_container` and `cache_blob_prefix` centralised in `AppConfig`. **PASS**

### CLAUDE.md/Testing

- All Azure Blob Storage I/O mocked via `unittest.mock.MagicMock` and `patch`.
- Cache hit, miss, and store paths tested independently in `test_cache.py` and `test_generator.py`.
- Backward compatibility tested with `cache=None` in `test_generator.py::TestGenerateDescriptionWithCache::test_without_cache_calls_summarize_for_all_files`.
- `folder_processor_from_config()` cache wiring tested in `test_processor.py::TestFolderProcessorFromConfig::test_creates_cache_from_config`.
- Coverage at 93%, above 90% threshold. **PASS**

### CLAUDE.md/Code Style

- Google-style docstrings on all public methods and module docstring.
- Stdlib `logging` with `[summary_cache]` prefix for observability -- no secrets in log messages.
- `contextlib.suppress(Exception)` used for container auto-creation (cleaner than bare try/except/pass).
- Ruff and pyright report zero issues. **PASS**

## Traceability

| Spec requirement | Implementation | Test |
|-----------------|----------------|------|
| `SummaryCache` class with get/put/content_hash | `description/cache.py` `SummaryCache` | `test_cache.py::TestContentHash`, `TestGet`, `TestPut` |
| SHA-256 content hashing | `SummaryCache.content_hash()` | `test_cache.py::TestContentHash::test_returns_consistent_sha256_hex_digest` |
| Cache get returns None on miss | `SummaryCache.get()` catches `ResourceNotFoundError` | `test_cache.py::TestGet::test_returns_none_on_cache_miss` |
| Cache get returns string on hit | `SummaryCache.get()` decodes UTF-8 blob | `test_cache.py::TestGet::test_returns_cached_summary_on_hit` |
| Cache put stores UTF-8 blob | `SummaryCache.put()` uploads encoded summary | `test_cache.py::TestPut::test_uploads_utf8_encoded_summary` |
| Container auto-creation | `SummaryCache.put()` calls `create_container()` | `test_cache.py::TestPut::test_creates_container_if_not_exists` |
| `summary_cache_from_config()` factory | `cache.py` `summary_cache_from_config()` | `test_cache.py::TestSummaryCacheFromConfig::test_passes_correct_config_fields` |
| `AppConfig.cache_container` default | `config.py` line 30 | `test_config.py::TestAppConfig::test_cache_container_has_default` |
| `AppConfig.cache_blob_prefix` default | `config.py` line 31 | `test_config.py::TestAppConfig::test_cache_blob_prefix_has_default` |
| `load_config()` reads `SF_CACHE_CONTAINER` | `config.py` line 71 | `test_config.py::TestLoadConfig::test_reads_cache_container_from_env` |
| `load_config()` reads `SF_CACHE_BLOB_PREFIX` | `config.py` line 72 | `test_config.py::TestLoadConfig::test_reads_cache_blob_prefix_from_env` |
| `generate_description()` accepts optional cache | `generator.py` `cache` parameter | `test_generator.py::TestGenerateDescriptionWithCache::test_without_cache_calls_summarize_for_all_files` |
| Cache hit skips `summarize_file()` | `_get_or_generate_summary()` returns cached | `test_generator.py::TestGenerateDescriptionWithCache::test_cache_hit_skips_summarize_file` |
| Cache miss calls LLM and stores | `_get_or_generate_summary()` calls put | `test_generator.py::TestGenerateDescriptionWithCache::test_cache_miss_calls_summarize_and_stores` |
| Empty content not cached | `_get_or_generate_summary()` checks `content` truthiness | `test_generator.py::TestGenerateDescriptionWithCache::test_does_not_cache_empty_content` |
| `classify_folder()` never cached | `generate_description()` calls it unconditionally | `test_generator.py::TestGenerateDescriptionWithCache::test_classify_folder_always_called_with_cache` |
| `FolderProcessor` accepts cache | `processor.py` `__init__` `cache` param | `test_processor.py::TestFolderProcessorAcceptsCache::test_accepts_optional_cache_parameter` |
| `upload_description()` passes cache | `processor.py` line 155 | `test_processor.py::TestUploadDescriptionWithCache::test_passes_cache_to_generate_description` |
| `folder_processor_from_config()` creates cache | `processor.py` line 216 | `test_processor.py::TestFolderProcessorFromConfig::test_creates_cache_from_config` |
