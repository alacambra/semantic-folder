---
document_id: IT-3-OUT
version: 1.0.0
last_updated: 2026-02-22
status: Complete
iteration_ref: IT-3-IN
---

# Iteration 3 — Completion Report: Microsoft Graph Integration

## Summary

IT-3 delivered the Microsoft Graph integration layer for the semantic-folder system. The timer trigger now runs a full delta processing pipeline every 5 minutes: it authenticates via MSAL, retrieves changed OneDrive items from the delta API, enumerates affected folders, and logs which folders need description regeneration. No AI generation yet — that is IT-4.

All 12 acceptance criteria pass. `make lint`, `make typecheck`, and `make test` are all clean (53 passed, 1 skipped).

**Post-spec deviation:** During testing preparation it was discovered that `/me/drive/root/delta` is unavailable with app-only permissions (client credentials flow). All delta and folder-children calls were updated to use `/users/{upn}/drive/...` instead, with `SF_DRIVE_USER` as a required environment variable. This is the correct Graph API pattern for service principals with admin-consented `Files.ReadWrite.All`.

## Deliverables Completed

| Deliverable | Spec ref | Status |
|-------------|----------|--------|
| `src/semantic_folder/graph/models.py` | D1 | Complete |
| `src/semantic_folder/graph/client.py` | D2 | Complete |
| `src/semantic_folder/graph/delta.py` | D3 | Complete |
| `src/semantic_folder/orchestration/processor.py` | D4 | Complete |
| `src/semantic_folder/functions/timer_trigger.py` | D5 | Complete |
| Tests (unit + integration stub) | D6 | Complete |
| `pyproject.toml` dependency additions | D7 | Complete |

## Files Created / Modified

| File | Status | Lines |
|------|--------|-------|
| `src/semantic_folder/graph/models.py` | Created | 24 |
| `src/semantic_folder/graph/client.py` | Created | 138 |
| `src/semantic_folder/graph/delta.py` | Created | 216 |
| `src/semantic_folder/orchestration/processor.py` | Created | 120 |
| `src/semantic_folder/graph/__init__.py` | Created | 0 |
| `src/semantic_folder/orchestration/__init__.py` | Created | 0 |
| `src/semantic_folder/functions/timer_trigger.py` | Modified | 41 |
| `pyproject.toml` | Modified | 46 |
| `tests/unit/graph/__init__.py` | Created | 0 |
| `tests/unit/graph/test_models.py` | Created | 81 |
| `tests/unit/graph/test_client.py` | Created | 183 |
| `tests/unit/graph/test_delta.py` | Created | 332 |
| `tests/unit/orchestration/__init__.py` | Created | 0 |
| `tests/unit/orchestration/test_processor.py` | Created | 309 |
| `tests/integration/__init__.py` | Created | 0 |
| `tests/integration/test_graph_integration.py` | Created | 28 |
| `tests/unit/test_smoke.py` | Modified | — |
| `.env.example` | Modified | 16 |
| `src/semantic_folder/config.py` | Created | 58 |
| `infra/function_app.tf` | Modified | — |
| `infra/keyvault.tf` | Modified | — |
| `host.json` | Modified | 18 |

## Validation Results

| Check | Command | Result |
|-------|---------|--------|
| Lint | `make lint` | PASS — 0 ruff errors, 23 files formatted |
| Type check | `make typecheck` | PASS — 0 pyright errors, 0 warnings |
| Tests | `make test` | PASS — 53 passed, 1 skipped, 93% coverage |

Integration test skipped: `SF_CLIENT_ID` not set in CI environment — correct and expected.

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `poetry install` succeeds with `msal`, `azure-storage-blob`, `pytest-mock` | PASS |
| 2 | `make lint` passes — 0 ruff errors | PASS |
| 3 | `make typecheck` passes — 0 pyright errors | PASS |
| 4 | `make test` runs and all unit tests pass without real credentials | PASS |
| 5 | `FolderProcessor.process_delta()` with mocked delta returns correct `FolderListing` objects | PASS |
| 6 | `DeltaProcessor.get_delta_token()` returns `None` when no blob exists | PASS |
| 7 | `fetch_changes(None)` calls `/users/{upn}/drive/root/delta` without token; `fetch_changes("tok")` passes `?token=tok` | PASS |
| 8 | `fetch_changes()` follows `@odata.nextLink` pagination until `@odata.deltaLink` | PASS |
| 9 | Loop prevention: folder where only `folder_description.md` changed → 0 `FolderListing` entries | PASS |
| 10 | `save_delta_token()` persists new delta token to Azure Blob Storage | PASS |
| 11 | Timer trigger logs `"Folder to regenerate: <path> (<n> files)"` at INFO per folder | PASS |
| 12 | Integration test (with real credentials) connects without exception | SKIP (no credentials in env) |

## Reference Documentation Review

### architectural-requirements/layer-responsibilities

- `graph/` package is a pure adapter — translates Graph API responses to domain models only. No business logic.
- `orchestration/processor.py` is the application layer — contains the "what constitutes needs regeneration" logic (`resolve_folders`).
- `functions/timer_trigger.py` is the entry point — calls the application layer only, no direct Graph calls.
- Dependency direction: `functions/` → `orchestration/` → `graph/`. Correct inward direction. **PASS**

### architectural-requirements/interface-design

- All classes accept dependencies via constructor injection (`GraphClient`, `DeltaProcessor` injected into `FolderProcessor`).
- Factory functions (`*_from_config(config: AppConfig)`) encapsulate production wiring. Originally named `*_from_env()`, renamed during config centralisation to reflect that they receive an `AppConfig` instance rather than reading `os.environ` directly.
- Timer trigger uses factory — single call wires the full chain. **PASS**

### architectural-requirements/error-handling

- `GraphAuthError` and `GraphApiError(status_code, message)` are typed exceptions.
- `GraphApiError` carries `status_code` for observability.
- Timer trigger catches `Exception`, logs with `logger.exception()`, and re-raises — consistent with IT-1 scaffolding pattern.
- `ValueError` raised in `fetch_changes()` if delta response lacks `@odata.deltaLink` (malformed response guard). **PASS**

### architectural-requirements/logging

- MSAL token acquisition failure logged at ERROR before raising.
- Loop prevention exclusions logged at DEBUG (not INFO — avoids log noise on steady-state runs).
- Delta token operations logged at DEBUG.
- Timer trigger logs folder path + file count at INFO per folder, and final count summary.
- No secrets or tokens appear in any log message. **PASS**

### architectural-requirements/testing

- All external I/O mocked in unit tests (`msal`, `BlobServiceClient`, `GraphClient.get`).
- Integration test uses `pytest.mark.skipif` conditional on `SF_CLIENT_ID` env var — clean skip, not an error.
- Coverage: 93% overall; new modules at 92–100%. **PASS**

### architectural-requirements/security-architecture

- No credentials logged at any level.
- MSAL token cache is in-memory only (MSAL default — no persistence to disk or logs).
- Secrets read from `os.environ` only via centralised `load_config()` in `config.py`; no other module reads env vars directly.
- `put_content()` raises `NotImplementedError` (stub) — no risk of accidental writes in this iteration. **PASS**

## Traceability

| Spec requirement | Implementation | Test |
|-----------------|----------------|------|
| MSAL auth via `ConfidentialClientApplication` | `GraphClient.__init__`, `_acquire_token` | `test_client.py::test_get_acquires_token` |
| `get()` sends Bearer token, returns parsed JSON | `GraphClient.get` | `test_client.py::test_get_success` |
| `GraphApiError` on non-2xx | `GraphClient.get` → `HTTPError` handler | `test_client.py::test_get_raises_graph_api_error_on_non2xx` |
| Delta token read from blob | `DeltaProcessor.get_delta_token` | `test_delta.py::test_get_delta_token_returns_none_when_not_found` |
| Delta token write to blob (create container if missing) | `DeltaProcessor.save_delta_token` | `test_delta.py::test_save_delta_token_uploads_encoded_token` |
| First-run delta call (no token param) | `DeltaProcessor.fetch_changes(None)` | `test_delta.py::test_fetch_changes_first_run_no_token` |
| Subsequent delta call (token param) | `DeltaProcessor.fetch_changes("tok")` | `test_delta.py::test_fetch_changes_with_token` |
| Pagination via `@odata.nextLink` | `DeltaProcessor.fetch_changes` loop | `test_delta.py::test_fetch_changes_follows_pagination` |
| Loop prevention | `DeltaProcessor._apply_loop_prevention` | `test_delta.py::test_fetch_changes_loop_prevention_*` |
| `resolve_folders` deduplicates parent IDs | `FolderProcessor.resolve_folders` | `test_processor.py::test_resolve_folders_*` |
| `list_folder` maps children response | `FolderProcessor.list_folder` | `test_processor.py::test_list_folder_*` |
| `process_delta` full pipeline order | `FolderProcessor.process_delta` | `test_processor.py::test_process_delta_*` |
| Timer trigger logs per-folder + summary | `timer_trigger.py` | `test_smoke.py` (import smoke), manual `func start` |

## Troubleshooting

Issues discovered and resolved during deployment and operational testing.

### T1: `/me/drive/...` unavailable with app-only permissions

- **Symptom**: Graph API returns 403 Forbidden when calling `/me/drive/root/delta`
- **Cause**: The client credentials flow (app-only) does not support the `/me/` endpoint — it requires a delegated user context
- **Fix**: Changed all Graph API calls to `/users/{upn}/drive/...` and added `SF_DRIVE_USER` as a required environment variable (see "Post-spec deviation" in Summary)

### T2: Log streaming unsupported on Linux Consumption plan

- **Symptom**: `func azure functionapp logstream` returns an error on the deployed function
- **Cause**: Live log streaming is not supported on the Linux Consumption (Y1) tier
- **Fix**: Provisioned Application Insights infrastructure in Terraform (`azurerm_log_analytics_workspace` + `azurerm_application_insights` in `function_app.tf`), wired `application_insights_connection_string` into the Function App's `site_config`

### T3: Python INFO logs not appearing in Application Insights

- **Symptom**: Azure Functions host traces visible in App Insights but Python `logger.info()` output missing
- **Cause**: `host.json` had `logLevel.default` set too restrictively and Application Insights sampling was dropping entries
- **Fix**: Updated `host.json` — set `logLevel.default` to `"Information"`, added `logLevel."Function.timer_trigger"` at `"Information"`, and set `samplingSettings.isEnabled` to `false`

### T4: `requirements.txt` missing for deployment

- **Symptom**: `func azure functionapp publish` fails with "requirements.txt is required for python function apps"
- **Cause**: Python Function Apps require a `requirements.txt` at the project root; Poetry does not generate one automatically
- **Fix**: Run `make requirements` (which executes `poetry export --without-hashes --only main -o requirements.txt`) before publishing. The `make deploy` target already depends on this

### T5: Terraform Key Vault secrets had placeholder values

- **Symptom**: Key Vault secrets contained literal `"placeholder"` strings instead of real credentials
- **Cause**: Initial Terraform setup in IT-1 used placeholder values pending App Registration output availability
- **Fix**: Wired real Terraform references into `keyvault.tf`: `azuread_application.semantic_folder.client_id`, `azuread_application_password.semantic_folder.value`, `data.azuread_client_config.current.tenant_id`

### T6: Env var prefix inconsistency (GRAPH_* vs SF_*)

- **Symptom**: Function App `app_settings` in Terraform used `GRAPH_CLIENT_ID` etc., but application code expected `SF_CLIENT_ID`
- **Cause**: Terraform `function_app.tf` was written before the `SF_` env var naming convention was established in IT-3
- **Fix**: Renamed all `GRAPH_*` references to `SF_*` in `function_app.tf` `app_settings` and corresponding Key Vault secret names in `keyvault.tf`

### T7: Centralised configuration (`config.py`)

- **Symptom**: Environment variable names and domain constants scattered across `client.py`, `delta.py`, and `processor.py` — each module reading `os.environ` independently
- **Cause**: Original IT-3 spec had each factory function reading its own env vars
- **Fix**: Created `src/semantic_folder/config.py` with a frozen `AppConfig` dataclass. `load_config()` is the single entry point for env var reads. All factory functions renamed from `*_from_env()` to `*_from_config(config: AppConfig)` and receive config via constructor injection
