---
document_id: IT-4-IN
version: 1.0.0
last_updated: 2026-02-23
status: Ready
purpose: Implement the placeholder description pipeline — generate and upload folder_description.md to OneDrive
audience: [Developers, reviewers]
dependencies: [IT-3-IN]
review_triggers: [Markdown format changes, Graph API upload contract changes, new dataclass fields]
---

# Iteration 4: Placeholder Description Pipeline

## Objective

Implement the full write-back pipeline that generates a `folder_description.md` file for each changed folder and uploads it to OneDrive via the Graph API. Use placeholder text instead of AI-generated content to prove the end-to-end pipeline works.

## Motivation

**Business driver:** The purpose of semantic-folder is to give Copilot 365 a compact, structured summary of each folder's contents so it does not need to open every file. After IT-3, the system detects which folders changed but does nothing with that information. IT-4 closes the loop by actually generating and uploading a description file for each affected folder.

**How this iteration fulfills it:** Delivers a description schema (dataclasses), a placeholder generator, a real `put_content()` implementation in GraphClient, and the orchestration wiring to generate + upload after each delta run. After IT-4, every delta cycle produces real `folder_description.md` files in OneDrive. The placeholder content (`[filename-description]`, `[folder-type]`) will be replaced with AI-generated text in IT-5, but the pipeline infrastructure — serialization, upload, error handling — is complete and proven.

## Prerequisites

No new developer prerequisites beyond IT-3. The same credentials (`SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_TENANT_ID`, `SF_DRIVE_USER`, `AzureWebJobsStorage`) are required for integration testing.

The Azure AD App Registration must have `Files.ReadWrite.All` application permission (admin-consented), which was provisioned in IT-1.

## Scope

### In Scope

1. **`src/semantic_folder/graph/client.py`** -- Implement `put_content()` (replace `NotImplementedError` stub with real PUT request)
2. **`src/semantic_folder/description/models.py`** -- New module: `FileDescription` and `FolderDescription` dataclasses with `to_markdown()` serialization
3. **`src/semantic_folder/description/generator.py`** -- New module: `generate_description()` function that takes a `FolderListing` and produces a `FolderDescription` with placeholder values
4. **`src/semantic_folder/orchestration/processor.py`** -- Extend `FolderProcessor` to accept description filename config, generate descriptions, and upload them via `put_content()`
5. **`src/semantic_folder/functions/timer_trigger.py`** and **`http_trigger.py`** -- Update logging to reflect upload activity
6. **Tests** -- Unit tests for all new modules and updated orchestration logic

### Out of Scope

- AI content generation -- placeholder text only in this iteration
- AI provider integration (OpenAI, Azure OpenAI, etc.) 
- File content reading from OneDrive (needed for AI summarization)
- Terraform / infrastructure changes -- no new Azure resources needed
- New environment variables -- `SF_FOLDER_DESCRIPTION_FILENAME` already exists in `AppConfig`
- Changes to `DeltaProcessor` or delta token logic
- Changes to `config.py` or `load_config()`

## Deliverables

### D1: Implement `put_content()` in `GraphClient`

Replace the `NotImplementedError` stub at `src/semantic_folder/graph/client.py:106-125` with a real PUT request.

**Current stub:**
```python
def put_content(
    self,
    path: str,
    content: bytes,
    content_type: str = "text/markdown",
) -> None:
    raise NotImplementedError("put_content will be implemented in IT-4")
```

**Implementation:**
```python
def put_content(
    self,
    path: str,
    content: bytes,
    content_type: str = "text/markdown",
) -> None:
    """Perform an authenticated PUT request to upload content to the Graph API.

    Args:
        path: URL path relative to BASE_URL (must start with '/').
        content: Raw bytes to upload.
        content_type: MIME type for the Content-Type header.

    Raises:
        GraphAuthError: If token acquisition fails.
        GraphApiError: If the API returns a non-2xx status code.
    """
    token = self._acquire_token()
    url = f"{GRAPH_BASE_URL}{path}"
    req = urllib_request.Request(
        url,
        data=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
        method="PUT",
    )
    try:
        with urllib_request.urlopen(req) as resp:
            resp.read()  # drain response body
    except HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw).get("error", {}).get("message", exc.reason)
        except Exception:
            detail = exc.reason
        raise GraphApiError(exc.code, detail) from exc
```

**Upload path pattern used by callers:**
```
/users/{drive_user}/drive/items/{folder_id}:/{filename}:/content
```

### D2: `src/semantic_folder/description/models.py`

New module with dataclasses that define the internal schema for folder descriptions.

```python
"""Data models for folder description content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileDescription:
    """Description of a single file within a folder.

    Attributes:
        filename: Name of the file (e.g. "SOW_2026_01.pdf").
        summary: Text summary of the file contents. Placeholder in IT-4,
            AI-generated in IT-5.
    """

    filename: str
    summary: str


@dataclass
class FolderDescription:
    """Complete description of a folder and its files.

    Attributes:
        folder_path: OneDrive path of the folder (from parentReference.path).
        folder_type: Classification of the folder. Placeholder in IT-4,
            AI-inferred in IT-5.
        files: Ordered list of file descriptions.
        updated_at: ISO date string (YYYY-MM-DD) when the description was generated.
    """

    folder_path: str
    folder_type: str
    files: list[FileDescription] = field(default_factory=list)
    updated_at: str = ""

    def to_markdown(self) -> str:
        """Serialize this folder description to Markdown with YAML frontmatter.

        Returns:
            String content suitable for writing to folder_description.md.
        """
        lines: list[str] = [
            "---",
            f"folder_path: {self.folder_path}",
            f'folder_type: "{self.folder_type}"',
            f"updated_at: {self.updated_at}",
            "---",
        ]
        for fd in self.files:
            lines.append("")
            lines.append(f"## {fd.filename}")
            lines.append("")
            lines.append(fd.summary)

        # Ensure trailing newline.
        lines.append("")
        return "\n".join(lines)
```

**Output example:**
```markdown
---
folder_path: /drive/root:/Customers/Nexplore
folder_type: "[folder-type]"
updated_at: 2026-02-23
---

## SOW_2026_01.pdf

[SOW_2026_01.pdf-description]

## invoice_2026_01.pdf

[invoice_2026_01.pdf-description]
```

### D3: `src/semantic_folder/description/generator.py`

New module with a function that converts a `FolderListing` to a `FolderDescription` with placeholder values.

```python
"""Placeholder description generator for folder contents."""

from __future__ import annotations

from datetime import UTC, datetime

from semantic_folder.description.models import FileDescription, FolderDescription
from semantic_folder.graph.models import FolderListing


def generate_description(listing: FolderListing) -> FolderDescription:
    """Generate a placeholder folder description from a folder listing.

    Creates a FolderDescription with placeholder values for folder_type
    and per-file summaries. These placeholders will be replaced with
    AI-generated content in IT-5.

    Args:
        listing: FolderListing from the folder enumeration step.

    Returns:
        FolderDescription with placeholder content for all files.
    """
    files = [
        FileDescription(
            filename=name,
            summary=f"[{name}-description]",
        )
        for name in listing.files
    ]
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type="[folder-type]",
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )
```

**Design note:** The `generate_description()` function is a pure function (no side effects, no I/O). In IT-5, the AI provider will be injected as a dependency either by replacing this function or by introducing a strategy pattern. The current interface (`FolderListing -> FolderDescription`) will remain stable.

### D4: Extend `FolderProcessor` in `src/semantic_folder/orchestration/processor.py`

Wire description generation and upload into the delta processing pipeline.

**Changes to `FolderProcessor.__init__`:**
```python
def __init__(
    self,
    delta_processor: DeltaProcessor,
    graph_client: GraphClient,
    drive_user: str,
    folder_description_filename: str,
) -> None:
```

Add `folder_description_filename` parameter (sourced from `AppConfig.folder_description_filename`).

**New method `upload_description`:**
```python
def upload_description(self, listing: FolderListing) -> None:
    """Generate a placeholder description and upload it to OneDrive.

    Args:
        listing: FolderListing for the folder to describe.
    """
    description = generate_description(listing)
    content = description.to_markdown().encode("utf-8")
    path = (
        f"/users/{self._drive_user}/drive/items/{listing.folder_id}"
        f":/{self._folder_description_filename}:/content"
    )
    self._graph.put_content(path, content)
    logger.info(
        "[upload_description] uploaded description;"
        " folder_path:%s;file_count:%d",
        listing.folder_path,
        len(description.files),
    )
```

**Changes to `process_delta`:**

After listing folders (step 4) and before saving the delta token (step 5), call `upload_description()` for each listing:

```python
def process_delta(self) -> list[FolderListing]:
    logger.info("[process_delta] starting delta processing pipeline")
    token = self._delta.get_delta_token()
    items, new_token = self._delta.fetch_changes(token)
    logger.info("[process_delta] fetched changes; item_count:%d", len(items))
    folder_ids = self.resolve_folders(items)
    logger.info("[process_delta] resolved folders; folder_count:%d", len(folder_ids))
    listings = [self.list_folder(fid) for fid in folder_ids]
    for listing in listings:
        self.upload_description(listing)
    self._delta.save_delta_token(new_token)
    logger.info("[process_delta] pipeline complete; listing_count:%d", len(listings))
    return listings
```

**Update `folder_processor_from_config`:**
```python
def folder_processor_from_config(config: AppConfig) -> FolderProcessor:
    client = graph_client_from_config(config)
    delta = delta_processor_from_config(client, config)
    return FolderProcessor(
        delta_processor=delta,
        graph_client=client,
        drive_user=config.drive_user,
        folder_description_filename=config.folder_description_filename,
    )
```

### D5: `src/semantic_folder/description/__init__.py`

Empty `__init__.py` for the new description package.

### D6: Tests

**`tests/unit/description/__init__.py`** -- Empty init for test package.

**`tests/unit/description/test_models.py`**

- Test `FileDescription` instantiation and field access
- Test `FolderDescription` instantiation and field access
- Test `FolderDescription.to_markdown()` produces correct YAML frontmatter and H2 file sections
- Test `to_markdown()` with empty files list produces valid output (frontmatter only)
- Test `to_markdown()` output ends with trailing newline
- Test YAML frontmatter `folder_type` is quoted (contains `[` characters)

**`tests/unit/description/test_generator.py`**

- Test `generate_description()` returns `FolderDescription` with correct `folder_path`
- Test `generate_description()` returns placeholder `"[folder-type]"` as `folder_type`
- Test `generate_description()` returns one `FileDescription` per file in listing
- Test each `FileDescription.summary` matches `"[{filename}-description]"` pattern
- Test `updated_at` is a valid ISO date string matching today's date
- Test with empty files list produces `FolderDescription` with empty files

**`tests/unit/graph/test_client.py`** (additions to existing file)

- Test `put_content()` sends PUT request with correct URL, Bearer token, Content-Type header, and body
- Test `put_content()` raises `GraphApiError` on non-2xx response
- Test `put_content()` raises `GraphAuthError` when token acquisition fails

**`tests/unit/orchestration/test_processor.py`** (additions to existing file)

- Test `upload_description()` calls `generate_description()` and `put_content()` with correct path
- Test `upload_description()` constructs the correct Graph API path pattern: `/users/{drive_user}/drive/items/{folder_id}:/{filename}:/content`
- Test `process_delta()` calls `upload_description()` for each listing before saving the delta token
- Test `FolderProcessor` constructor accepts `folder_description_filename` parameter
- Test `folder_processor_from_config()` passes `folder_description_filename` from config

**Directory structure for new tests:**
```
tests/
  unit/
    description/
      __init__.py
      test_models.py
      test_generator.py
    graph/
      test_client.py         # (additions)
    orchestration/
      test_processor.py      # (additions)
```

## Acceptance Criteria

1. `make lint` passes -- ruff reports no errors in all new and modified modules
2. `make typecheck` passes -- pyright reports no type errors in all new and modified modules
3. `make test` runs and all unit tests pass without real Azure credentials (mocks only)
4. `GraphClient.put_content()` sends a PUT request with `Authorization: Bearer <token>` and `Content-Type: text/markdown` headers, and the file content as the request body
5. `GraphClient.put_content()` raises `GraphApiError` on non-2xx response (consistent with `get()` error handling)
6. `FolderDescription.to_markdown()` produces output matching the specified format: YAML frontmatter with `folder_path`, `folder_type` (quoted), `updated_at`, followed by H2-separated file sections
7. `generate_description()` returns placeholder values: `"[folder-type]"` for folder_type and `"[{filename}-description]"` for each file summary
8. `FolderProcessor.upload_description()` constructs the correct upload path: `/users/{drive_user}/drive/items/{folder_id}:/{filename}:/content`
9. `FolderProcessor.process_delta()` calls `upload_description()` for each folder listing returned by the enumeration step
10. `process_delta()` uploads descriptions before saving the delta token (so a failed upload does not advance the token, allowing retry on next cycle)
11. Coverage remains at or above 90%
12. No changes to `config.py`, `delta.py`, or any environment variable definitions

## Reference Documents

- `architectural-requirements/layer-responsibilities` -- description module is a domain layer; orchestration wires it to graph adapter
- `architectural-requirements/interface-design` -- `generate_description()` is a pure function; `upload_description()` on the orchestrator coordinates the layers
- `architectural-requirements/error-handling` -- `put_content()` raises `GraphApiError` consistent with `get()`; upload errors propagate to caller
- `architectural-requirements/logging` -- upload activity logged at INFO with folder_path and file_count; no file content in logs
- `architectural-requirements/testing` -- all new code has unit tests; `put_content()` mocked in orchestration tests
- `iterations/it-3.in.md` -- predecessor iteration establishing the delta pipeline that IT-4 extends

## Pre-Development Review

### Skills reviewed

| Skill | Relevance |
| ----- | --------- |
| architectural-requirements/layer-responsibilities | `description/` is a domain-adjacent module (pure data + pure function); `orchestration/` coordinates it with the `graph/` adapter -- no cross-layer leakage |
| architectural-requirements/interface-design | `generate_description()` is a pure function with a stable interface (`FolderListing -> FolderDescription`); constructor injection for `folder_description_filename` on `FolderProcessor` |
| architectural-requirements/error-handling | `put_content()` raises `GraphApiError` consistent with `get()` -- same error hierarchy; upload failures propagate to caller (timer/HTTP trigger) |
| architectural-requirements/logging | Upload activity logged at INFO with structured fields (`folder_path`, `file_count`); no file content or tokens in logs |
| architectural-requirements/testing | All new code has unit tests; `put_content()` and `generate_description()` mocked in orchestration tests; test structure mirrors source |
| architectural-requirements/configuration | No new env vars; `folder_description_filename` already in `AppConfig`; no module reads `os.environ` directly |
| architectural-requirements/security-architecture | No secrets or file content logged; `put_content()` uses the same Bearer token flow as `get()`; no new credential paths |
| architectural-requirements/data-flow-architecture | Data flow is explicit: `FolderListing` -> `generate_description()` -> `FolderDescription` -> `to_markdown()` -> bytes -> `put_content()` |

### Findings

1. **Layer placement of `description/` package:** The `description/models.py` module contains pure dataclasses (`FileDescription`, `FolderDescription`) with a `to_markdown()` serialization method. The `description/generator.py` module contains a pure function with no I/O. Both are domain-level concerns (data schema + business logic for content generation). They sit alongside `graph/` (adapter) and `orchestration/` (application) as a domain module. The orchestrator coordinates between the domain description module and the graph adapter for upload. PASS -- correct layer separation.

2. **Dependency direction:** `orchestration/processor.py` imports from `description/generator.py` and `graph/client.py`. The description module imports from `graph/models.py` (for `FolderListing` type). This keeps dependencies flowing inward: functions -> orchestration -> {description, graph}. The description module depends only on graph models (data structures), not on graph client (I/O). PASS -- correct dependency direction.

3. **Error handling consistency:** `put_content()` follows the exact same pattern as `get()`: acquire token, build request, handle `HTTPError` by extracting detail from JSON response body, raise `GraphApiError(status_code, detail)`. No new exception types needed. PASS -- consistent error hierarchy.

4. **Upload ordering in `process_delta()`:** The spec requires uploading descriptions before saving the delta token (AC10). This is correct: if an upload fails, the delta token is not advanced, so the next timer cycle will re-process the same folders. This provides at-least-once delivery semantics for description generation. PASS -- correct ordering for fault tolerance.

5. **Pure function design of `generate_description()`:** The function has no side effects and no I/O. It uses `datetime.now(tz=UTC)` for the timestamp, which is deterministic enough for a date string. In IT-5, this function will be replaced or augmented with AI calls, but the interface (`FolderListing -> FolderDescription`) remains stable. PASS -- clean extension point for IT-5.

6. **YAML frontmatter quoting:** The `folder_type` value contains bracket characters (`[folder-type]`) which could be misinterpreted as YAML sequences. The spec wraps it in double quotes in the `to_markdown()` output. PASS -- correct YAML serialization.

7. **No changes to existing modules outside scope:** The spec explicitly states no changes to `config.py`, `delta.py`, or environment variables (AC12). Only `client.py` (implement stub), `processor.py` (extend pipeline), and triggers (update logging) are modified. PASS -- minimal blast radius.

### Specification Review Status: APPROVED

## Independent Validation

### Readiness checklist

- [x] Scope clear and bounded -- 2 new modules (description/models, description/generator), 1 stub implementation (put_content), 1 extended module (processor), trigger updates, tests
- [x] Deliverables actionable -- all classes, methods, signatures, and output formats specified with code examples
- [x] Acceptance criteria testable -- each AC maps to a concrete test assertion or CLI command (`make lint`, `make typecheck`, `make test`)
- [x] Reference docs identified -- 8 architectural requirements checked and documented
- [x] Dependencies satisfied -- IT-3 complete (delta pipeline, graph client stub, config, models all in place)

### Five Pillars check

- [x] **Interface Contracts:** `put_content(path, content, content_type)` signature preserved from IT-3 stub; `generate_description(listing) -> FolderDescription` defined; `FolderDescription.to_markdown() -> str` defined; `FolderProcessor.upload_description(listing) -> None` defined; `FolderProcessor.__init__` extended with `folder_description_filename`
- [x] **Data Structures:** `FileDescription(filename, summary)` and `FolderDescription(folder_path, folder_type, files, updated_at)` fully specified with field types; `to_markdown()` output format documented with example
- [x] **Configuration Formats:** No new configuration needed; `folder_description_filename` already exists in `AppConfig` with default `"folder_description.md"`; upload path pattern documented: `/users/{drive_user}/drive/items/{folder_id}:/{filename}:/content`
- [x] **Behavioral Requirements:** Upload-before-token-save ordering specified (AC10); placeholder content patterns defined (`[folder-type]`, `[{filename}-description]`); `to_markdown()` format with YAML frontmatter + H2 sections defined; trailing newline required
- [x] **Quality Criteria:** AC1-AC12 all measurable; coverage target >= 90%; lint/typecheck/test commands specified

### Independent Validation Status: READY_FOR_DEV
