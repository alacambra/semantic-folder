---
document_id: IT-2-IN
version: 1.0.0
last_updated: 2026-02-22
status: Draft
purpose: Add .devcontainer setup for sandboxed Claude agent development environment
audience: [Developers, reviewers]
dependencies: [IT-1-IN]
review_triggers: [Scope changes, allowed domain list changes, base image changes]
---

# Iteration 2: Devcontainer — Sandboxed Claude Agent Environment

## Objective

Add a `.devcontainer` setup (three files) that provides a secure, sandboxed development environment for Claude agents — adapted from the Anthropic claude-code reference implementation to fit this Python/Azure project.

## Motivation

**Business driver:** Claude agents running in this project must not have arbitrary outbound network access. A whitelist-only firewall ensures the agent can only reach approved endpoints, preventing data exfiltration and unintended external calls.

**How this iteration fulfills it:** Delivers `.devcontainer/Dockerfile`, `.devcontainer/devcontainer.json`, and `.devcontainer/init-firewall.sh` — adapted from the Anthropic claude-code reference implementation at `https://github.com/anthropics/claude-code/tree/main/.devcontainer` — so VS Code opens the project in a container with iptables-enforced egress filtering. The agent can only reach a defined allowlist of domains required for normal development operations.

## Prerequisites

### One-time setup (developer workstation)

#### Step 1 — Install Docker Desktop

- Download from <https://www.docker.com/products/docker-desktop>
- Start Docker Desktop and ensure it is running (whale icon in menu bar)

#### Step 2 — Install VS Code Dev Containers extension

- Open VS Code → `Cmd+Shift+X` → search "Dev Containers"
- Install "Dev Containers" by Microsoft (`ms-vscode-remote.remote-containers`)

#### Step 3 — Open the project in the devcontainer

- Open this project in VS Code
- VS Code will detect `.devcontainer/` and show a popup: "Reopen in Container" → click it
- Alternatively: `Cmd+Shift+P` → "Dev Containers: Reopen in Container"
- Alternatively: click the green `><` icon in the bottom-left corner of VS Code → "Reopen in Container"
- First build takes 5–10 minutes (downloads Python, Azure CLI, Terraform, etc.)
- Subsequent opens are instant (image is cached)

#### Step 4 — Verify the environment (inside the container terminal)

```bash
whoami            # should return: vscode
python --version  # should return: Python 3.12.x
poetry --version  # should return: Poetry 2.x
az --version      # Azure CLI present
func --version    # Azure Functions Core Tools v4.x
terraform --version  # Terraform v1.5+
claude --version  # Claude Code CLI present
```

#### Step 5 — Verify the firewall

```bash
curl https://api.anthropic.com   # succeeds (or returns 4xx — not blocked)
curl https://example.com         # fails — connection refused/timed out (firewall working)
```

### Per-session workflow

Always open the project via VS Code and work inside the container. Claude Code, terminals, and `make` commands all execute inside the sandboxed environment automatically. No further action is required — the firewall is enforced at the kernel level for the duration of the session.

## Scope

### In Scope

1. **`.devcontainer/Dockerfile`** — Python 3.12 base image with full development toolchain:
   - Base image: `python:3.12-slim` (not node:20 — this is a Python project)
   - System packages: `git`, `zsh`, `vim`, `nano`, `curl`, `wget`, `iptables`, `ipset`, `dnsutils`, `sudo`, `ca-certificates`
   - Node.js (via NodeSource or nvm) — required only to install Claude Code CLI via npm
   - Claude Code CLI: installed via `npm install -g @anthropic-ai/claude-code`
   - pyenv or deadsnakes PPA for Python version management
   - Poetry ≥2.0 via official installer
   - Azure CLI via Microsoft's official install script
   - Azure Functions Core Tools v4 via npm or apt
   - Terraform ≥1.5 via HashiCorp apt repository
   - Non-root user `vscode` (uid 1000) with passwordless sudo
   - Working directory: `/workspaces/semantic-folder`

2. **`.devcontainer/devcontainer.json`** — VS Code devcontainer configuration:
   - `build.dockerfile`: `"Dockerfile"`
   - `runArgs`: `["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"]` — required for iptables manipulation
   - `postStartCommand`: runs `sudo /workspaces/semantic-folder/.devcontainer/init-firewall.sh`
   - `remoteUser`: `"vscode"`
   - VS Code extensions:
     - `"anthropic.claude-code"` — Claude Code extension
     - `"ms-python.python"` — Python language support
   - Volume mounts:
     - bash/zsh history persistence: named volume → `/home/vscode/.zsh_history`
     - Claude config persistence: named volume → `/home/vscode/.claude`
   - `mounts` field using `"source=semantic-folder-claude,target=/home/vscode/.claude,type=volume"` and `"source=semantic-folder-zshhistory,target=/home/vscode/.zsh_history,type=volume"`

3. **`.devcontainer/init-firewall.sh`** — Whitelist-only iptables firewall script:
   - Fetches GitHub IP ranges from `https://api.github.com/meta` (allowed before firewall applied)
   - Creates ipset named `"allowed-domains"` (hash:net type)
   - Resolves each allowed domain to IP(s) via DNS and adds to ipset
   - Sets iptables DROP policy on OUTPUT chain
   - Whitelists: loopback, established/related connections, DNS (port 53 UDP/TCP), allowed ipset
   - Allowed domains:
     - `api.anthropic.com` — Claude API
     - `pypi.org` — Python package index
     - `files.pythonhosted.org` — Python package files
     - `graph.microsoft.com` — Microsoft Graph API
     - `login.microsoftonline.com` — Azure AD authentication
     - `*.blob.core.windows.net` — Azure Blob Storage (wildcards handled via DNS resolution of known endpoints)
     - `*.azurewebsites.net` — Azure Functions endpoints
     - `*.scm.azurewebsites.net` — Azure Functions Kudu/SCM
     - `registry.terraform.io` — Terraform registry
     - `releases.hashicorp.com` — HashiCorp releases
     - GitHub IP ranges (from `api.github.com/meta` — as in reference implementation)
   - Script is idempotent: checks if ipset already exists before creating
   - Made executable (`chmod +x`) and runs with `#!/usr/bin/env bash` + `set -euo pipefail`

### Out of Scope

- No application code changes (`src/`, `function_app.py`, etc.)
- No `pyproject.toml` changes
- No CI/CD containerization or production Docker image
- No changes to Terraform infrastructure
- No modifications to existing iteration files or Makefile

## Deliverables

### D1: `.devcontainer/Dockerfile`

File at `.devcontainer/Dockerfile` with:
- `FROM python:3.12-slim`
- `ARG` for user uid/gid (default 1000)
- System package installation in single `RUN` layer for cache efficiency
- Node.js installation (LTS via NodeSource script or direct apt)
- Claude Code CLI installation: `npm install -g @anthropic-ai/claude-code`
- Poetry installation via `curl https://install.python-poetry.org | python3 -`
- Azure CLI installation via Microsoft apt repository
- Azure Functions Core Tools v4 installation
- Terraform installation via HashiCorp apt repository
- Non-root user `vscode` creation with home directory and passwordless sudo in sudoers
- `USER vscode` as final user
- `WORKDIR /workspaces/semantic-folder`

### D2: `.devcontainer/devcontainer.json`

```json
{
  "name": "semantic-folder",
  "build": {
    "dockerfile": "Dockerfile"
  },
  "runArgs": [
    "--cap-add=NET_ADMIN",
    "--cap-add=NET_RAW"
  ],
  "postStartCommand": "sudo /workspaces/semantic-folder/.devcontainer/init-firewall.sh",
  "remoteUser": "vscode",
  "customizations": {
    "vscode": {
      "extensions": [
        "anthropic.claude-code",
        "ms-python.python"
      ]
    }
  },
  "mounts": [
    "source=semantic-folder-zshhistory,target=/home/vscode/.zsh_history,type=volume",
    "source=semantic-folder-claude,target=/home/vscode/.claude,type=volume"
  ]
}
```

### D3: `.devcontainer/init-firewall.sh`

Shell script at `.devcontainer/init-firewall.sh` with:
- `#!/usr/bin/env bash` + `set -euo pipefail`
- Idempotency guard: destroy and recreate ipset if already exists
- GitHub IP range fetching from `https://api.github.com/meta` using `curl` + `jq`
- DNS resolution of each domain in the allowlist using `dig +short` or `nslookup`
- `ipset create allowed-domains hash:net` for IP storage
- `iptables` rules:
  - `-P OUTPUT DROP` — default deny outbound
  - `-A OUTPUT -o lo -j ACCEPT` — loopback
  - `-A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT` — established connections
  - `-A OUTPUT -p udp --dport 53 -j ACCEPT` — DNS UDP
  - `-A OUTPUT -p tcp --dport 53 -j ACCEPT` — DNS TCP
  - `-A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT` — allowlist
- Allowed domain list matching Scope item 3 above
- Script ends with `echo "Firewall configured successfully"` for log confirmation

## Acceptance Criteria

1. VS Code opens the project in the devcontainer without errors (Docker build succeeds)
2. The container runs as non-root user `vscode` — `whoami` returns `vscode`
3. `claude --version` succeeds inside the container
4. `poetry --version` returns ≥2.0 inside the container
5. `az --version` succeeds inside the container (Azure CLI present)
6. `func --version` returns v4.x inside the container (Azure Functions Core Tools)
7. `terraform --version` returns ≥1.5 inside the container
8. `curl https://api.anthropic.com` succeeds (or returns 4xx — not blocked by firewall)
9. `curl https://pypi.org` succeeds (not blocked by firewall)
10. `curl https://example.com` fails (blocked — not on allowlist, demonstrates firewall works)
11. `init-firewall.sh` is idempotent: running it twice does not produce errors
12. `iptables -L OUTPUT` shows DROP default policy after `init-firewall.sh` runs

## Pre-Development Review

### Skills reviewed

| Skill | Relevance |
|-------|-----------|
| architectural-requirements/security-architecture | Firewall, network egress, secrets protection |
| architectural-requirements/deployment-architecture | Container configuration, non-root user |
| architectural-requirements/technology-stack | Python 3.12, Poetry, development toolchain |
| architectural-requirements/build-cicd-architecture | Development environment consistency |

### Findings

No code quality linters (ruff, pyright, pytest) apply to shell scripts and JSON — these are infrastructure files only. The architectural requirements for security (REQ-A-058 to REQ-A-061) are satisfied by the firewall design: no credentials appear in scripts, only approved external endpoints are reachable.

**Deviation noted:** The Dockerfile uses `python:3.12-slim` rather than a node base, which deviates from the Anthropic reference (`node:20`). This is intentional — this project is Python-first. Node.js is installed additively to support Claude Code CLI via npm.

### Specification Review Status: APPROVED

## Independent Validation

### Readiness checklist

- [x] Scope clear and bounded — exactly 3 files, no application code changes
- [x] Deliverables actionable — D1/D2/D3 specify file content precisely enough to code
- [x] Acceptance criteria testable — each AC is verifiable with a command inside the container
- [x] Reference docs identified — Anthropic claude-code reference, architectural-requirements skill
- [x] Dependencies satisfied — IT-1 complete (project structure exists, .devcontainer dir created)

### Five Pillars check

- [x] Interface Contracts: `devcontainer.json` defines the VS Code ↔ container contract precisely
- [x] Data Structures: ipset `hash:net`, iptables chains — standard Linux primitives, well-defined
- [x] Configuration Formats: JSON for devcontainer.json, bash for scripts — standard formats
- [x] Behavioral Requirements: firewall rules, allowed domains, idempotency all specified
- [x] Quality Criteria: AC1-AC12 are measurable inside the running container

### Independent Validation Status: READY_FOR_DEV

## Reference Documents

- Anthropic claude-code reference: `https://github.com/anthropics/claude-code/tree/main/.devcontainer`
- `architectural-requirements/security-architecture` — REQ-A-058 to REQ-A-061
- `architectural-requirements/deployment-architecture` — REQ-A-062 to REQ-A-065
- `architectural-requirements/technology-stack` — REQ-A-093 (Python 3.12, Poetry)
- `iterations/it-1.in.md` — Established project structure and toolchain
