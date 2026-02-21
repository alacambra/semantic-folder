---
document_id: IT-1-IN
version: 1.2.0
last_updated: 2026-02-21
status: Ready
purpose: Project bootstrap — DevOps foundation and Azure Functions deployment infrastructure
audience: [Developers, reviewers]
dependencies: []
review_triggers: [Scope changes, requirements updated]
---

# Iteration 1: DevOps Foundation & Azure Functions Deployment

## Objective

Establish the Python project scaffolding, local development environment, Terraform-managed Azure infrastructure, and a deployable Azure Function App — so that all subsequent iterations have a working CI/CD pipeline and can deploy code to Azure from day one.

## Motivation

**Business driver:** Datamantics UG needs Semantic Folder Grounding deployed as an Azure Function that runs against their OneDrive. Before any application logic can be built, the deployment pipeline and Azure infrastructure must exist.

**How this iteration fulfills it:** This iteration delivers a deployable "hello world" Azure Function with the full DevOps chain: local dev environment (pyenv + Poetry), Terraform-provisioned Azure resources (Function App, Storage Account, App Registration), and a working deployment flow. After this iteration, `func azure functionapp publish` works and the function runs in Azure.

## Prerequisites

The following tools must be installed locally before development begins:

| Tool | Version | Install |
|------|---------|---------|
| pyenv | latest | `brew install pyenv` |
| Python | 3.12.x (via pyenv) | `pyenv install 3.12` |
| Poetry | ≥2.0 | already installed |
| Azure CLI | latest | `brew install azure-cli` |
| Azure Functions Core Tools | v4 | `brew tap azure/functions && brew install azure-functions-core-tools@4` |
| Terraform | ≥1.5 | `brew install terraform` |

Additionally required:

- Azure subscription with permissions to create resources
- Azure AD admin consent for App Registration API permissions

## Scope

### In Scope

1. **Local development environment**
   - pyenv with Python 3.12
   - Poetry project with `src/` layout
   - pyproject.toml with production dependency: `azure-functions`
   - pyproject.toml with dev dependencies: ruff, pyright, pytest, pytest-asyncio, pytest-cov
   - .python-version file (3.12.x)

2. **Azure Functions project structure (V2 programming model)**
   - `function_app.py` at project root — V2 entry point, registers blueprints from `src/`
   - `sys.path` manipulation in `function_app.py` to resolve `src/` layout imports
   - Timer trigger blueprint (runs on schedule — PoC trigger)
   - HTTP trigger blueprint (health check / future webhook endpoint)
   - `host.json`, `local.settings.json` (gitignored), `.funcignore`

3. **Terraform infrastructure**
   - Resource Group
   - Storage Account (required by Functions runtime + future delta token persistence)
   - App Service Plan (Consumption / Y1)
   - Function App (Python 3.12 runtime, Linux)
   - App Registration (Entra ID) with `Files.ReadWrite.All`, `Sites.Read.All` permissions
   - Key Vault for secrets (Graph client secret, AI API keys)
   - Output: Function App URL, Key Vault URI, Storage connection string
   - State: local `.tfstate` file (remote backend deferred to CI/CD iteration)

4. **Configuration and secrets**
   - `local.settings.json` for local dev (gitignored)
   - `.env.example` with all required variables:
     - `AzureWebJobsStorage` — Storage Account connection string
     - `FUNCTIONS_WORKER_RUNTIME` — must be `python`
     - `GRAPH_CLIENT_ID` — App Registration client ID (Key Vault ref in Azure)
     - `GRAPH_CLIENT_SECRET` — App Registration secret (Key Vault ref in Azure)
     - `GRAPH_TENANT_ID` — Azure AD tenant ID (Key Vault ref in Azure)
     - `KEY_VAULT_URI` — Key Vault URI (output from terraform apply)
   - Function App settings wired to Key Vault references for: `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_TENANT_ID`

5. **Project scaffolding**
   - `.gitignore` (Python, Azure Functions, IDE, .env)
   - `Makefile` with targets: `lint`, `typecheck`, `test`, `deploy`
   - Minimal `src/semantic_folder/__init__.py` package
   - Smoke test validating package import and blueprint registration

6. **Deployment validation**
   - Local: `func start` runs both triggers successfully
   - Azure: `func azure functionapp publish` deploys and function executes

### Out of Scope

- Microsoft Graph API integration (iteration 2)
- AI provider layer and description generation (iteration 2+)
- Webhook subscription setup (future iteration)
- CI/CD pipeline in GitHub Actions (future iteration — manual deploy is sufficient for now)
- Monitoring, alerts, Application Insights dashboards (future iteration)
- Loguru integration (future iteration — stdlib `logging` sufficient for bootstrap)

## Architectural Deviations

| Reference requirement | Deviation | Justification |
|-----------------------|-----------|---------------|
| REQ-A-093: mypy ≥1.8 for type checking | Using pyright instead | Better VS Code integration and faster incremental checks for Azure Functions development |
| REQ-A-062: pip-installable CLI package | Azure Function deployment | This project deploys as an Azure Function, not a CLI tool. The Azure Functions deployment model supersedes pip packaging. |
| REQ-A-093: no Azure-specific dependencies in reference stack | `azure-functions` added as production dependency | Required by the Azure Functions runtime — not part of the reference stack which targets CLI applications |
| REQ-A-037: Loguru for structured logging | Using Python stdlib `logging` | Azure Functions natively integrates with stdlib `logging` — output appears in Azure portal log stream and Application Insights without configuration. Loguru requires custom sink wiring. Deferred to a future iteration if structured JSON logging is needed. |

## Deliverables

### D1: Project structure

```text
semantic-folder/
├── .python-version                    # 3.12.x
├── pyproject.toml                     # Poetry project config
├── poetry.lock                        # Locked dependencies
├── .gitignore                         # Python + Azure Functions + IDE
├── .env.example                       # Documented env vars (see Scope item 4)
├── .funcignore                        # Excludes tests/, infra/, .git/, iterations/, __pycache__/
├── host.json                          # Functions host config (see D2 content below)
├── local.settings.json                # Local dev settings (gitignored)
├── Makefile                           # lint, typecheck, test, deploy targets
├── function_app.py                    # V2 entry point — registers blueprints, adds src/ to sys.path
│
├── src/
│   └── semantic_folder/
│       ├── __init__.py
│       └── functions/
│           ├── __init__.py
│           ├── timer_trigger.py       # Blueprint: scheduled trigger (PoC entry point)
│           └── http_trigger.py        # Blueprint: health check / webhook endpoint
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Adds src/ to sys.path for test discovery
│   └── unit/
│       ├── __init__.py
│       └── test_smoke.py             # Validates package import + blueprint registration
│
├── infra/
│   ├── main.tf                        # Root module
│   ├── variables.tf                   # Input variables
│   ├── outputs.tf                     # Outputs (URLs, connection strings)
│   ├── providers.tf                   # Azure provider config
│   ├── resource_group.tf              # Resource group
│   ├── storage.tf                     # Storage account
│   ├── function_app.tf                # Function App + App Service Plan
│   ├── keyvault.tf                    # Key Vault + access policies
│   ├── app_registration.tf            # Entra ID app + API permissions
│   └── terraform.tfvars.example       # Example variable values
│
└── iterations/
    └── it-1.in.md                     # This file
```

### D2: Azure Functions — Timer trigger (blueprint)

- Registered as a blueprint in `function_app.py`
- CRON schedule: `0 */5 * * * *` (every 5 minutes, Azure 6-field format)
- Logs execution start/end using Python stdlib `logging`
- Top-level exception handling — errors logged, not swallowed silently
- Placeholder for Graph delta processing (implemented in iteration 2)

`host.json` required content:

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": { "isEnabled": true }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

### D3: Azure Functions — HTTP trigger (blueprint)

- Registered as a blueprint in `function_app.py`
- GET `/api/health` returns `{"status": "ok", "version": "0.1.0"}`
- Top-level exception handling with structured error response
- Logging via Python stdlib `logging`
- Will serve as webhook endpoint in future iteration

### D4: Terraform infrastructure

- All resources created with `terraform apply`
- Function App running and reachable
- Key Vault provisioned with access policy for Function App managed identity
- App Registration created with required Graph API permissions (admin consent needed manually)
- State stored locally (`.tfstate` gitignored)

### D5: Local development workflow

- `make lint` — runs `ruff check` + `ruff format --check`
- `make typecheck` — runs `pyright`
- `make test` — runs `pytest --cov=src --cov-report=term-missing --cov-fail-under=80`
- `make deploy` — runs `func azure functionapp publish $(FUNCTION_APP_NAME)` (app name from env var)
- `func start` — runs functions locally

## Acceptance Criteria

1. `poetry install` succeeds and creates a working virtual environment with Python 3.12
2. `make lint` passes with zero warnings
3. `make typecheck` passes with zero errors
4. `make test` passes — smoke test validates: (a) `semantic_folder` package is importable, (b) timer blueprint is a valid `azure.functions.Blueprint`, (c) HTTP blueprint is a valid `azure.functions.Blueprint`; coverage ≥80%
5. `func start` launches locally — timer trigger fires, HTTP trigger responds at `/api/health`
6. `terraform plan` shows a clean plan with all resources
7. `terraform apply` provisions all Azure resources successfully
8. `func azure functionapp publish` deploys the function to Azure
9. Timer trigger executes in Azure (visible in Function App logs)
10. HTTP health endpoint responds from Azure URL

## Pre-Development Review

### Skills reviewed

| Skill | Relevance |
|-------|-----------|
| architectural-requirements/technology-stack | Tech stack alignment |
| architectural-requirements/directory-structure | Directory conventions |
| architectural-requirements/build-cicd-architecture | Build/CI approach |
| architectural-requirements/deployment-architecture | Deployment approach |
| architectural-requirements/configuration | Configuration approach |
| architectural-requirements/error-handling | Error handling in triggers |
| architectural-requirements/testing | Test approach |

### Findings resolved (v1.0 → v1.1)

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | FAIL | Missing `function_app.py` entry point | Added to D1 tree; described as V2 entry point with blueprint registration |
| 2 | FAIL | `src/` layout import resolution | `function_app.py` adds `src/` to `sys.path`; `conftest.py` does the same for tests |
| 3 | WARN | pyright vs mypy not documented | Added to Architectural Deviations table |
| 4 | WARN | Missing prerequisites section | Added Prerequisites section with all required tools |
| 5 | WARN | No error handling in triggers | Added top-level exception handling requirement to D2 and D3 |
| 6 | WARN | Smoke test too vague | AC4 now specifies: validates package import + blueprint registration |

### Specification Review Status: APPROVED

## Independent Validation

### Readiness checklist

- [x] Scope clear and bounded
- [x] Deliverables actionable (can start coding)
- [x] Acceptance criteria testable
- [x] Reference docs identified
- [x] Dependencies satisfied

### Findings resolved (v1.1 → v1.2)

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | WARN | `.env.example` variables not enumerated | Added explicit variable list to Scope item 4 |
| 2 | WARN | No coverage threshold | Added `--cov-fail-under=80` to D5 and AC4 |
| 3 | WARN | `host.json` content not specified | Added required JSON content to D2 |
| 4 | WARN | Logging library not resolved | stdlib `logging` chosen; added to Architectural Deviations (REQ-A-037) |
| 5 | WARN | Terraform state backend ambiguous | Local `.tfstate` for this iteration; documented in Scope item 3 and D4 |

### Independent Validation Status: READY_FOR_DEV

## Reference Documents

- [semantic-folder-grounding.md](../semantic-folder-grounding.md) — Full product specification
- architectural-requirements skill — Technology stack, directory structure, build/CI-CD
- Azure Functions Python V2 programming model documentation
