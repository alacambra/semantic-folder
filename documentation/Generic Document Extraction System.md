# Semantic Folder Grounding — Generic Document Extraction System

## Design Principle

Every office document, regardless of type, answers the same fundamental questions:
- **What is it?** (type, purpose)
- **Who is involved?** (parties, sender, recipient)
- **When?** (dates — issued, due, period)
- **What are the key facts?** (the domain-specific content)
- **What action does it require?** (if any)

The system uses a **common envelope + typed payload** pattern:
a small set of universal fields that every document shares,
plus a flexible `facts` block that captures what matters for *that specific* document.

---

## Architecture: Two-Layer Schema

### Layer 1: Universal Envelope (same for ALL documents)

```yaml
- file: Bescheid_Finanzamt_2026-02-10.pdf
  doc_type: tax-notice           # controlled vocabulary, see below
  doc_lang: de
  date: "2026-02-10"             # primary date (issued/created)
  parties:
    from: Finanzamt Darmstadt
    to: Datamantics UG
  summary: >
    Reminder for missing Q4 2025 Umsatzsteuervoranmeldung.
    Deadline to submit: 2026-03-01. Penalty threatened if not filed.
  action_required: Submit Q4 2025 UStVA by 2026-03-01
  urgency: high                  # high / medium / low / none
  tags: [tax, ust-voranmeldung, finanzamt, deadline]
```

### Layer 2: Typed Facts (varies by doc_type)

The `facts` block captures the **domain-specific structured data** —
only the fields that matter for that document type.
The extraction prompt decides which facts to extract based on what it sees.

```yaml
  facts:
    # For a bill/receipt:
    amount: 290.00
    currency: EUR
    vat_amount: 46.22
    vat_rate: 19

    # For a contract:
    contract_start: "2026-01-01"
    contract_end: "2026-12-31"
    monthly_fee: 5000.00

    # For an Amt letter:
    reference_number: 123/456/78901
    deadline: "2026-03-01"
    penalty: 250.00

    # For a project document:
    client: Nexplore
    project: Developer Knowledge Platform
    phase: proposal
```

The key insight: **`facts` is a free-form key-value block**.
The extraction LLM decides what's important. No rigid schema per type.

---

## Document Type Vocabulary

A controlled but extensible list. The extraction prompt maps each document to one:

```yaml
doc_types:
  # Financial
  - invoice-incoming     # Bill you received (Eingangsrechnung)
  - invoice-outgoing     # Bill you sent (Ausgangsrechnung)
  - receipt              # Payment confirmation, Kassenbon
  - bank-statement       # Kontoauszug
  - payment-confirmation # Überweisungsbestätigung

  # Tax & Government
  - tax-notice           # Steuerbescheid, Finanzamt letters
  - tax-declaration      # Your own filings (UStVA, EÜR)
  - government-letter    # Any Amt/Behörde communication
  - registration         # Gewerbeanmeldung, Handelsregister

  # Legal & Contracts
  - contract             # Vertrag, SOW, Rahmenvertrag
  - amendment            # Nachtrag, Änderungsvereinbarung
  - terms-of-service     # AGB, ToS
  - nda                  # Geheimhaltungsvereinbarung

  # Insurance
  - insurance-policy     # Versicherungsschein
  - insurance-claim      # Schadensmeldung
  - insurance-letter     # General insurer correspondence

  # Customer & Project
  - proposal             # Angebot
  - project-doc          # Specs, architecture, meeting notes
  - correspondence       # Email printout, formal letter
  - report               # Status report, analysis

  # HR & Personal
  - employment-doc       # Arbeitsvertrag, Bescheinigung
  - certificate          # Zertifikat, Nachweis

  # Other
  - reference-material   # Guides, manuals, standards
  - other                # Fallback
```

---

## Complete Example: One Folder, Mixed Document Types

```yaml
folder:
  path: /drive/root:/oficina/steuerberater/2026/gener
  type: business-expenses
  period: "2026-01"
  updated_at: "2026-02-25"

documents:
  # --- A receipt ---
  - file: Tankstelle_Repsol_2026-01-26_LaJonquera_45__51EUR.jpeg
    doc_type: receipt
    doc_lang: es
    date: "2026-01-26"
    parties:
      from: Repsol
      to: null
    summary: Diesel fuel purchase at Repsol La Jonquera, 38.04L for €45.51.
    action_required: null
    urgency: none
    tags: [fuel, travel, spain, diesel]
    facts:
      amount: 45.51
      currency: EUR
      vat_amount: null
      vat_rate: null
      country: ES
      location: La Jonquera
      fuel_type: Diesel e+
      liters: 38.04
      expense_category: travel

  # --- A software subscription invoice ---
  - file: Software_Anthropic_2026-01-18_107__10EUR.pdf
    doc_type: invoice-incoming
    doc_lang: en
    date: "2026-01-18"
    parties:
      from: Anthropic, PBC
      to: Datamantics UG
    summary: Claude Max plan (5x) subscription, Jan–Feb 2026, €107.10 incl. 19% VAT.
    action_required: null
    urgency: none
    tags: [software, ai, subscription, anthropic]
    facts:
      amount: 107.10
      currency: EUR
      vat_amount: 17.10
      vat_rate: 19
      country: DE
      service: Claude Max plan (5x)
      billing_period: "2026-01-18 to 2026-02-18"
      expense_category: software
      payment_method: credit-card

  # --- A government letter ---
  - file: Bescheid_Finanzamt_2026-02-10.pdf
    doc_type: tax-notice
    doc_lang: de
    date: "2026-02-10"
    parties:
      from: Finanzamt Darmstadt
      to: Albert Lacambra Basil / Datamantics UG
    summary: >
      Reminder for missing Q4 2025 Umsatzsteuervoranmeldung.
      Penalty threatened if not filed by 2026-03-01.
    action_required: Submit Q4 2025 UStVA by 2026-03-01
    urgency: high
    tags: [tax, ust-voranmeldung, finanzamt, deadline, penalty]
    facts:
      reference_number: 26/123/45678
      tax_type: Umsatzsteuer
      missing_period: Q4 2025
      deadline: "2026-03-01"
      penalty_threatened: true

  # --- A customer proposal ---
  - file: Angebot_Nexplore_2026-01-15_DevKnowledge.pdf
    doc_type: proposal
    doc_lang: en
    date: "2026-01-15"
    parties:
      from: Datamantics UG
      to: Nexplore GmbH
    summary: >
      Proposal for AI-assisted developer knowledge and tooling strategy.
      3-phase approach, estimated 45 person-days, €54,000 total.
    action_required: Follow up on client feedback
    urgency: medium
    tags: [nexplore, proposal, ai, developer-tools, knowledge-management]
    facts:
      client: Nexplore GmbH
      project: Developer Knowledge Platform
      phase: proposal
      estimated_effort: 45 person-days
      estimated_value: 54000.00
      currency: EUR
      valid_until: "2026-02-15"

  # --- An insurance policy ---
  - file: Police_Haftpflicht_Allianz_2025.pdf
    doc_type: insurance-policy
    doc_lang: de
    date: "2025-03-01"
    parties:
      from: Allianz Versicherung
      to: Datamantics UG
    summary: >
      Business liability insurance (Betriebshaftpflicht) for IT consulting.
      Coverage up to €3M. Policy active until 2026-02-28.
    action_required: Renew before 2026-02-28
    urgency: medium
    tags: [insurance, liability, allianz, haftpflicht]
    facts:
      policy_number: BH-2025-987654
      insurance_type: Betriebshaftpflicht
      coverage_max: 3000000.00
      currency: EUR
      annual_premium: 480.00
      start_date: "2025-03-01"
      end_date: "2026-02-28"
      status: active
      auto_renew: true
```

---

## Generic Extraction Prompt

This single prompt works for ANY document type:

```
You are a document data extractor for a German IT consultancy (Datamantics UG,
operated by Albert Lacambra Basil). Extract structured metadata from the
provided document.

Return ONLY valid YAML (no markdown fences, no commentary). Follow this
exact structure:

file: "{filename}"
doc_type: <see list below>
doc_lang: <2-letter ISO code of the document's language>
date: "YYYY-MM-DD"  # primary date: issue date, receipt date, or letter date
parties:
  from: <who sent/issued this>
  to: <who received this, or null>
summary: >
  2-3 sentences. State what the document IS, its key content,
  and any critical dates or amounts. Be factual, no filler.
action_required: <what needs to be done, or null if purely informational>
urgency: <high if deadline within 30 days or legal/financial risk,
          medium if requires attention but no immediate deadline,
          low if routine, none if purely archival>
tags: [<lowercase keywords for search — include: topic, vendor/entity,
       document purpose, relevant domain>]
facts:
  <key>: <value>
  # Extract ALL notable structured data points from the document.
  # Use clear, consistent key names in snake_case.
  # Common keys (use when applicable):
  #   amount, currency, vat_amount, vat_rate — for anything with money
  #   deadline, due_date, valid_until — for time-sensitive items
  #   reference_number, policy_number, invoice_number — for identifiers
  #   client, project, phase — for project-related docs
  #   contract_start, contract_end, notice_period — for contracts
  #   country — 2-letter ISO code where transaction/entity is located
  #   expense_category — one of: travel, software, telecom, hosting,
  #     office, professional, insurance, fees, meals
  # Add any other keys that capture important document-specific data.
  # Do NOT include keys with null values — omit them entirely.

Allowed doc_type values:
invoice-incoming, invoice-outgoing, receipt, bank-statement,
payment-confirmation, tax-notice, tax-declaration, government-letter,
registration, contract, amendment, terms-of-service, nda,
insurance-policy, insurance-claim, insurance-letter, proposal,
project-doc, correspondence, report, employment-doc, certificate,
reference-material, other

Rules:
- Extract facts from the ACTUAL document content, never invent data
- For amounts: use decimal numbers (45.51 not "45,51 EUR")
- For dates: always YYYY-MM-DD format
- For German documents: keep vendor/entity names as-is but translate
  the summary and tags to English for consistent search
- If the document is a scan/image and partially illegible, note this
  in the summary
- tags should be 4-8 lowercase terms useful for keyword search
```

---

## Updated System Prompt for the Copilot Agent

```
You are Datamantics Admin Assistant, an agent for Datamantics UG,
a German IT consultancy operated by Albert Lacambra Basil.

## Data structure

Every OneDrive folder contains a `folder_description.yaml` with:
- folder.path, folder.type, folder.period, folder.updated_at
- documents[]: array of structured records, one per file

Each document record has:
- ENVELOPE (always present): file, doc_type, doc_lang, date, parties
  (from/to), summary, action_required, urgency, tags
- FACTS (varies by document): key-value pairs with domain-specific
  structured data (amounts, dates, identifiers, etc.)

## How to answer questions

### Step 1: Identify relevant folders
Search folder_description.yaml files by:
- tags (keyword match)
- doc_type (filter by document kind)
- folder.type or folder.period (scope by purpose or time)

### Step 2: Filter documents
Within matching folders, filter by:
- doc_type for "show me all invoices" → doc_type: invoice-incoming
- tags for topic search → tags contain "nexplore" or "insurance"
- facts.expense_category for spending queries
- urgency/action_required for "what needs attention?"
- date ranges for time-bounded queries
- parties.from or parties.to for entity-specific queries

### Step 3: Answer from structured data
- For aggregations (totals, counts): use facts.amount + facts.currency
- For status questions: check action_required and urgency
- For "find document X": match on tags, summary, parties, or filename
- For detail questions: read the actual file if the YAML summary
  is insufficient

## Query patterns and strategies

| User asks... | Strategy |
|---|---|
| "How much did I spend on X?" | Filter by tags/expense_category, sum facts.amount |
| "Any deadlines coming up?" | Filter urgency: high/medium, check action_required |
| "What's the status with [client]?" | Filter parties or tags for client name |
| "Find the Allianz insurance" | Filter doc_type: insurance-*, tags: allianz |
| "Summarize January expenses" | Filter folder.period: 2026-01, list by category |
| "What did the Finanzamt say?" | Filter doc_type: tax-notice or tags: finanzamt |
| "Which contracts expire soon?" | Filter doc_type: contract, check facts.contract_end |

## Rules

- NEVER fabricate document names, amounts, paths, or facts
- When computing totals, list the individual items (file + amount)
- Distinguish currencies — do not mix EUR and USD without noting it
- If multiple folders match, present all options
- Cite folder_path and filename for every document you reference
- If a document's summary is insufficient, say so and offer to
  read the full file
- All data stays within the Microsoft 365 tenant
- For the Steuerberater: group by expense_category and country,
  flag missing VAT info

## Response style

- Concise and direct
- Monetary values: always €XX.XX or $XX.XX format
- Document lists: table with [Date | Type | Vendor | Amount | File]
- Always include the folder path when citing documents
- For action items: state what, by when, and which document
```

---

## Folder-Level Aggregations (Optional but Recommended)

Add a computed `overview` block at the top of each folder YAML.
This lets the model answer folder-level questions without scanning all records:

```yaml
overview:
  document_count: 17
  date_range: "2026-01-16 to 2026-02-02"
  types_present: [receipt, invoice-incoming, payment-confirmation]
  total_amount_eur: 498.29
  has_action_items: false
  by_expense_category:
    travel: {count: 9, total: 278.53}
    software: {count: 2, total: 127.09}
    telecom: {count: 2, total: 48.97}
    hosting: {count: 2, total: 37.06}
    fees: {count: 1, total: 290.00}
  by_country:
    DE: {count: 5, total: 196.07}
    FR: {count: 4, total: 125.03}
    ES: {count: 3, total: 61.50}
  missing_vat: [
    "Tankstelle_Repsol_2026-01-26_LaJonquera_45__51EUR.jpeg",
    "Maut_Autema_2026-01-28_StVicenc_9__76EUR.jpeg"
  ]
```

---

## Implementation Summary

```
                    ┌──────────────────────┐
                    │   Document arrives    │
                    │   (any type)          │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Generic Extraction   │
                    │  Prompt (one prompt   │
                    │  handles all types)   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Validate + Append    │
                    │  to folder YAML       │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Recompute folder     │
                    │  overview block       │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Copilot queries      │
                    │  structured YAML      │
                    │  (not prose)          │
                    └──────────────────────┘
```

The key insight: **one extraction prompt, one schema pattern, any document type**.
The `facts` block is intentionally free-form — the LLM decides what's important
based on what it sees, but the envelope (type, date, parties, tags, urgency)
is always consistent and queryable.