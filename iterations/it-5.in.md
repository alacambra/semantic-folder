---
document_id: IT-5-IN
version: 1.0.0
last_updated: 2026-02-23
status: Ready
purpose: Replace placeholder descriptions with AI-generated content via Anthropic API
audience: [Developers, reviewers]
dependencies: [IT-4-IN]
review_triggers:
  [
    Anthropic API contract changes,
    prompt template changes,
    new config fields,
    generator interface changes,
  ]
---

# Iteration 5: AI Description Generation

## Objective

Replace the placeholder description generator with real AI-generated content using the Anthropic API (Claude 3.5 Haiku). Each folder's files are summarized individually and the folder is classified by type, producing meaningful `folder_description.md` files in OneDrive.

## Motivation

**Business driver:** After IT-4, the system uploads `folder_description.md` files with placeholder text (`[folder-type]`, `[filename-description]`). These are structurally correct but useless for Copilot 365. IT-5 replaces placeholders with AI-generated summaries so Copilot gets real semantic context about each folder's contents.

**How this iteration fulfills it:** Introduces an `AnthropicDescriber` class that calls the Anthropic Messages API to generate per-file summaries and folder classification. The existing `generate_description()` pure function is replaced with a method that reads file content from OneDrive via the Graph API and sends it to Claude for summarization. The `FolderListing → FolderDescription` data flow remains stable — only the content quality changes.

## Prerequisites

- Anthropic API key with access to `claude-3-5-haiku-20241022`
- All IT-4 prerequisites remain (Azure AD credentials, `AzureWebJobsStorage`)

## Scope

### In Scope

1. **`src/semantic_folder/config.py`** — Add `anthropic_api_key` (required) and `anthropic_model` (optional, defaults to `claude-3-5-haiku-20241022`) to `AppConfig` and `load_config()`
2. **`src/semantic_folder/graph/client.py`** — Add `get_content()` method to download raw file bytes from OneDrive
3. **`src/semantic_folder/graph/models.py`** — Extend `FolderListing` with `file_ids: list[str]` alongside existing `files: list[str]` (file names)
4. **`src/semantic_folder/orchestration/processor.py`** — Update `list_folder()` to populate `file_ids`; update `upload_description()` to read file content and pass it to the AI describer
5. **`src/semantic_folder/description/describer.py`** — New module: `AnthropicDescriber` class wrapping the Anthropic Messages API
6. **`src/semantic_folder/description/generator.py`** — Replace placeholder logic with calls to `AnthropicDescriber`; accept describer as a dependency
7. **`pyproject.toml`** — Add `anthropic` dependency
8. **Tests** — Unit tests for all new and modified modules

### Out of Scope

- Async/parallel API calls — synchronous only
- Special handling for PDFs, images, or binary files — file content is sent as-is (text-based files will produce good summaries; binary files will get name-based descriptions)
- Cost controls, rate limiting, or token budgets
- Prompt tuning beyond a reasonable first version
- Terraform / infrastructure changes
- Changes to `DeltaProcessor` or delta token logic

## Deliverables

### D1: Extend `AppConfig` in `src/semantic_folder/config.py`

Add two new fields to `AppConfig`:

```python
# Required — no defaults, fail at startup if missing
anthropic_api_key: str

# Domain constants — defaults provided, overridable via env
anthropic_model: str = "claude-3-5-haiku-20241022"
```

Update `load_config()`:

```python
anthropic_api_key=os.environ["SF_ANTHROPIC_API_KEY"],
anthropic_model=os.environ.get("SF_ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
```

### D2: Add `get_content()` to `GraphClient`

New method on `GraphClient` that downloads raw file bytes:

```python
def get_content(self, path: str) -> bytes:
    """Perform an authenticated GET request to download raw content.

    Args:
        path: URL path relative to BASE_URL (must start with '/').

    Returns:
        Raw response bytes.

    Raises:
        GraphAuthError: If token acquisition fails.
        GraphApiError: If the API returns a non-2xx status code.
    """
    token = self._acquire_token()
    url = f"{GRAPH_BASE_URL}{path}"
    req = urllib_request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(req) as resp:
            return resp.read()
    except HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw).get("error", {}).get("message", exc.reason)
        except Exception:
            detail = exc.reason
        raise GraphApiError(exc.code, detail) from exc
```

**Usage pattern by callers:**

```
/users/{drive_user}/drive/items/{file_id}/content
```

### D3: Extend `FolderListing` in `src/semantic_folder/graph/models.py`

Add `file_ids` field to track item IDs alongside file names:

```python
@dataclass
class FolderListing:
    """Represents the contents of a OneDrive folder after enumeration."""

    folder_id: str
    folder_path: str
    files: list[str] = field(default_factory=list)
    file_ids: list[str] = field(default_factory=list)
```

`files[i]` and `file_ids[i]` correspond to the same file (parallel lists).

### D4: `src/semantic_folder/description/describer.py`

New module with the `AnthropicDescriber` class:

```python
"""AI description generation via Anthropic Messages API."""

from __future__ import annotations

import logging

import anthropic

logger = logging.getLogger(__name__)

# Content size limit per file (first 8 KB)
MAX_FILE_CONTENT_BYTES = 8192


class AnthropicDescriber:
    """Generates file summaries and folder classifications using Claude."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022") -> None:
        """Initialise the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model identifier to use for generation.
        """
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize_file(self, filename: str, content: bytes) -> str:
        """Generate a one-line summary of a file.

        Args:
            filename: Name of the file.
            content: Raw file content (truncated to MAX_FILE_CONTENT_BYTES).

        Returns:
            A brief summary string.
        """
        truncated = content[:MAX_FILE_CONTENT_BYTES]
        try:
            text_content = truncated.decode("utf-8", errors="replace")
        except Exception:
            text_content = f"[binary file: {filename}]"

        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Summarize this file in one sentence. "
                        f"File name: {filename}\n\n"
                        f"Content:\n{text_content}"
                    ),
                }
            ],
        )
        return message.content[0].text

    def classify_folder(self, folder_path: str, filenames: list[str]) -> str:
        """Classify a folder into a category based on its path and contents.

        Args:
            folder_path: OneDrive path of the folder.
            filenames: List of file names in the folder.

        Returns:
            A short folder type classification (e.g. "project-docs", "invoices").
        """
        file_list = "\n".join(f"- {f}" for f in filenames)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Classify this folder into a short category label "
                        f"(1-2 words, lowercase, hyphenated). "
                        f"Folder path: {folder_path}\n"
                        f"Files:\n{file_list}"
                    ),
                }
            ],
        )
        return message.content[0].text.strip()
```

**Design notes:**
- `summarize_file()` truncates content to 8 KB to keep token usage low
- Binary files decoded with `errors="replace"` — garbled text will produce a generic summary, which is acceptable for IT-5
- `classify_folder()` uses file names only (no content) — lightweight and cheap
- Both methods use low `max_tokens` to control cost
- No retry logic — failures propagate to the caller (at-least-once semantics via delta token ordering)

### D5: Replace `generate_description()` in `src/semantic_folder/description/generator.py`

Replace the placeholder function with one that accepts a describer and file content:

```python
"""AI-powered description generator for folder contents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from semantic_folder.description.models import FileDescription, FolderDescription

if TYPE_CHECKING:
    from semantic_folder.description.describer import AnthropicDescriber
    from semantic_folder.graph.models import FolderListing


def generate_description(
    listing: FolderListing,
    describer: AnthropicDescriber,
    file_contents: dict[str, bytes],
) -> FolderDescription:
    """Generate a folder description using AI.

    Args:
        listing: FolderListing from the folder enumeration step.
        describer: AnthropicDescriber instance for AI generation.
        file_contents: Mapping of filename to raw file content bytes.

    Returns:
        FolderDescription with AI-generated content.
    """
    folder_type = describer.classify_folder(listing.folder_path, listing.files)
    files = [
        FileDescription(
            filename=name,
            summary=describer.summarize_file(name, file_contents.get(name, b"")),
        )
        for name in listing.files
    ]
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type=folder_type,
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )
```

**Interface change:** `generate_description()` now takes two additional parameters: `describer` and `file_contents`. This is a breaking change from IT-4's pure function, but the `FolderListing → FolderDescription` output contract remains stable.

### D6: Update `FolderProcessor` in `src/semantic_folder/orchestration/processor.py`

**Changes to `__init__`:**

```python
def __init__(
    self,
    delta_processor: DeltaProcessor,
    graph_client: GraphClient,
    drive_user: str,
    describer: AnthropicDescriber,
    folder_description_filename: str = "folder_description.md",
) -> None:
```

Add `describer` parameter. Store as `self._describer`.

**New method `read_file_contents`:**

```python
def read_file_contents(self, listing: FolderListing) -> dict[str, bytes]:
    """Download content for each file in a folder listing.

    Args:
        listing: FolderListing with file names and IDs.

    Returns:
        Mapping of filename to raw bytes content.
    """
    contents: dict[str, bytes] = {}
    for name, file_id in zip(listing.files, listing.file_ids):
        path = f"/users/{self._drive_user}/drive/items/{file_id}/content"
        try:
            contents[name] = self._graph.get_content(path)
        except Exception:
            logger.warning(
                "[read_file_contents] failed to read file; filename:%s;file_id:%s",
                name,
                file_id,
            )
            contents[name] = b""
    return contents
```

**Update `upload_description`:**

```python
def upload_description(self, listing: FolderListing) -> None:
    file_contents = self.read_file_contents(listing)
    description = generate_description(listing, self._describer, file_contents)
    content = description.to_markdown().encode("utf-8")
    path = (
        f"/users/{self._drive_user}/drive/items/{listing.folder_id}"
        f":/{self._folder_description_filename}:/content"
    )
    self._graph.put_content(path, content)
    logger.info(
        "[upload_description] uploaded description; folder_path:%s;file_count:%d",
        listing.folder_path,
        len(description.files),
    )
```

**Update `list_folder`:**

Populate `file_ids` from the Graph API response:

```python
file_ids = [
    child[FIELD_ID]
    for child in children
    if FIELD_FOLDER not in child and FIELD_ID in child
]

return FolderListing(
    folder_id=folder_id, folder_path=folder_path, files=files, file_ids=file_ids
)
```

**Update `folder_processor_from_config`:**

```python
def folder_processor_from_config(config: AppConfig) -> FolderProcessor:
    client = graph_client_from_config(config)
    delta = delta_processor_from_config(client, config)
    describer = anthropic_describer_from_config(config)
    return FolderProcessor(
        delta_processor=delta,
        graph_client=client,
        drive_user=config.drive_user,
        describer=describer,
        folder_description_filename=config.folder_description_filename,
    )
```

### D7: Factory function in `src/semantic_folder/description/describer.py`

```python
def anthropic_describer_from_config(config: AppConfig) -> AnthropicDescriber:
    """Construct an AnthropicDescriber from application configuration.

    Args:
        config: Application configuration instance.

    Returns:
        Configured AnthropicDescriber instance.
    """
    return AnthropicDescriber(
        api_key=config.anthropic_api_key,
        model=config.anthropic_model,
    )
```

Use `TYPE_CHECKING` import for `AppConfig` as done in other modules.

### D8: Add `anthropic` dependency to `pyproject.toml`

```toml
dependencies = [
    "azure-functions>=1.21",
    "msal>=1.31",
    "azure-storage-blob>=12.23",
    "anthropic>=0.43",
]
```

### D9: Tests

**`tests/unit/description/test_describer.py`** (new)

- Test `AnthropicDescriber.__init__` creates an `anthropic.Anthropic` client with the given API key
- Test `summarize_file()` calls `messages.create` with correct model, max_tokens, and prompt containing filename and content
- Test `summarize_file()` truncates content to `MAX_FILE_CONTENT_BYTES`
- Test `summarize_file()` handles binary content gracefully (decode with `errors="replace"`)
- Test `summarize_file()` returns the text from the first content block
- Test `classify_folder()` calls `messages.create` with folder path and file list
- Test `classify_folder()` returns stripped text from the response
- Test `anthropic_describer_from_config()` passes API key and model from config

**`tests/unit/description/test_generator.py`** (updated)

- Update all tests to pass `describer` mock and `file_contents` dict
- Test `generate_description()` calls `describer.classify_folder()` with correct args
- Test `generate_description()` calls `describer.summarize_file()` once per file with corresponding content
- Test with empty files list produces `FolderDescription` with empty files and still calls `classify_folder()`
- Test `updated_at` is a valid ISO date string matching today's date

**`tests/unit/graph/test_client.py`** (additions)

- Test `get_content()` sends GET request with correct URL and Bearer token
- Test `get_content()` returns raw bytes from response
- Test `get_content()` raises `GraphApiError` on non-2xx response
- Test `get_content()` raises `GraphAuthError` when token acquisition fails

**`tests/unit/graph/test_models.py`** (additions if needed)

- Test `FolderListing` accepts `file_ids` field
- Test `FolderListing` defaults `file_ids` to empty list

**`tests/unit/orchestration/test_processor.py`** (updates)

- Update `FolderProcessor` construction to include `describer` mock
- Test `read_file_contents()` calls `get_content()` for each file ID with correct path
- Test `read_file_contents()` returns empty bytes on download failure (with warning log)
- Test `upload_description()` calls `read_file_contents()` then `generate_description()` with results
- Test `list_folder()` populates `file_ids` from Graph API response
- Test `folder_processor_from_config()` creates `AnthropicDescriber` from config and passes it

**`tests/unit/config/test_config.py`** (additions if exists, or inline)

- Test `load_config()` reads `SF_ANTHROPIC_API_KEY` from env
- Test `load_config()` reads `SF_ANTHROPIC_MODEL` with default fallback
- Test `load_config()` raises `KeyError` when `SF_ANTHROPIC_API_KEY` is missing

## Acceptance Criteria

1. `make lint` passes — ruff reports no errors in all new and modified modules
2. `make typecheck` passes — pyright reports no type errors in all new and modified modules
3. `make test` runs and all unit tests pass without real Anthropic credentials (mocks only)
4. `AppConfig` includes `anthropic_api_key` (required) and `anthropic_model` (optional, default `claude-3-5-haiku-20241022`)
5. `GraphClient.get_content()` sends an authenticated GET and returns raw bytes
6. `GraphClient.get_content()` raises `GraphApiError` on non-2xx response (consistent with `get()` and `put_content()`)
7. `FolderListing.file_ids` is populated by `list_folder()` in parallel with `files`
8. `AnthropicDescriber.summarize_file()` calls the Anthropic Messages API with the file name and truncated content (max 8 KB)
9. `AnthropicDescriber.classify_folder()` calls the Anthropic Messages API with the folder path and file names
10. `generate_description()` uses the describer to produce real summaries and folder type instead of placeholders
11. `FolderProcessor.upload_description()` reads file content via `get_content()` before calling `generate_description()`
12. `process_delta()` upload-before-token-save ordering is preserved (at-least-once semantics)
13. Coverage remains at or above 90%
14. The `anthropic` package is declared in `pyproject.toml` dependencies

## Reference Documents

- `architectural-requirements/layer-responsibilities` — `description/describer.py` is an adapter (external I/O to Anthropic); generator remains domain logic that coordinates the adapter
- `architectural-requirements/interface-design` — `generate_description()` signature extended with `describer` and `file_contents`; `AnthropicDescriber` injected via constructor into `FolderProcessor`
- `architectural-requirements/error-handling` — `get_content()` follows the same `GraphApiError` pattern; Anthropic API errors propagate to caller
- `architectural-requirements/logging` — File download failures logged at WARNING; upload activity logged at INFO; no file content or API keys in logs
- `architectural-requirements/testing` — All Anthropic API calls mocked; `get_content()` mocked in orchestration tests
- `architectural-requirements/configuration` — Two new env vars (`SF_ANTHROPIC_API_KEY`, `SF_ANTHROPIC_MODEL`); `load_config()` is the only module reading `os.environ`
- `iterations/it-4.in.md` — Predecessor iteration establishing the description pipeline that IT-5 enhances
