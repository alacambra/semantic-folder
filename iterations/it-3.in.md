---
document_id: IT-3-IN
version: 1.0.0
last_updated: 2026-02-22
status: Draft
purpose: Implement Microsoft Graph integration for delta API processing and folder enumeration
audience: [Developers, reviewers]
dependencies: [IT-1-IN, IT-2-IN]
review_triggers: [Graph API contract changes, MSAL library updates, delta token storage changes]
---

# Iteration 3: Microsoft Graph Integration — Delta API & Folder Enumeration

## Objective

Implement the Microsoft Graph integration layer: authenticate via MSAL, poll the OneDrive delta API to detect file changes, enumerate affected folders and their file listings, and wire the orchestration into the timer trigger.

## Motivation

**Business driver:** The core value of the system is automatic, always-current folder descriptions. This requires knowing *which* folders changed — the delta API is the efficient, incremental way to detect this without scanning all of OneDrive on every run.

**How this iteration fulfills it:** Delivers a working Graph client (`graph/client.py`), delta processor (`graph/delta.py`), data models (`graph/models.py`), and folder enumerator (`orchestration/processor.py`). After IT-3, the timer trigger runs every 5 minutes, reads OneDrive changes via the delta API, and logs which folders need regeneration — the foundation for AI generation in IT-4.

## Prerequisites

No new developer prerequisites beyond IT-2 devcontainer. All Graph API credentials are already configured via:

```bash
SF_CLIENT_ID=<your-app-registration-client-id>
SF_CLIENT_SECRET=<your-app-registration-client-secret>
SF_TENANT_ID=<your-azure-ad-tenant-id>
AzureWebJobsStorage=<your-storage-connection-string>
```

These must be set in `.env` (local) or Azure Function App settings (cloud). Unit tests run without real credentials via mocks.

## Scope

### In Scope

1. **`src/semantic_folder/graph/client.py`** — Microsoft Graph API client
2. **`src/semantic_folder/graph/delta.py`** — Delta API processor with token persistence
3. **`src/semantic_folder/graph/models.py`** — Data models for DriveItem, FolderListing
4. **`src/semantic_folder/orchestration/processor.py`** — Folder enumeration orchestrator
5. **Updated `src/semantic_folder/functions/timer_trigger.py`** — Wire in delta processing
6. **New dependencies in `pyproject.toml`** — `msal`, `azure-storage-blob`, `pytest-mock`
7. **Tests** — Unit tests for all new modules; integration test stub

### Out of Scope

- AI generation (IT-4)
- Writing `folder_description.md` back to OneDrive (IT-4)
- Graph webhook / real-time trigger (future iteration)
- HTTP health endpoint changes
- Terraform changes (App Registration and Storage Account already provisioned in IT-1)
- `.env.example` changes (all required vars already documented)

## Deliverables

### D1: `src/semantic_folder/graph/models.py`

Data models shared across the Graph and orchestration layers:

```python
from dataclasses import dataclass, field

@dataclass
class DriveItem:
    id: str
    name: str
    parent_id: str
    parent_path: str
    is_folder: bool
    is_deleted: bool

@dataclass
class FolderListing:
    folder_id: str
    folder_path: str
    files: list[str] = field(default_factory=list)
```

No business logic in models — pure data containers.

### D2: `src/semantic_folder/graph/client.py`

MSAL-authenticated client for Microsoft Graph API:

```python
class GraphClient:
    BASE_URL = "https://graph.microsoft.com/v1.0"
    SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(self, client_id: str, client_secret: str, tenant_id: str) -> None: ...

    def get(self, path: str) -> dict: ...
    # GET {BASE_URL}{path} with Bearer token; raises GraphApiError on non-2xx

    def put_content(self, path: str, content: bytes, content_type: str = "text/markdown") -> None: ...
    # PUT {BASE_URL}{path} — stub for IT-4; raises GraphApiError on non-2xx
```

**Errors:**
```python
class GraphAuthError(Exception): ...   # MSAL token acquisition failure
class GraphApiError(Exception):        # Non-2xx response from Graph API
    def __init__(self, status_code: int, message: str) -> None: ...
```

**Token caching:** MSAL `ConfidentialClientApplication` with in-memory token cache (MSAL manages refresh automatically). No custom cache required.

**Constructor reads from environment** via `os.environ` — not injected as parameters in production use, but accepts explicit parameters for testability.

**Factory function for production use:**
```python
def graph_client_from_env() -> GraphClient:
    return GraphClient(
        client_id=os.environ["SF_CLIENT_ID"],
        client_secret=os.environ["SF_CLIENT_SECRET"],
        tenant_id=os.environ["SF_TENANT_ID"],
    )
```

### D3: `src/semantic_folder/graph/delta.py`

Delta API processor with token persistence in Azure Blob Storage:

```python
class DeltaProcessor:
    DELTA_CONTAINER = "semantic-folder-state"
    DELTA_BLOB = "delta-token/current.txt"

    def __init__(self, graph_client: GraphClient, storage_connection_string: str) -> None: ...

    def get_delta_token(self) -> str | None: ...
    # Read blob DELTA_BLOB from container DELTA_CONTAINER.
    # Return None if blob does not exist (first run).

    def save_delta_token(self, token: str) -> None: ...
    # Write token string to blob. Create blob/container if not exists.

    def fetch_changes(self, token: str | None) -> tuple[list[DriveItem], str]: ...
    # Call GET /me/drive/root/delta (no token param on first run)
    # or GET /me/drive/root/delta?token=<token> (subsequent runs).
    # Follow @odata.nextLink pagination until @odata.deltaLink is reached.
    # Extract new delta token from @odata.deltaLink URL.
    # Map response items to DriveItem dataclass.
    # Returns (items, new_token).
```

**Loop prevention** in `fetch_changes`: after collecting all items, group by `parent_id`. For any parent_id where the only changed item name is `"folder_description.md"`, exclude all items for that parent from the returned list. Log excluded parents at DEBUG level.

**Factory function:**
```python
def delta_processor_from_env(graph_client: GraphClient) -> DeltaProcessor:
    return DeltaProcessor(
        graph_client=graph_client,
        storage_connection_string=os.environ["AzureWebJobsStorage"],
    )
```

### D4: `src/semantic_folder/orchestration/processor.py`

Orchestrates the full delta-to-folder-listing pipeline:

```python
class FolderProcessor:
    def __init__(self, delta_processor: DeltaProcessor, graph_client: GraphClient) -> None: ...

    def resolve_folders(self, items: list[DriveItem]) -> list[str]:
        # Collect unique parent_id values from non-deleted file items (not folders themselves).
        # Return deduplicated list of folder IDs.

    def list_folder(self, folder_id: str) -> FolderListing:
        # GET /me/drive/items/{folder_id}/children
        # Map response to FolderListing: folder_id, folder_path (from driveItem.parentReference.path), files=[item names]
        # files list includes only file names (not sub-folders).

    def process_delta(self) -> list[FolderListing]:
        # 1. token = delta_processor.get_delta_token()
        # 2. items, new_token = delta_processor.fetch_changes(token)
        # 3. folder_ids = resolve_folders(items)
        # 4. listings = [list_folder(fid) for fid in folder_ids]
        # 5. delta_processor.save_delta_token(new_token)
        # 6. return listings
```

**Factory function:**
```python
def folder_processor_from_env() -> FolderProcessor:
    client = graph_client_from_env()
    delta = delta_processor_from_env(client)
    return FolderProcessor(delta_processor=delta, graph_client=client)
```

### D5: Updated `src/semantic_folder/functions/timer_trigger.py`

Replace the placeholder comment with delta processing:

```python
from semantic_folder.orchestration.processor import folder_processor_from_env

# Inside timer_trigger():
processor = folder_processor_from_env()
listings = processor.process_delta()
for listing in listings:
    logger.info("Folder to regenerate: %s (%d files)", listing.folder_path, len(listing.files))
logger.info("Delta processing complete — %d folder(s) need regeneration", len(listings))
```

### D6: Tests

**`tests/unit/graph/test_models.py`** — Instantiation and field access of `DriveItem` and `FolderListing`.

**`tests/unit/graph/test_client.py`**
- Mock `msal.ConfidentialClientApplication.acquire_token_for_client`
- Test `get()` constructs correct URL, sends Bearer token, returns parsed JSON
- Test `get()` raises `GraphApiError` on non-2xx response
- Test `put_content()` sends correct Content-Type and body

**`tests/unit/graph/test_delta.py`**
- Mock `azure.storage.blob.BlobServiceClient`
- Test `get_delta_token()` returns `None` when blob not found
- Test `get_delta_token()` returns stored token string when blob exists
- Test `save_delta_token()` calls blob upload with correct content
- Mock `GraphClient.get`
- Test `fetch_changes(None)` calls `/me/drive/root/delta` without token param
- Test `fetch_changes("tok123")` calls `/me/drive/root/delta?token=tok123`
- Test pagination: response with `@odata.nextLink` triggers second call; `@odata.deltaLink` stops loop
- Test loop prevention: items where only `folder_description.md` changed are excluded

**`tests/unit/orchestration/test_processor.py`**
- Mock `DeltaProcessor` and `GraphClient`
- Test `resolve_folders()` deduplicates parent IDs, excludes folder items
- Test `list_folder()` maps Graph children response to `FolderListing`
- Test `process_delta()` calls components in correct order; saves token after listing

**`tests/integration/test_graph_integration.py`**
```python
import pytest, os
pytestmark = pytest.mark.skipif(
    not os.getenv("SF_CLIENT_ID"),
    reason="Real Graph credentials not available"
)

def test_fetch_delta_real():
    # Instantiate real FolderProcessor from env, call process_delta()
    # Assert: returns list (may be empty on clean run), no exception raised
```

**Directory structure for new tests:**
```
tests/
  unit/
    graph/
      __init__.py
      test_models.py
      test_client.py
      test_delta.py
    orchestration/
      __init__.py
      test_processor.py
  integration/
    __init__.py
    test_graph_integration.py
```

### D7: `pyproject.toml` dependency additions

```toml
dependencies = [
    "azure-functions>=1.21",
    "msal>=1.31",
    "azure-storage-blob>=12.23",
]

[dependency-groups]
dev = [
    # existing entries...
    "pytest-mock>=3.14",
]
```

## Acceptance Criteria

1. `poetry install` succeeds with `msal`, `azure-storage-blob`, and `pytest-mock` present in the resolved environment
2. `make lint` passes — ruff reports no errors in `src/semantic_folder/graph/`, `src/semantic_folder/orchestration/`, or updated `timer_trigger.py`
3. `make typecheck` passes — pyright reports no type errors in all new and modified modules
4. `make test` runs and all unit tests pass without real Azure credentials (mocks only)
5. `FolderProcessor.process_delta()` with a mocked delta response returns the correct `FolderListing` objects (correct folder_path and files list)
6. `DeltaProcessor.get_delta_token()` returns `None` when no blob exists (first-run scenario)
7. `DeltaProcessor.fetch_changes(None)` calls Graph with no token parameter; `fetch_changes("tok")` passes `?token=tok`
8. `DeltaProcessor.fetch_changes()` follows `@odata.nextLink` pagination until `@odata.deltaLink` is reached
9. Loop prevention: a delta response where only `folder_description.md` changed in a folder produces zero `FolderListing` entries for that folder
10. `DeltaProcessor.save_delta_token()` persists the new delta token to Azure Blob Storage after each run
11. Timer trigger logs `"Folder to regenerate: <path> (<n> files)"` at INFO level for each folder returned by `process_delta()`
12. Integration test (`SF_CLIENT_ID` set) connects to real Graph API and returns without exception

## Pre-Development Review

### Skills reviewed

| Skill | Relevance |
|-------|-----------|
| architectural-requirements/layer-responsibilities | `graph/` is an adapter layer; `orchestration/` is application layer — no cross-layer leakage |
| architectural-requirements/interface-design | Factory functions provide production wiring; constructor injection enables testability |
| architectural-requirements/error-handling | `GraphAuthError`, `GraphApiError` typed exceptions; timer trigger catches and re-raises |
| architectural-requirements/logging | INFO for folder regeneration list; DEBUG for loop prevention exclusions; no secrets in logs |
| architectural-requirements/testing | Unit tests mock all external I/O; integration test skipped without real credentials |
| architectural-requirements/configuration | Env vars via `os.environ`; factory functions encapsulate production wiring |
| architectural-requirements/security-architecture | No credentials logged; MSAL token cache in-memory only; secrets read from env (Key Vault refs in Azure) |

### Findings

1. **Layer responsibility:** The `graph/` package is a pure adapter — it only translates between Graph API responses and domain models. No business logic in `client.py` or `delta.py`. Business logic (what constitutes "needs regeneration") lives in `orchestration/processor.py`. ✅ Correct.

2. **Dependency direction:** `orchestration/processor.py` depends on `graph/` (adapter). `functions/timer_trigger.py` depends on `orchestration/`. This follows the correct inward dependency direction. ✅ Correct.

3. **Error handling:** Timer trigger catches `Exception` and re-raises after logging — consistent with existing pattern in IT-1 scaffolding. `GraphApiError` carries `status_code` for observability. ✅ Correct.

4. **Loop prevention placement:** Implemented inside `DeltaProcessor.fetch_changes()` rather than in `FolderProcessor`. This is correct — the delta processor is responsible for yielding only actionable items, not the orchestrator. ✅ Correct.

5. **Storage container creation:** `save_delta_token()` creates the container if it does not exist. The container name `semantic-folder-state` is deterministic and idempotent. ✅ No race condition risk in single-instance Azure Function.

6. **`put_content` stub:** Declared in D2 but not yet called. This is intentional — the interface is defined now so IT-4 can add calls without changing the client contract. ✅ Acceptable pre-implementation.

### Specification Review Status: APPROVED

## Independent Validation

### Readiness checklist

- [x] Scope clear and bounded — 4 new modules, 1 updated trigger, 1 pyproject.toml update, tests
- [x] Deliverables actionable — all classes, methods, and signatures specified precisely enough to code
- [x] Acceptance criteria testable — each AC maps to a concrete test assertion or CLI command
- [x] Reference docs identified — architectural-requirements skills listed and checked
- [x] Dependencies satisfied — IT-1 (App Registration, Storage Account, Azure Functions scaffolding) and IT-2 (devcontainer) complete

### Five Pillars check

- [x] **Interface Contracts:** `GraphClient.get()`, `GraphClient.put_content()`, `DeltaProcessor.fetch_changes()`, `FolderProcessor.process_delta()` — all signatures defined with parameter types and return types
- [x] **Data Structures:** `DriveItem` and `FolderListing` dataclass fields specified; Graph API JSON field mappings documented in D3 (`@odata.nextLink`, `@odata.deltaLink`, `parentReference.path`)
- [x] **Configuration Formats:** All env var names listed (`SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_TENANT_ID`, `AzureWebJobsStorage`); blob container and blob name constants documented
- [x] **Behavioral Requirements:** Delta pagination loop termination condition, loop prevention logic, token-first-run behavior, factory function wiring — all specified
- [x] **Quality Criteria:** AC1-AC12 are all measurable via `make test`, `make lint`, `make typecheck`, or direct assertions

### Independent Validation Status: READY_FOR_DEV

## Reference Documents

- `architectural-requirements/layer-responsibilities` — adapter vs. application layer boundaries
- `architectural-requirements/interface-design` — constructor injection + factory function pattern
- `architectural-requirements/error-handling` — typed exceptions, re-raise after logging
- `architectural-requirements/logging` — INFO/DEBUG levels, no secrets in logs
- `architectural-requirements/testing` — mock external I/O, integration test conditional skip
- `architectural-requirements/security-architecture` — credential handling, in-memory token cache
- `iterations/it-1.in.md` — Established Azure infrastructure (App Registration, Storage Account)
- `semantic-folder-grounding.md` — Full product specification, Graph API data flows
