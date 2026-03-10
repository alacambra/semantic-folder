# Semantic Folder System Ontology

> **Purpose**: Single source of truth for domain concepts and entities.
> **Audience**: Developers, AI assistants, architects.
> **Last Updated**: 2026-03-10
> **Version**: 1.0

---

# Part 1: Conceptual Layer

## 1. Core Domain Concepts

| Concept                     | Definition                                                                                                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Folder Description**      | An AI-generated Markdown file summarizing the contents of a OneDrive folder, written back to that folder as `folder_description.md`.                                        |
| **Delta Detection**         | The mechanism by which the system discovers which OneDrive folders have changed since the last run, using the Microsoft Graph Delta API.                                    |
| **File Summarization**      | The process of generating a one-sentence AI summary for each file in a changed folder, dispatched by file type (text, docx, pdf, image).                                    |
| **Folder Classification**   | The process of assigning a short category label (e.g. "project-docs", "invoices") to a folder based on its path and file names.                                             |
| **Summary Caching**         | Content-addressed caching of per-file summaries in Azure Blob Storage, keyed by SHA-256 hash, to avoid redundant LLM calls for unchanged files.                             |
| **Loop Prevention**         | A safety mechanism that excludes folders from processing when the only detected change is the `folder_description.md` file itself, preventing infinite regeneration cycles. |
| **Delta Token Persistence** | Storage of the Microsoft Graph delta token in Azure Blob Storage so the system can resume incremental change tracking across runs.                                          |

## 2. Business Workflows

### 2.1 Primary Workflow: Delta-to-Description Pipeline

The system runs on a daily timer (02:00 UTC) or on-demand via HTTP trigger.

```
+-------------------+
| 1. Get Delta Token|  Read persisted token from blob (None on first run)
+--------+----------+
         |
         v
+-------------------+
| 2. Fetch Changes  |  Call Graph Delta API, paginate, apply loop prevention
+--------+----------+
         |
         v
+-------------------+
| 3. Resolve Folders|  Deduplicate parent folder IDs from changed file items
+--------+----------+
         |
         v
+-------------------+
| 4. Enumerate      |  GET /children for each folder → FolderListing
+--------+----------+
         |
         v
+-------------------+
| 5. Read Contents  |  Download raw bytes for each file via Graph API
+--------+----------+
         |
         v
+-------------------+
| 6. Describe       |  For each file: check cache → summarize via LLM → cache result
|                   |  Classify folder type via LLM
+--------+----------+
         |
         v
+-------------------+
| 7. Upload         |  Serialize FolderDescription to Markdown, PUT to OneDrive
+--------+----------+
         |
         v
+-------------------+
| 8. Save Token     |  Persist new delta token (only after successful upload)
+-------------------+
```

**Key invariant**: Descriptions are uploaded (step 7) _before_ the delta token is saved (step 8). A failed upload does not advance the token, allowing retry on the next cycle.

### 2.2 Entry Points

| Entry Point      | Trigger                  | Auth           | Notes                           |
| ---------------- | ------------------------ | -------------- | ------------------------------- |
| `timer_trigger`  | CRON `0 0 2 * * *`       | N/A (internal) | Daily scheduled run             |
| `manual_trigger` | HTTP POST `/api/trigger` | Function key   | On-demand, returns JSON results |
| `health_check`   | HTTP GET `/api/health`   | Anonymous      | Returns `{status, version}`     |

## 3. External Dependencies

| System                  | Protocol                  | Purpose                                                             |
| ----------------------- | ------------------------- | ------------------------------------------------------------------- |
| **Microsoft Graph API** | HTTPS REST                | OneDrive delta, folder children, file content download, file upload |
| **Azure AD / MSAL**     | OAuth2 client credentials | Authentication for Graph API                                        |
| **Anthropic API**       | HTTPS REST                | File summarization, folder classification (Claude Haiku)            |
| **Azure Blob Storage**  | Azure SDK                 | Delta token persistence, summary cache                              |
| **Azure Key Vault**     | RBAC + secret references  | Secrets management (production)                                     |

## 4. Semantic Relationships

```
AppConfig ─────── configures ──────┬── GraphClient
                                   ├── DeltaProcessor
                                   ├── AnthropicDescriber
                                   └── SummaryCache

FolderProcessor ── orchestrates ──── Delta-to-Description Pipeline
                 ├─ delegates_to ── DeltaProcessor   (steps 1-2, 8)
                 ├─ delegates_to ── GraphClient       (steps 4-5, 7)
                 ├─ delegates_to ── AnthropicDescriber (step 6)
                 └─ delegates_to ── SummaryCache       (step 6)

DeltaProcessor ─── produces ────── list[DriveItem]
FolderProcessor ── produces ────── FolderListing
AnthropicDescriber ── produces ── file summaries (str), folder type (str)
generate_description ── produces ── FolderDescription
FolderDescription ── serializes_to ── Markdown (folder_description.md)

SummaryCache ──── validates ────── content identity via SHA-256 hash
DeltaProcessor ── governs ──────── loop prevention (filters self-changes)
```

---

# Part 2: Entity Reference Model

## 5. Aggregate Roots & Boundaries

This system has no database; all persistence is blob-based. The concept of aggregates applies at the orchestration level.

### 5.1 FolderProcessor (Orchestration Aggregate)

```
FolderProcessor
├── owns DeltaProcessor     (delta token lifecycle)
├── owns GraphClient        (all Graph API I/O)
├── owns AnthropicDescriber (all LLM I/O)
└── owns SummaryCache       (cache lifecycle)
```

The `FolderProcessor` is the composition root for the pipeline. All child components are injected via constructor and share no state between them.

## 6. Entity Catalog

### 6.1 DriveItem

| Attribute     | Type   | Description                   |
| ------------- | ------ | ----------------------------- |
| `id`          | `str`  | OneDrive item ID              |
| `name`        | `str`  | File or folder name           |
| `parent_id`   | `str`  | Parent folder's item ID       |
| `parent_path` | `str`  | Parent folder's OneDrive path |
| `is_folder`   | `bool` | True if item is a folder      |
| `is_deleted`  | `bool` | True if item was deleted      |

**Location**: `src/semantic_folder/graph/models.py:21`
**Role**: Transient data object parsed from Graph Delta API responses. No persistence — exists only during pipeline execution.

### 6.2 FolderListing

| Attribute     | Type        | Description                    |
| ------------- | ----------- | ------------------------------ |
| `folder_id`   | `str`       | OneDrive item ID of the folder |
| `folder_path` | `str`       | OneDrive path of the folder    |
| `files`       | `list[str]` | File names in the folder       |
| `file_ids`    | `list[str]` | Corresponding file item IDs    |

**Location**: `src/semantic_folder/graph/models.py:33`
**Role**: Represents an enumerated folder's contents. Produced by `FolderProcessor.list_folder()`, consumed by content reading and description generation.

### 6.3 FileDescription

| Attribute  | Type  | Description                       |
| ---------- | ----- | --------------------------------- |
| `filename` | `str` | Name of the file                  |
| `summary`  | `str` | AI-generated one-sentence summary |

**Location**: `src/semantic_folder/description/models.py:9`
**Role**: Value object representing a single file's summary within a folder description.

### 6.4 FolderDescription

| Attribute     | Type                    | Description                       |
| ------------- | ----------------------- | --------------------------------- |
| `folder_path` | `str`                   | OneDrive path of the folder       |
| `folder_type` | `str`                   | AI-inferred category label        |
| `files`       | `list[FileDescription]` | Ordered list of file descriptions |
| `updated_at`  | `str`                   | ISO date string (YYYY-MM-DD)      |

**Location**: `src/semantic_folder/description/models.py:23`
**Role**: The complete output model. Serialized to Markdown via `to_markdown()` and uploaded to OneDrive as `folder_description.md`.

### 6.5 AppConfig

| Attribute                     | Type    | Description                          |
| ----------------------------- | ------- | ------------------------------------ |
| `client_id`                   | `str`   | Azure AD application ID              |
| `client_secret`               | `str`   | Azure AD client secret               |
| `tenant_id`                   | `str`   | Azure AD tenant ID                   |
| `drive_user`                  | `str`   | OneDrive user UPN or object ID       |
| `storage_connection_string`   | `str`   | Azure Storage connection string      |
| `anthropic_api_key`           | `str`   | Anthropic API key                    |
| `delta_container`             | `str`   | Blob container for delta token       |
| `delta_blob`                  | `str`   | Blob path for delta token            |
| `folder_description_filename` | `str`   | Name of generated description file   |
| `anthropic_model`             | `str`   | Model identifier for Claude          |
| `max_file_content_bytes`      | `int`   | Max bytes per file for summarization |
| `cache_container`             | `str`   | Blob container for summary cache     |
| `cache_blob_prefix`           | `str`   | Blob prefix for cached summaries     |
| `anthropic_max_retries`       | `int`   | Max SDK retry attempts               |
| `anthropic_request_delay`     | `float` | Inter-request delay (seconds)        |

**Location**: `src/semantic_folder/config.py:8`
**Role**: Frozen dataclass. Single source of truth for all configuration. Only `load_config()` reads environment variables; all other modules receive config via constructor injection.

## 7. Service Components

### 7.1 GraphClient

**Location**: `src/semantic_folder/graph/client.py:36`
**Purpose**: Authenticated HTTP client for Microsoft Graph API.

| Method                       | Description                        |
| ---------------------------- | ---------------------------------- |
| `get(path)`                  | Authenticated GET → parsed JSON    |
| `get_content(path)`          | Authenticated GET → raw bytes      |
| `put_content(path, content)` | Authenticated PUT → upload content |

**Authentication**: MSAL client credentials flow via `ConfidentialClientApplication`.

### 7.2 DeltaProcessor

**Location**: `src/semantic_folder/graph/delta.py:33`
**Purpose**: Manages Graph Delta API pagination, token persistence, and loop prevention.

| Method                    | Description                                                |
| ------------------------- | ---------------------------------------------------------- |
| `get_delta_token()`       | Read persisted token from blob                             |
| `save_delta_token(token)` | Write token to blob                                        |
| `fetch_changes(token)`    | Fetch + paginate + filter → `(list[DriveItem], new_token)` |

### 7.3 AnthropicDescriber

**Location**: `src/semantic_folder/description/describer.py:82`
**Purpose**: AI description generation via Anthropic Messages API.

| Method                                    | Description                                  |
| ----------------------------------------- | -------------------------------------------- |
| `summarize_file(filename, content)`       | Dispatch by file type → one-sentence summary |
| `classify_folder(folder_path, filenames)` | Folder path + file list → category label     |

**File type dispatch**:

```
summarize_file(filename, content)
    │
    ├── .docx  → _summarize_docx()   (extract via python-docx, then text prompt)
    ├── .pdf   → _summarize_pdf()    (base64 document content block)
    ├── images → _summarize_image()  (base64 image content block)
    └── other  → _summarize_text()   (UTF-8 decode, text prompt)
```

**Resilience**: SDK-level retries (`max_retries`), inter-request delay (`time.sleep`), per-method exception catch with fallback strings.

### 7.4 SummaryCache

**Location**: `src/semantic_folder/description/cache.py:23`
**Purpose**: Content-addressed cache for file summaries in Azure Blob Storage.

| Method                       | Description                       |
| ---------------------------- | --------------------------------- |
| `content_hash(content)`      | SHA-256 hex digest (static)       |
| `get(content_hash)`          | Retrieve cached summary or `None` |
| `put(content_hash, summary)` | Store summary in blob             |

**Key scheme**: `{blob_prefix}{sha256_hex}` (e.g. `summary-cache/a1b2c3...`)

### 7.5 FolderProcessor

**Location**: `src/semantic_folder/orchestration/processor.py:33`
**Purpose**: Top-level orchestrator for the full pipeline.

| Method                        | Description                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| `process_delta()`             | Full pipeline: token → delta → resolve → enumerate → describe → upload → save token |
| `resolve_folders(items)`      | Deduplicate parent folder IDs from changed files                                    |
| `list_folder(folder_id)`      | Enumerate folder children → `FolderListing`                                         |
| `read_file_contents(listing)` | Download file bytes via Graph API                                                   |
| `upload_description(listing)` | Generate description + upload Markdown                                              |

## 8. Value Objects

| Value Object        | Location                   | Description                                     |
| ------------------- | -------------------------- | ----------------------------------------------- |
| `FileDescription`   | `description/models.py:9`  | Immutable filename + summary pair               |
| `DriveItem`         | `graph/models.py:21`       | Immutable snapshot of a Graph drive item        |
| `FolderListing`     | `graph/models.py:33`       | Immutable snapshot of a folder's file list      |
| `FolderDescription` | `description/models.py:23` | Immutable folder description with serialization |

Note: All are dataclasses without identity semantics — equality is by value. None are persisted directly; they are transient pipeline data.

## 9. Constants Reference

### 9.1 Graph API Protocol Constants

**Location**: `src/semantic_folder/graph/models.py`

| Constant                 | Value                | Purpose                               |
| ------------------------ | -------------------- | ------------------------------------- |
| `FIELD_ID`               | `"id"`               | Item ID field                         |
| `FIELD_NAME`             | `"name"`             | Item name field                       |
| `FIELD_FOLDER`           | `"folder"`           | Folder facet (presence = is folder)   |
| `FIELD_DELETED`          | `"deleted"`          | Deleted facet (presence = is deleted) |
| `FIELD_PARENT_REFERENCE` | `"parentReference"`  | Parent reference object               |
| `FIELD_PATH`             | `"path"`             | Path within parent reference          |
| `FIELD_TOKEN`            | `"token"`            | Delta token query parameter           |
| `ODATA_DELTA_LINK`       | `"@odata.deltaLink"` | Final pagination link with new token  |
| `ODATA_NEXT_LINK`        | `"@odata.nextLink"`  | Next pagination link                  |
| `ODATA_VALUE`            | `"value"`            | Array of items in response            |

### 9.2 Graph Endpoint Constants

**Location**: `src/semantic_folder/graph/client.py`

| Constant             | Value                                      |
| -------------------- | ------------------------------------------ |
| `GRAPH_BASE_URL`     | `https://graph.microsoft.com/v1.0`         |
| `GRAPH_SCOPES`       | `["https://graph.microsoft.com/.default"]` |
| `AUTHORITY_BASE_URL` | `https://login.microsoftonline.com`        |

### 9.3 Describer Constants

**Location**: `src/semantic_folder/description/describer.py`

| Constant                         | Value                        | Purpose                          |
| -------------------------------- | ---------------------------- | -------------------------------- |
| `DEFAULT_MAX_FILE_CONTENT_BYTES` | `8192`                       | Max bytes read per file          |
| `DEFAULT_MAX_RETRIES`            | `3`                          | SDK retry attempts               |
| `DEFAULT_REQUEST_DELAY`          | `1.0`                        | Inter-request throttle (seconds) |
| `_IMAGE_EXTENSIONS`              | `.png .jpg .jpeg .gif .webp` | Supported image types            |

## 10. Error Handling

| Exception        | Location                      | Raised When                                                  |
| ---------------- | ----------------------------- | ------------------------------------------------------------ |
| `GraphAuthError` | `graph/client.py:23`          | MSAL token acquisition fails                                 |
| `GraphApiError`  | `graph/client.py:27`          | Graph API returns non-2xx (carries `status_code`, `message`) |
| `ValueError`     | `graph/delta.py:153`          | Delta response missing `@odata.deltaLink`                    |
| `ValueError`     | `description/describer.py:54` | No `TextBlock` in Anthropic response                         |
| `KeyError`       | `config.py` (implicit)        | Required env var missing at startup                          |

## 11. Dependency Injection Pattern

All modules follow the `*_from_config(config: AppConfig)` factory pattern:

```
load_config()                           ← only place that reads os.environ
    │
    v
AppConfig ──┬── graph_client_from_config()     → GraphClient
            ├── delta_processor_from_config()   → DeltaProcessor
            ├── anthropic_describer_from_config()→ AnthropicDescriber
            ├── summary_cache_from_config()     → SummaryCache
            └── folder_processor_from_config()  → FolderProcessor (wires all above)
```

Tests inject mocks directly via constructors, bypassing factory functions entirely.

## 12. Module Dependency Graph

```
functions/
├── timer_trigger.py ──┐
└── http_trigger.py  ──┤
                       v
              orchestration/
              └── processor.py ──┬── graph/client.py
                                 ├── graph/delta.py ──── graph/client.py
                                 ├── graph/models.py
                                 ├── description/describer.py
                                 ├── description/generator.py
                                 ├── description/cache.py
                                 └── description/models.py
                                      │
                                 config.py (injected everywhere)
```

No circular dependencies. All arrows point downward from entry points through orchestration to infrastructure adapters.
