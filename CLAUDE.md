# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**semantic-folder** is an Azure Functions (Python v2) application that auto-generates AI-powered folder descriptions for OneDrive via Microsoft Graph API. It runs on a daily timer, detects file changes via the Graph Delta API, and generates AI-powered descriptions using the Anthropic API (Claude 3.5 Haiku).

## Commands

```bash
poetry install                # Install all dependencies
make lint                     # Ruff check + format verification
make typecheck                # Pyright static type checking
make test                     # Pytest with coverage (--cov=src)
make requirements             # Export poetry lock → requirements.txt
make deploy                   # Deploy to Azure (requires FUNCTION_APP_NAME)
```

Run a single test:
```bash
poetry run pytest tests/unit/graph/test_client.py -v
poetry run pytest tests/unit/graph/test_client.py::TestAcquireToken::test_returns_token_on_success -v
```

## Architecture

Three-layer design with dependency injection throughout:

```
functions/          → Azure Function entry points (timer_trigger, http_trigger)
    ↓
orchestration/      → Business logic (FolderProcessor: delta → resolve → enumerate → describe → upload)
    ↓
description/        → AI description generation (AnthropicDescriber, generator, models)
graph/              → Infrastructure adapters (GraphClient, DeltaProcessor, models)
```

- **config.py** — `AppConfig` frozen dataclass, loaded from env vars via `load_config()`
- **graph/client.py** — `GraphClient` wraps MSAL client-credentials flow + Graph API HTTP calls (`get`, `get_content`, `put_content`)
- **graph/delta.py** — `DeltaProcessor` handles Delta API pagination, blob-stored delta tokens, loop prevention (filters out `folder_description.md`-only changes)
- **graph/models.py** — `DriveItem`, `FolderListing` dataclasses with Graph API field constants
- **description/describer.py** — `AnthropicDescriber` wraps the Anthropic Messages API for file summarization and folder classification
- **description/generator.py** — `generate_description()` coordinates describer calls to produce `FolderDescription` from `FolderListing`
- **description/models.py** — `FileDescription`, `FolderDescription` dataclasses with Markdown serialization
- **orchestration/processor.py** — `FolderProcessor` orchestrates the full pipeline; `process_delta()` is the main entry point
- **functions/timer_trigger.py** — Wires everything via `folder_processor_from_config(config)`

Each module provides a `*_from_config()` factory function for production wiring. Tests inject mocks directly via constructors.

## Code Style

- **Ruff** rules: E, F, I, W, UP, B, SIM, RUF — line length 100
- **Pyright** basic mode, Python 3.12
- **Docstrings**: Google-style (summary, Args/Returns/Raises)
- **Logging**: stdlib `logging`; never log secrets; use `logger.exception()` for errors

## Configuration Management

- All application config lives in `config.py` as a frozen `AppConfig` dataclass
- Required values (vary per environment) have no defaults — `KeyError` at startup if missing
- Domain constants (e.g. blob container name, description filename) have defaults but are overridable via env vars
- Factory functions use the `*_from_config(config: AppConfig)` pattern — they never read `os.environ` directly
- Only `load_config()` reads `os.environ`; all other modules receive config via constructor injection

## Constants

- **Application config** (env vars, domain constants): centralised in `config.py` `AppConfig`
- **MS Graph protocol constants** (`FIELD_*`, `ODATA_*`): stay in `graph/models.py` — fixed API field names that depend on the MS Graph contract
- **MS endpoint constants** (`GRAPH_BASE_URL`, `GRAPH_SCOPES`, `AUTHORITY_BASE_URL`): stay in `graph/client.py` — fixed service URLs
- No magic strings: all string literals used as dict keys, API field names, or config values must be named constants

## Testing

- Tests mirror `src/` structure under `tests/unit/`
- All external I/O (MSAL, BlobServiceClient, Graph HTTP, Anthropic API) is mocked
- Integration tests in `tests/integration/` skip via `@pytest.mark.skipif` when credentials absent
- Coverage target: maintain ≥90%

## Environment Variables

Required: `SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_TENANT_ID`, `SF_DRIVE_USER`, `AzureWebJobsStorage`, `SF_ANTHROPIC_API_KEY`
Optional (with defaults): `SF_DELTA_CONTAINER`, `SF_DELTA_BLOB`, `SF_FOLDER_DESCRIPTION_FILENAME`, `SF_ANTHROPIC_MODEL`

See `.env.example` for the full template.

## Infrastructure

Terraform in `infra/` deploys to Azure (germanywestcentral): Resource Group, Storage Account, Function App (Linux/Python 3.12/Y1), Key Vault with RBAC, Azure AD App Registration. Function App uses SystemAssigned managed identity to read Key Vault secrets via `@Microsoft.KeyVault(SecretUri=...)` references.

## Iteration Process

Development follows numbered iterations in `iterations/`. Each has an input spec (`it-N.in.md`) and completion report (`it-N.out.md`). Currently at IT-5 complete. The system now generates AI-powered folder descriptions using the Anthropic API.
