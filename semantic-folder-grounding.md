# Semantic Folder Grounding

**AI-Powered Knowledge Context for Microsoft Copilot**
Datamantics UG — Internal Administration Use Case

_Version 3.0 | March 2026 | Albert Lacambra Basil | CONFIDENTIAL_

---

## 1. Executive Summary

Datamantics UG is a lean German IT consultancy operated by Albert Lacambra Basil. Day-to-day administration spans customer relationships, service contracts, insurance policies, and running costs — all managed through OneDrive. A virtual assistant (VA) supports operations, requiring the ability to act independently on client and administrative matters without relying on the principal for context.

This document describes **Semantic Folder Grounding**: an automated background service that continuously generates and maintains AI-readable context files across the Datamantics OneDrive. These files serve two purposes simultaneously — enabling Microsoft Copilot chat to answer natural language questions accurately, and providing structured knowledge to Copilot Studio agents that perform specific administrative tasks autonomously.

The AI phase reads each file's actual content and extracts structured metadata (document type, dates, parties, amounts, tags) into a JSON file per folder — no manual tagging, no predefined structure. The business context — Datamantics UG, German IT consultancy — is provided once and applies globally.

**Key Outcomes**

- Albert and the VA get accurate Copilot answers about clients, contracts, insurance, and costs
- VA can orient in any client situation and act independently without asking Albert
- Copilot Studio agents read the same context files to perform billing, proposals, status reports
- Descriptions update automatically as files are added, modified, or deleted
- AI provider is Anthropic Claude (Haiku 4.5), configurable via environment variable
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

The solution generates and maintains a `folder_description.json` file in every Datamantics OneDrive folder. This file is written by an AI that reads each file's actual content (text, PDF, images, docx) and extracts structured metadata — document type, language, dates, parties, a factual summary, searchable tags, and domain-specific facts (amounts, reference numbers, deadlines, etc.).

Each document gets a structured JSON record with a universal envelope (file, doc_type, doc_lang, date, parties, summary, tags) plus a free-form `facts` block for domain-specific data. The AI determines what facts matter for each document based on its content — an invoice gets amounts and due dates, a contract gets terms and notice periods, an insurance policy gets coverage and expiry.

A root-level `onedrive_index.json` file acts as a table of contents, aggregating all folder descriptions into a single searchable index for Copilot.

### 3.2 The Three-Layer Knowledge Model

| Layer                              | Role                                                                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Folder descriptions            | Auto-generated context files in every folder. Single source of truth for humans and agents alike. Updated automatically on every file change.                                                            |
| 2 — Copilot chat grounding         | Copilot indexes description files alongside documents. Albert and the VA ask natural language questions and receive contextually accurate answers.                                                       |
| 3 — Copilot Studio agent grounding | Agents are configured to read the relevant folder description before acting. Billing agent reads the customer description. Insurance agent reads the insurance description. No hardcoded schemas needed. |

The critical design point: **layers 2 and 3 consume the same files**. Building the description layer once unlocks both Copilot chat and agent automation simultaneously.

### 3.3 Example: Customer Folder Description

```json
{
  "folder": {
    "path": "/drive/root:/Kunden/Nexplore",
    "type": "client-engagement",
    "updated_at": "2026-03-10"
  },
  "period": "2026-01",
  "overview": {
    "document_count": 2,
    "by_expense_category": {},
    "by_country": {},
    "total_amount_eur": 15300.00
  },
  "documents": [
    {
      "file": "SOW_2026_01.pdf",
      "doc_type": "contract",
      "doc_lang": "de",
      "date": "2026-01-15",
      "parties": { "from": "Datamantics UG", "to": "Nexplore GmbH" },
      "summary": "Statement of Work for IT consultancy engagement starting January 2026. Defines scope, deliverables, and billing rate for the current phase.",
      "tags": ["sow", "contract", "nexplore", "consultancy", "engagement"],
      "facts": {
        "contract_start": "2026-01-15",
        "contract_end": "2026-06-30",
        "notice_period": "30 days",
        "amount": 850.00,
        "currency": "EUR"
      }
    },
    {
      "file": "invoice_2026_01.pdf",
      "doc_type": "invoice-outgoing",
      "doc_lang": "de",
      "date": "2026-01-31",
      "parties": { "from": "Datamantics UG", "to": "Nexplore GmbH" },
      "summary": "Monthly invoice for January 2026 consultancy services. Covers 18 days at the agreed daily rate.",
      "tags": ["invoice", "nexplore", "billing", "january-2026"],
      "facts": {
        "invoice_number": "RE-2026-001",
        "amount": 15300.00,
        "currency": "EUR",
        "vat_rate": 19,
        "vat_amount": 2907.00
      }
    }
  ]
}
```

### 3.4 Example: Insurance Folder Description

```json
{
  "folder": {
    "path": "/drive/root:/Versicherungen/Berufshaftpflicht",
    "type": "insurance-policies",
    "updated_at": "2026-03-10"
  },
  "period": null,
  "overview": {
    "document_count": 2,
    "by_expense_category": {},
    "by_country": {},
    "total_amount_eur": 1000890.00
  },
  "documents": [
    {
      "file": "PI_policy_2026.pdf",
      "doc_type": "insurance-policy",
      "doc_lang": "de",
      "date": "2026-01-01",
      "parties": { "from": "Allianz Versicherung", "to": "Datamantics UG" },
      "summary": "Professional indemnity insurance policy for 2026. Covers claims arising from IT consultancy services with a limit of EUR 1,000,000 per incident.",
      "tags": ["insurance", "professional-indemnity", "allianz", "policy", "2026"],
      "facts": {
        "policy_number": "BH-2026-4471",
        "valid_until": "2026-12-31",
        "amount": 1000000.00,
        "currency": "EUR",
        "premium": 890.00
      }
    },
    {
      "file": "PI_policy_2025.pdf",
      "doc_type": "insurance-policy",
      "doc_lang": "de",
      "date": "2025-01-01",
      "parties": { "from": "Allianz Versicherung", "to": "Datamantics UG" },
      "summary": "Expired professional indemnity insurance policy for 2025. Superseded by PI_policy_2026.pdf.",
      "tags": ["insurance", "professional-indemnity", "allianz", "policy", "2025", "expired"],
      "facts": {
        "policy_number": "BH-2025-4471",
        "valid_until": "2025-12-31"
      }
    }
  ]
}
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
- Filters out `folder_description.json` changes to prevent infinite loops
- Calls the AI layer with the folder path and file listing
- Writes the generated description back to OneDrive via Graph API
- Stores the new delta token for the next run

### 4.3 AI Layer — Generating Descriptions

The AI receives each file's actual content — text, PDF documents, images, Word files — plus a structured extraction prompt that defines the output schema and business context (Datamantics UG, German IT consultancy). It extracts structured JSON metadata per file: document type (from a controlled vocabulary of 24 types), language, date, parties, factual summary, searchable tags, and domain-specific facts. JSON was chosen over YAML because Microsoft 365 Copilot only indexes `.json` files natively.

The folder is also classified by the AI into a short category label (e.g. "client-engagement", "insurance-policies") based on its path and file names.

The AI provider is Anthropic Claude (currently Claude Haiku 4.5), configurable via environment variable `SF_ANTHROPIC_MODEL`.

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
     b.  Skip if only folder_description.json changed (loop prevention)
     c.  Download each file's content via Graph API
     d.  For each file: extract structured JSON metadata via AI (with caching)
     e.  Classify folder type via AI
     f.  Serialize to JSON, upload folder_description.json via Graph API
     g.  Update root onedrive_index.json with all folder descriptions
          |
          v
5.  Copilot indexes updated folder_description.json automatically
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

Agents are configured to read the relevant `folder_description.json` as their primary context source before performing any task. The structured JSON format with typed fields (amounts, dates, reference numbers) makes agent parsing reliable:

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
- **AI extracts structured metadata** — two-layer schema (universal envelope + free-form facts) per document, with a controlled vocabulary of 24 document types
- **Single source of truth** — the same JSON description files serve Copilot chat and Copilot Studio agents
- **Content-aware extraction** — AI reads actual file content (text, PDF, images, docx) not just filenames
- **Simplicity over optimisation** — full regeneration on every change; no partial update complexity
- **Resilience by design** — delta token ensures no missed changes across restarts or downtime
- **GDPR-aware** — file content is sent to the AI for extraction but not persisted outside the cache; extracted metadata stays in OneDrive within the Microsoft 365 tenant

---

## 8. Recommended Next Steps

| Step                           | Detail                                                                                                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Azure App Registration     | Register app in Azure portal. Grant `Files.ReadWrite.All` and `Sites.Read.All` permissions. Admin consent required.                                                                         |
| 2 — Run PoC script             | Python script authenticates via MSAL, calls Graph delta API, lists all folders, generates descriptions via Anthropic Claude or Azure OpenAI, writes `folder_description.json` to each folder. |
| 3 — Test Copilot chat          | Ask Copilot: client status queries, insurance questions, cost summaries. Compare answers before and after descriptions are in place.                                                        |
| 4 — VA onboarding test         | VA opens several client folders. Validates that descriptions provide sufficient context to act without asking Albert.                                                                       |
| 5 — First agent                | Configure a Copilot Studio agent to read `folder_description.json` before performing a billing or status task. Validate output quality.                                                       |
| 6 — Webhook deployment         | Deploy Azure Function with Graph webhook subscription for real-time updates. Delta token stored in Azure Storage.                                                                           |
| 7 — Client offering evaluation | Assess packaging as a Datamantics managed service for SME clients based on PoC results.                                                                                                     |

---

_Datamantics UG — AI-Driven Knowledge Management for Lean IT Operations_
_Version 3.0 | March 2026 | CONFIDENTIAL_
