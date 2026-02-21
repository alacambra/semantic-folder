# Semantic Folder Grounding

**AI-Powered Knowledge Context for Microsoft Copilot**
Datamantics UG — Internal Administration Use Case

_Version 1.0 | February 2026 | Albert Lacambra Basil | CONFIDENTIAL_

---

## 1. Executive Summary

Datamantics UG is a lean German IT consultancy operated by Albert Lacambra Basil. Day-to-day administration spans customer relationships, service contracts, insurance policies, and running costs — all managed through OneDrive. A virtual assistant (VA) supports operations, requiring the ability to act independently on client and administrative matters without relying on the principal for context.

This document describes **Semantic Folder Grounding**: an automated background service that continuously generates and maintains AI-readable context files across the Datamantics OneDrive. These files serve two purposes simultaneously — enabling Microsoft Copilot chat to answer natural language questions accurately, and providing structured knowledge to Copilot Studio agents that perform specific administrative tasks autonomously.

The AI phase reads folder paths and file listings and infers all relevant context without any hardcoded schemas, manual tagging, or predefined structure. The business context — Datamantics UG, German IT consultancy — is provided once and applies globally.

**Key Outcomes**

- Albert and the VA get accurate Copilot answers about clients, contracts, insurance, and costs
- VA can orient in any client situation and act independently without asking Albert
- Copilot Studio agents read the same context files to perform billing, proposals, status reports
- Descriptions update automatically as files are added, modified, or deleted
- AI provider is swappable — Anthropic Claude, Azure OpenAI, or local models via one config line
- No Power Automate, no manual tagging, no hardcoded schemas

---

## 2. Problem Statement

### 2.1 The Datamantics Administration Context

Datamantics OneDrive contains documents across four core administrative domains: customers (contracts, proposals, SOWs, invoices), insurance (liability, professional indemnity, health policies), active services (running engagements, deliverables, status), and costs (subscriptions, recurring expenses, bank statements, tax documents).

Copilot indexes these files but has no understanding of the organisational context behind them. It cannot determine:

- Which client engagement is currently active versus closed
- Which contract version is the authoritative reference for billing
- What an insurance folder covers and when policies expire
- Which costs are fixed recurring versus one-off
- What the VA needs to know to act on a client folder without asking Albert

### 2.2 The Two-User Problem

Albert holds full context on every client and administrative matter. The VA does not. Without a structured, always-current description of each folder, the VA must either ask Albert repeatedly — creating overhead — or risk acting on incomplete information.

The same problem applies to Copilot Studio agents: an agent tasked with generating an invoice or drafting a proposal has no way to determine the correct engagement type, rate, or authoritative document without explicit context. The result is generic, unreliable outputs for the very administrative tasks they should be accelerating.

### 2.3 Why Existing Approaches Fall Short

| Approach                         | Limitation for Datamantics                                                                                             |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Manual Copilot prompting         | Albert must remember folder paths and file names for every query; not scalable as client base grows                    |
| SharePoint metadata tagging      | Manual effort per file; becomes stale immediately when new contracts or invoices arrive                                |
| Power Automate flows             | Too fragile to build reliably for developers; produces no useful outcome for the VA or agents                          |
| Copilot Studio without grounding | Agents lack folder context; billing agent cannot find the correct SOW; status agent cannot identify active engagements |
| Doing nothing                    | VA cannot act independently; Copilot answers administrative questions unreliably; agent automation is blocked          |

---

## 3. Proposed Solution

### 3.1 Core Concept

The solution generates and maintains a `folder_description.md` file in every Datamantics OneDrive folder. This file is written by an AI that reads the folder path and file listing and infers the relevant administrative context from that information alone — no predefined schema, no manual input.

A customer folder produces a description oriented around engagement status, contracts, and invoicing. An insurance folder surfaces coverage, expiry, and policy type. A costs folder surfaces fixed versus variable expenses. The AI determines what matters for each folder based on what it finds there.

### 3.2 The Three-Layer Knowledge Model

| Layer                              | Role                                                                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Folder descriptions            | Auto-generated context files in every folder. Single source of truth for humans and agents alike. Updated automatically on every file change.                                                            |
| 2 — Copilot chat grounding         | Copilot indexes description files alongside documents. Albert and the VA ask natural language questions and receive contextually accurate answers.                                                       |
| 3 — Copilot Studio agent grounding | Agents are configured to read the relevant folder description before acting. Billing agent reads the customer description. Insurance agent reads the insurance description. No hardcoded schemas needed. |

The critical design point: **layers 2 and 3 consume the same files**. Building the description layer once unlocks both Copilot chat and agent automation simultaneously.

### 3.3 Example: Customer Folder Description

```markdown
# Customer: Nexplore GmbH

**Inferred type:** Active customer — IT consultancy engagement

**Key documents:**

- SOW_2026_01.pdf — current active contract (AUTHORITATIVE)
- invoice_2026_01.pdf — most recent invoice
- proposal_2025_11.pdf — superseded, kept for reference

**Context for VA:**
This is an active client. The current engagement scope and rate are
defined in SOW_2026_01.pdf. Earlier proposal documents are
for reference only and should not be cited as current agreements.

**Context for agents:**
Billing tasks: use SOW_2026_01.pdf as the authoritative reference.
Client communications: verify engagement status from this file first.
Do not reference superseded proposal documents.

**Last updated:** 2026-02-21 (automated)
```

### 3.4 Example: Insurance Folder Description

```markdown
# Insurance: Professional Indemnity

**Inferred type:** Active insurance policy folder

**Key documents:**

- PI_policy_2026.pdf — current policy (ACTIVE)
- PI_policy_2025.pdf — expired, prior year
- certificate_2026.pdf — coverage certificate

**Context for VA:**
Current professional indemnity coverage is defined in PI_policy_2026.pdf.
The 2025 policy is expired. Certificate of coverage is available separately.

**Context for agents:**
When checking insurance coverage, read PI_policy_2026.pdf only.
Flag PI_policy_2025.pdf as expired — do not cite for current coverage.

**Last updated:** 2026-02-21 (automated)
```

### 3.5 File Lifecycle Handling

Every file change triggers a full regeneration of the affected folder description. No partial updates, no stale data:

| Event                                         | Result                                                          |
| --------------------------------------------- | --------------------------------------------------------------- |
| New contract uploaded to customer folder      | Description updated — new SOW appears as authoritative document |
| Invoice added                                 | Description updated — latest invoice reflected                  |
| Old policy replaced by new insurance document | Description updated — old policy flagged as expired             |
| File deleted                                  | Description updated — file removed from context                 |
| Folder renamed                                | Description regenerated at new path with updated inferred type  |

---

## 4. Technical Architecture

### 4.1 Trigger Layer — Detecting File Changes

| Mode                       | How it works                                                                                                                                                                |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Event-driven (production)  | A Microsoft Graph API webhook subscription fires an HTTP notification the moment any file changes in OneDrive. Real-time, no polling, no missed events.                     |
| Scheduled (PoC / fallback) | A Python script runs on a schedule. It calls the Graph delta API with a stored delta token to retrieve all changes since the last run. Simple, requires no public endpoint. |

Both modes use the **Graph delta API with a delta token** — an opaque bookmark that represents the state of the drive at a specific point in time. The service stores this token after each run and advances it forward, ensuring no changes are ever missed across restarts or downtime.

### 4.2 Orchestration Layer — Processing Changes

A lightweight Python service (Azure Function, Azure Container App, or standalone script) that:

- Receives the webhook notification or runs on schedule
- Calls the Graph delta API with the stored token to get changed items
- Resolves which folder each changed item belongs to
- Filters out `folder_description.md` changes to prevent infinite loops
- Calls the AI layer with the folder path and file listing
- Writes the generated description back to OneDrive via Graph API
- Stores the new delta token for the next run

### 4.3 AI Layer — Generating Descriptions

The AI receives the folder path, file names, and file types, plus a fixed system prompt identifying the business context as Datamantics UG, a German IT consultancy. It infers all relevant structure from that information alone — folder type, key documents, authoritative files, context for the VA, context for agents.

The AI provider is fully abstracted, switchable via configuration:

```yaml
# config.yaml — change one line to switch AI provider
ai_provider: anthropic

providers:
  anthropic:
    model: claude-3-5-haiku-20241022
    api_key_env: ANTHROPIC_API_KEY

  azure_openai:
    endpoint: https://yourinstance.openai.azure.com
    deployment: gpt-4o-mini
    api_key_env: AZURE_OPENAI_KEY

  ollama:
    endpoint: http://localhost:11434
    model: llama3.2
```

### 4.4 Full Architecture Flow

```
1.  File created / modified / deleted in Datamantics OneDrive
          |
          v
2.  Microsoft Graph fires webhook → POST to orchestration endpoint
    (or: scheduled script wakes up)
          |
          v
3.  Orchestration calls delta API with stored token
          → receives list of changed driveItems
          → stores new delta token
          |
          v
4.  For each affected folder:
     a.  List all files in folder via Graph API
     b.  Skip if only folder_description.md changed (loop prevention)
     c.  Call AI provider: folder path + file listing + business context
     d.  Receive generated Markdown description
     e.  Write / update folder_description.md via Graph API
          |
          v
5.  Copilot indexes updated folder_description.md automatically
          |
     ┌────┴────┐
     v         v
  Copilot    Copilot Studio
  chat       agents read
  answers    description
  improve    before acting
```

---

## 5. End User Experience

Neither Albert nor the VA interacts with the technical layer in any way. Files are saved to OneDrive as normal. Copilot and agents are used as normal. The improvement is entirely transparent.

### 5.1 Albert — Principal Consultant

Copilot queries that now work accurately:

- _"What is the current status of Nexplore?"_ → Copilot reads the customer description and summarises the engagement
- _"Is there a signed contract for Client X?"_ → Copilot identifies the authoritative SOW from the description
- _"What does my professional indemnity insurance cover?"_ → Copilot reads the insurance description accurately
- _"What are my fixed monthly running costs?"_ → Copilot reads the costs folder and lists recurring items
- _"Which clients have outstanding invoices?"_ → Agent reads all customer descriptions and flags unpaid invoices

### 5.2 Virtual Assistant

The VA can orient themselves in any client or administrative situation without asking Albert:

- Open a customer folder and immediately understand engagement status, key contacts, active contract
- Know which document is the authoritative version without asking Albert
- Prepare client communications with correct context from the description
- Check insurance coverage details without hunting through policy PDFs
- Identify which cost documents relate to recurring versus one-off expenses

### 5.3 Copilot Studio Agents

Agents are configured to read the relevant `folder_description.md` as their primary context source before performing any task:

| Agent task                  | Context consumed from folder description                      |
| --------------------------- | ------------------------------------------------------------- |
| Generate client invoice     | Engagement type, rate structure, active SOW reference         |
| Draft client proposal       | Client history, previous proposals, current engagement status |
| Check insurance coverage    | Policy type, active versus expired, coverage scope            |
| Monthly cost summary        | Fixed recurring costs, active subscriptions, one-off items    |
| Client status report for VA | Full engagement summary, active documents, open items         |

### 5.4 Before and After

| Before (no grounding)                                             | After (with Semantic Folder Grounding)                                 |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| VA must ask Albert before acting on any client matter             | VA reads folder description and acts independently                     |
| Copilot gives vague answers about client status                   | Copilot identifies correct engagement, contract, and status accurately |
| Agents need hardcoded schemas to act correctly                    | Agents read inferred context — no schemas, no manual setup per client  |
| Insurance queries require opening and reading each PDF            | Copilot answers from auto-maintained insurance descriptions            |
| Adding a new client means manual setup for agents to recognise it | New client folder is described automatically within seconds            |

---

## 6. Deployment Options

| Stage                                  | Description                                                                                                                                                                                                    |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PoC — Scheduled script                 | Python script runs manually or on schedule. Uses Graph delta API with stored token. No public endpoint needed. Validates that Copilot answers improve before any infrastructure spend. Estimated setup: 1 day. |
| Pilot — Azure Function + webhook       | Azure Function receives Graph webhook notifications in real time. Descriptions update within seconds of file changes. Requires public HTTPS endpoint. Estimated setup: 2–3 days.                               |
| Production — Azure Container App       | Full orchestration service with monitoring, auto-token-renewal, and multi-folder parallelism. Estimated monthly cost: €5–15 excluding AI token costs.                                                          |
| Extended — Datamantics client offering | Package as a managed service for Datamantics SME clients. Each client gets isolated folder grounding for their own Copilot environment.                                                                        |

### 6.1 Azure Requirements

- Azure App Registration — permissions: `Files.ReadWrite.All`, `Sites.Read.All`
- Azure Function or Container App — orchestration runtime
- Azure Storage or Key Vault — delta token persistence and secret management
- Public HTTPS endpoint — required only for webhook mode, not for scheduled script
- Anthropic API key or Azure OpenAI deployment — AI description generation

---

## 7. Design Principles

- **Zero friction for Albert and the VA** — the solution is entirely invisible to both users
- **No Power Automate** — excluded for being too fragile for developers and too opaque for users
- **AI infers structure** — no hardcoded schemas; the AI determines what matters per folder from what it finds
- **Single source of truth** — the same description files serve Copilot chat and Copilot Studio agents
- **Swappable AI provider** — one config line switches between Anthropic Claude, Azure OpenAI, or local models
- **Simplicity over optimisation** — full regeneration on every change; no partial update complexity
- **Resilience by design** — delta token ensures no missed changes across restarts or downtime
- **GDPR-aware** — no file content is stored; only file names and metadata are processed; all data stays within the Microsoft 365 tenant

---

## 8. Recommended Next Steps

| Step                           | Detail                                                                                                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Azure App Registration     | Register app in Azure portal. Grant `Files.ReadWrite.All` and `Sites.Read.All` permissions. Admin consent required.                                                                         |
| 2 — Run PoC script             | Python script authenticates via MSAL, calls Graph delta API, lists all folders, generates descriptions via Anthropic Claude or Azure OpenAI, writes `folder_description.md` to each folder. |
| 3 — Test Copilot chat          | Ask Copilot: client status queries, insurance questions, cost summaries. Compare answers before and after descriptions are in place.                                                        |
| 4 — VA onboarding test         | VA opens several client folders. Validates that descriptions provide sufficient context to act without asking Albert.                                                                       |
| 5 — First agent                | Configure a Copilot Studio agent to read `folder_description.md` before performing a billing or status task. Validate output quality.                                                       |
| 6 — Webhook deployment         | Deploy Azure Function with Graph webhook subscription for real-time updates. Delta token stored in Azure Storage.                                                                           |
| 7 — Client offering evaluation | Assess packaging as a Datamantics managed service for SME clients based on PoC results.                                                                                                     |

---

_Datamantics UG — AI-Driven Knowledge Management for Lean IT Operations_
_Version 1.0 | February 2026 | CONFIDENTIAL_
