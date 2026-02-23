---
document_id: GAP-3-TO-4
version: 1.0.0
last_updated: 2026-02-23
purpose: Document commits between IT-3 tag (v0.2.0) and IT-4 start
---

# Gap: IT-3 -> IT-4

## Untracked Commits

| Commit    | Date       | Author    | Message                                                        |
| --------- | ---------- | --------- | -------------------------------------------------------------- |
| `8ba0b36` | 2026-02-23 | alacambra | feat: improve build pipeline and adopt structured logging      |
| `2611d17` | 2026-02-23 | alacambra | feat: add manual HTTP trigger for on-demand delta processing   |

## Change Details

### 8ba0b36 -- feat: improve build pipeline and adopt structured logging

**Files changed:** `.gitignore`, `.vscode/tasks.json`, `Makefile`, `infra/host.json`, `requirements.txt`, `src/semantic_folder/functions/http_trigger.py`, `src/semantic_folder/functions/timer_trigger.py`, `src/semantic_folder/graph/client.py`, `src/semantic_folder/graph/delta.py`, `src/semantic_folder/orchestration/processor.py`

**Changes:**

- Refactored `Makefile` to add `package` target for clean Azure deployment packaging (copies only deployment artifacts into `dist/publish/`)
- Added `deploy` VS Code task in `.vscode/tasks.json` for IDE-driven deployment
- Added `requirements.txt` to `.gitignore` since it is a generated file
- Standardised all log messages across `http_trigger.py`, `timer_trigger.py`, `client.py`, `delta.py`, and `processor.py` to use `[function_name]` prefix format with semicolon-delimited structured fields for observability
- Added `infra/host.json` (infrastructure-specific host config)

**Classification:** Post-iteration improvement -- operational hygiene and observability enhancements. Extends IT-3 deliverables D5 (timer trigger), D2 (graph client), D3 (delta processor), and D4 (folder processor) with improved logging format. Build pipeline enhancement extends IT-1 deployment workflow.

### 2611d17 -- feat: add manual HTTP trigger for on-demand delta processing

**Files changed:** `src/semantic_folder/functions/http_trigger.py`

**Changes:**

- Added `POST /api/trigger` endpoint (`manual_trigger` function) with `AuthLevel.FUNCTION` authentication
- Endpoint executes the same delta processing pipeline as the timer trigger but returns results as JSON HTTP response
- Response includes `status`, `folders_processed` count, and per-folder `folder_path` and `file_count` details
- Error handling follows the same pattern as existing functions (catch `Exception`, log with `exc_info`, return 500)

**Classification:** New feature -- enables on-demand triggering of the delta processing pipeline without waiting for the 5-minute timer schedule. This was not part of IT-3 scope but uses the IT-3 infrastructure (`FolderProcessor.process_delta()`) without modification.

**Traceability:** Both commits use only the existing IT-3 API surface (`load_config()`, `folder_processor_from_config()`, `process_delta()`). No new modules or external dependencies introduced. The `manual_trigger` endpoint currently lacks dedicated unit tests -- this should be addressed in a future iteration.

**Action required:** None -- changes are self-contained and do not affect IT-4 scope or design. The `manual_trigger` endpoint will benefit from IT-4's implementation since it will also trigger folder description generation in future.
