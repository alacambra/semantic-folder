# Semantic Folder System Ontology

> **Purpose**: Single source of truth for domain concepts and entities.
> **Audience**: Developers, AI assistants, architects.
> **Last Updated**: 2026-03-10
> **Version**: 2.0

---

# Part 1: Conceptual Layer

## 1. Core Domain Concepts

| Concept                     | Definition                                                                                                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Folder Description**      | An AI-generated JSON file containing structured metadata for every file in a OneDrive folder, written back to that folder as `folder_description.json`.                     |
| **Delta Detection**         | The mechanism by which the system discovers which OneDrive folders have changed since the last run, using the Microsoft Graph Delta API.                                    |
| **Metadata Extraction**     | The process of extracting structured JSON metadata (doc_type, language, date, parties, summary, tags, facts) from each file via AI, dispatched by file type (text, docx, pdf, image). |
| **Folder Classification**   | The process of assigning a short category label (e.g. "client-engagement", "insurance-policies") to a folder based on its path and file names.                              |
| **Metadata Caching**        | Content-addressed caching of per-file extracted metadata in Azure Blob Storage, keyed by SHA-256 hash, to avoid redundant LLM calls for unchanged files.                    |
| **Loop Prevention**         | A safety mechanism that excludes folders from processing when the only detected change is the `folder_description.json` file itself, preventing infinite regeneration cycles. |
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
| 6. Describe       |  For each file: check cache → extract JSON metadata via LLM → cache
|                   |  Classify folder type via LLM
+--------+----------+
         |
         v
+-------------------+
| 7. Upload         |  Serialize FolderDescription to JSON, PUT to OneDrive
+--------+----------+
         |
         v
+-------------------+
| 8. Save Token     |  Persist new delta token (only after successful upload)
+-------------------+
```

**Key invariant**: Descriptions are uploaded (step 7) _before_ the delta token is saved (step 8). A failed upload does not advance the token, allowing retry on the next cycle.

### 2.2 Entry Points

| Entry Point      | Trigger                  | Auth           | Notes                                                                     |
| ---------------- | ------------------------ | -------------- | ------------------------------------------------------------------------- |
| `timer_trigger`  | CRON `0 0 2 * * *`       | N/A (internal) | Daily scheduled run                                                       |
| `manual_trigger` | HTTP POST `/api/trigger` | Function key   | On-demand, returns JSON results                                           |
| `health_check`   | HTTP GET `/api/health`   | Anonymous      | Returns `{status, version}`                                               |
| `cleanup_legacy` | HTTP POST `/api/cleanup` | Function key   | Deletes legacy `.yaml`/`.md` description files, supports `?dry_run=true`  |

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
AnthropicDescriber ── produces ── JSON metadata (str), folder type (str)
generate_description ── produces ── FolderDescription (with DocumentRecords)
FolderDescription ── serializes_to ── JSON (folder_description.json)

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

### 6.3 Parties

| Attribute | Type           | Description                                      |
| --------- | -------------- | ------------------------------------------------ |
| `from_`   | `str`          | Who sent or issued the document                  |
| `to`      | `str \| None`  | Who received the document, or None if N/A        |

**Location**: `src/semantic_folder/description/models.py:30`
**Role**: Value object for sender/recipient within a DocumentRecord. `from_` maps to `from` in JSON serialization.

### 6.4 DocumentRecord

| Attribute  | Type                | Description                                                    |
| ---------- | ------------------- | -------------------------------------------------------------- |
| `file`     | `str`               | Filename as it appears in OneDrive                             |
| `doc_type` | `str`               | Controlled vocabulary value from DOC_TYPES (24 allowed values) |
| `doc_lang` | `str`               | Two-letter ISO 639-1 language code                             |
| `date`     | `str`               | Primary date in YYYY-MM-DD format                              |
| `parties`  | `Parties`           | Sender and recipient                                           |
| `summary`  | `str`               | 2-3 sentence factual summary in English                        |
| `tags`     | `list[str]`         | Lowercase keyword list for search (4-8 terms)                  |
| `facts`    | `dict[str, Any]`    | Free-form key-value pairs with domain-specific structured data |
| `period`   | `str \| None`       | Covered time period (e.g. "2024-01 to 2024-12"), or None       |

**Location**: `src/semantic_folder/description/models.py:42`
**Role**: Structured metadata for a single file extracted by the LLM. Universal envelope (file through tags) plus free-form facts block.

### 6.5 FolderDescription

| Attribute     | Type                   | Description                           |
| ------------- | ---------------------- | ------------------------------------- |
| `folder_path` | `str`                  | OneDrive path of the folder           |
| `folder_type` | `str`                  | AI-inferred category label            |
| `overview`    | `str`                  | Brief natural-language folder summary |
| `period`      | `str \| None`          | Covered time period, or None          |
| `documents`   | `list[DocumentRecord]` | Ordered list of document records      |
| `updated_at`  | `str`                  | ISO date string (YYYY-MM-DD)          |

**Location**: `src/semantic_folder/description/models.py:86`
**Role**: The complete output model. Serialized to JSON via `to_json()` and uploaded to OneDrive as `folder_description.json`.

### 6.6 DOC_TYPES

**Location**: `src/semantic_folder/description/models.py:26` (loaded from `resources/doc_types.json` via `json.load()`)
**Type**: `frozenset[str]` — 24 allowed values
**Role**: Controlled vocabulary for `DocumentRecord.doc_type`. Used both for LLM prompt injection (allowed values list) and for validation in `parse_document_record()`. Single source of truth — update `resources/doc_types.json` to add/remove types without code changes.

### 6.7 AppConfig

| Attribute                     | Type    | Description                                                       |
| ----------------------------- | ------- | ----------------------------------------------------------------- |
| `client_id`                   | `str`   | Azure AD application ID                                           |
| `client_secret`               | `str`   | Azure AD client secret                                            |
| `tenant_id`                   | `str`   | Azure AD tenant ID                                                |
| `drive_user`                  | `str`   | OneDrive user UPN or object ID                                    |
| `storage_connection_string`   | `str`   | Azure Storage connection string                                   |
| `anthropic_api_key`           | `str`   | Anthropic API key                                                 |
| `delta_container`             | `str`   | Blob container for delta token                                    |
| `delta_blob`                  | `str`   | Blob path for delta token                                         |
| `folder_description_filename` | `str`   | Name of generated description file                                |
| `anthropic_model`             | `str`   | Model identifier for Claude                                       |
| `max_file_content_bytes`      | `int`   | Max bytes per file for summarization                              |
| `cache_container`             | `str`   | Blob container for summary cache                                  |
| `cache_blob_prefix`           | `str`   | Blob prefix for cached summaries (default `json-metadata-cache/`) |
| `anthropic_max_retries`       | `int`   | Max SDK retry attempts                                            |
| `anthropic_request_delay`     | `float` | Inter-request delay (seconds)                                     |
| `index_filename`              | `str`   | Name of the folder index file                                     |
| `index_owner`                 | `str`   | Owner identifier for the index                                    |

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
| `delete(path)`               | Authenticated DELETE → remove item |

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

**Location**: `src/semantic_folder/description/describer.py:135`
**Purpose**: AI metadata extraction and folder classification via Anthropic Messages API.

| Method                                    | Description                                              |
| ----------------------------------------- | -------------------------------------------------------- |
| `extract_metadata(filename, content)`     | Dispatch by file type → structured JSON metadata string  |
| `classify_folder(folder_path, filenames)` | Folder path + file list → category label                 |
| `summarize_file(filename, content)`       | Legacy: dispatch by file type → one-sentence summary     |

**Primary method — `extract_metadata` file type dispatch**:

```
extract_metadata(filename, content)
    │
    ├── .docx  → _extract_docx()       (extract via python-docx, then extraction prompt)
    ├── .pdf   → _extract_pdf()        (base64 document content block)
    ├── images → _extract_image()      (base64 image content block)
    └── other  → _extract_text_file()  (UTF-8 decode, extraction prompt)
```

**Extraction prompt**: `_EXTRACTION_PROMPT_TEMPLATE` defines the JSON schema, business context, and rules. `{allowed_doc_types}` placeholder is injected dynamically from `DOC_TYPES`. Max tokens: 1024.

**Resilience**: SDK-level retries (`max_retries`), inter-request delay (`time.sleep`). Errors propagate to caller (handled by `generate_description()` fallback).

### 7.4 SummaryCache

**Location**: `src/semantic_folder/description/cache.py:23`
**Purpose**: Content-addressed cache for extracted metadata in Azure Blob Storage.

| Method                       | Description                         |
| ---------------------------- | ----------------------------------- |
| `content_hash(content)`      | SHA-256 hex digest (static)         |
| `get(content_hash)`          | Retrieve cached metadata or `None`  |
| `put(content_hash, metadata)`| Store metadata JSON string in blob  |

**Key scheme**: `{blob_prefix}{sha256_hex}` (e.g. `json-metadata-cache/a1b2c3...`)

### 7.5 FolderProcessor

**Location**: `src/semantic_folder/orchestration/processor.py:33`
**Purpose**: Top-level orchestrator for the full pipeline.

| Method | Description |
| --- | --- |
| `process_delta()` | Full pipeline: token → delta → resolve → enumerate → describe → upload → save token |
| `resolve_folders(items)` | Deduplicate parent folder IDs from changed files |
| `list_folder(folder_id)` | Enumerate folder children → `FolderListing` |
| `read_file_contents(listing)` | Download file bytes via Graph API |
| `upload_description(listing)` | Generate description + upload JSON |
| `update_index()` | Rebuild and upload the folder index file |
| `cleanup_legacy_descriptions(dry_run)` | Delete legacy `.yaml`/`.md` description files from OneDrive |

## 8. Value Objects

| Value Object        | Location                    | Description                                          |
| ------------------- | --------------------------- | ---------------------------------------------------- |
| `Parties`           | `description/models.py:30`  | Immutable sender/recipient pair                      |
| `DocumentRecord`    | `description/models.py:42`  | Immutable structured metadata for a single file      |
| `DriveItem`         | `graph/models.py:21`        | Immutable snapshot of a Graph drive item             |
| `FolderListing`     | `graph/models.py:33`        | Immutable snapshot of a folder's file list           |
| `FolderDescription` | `description/models.py:86`  | Immutable folder description with JSON serialization |

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
| `ValueError`     | `description/describer.py:107` | No `TextBlock` in Anthropic response                        |
| `ValueError`     | `description/generator.py:99`  | JSON parse failure in `parse_document_record()`             |
| `ValueError`     | `description/generator.py:102` | Extracted data is not a JSON object                         |
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
