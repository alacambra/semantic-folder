---
document_id: GAP-5-TO-6
version: 1.0.0
last_updated: 2026-02-23
purpose: Document changes between IT-5 and IT-6 start
---

# Gap: IT-5 -> IT-6

## Changes (commit `95a60c1`)

The following changes were made after IT-5 (commit `f507dcf`) but before IT-6 scope definition. These changes enhance the Anthropic describer with file-type-specific handling and make the content size limit configurable.

### Source Changes

**`src/semantic_folder/config.py`**

- Added `max_file_content_bytes: int = 8192` field to `AppConfig`
- Added `SF_MAX_FILE_CONTENT_BYTES` environment variable support in `load_config()`

**`src/semantic_folder/description/describer.py`**

- Renamed `MAX_FILE_CONTENT_BYTES` to `DEFAULT_MAX_FILE_CONTENT_BYTES`
- Added `max_file_content_bytes` constructor parameter to `AnthropicDescriber`
- Added file-type dispatch: `.docx` (text extraction via python-docx), `.pdf` (base64 document block), default (UTF-8 text)
- Added helper functions: `_file_extension()`, `_extract_docx_text()`
- Added structured logging to all summarization and classification methods
- Updated `anthropic_describer_from_config()` to pass `max_file_content_bytes`

### Test Changes

**`tests/unit/description/test_describer.py`**

- Added `TestFileExtension` test class
- Added `TestExtractDocxText` test class
- Renamed `TestSummarizeFile` to `TestSummarizeFileText` (text path tests)
- Added `TestSummarizeFileDocx` test class (docx path tests)
- Added `TestSummarizeFilePdf` test class (pdf path tests)
- Updated `TestAnthropicDescriberFromConfig` to verify `max_file_content_bytes`

### Dependency Changes

**`pyproject.toml`** -- Added `python-docx>=1.2.0,<2.0.0` dependency
**`poetry.lock`** -- Updated with python-docx and transitive dependencies
**`requirements.txt`** -- Regenerated

### Infrastructure Changes

**`infra/function_app.tf`** -- Added `SF_ANTHROPIC_API_KEY` Key Vault reference and `SF_MAX_FILE_CONTENT_BYTES = "5242880"` (5 MB)
**`infra/keyvault.tf`** -- Added `anthropic-api-key` secret resource
**`infra/variables.tf`** -- Added `anthropic_api_key` variable

**Classification:** Post-iteration enhancement -- extends IT-5's `AnthropicDescriber` with richer file-type handling (docx, pdf) and configurable content size limits. Infrastructure changes wire the Anthropic API key into Azure deployment.

**Traceability:** All changes build on the IT-5 API surface (`AnthropicDescriber`, `AppConfig`). No new modules introduced. The `python-docx` dependency is new.

**Action required:** None -- changes are self-contained and orthogonal to IT-6 scope (per-file summary cache).
