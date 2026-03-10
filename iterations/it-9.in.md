---
document_id: IT-9-IN
version: 1.2.0
last_updated: 2026-03-10
status: Ready
purpose: Replace prose Markdown folder descriptions with structured YAML metadata extraction
audience: [Developers, reviewers]
dependencies: [IT-8-IN]
review_triggers:
  [
    Schema model changes,
    Extraction prompt changes,
    YAML serialization format changes,
    Description filename changes,
    Config default changes,
  ]
---

# Iteration 9: Structured YAML Document Extraction

## Objective

Replace the current prose-based Markdown folder descriptions (`folder_description.md`) with structured YAML metadata files (`folder_description.yaml`) using a two-layer schema: a universal envelope (doc_type, date, parties, summary, tags) per file plus a free-form `facts` block for domain-specific data. The data is consultative/archival only -- no urgency or action tracking fields.

## Motivation

**Business driver:** The current system produces one-sentence prose summaries per file inside a Markdown file. This format is difficult to query programmatically (e.g., "find all invoices over 100 EUR", "show all receipts from January"). A copilot agent cannot reliably extract structured data from free-text summaries. The design document "Generic Document Extraction System" defines a structured YAML format that makes folder contents machine-queryable while remaining human-readable. The data is consultative -- no urgency tracking or action-item management is required.

**How this iteration fulfills it:** This iteration implements the core extraction pipeline: new data models for the two-layer schema, a new extraction prompt that returns structured YAML per file, YAML parsing and validation, YAML serialization for the folder description file, and the config/filename changes to switch from `.md` to `.yaml`. After this iteration, every processed folder will contain a `folder_description.yaml` with structured, queryable metadata for each file.

## Architecture Diagram

```text
                  generate_description(listing, describer, file_contents, cache)
                              |
                    +---------+---------+
                    |                   |
              classify_folder      for each file:
              (unchanged)            extract_metadata(filename, content)
                    |                   |
                    |              describer.extract_metadata(filename, content)
                    |                   |
                    |              parse YAML response -> DocumentRecord
                    |                   |
                    v                   v
              FolderDescription(folder_path, folder_type, documents=[...], updated_at)
                              |
                        to_yaml() -> YAML string
                              |
                        upload as folder_description.yaml
```

## Prerequisites

- All IT-8 prerequisites remain
- PyYAML dependency added to `pyproject.toml` (for YAML serialization and parsing)

## Scope

### In Scope

1. New data models in `description/models.py` (D1)
2. New `extract_metadata()` method in `description/describer.py` (D2)
3. Updated `generate_description()` in `description/generator.py` (D3)
4. Config default change in `config.py` (D4)
5. Processor serialization update in `orchestration/processor.py` (D5)
6. PyYAML dependency (D6)
7. Unit tests for all new and changed code (D7)
8. Update `CLAUDE.md` Architecture section (D8)

### Out of Scope

- Folder-level `overview` aggregation block (deferred to IT-10)
- Updated copilot agent system prompt (deferred to IT-10 or later)
- Migration of existing `folder_description.md` files to `.yaml` (old files remain; new runs produce `.yaml`)
- Changes to `SummaryCache` keying strategy (cache continues to store per-file strings; the cached value becomes the raw YAML extraction instead of a one-sentence summary)
- Changes to `classify_folder()` (continues to produce a folder_type string)
- Urgency levels or action-required tracking (data is consultative, not actionable)
- Removal of the old `summarize_file()` method from `AnthropicDescriber` (kept for any future use; `generate_description` switches to calling `extract_metadata`)

## Deliverables

### D1: Replace data models in `src/semantic_folder/description/models.py`

Remove `FileDescription` and `to_markdown()`. Replace with structured YAML models.

**Constants:**

```python
DOC_TYPES: frozenset[str] = frozenset({
    "invoice-incoming",
    "invoice-outgoing",
    "receipt",
    "bank-statement",
    "payment-confirmation",
    "tax-notice",
    "tax-declaration",
    "government-letter",
    "registration",
    "contract",
    "amendment",
    "terms-of-service",
    "nda",
    "insurance-policy",
    "insurance-claim",
    "insurance-letter",
    "proposal",
    "project-doc",
    "correspondence",
    "report",
    "employment-doc",
    "certificate",
    "reference-material",
    "other",
})
```

**New dataclasses:**

```python
@dataclass
class Parties:
    """Sender and recipient of a document.

    Attributes:
        from_: Who sent or issued the document.
        to: Who received the document, or None if not applicable.
    """

    from_: str
    to: str | None = None


@dataclass
class DocumentRecord:
    """Structured metadata for a single file extracted by the LLM.

    Layer 1 (universal envelope) fields are always present.
    Layer 2 (facts) is a free-form dict whose keys vary by doc_type.

    Attributes:
        file: Filename as it appears in OneDrive.
        doc_type: Controlled vocabulary value from DOC_TYPES.
        doc_lang: Two-letter ISO 639-1 language code.
        date: Primary date in YYYY-MM-DD format (issued, created, received).
        parties: Sender and recipient.
        summary: 2-3 sentence factual summary in English.
        tags: Lowercase keyword list for search (4-8 terms).
        facts: Free-form key-value pairs with domain-specific structured data.
    """

    file: str
    doc_type: str
    doc_lang: str
    date: str
    parties: Parties
    summary: str
    tags: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)
```

**Updated `FolderDescription`:**

```python
@dataclass
class FolderDescription:
    """Complete structured description of a folder and its files.

    Attributes:
        folder_path: OneDrive path of the folder (from parentReference.path).
        folder_type: Classification of the folder (AI-inferred).
        documents: Ordered list of structured document records.
        updated_at: ISO date string (YYYY-MM-DD) when the description was generated.
    """

    folder_path: str
    folder_type: str
    documents: list[DocumentRecord] = field(default_factory=list)
    updated_at: str = ""

    def to_yaml(self) -> str:
        """Serialize this folder description to YAML.

        Returns:
            String content suitable for writing to folder_description.yaml.
        """
```

The `to_yaml()` method uses `yaml.dump()` (PyYAML) to produce clean YAML output with the structure:

```yaml
folder:
  path: /drive/root:/oficina/steuerberater/2026/gener
  type: business-expenses
  updated_at: "2026-02-25"

documents:
  - file: Software_Anthropic_2026-01-18_107__10EUR.pdf
    doc_type: invoice-incoming
    doc_lang: en
    date: "2026-01-18"
    parties:
      from: Anthropic, PBC
      to: Datamantics UG
    summary: Claude Max plan (5x) subscription, Jan-Feb 2026, ...
    tags: [software, ai, subscription, anthropic]
    facts:
      amount: 107.10
      currency: EUR
```

Implementation details for `to_yaml()`:

- Build a plain dict structure from the dataclass fields, then call `yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)`.
- The `tags` list should use flow style `[a, b, c]` for compactness. Use a custom `yaml.Dumper` subclass or representer to achieve this.
- The `Parties.from_` field (Python name with trailing underscore) must be serialized as the YAML key `from` (without underscore). The `to_yaml()` dict-building code must explicitly map `from_` -> `from` when constructing the `parties` sub-dict.
- Omit `facts` key entirely when the dict is empty (cleaner output).

### D2: Add `extract_metadata()` method in `src/semantic_folder/description/describer.py`

New public method on `AnthropicDescriber`:

```python
def extract_metadata(self, filename: str, content: bytes) -> str:
    """Extract structured YAML metadata from a file.

    Dispatches to the appropriate content strategy based on file extension
    (text, docx, pdf, image) and sends the extraction prompt instead of
    the one-sentence summary prompt. Returns the raw YAML string from the
    LLM response.

    Args:
        filename: Name of the file.
        content: Raw file content.

    Returns:
        Raw YAML string from the LLM extraction response.

    Raises:
        Exception: Propagates API errors to the caller for handling.
    """
```

**New module-level constant for the extraction prompt:**

```python
_EXTRACTION_PROMPT_TEMPLATE = """\
You are a document data extractor for a German IT consultancy (Datamantics UG, \
operated by Albert Lacambra Basil). Extract structured metadata from the \
provided document.

Return ONLY valid YAML (no markdown fences, no commentary). Follow this \
exact structure:

file: "{filename}"
doc_type: <see list below>
doc_lang: <2-letter ISO code of the document's language>
date: "YYYY-MM-DD"
parties:
  from: <who sent/issued this>
  to: <who received this, or null>
summary: >
  2-3 sentences. State what the document IS, its key content,
  and any critical dates or amounts. Be factual, no filler.
tags: [<lowercase keywords for search -- include: topic, vendor/entity, \
document purpose, relevant domain>]
facts:
  <key>: <value>
  # Extract ALL notable structured data points from the document.
  # Use clear, consistent key names in snake_case.
  # Common keys (use when applicable):
  #   amount, currency, vat_amount, vat_rate -- for anything with money
  #   deadline, due_date, valid_until -- for time-sensitive items
  #   reference_number, policy_number, invoice_number -- for identifiers
  #   client, project, phase -- for project-related docs
  #   contract_start, contract_end, notice_period -- for contracts
  #   country -- 2-letter ISO code where transaction/entity is located
  #   expense_category -- one of: travel, software, telecom, hosting, \
office, professional, insurance, fees, meals
  # Add any other keys that capture important document-specific data.
  # Do NOT include keys with null values -- omit them entirely.

Allowed doc_type values:
invoice-incoming, invoice-outgoing, receipt, bank-statement, \
payment-confirmation, tax-notice, tax-declaration, government-letter, \
registration, contract, amendment, terms-of-service, nda, \
insurance-policy, insurance-claim, insurance-letter, proposal, \
project-doc, correspondence, report, employment-doc, certificate, \
reference-material, other

Rules:
- Extract facts from the ACTUAL document content, never invent data
- For amounts: use decimal numbers (45.51 not "45,51 EUR")
- For dates: always YYYY-MM-DD format
- For German documents: keep vendor/entity names as-is but translate \
the summary and tags to English for consistent search
- If the document is a scan/image and partially illegible, note this \
in the summary
- tags should be 4-8 lowercase terms useful for keyword search"""

_EXTRACTION_MAX_TOKENS = 1024
```

**Dispatch logic:** `extract_metadata` follows the same extension-based dispatch as `summarize_file` (docx -> extract text first, pdf -> base64 document block, image -> base64 image block, other -> UTF-8 text) but uses `_EXTRACTION_PROMPT_TEMPLATE` (with `{filename}` substituted) and `_EXTRACTION_MAX_TOKENS` instead of the one-sentence prompt and 150-token limit.

The method builds content blocks in the same way as the existing `_summarize_*` methods, but the text prompt is the extraction prompt. The method does NOT catch exceptions -- errors propagate to the caller (`generate_description`) for fallback handling.

**Private helper methods (optional refactoring):** To avoid duplicating the content block construction across `summarize_file` and `extract_metadata`, each private method (`_summarize_text`, `_summarize_pdf`, etc.) can be refactored to accept a `prompt` and `max_tokens` parameter. However, this refactoring is optional -- the implementation may duplicate the dispatch logic in `extract_metadata` as a simpler approach. Either approach is acceptable as long as the extraction prompt is used and max_tokens is 1024.

### D3: Update `generate_description()` in `src/semantic_folder/description/generator.py`

Replace the current per-file flow that calls `summarize_file` with a new flow that calls `extract_metadata` and parses the result.

**Remove:** `FileDescription` import, `_get_or_generate_summary()` function.

**Add:** `parse_document_record()` function, `_get_or_extract_metadata()` function.

```python
import yaml

from semantic_folder.description.models import (
    DOC_TYPES,
    DocumentRecord,
    FolderDescription,
    Parties,
)


def parse_document_record(yaml_str: str, filename: str) -> DocumentRecord:
    """Parse a raw YAML string from the LLM into a DocumentRecord.

    Validates doc_type against DOC_TYPES. Falls back to "other" for
    unknown types. Handles missing or malformed fields gracefully.

    Args:
        yaml_str: Raw YAML string returned by the LLM.
        filename: Original filename (used as fallback for the file field).

    Returns:
        Validated DocumentRecord instance.

    Raises:
        ValueError: If the YAML cannot be parsed at all.
    """
```

Validation rules:
- `yaml.safe_load(yaml_str)` to parse. If it raises, raise `ValueError`.
- `doc_type`: if not in `DOC_TYPES`, replace with `"other"`.
- `parties`: parse `from` key (note: YAML `from` is a string key, not a Python keyword) into `Parties(from_=..., to=...)`. If missing, default to `Parties(from_="unknown")`.
- `tags`: if not a list, default to `[]`.
- `facts`: if not a dict, default to `{}`.
- `file`: use the parsed value if present, otherwise fall back to `filename`.
- `doc_lang`: default to `"und"` (undetermined) if missing.
- `date`: default to `""` if missing.
- `summary`: default to `""` if missing.

**Updated `generate_description()`:**

```python
def generate_description(
    listing: FolderListing,
    describer: AnthropicDescriber,
    file_contents: dict[str, bytes],
    cache: SummaryCache | None = None,
) -> FolderDescription:
```

Signature unchanged. Internally:
1. Call `describer.classify_folder(listing.folder_path, listing.files)` (unchanged).
2. For each file in `listing.files`:
   a. Call `_get_or_extract_metadata(name, content, describer, cache)` to get the raw YAML string (with cache check/store, same pattern as old `_get_or_generate_summary`).
   b. Call `parse_document_record(yaml_str, name)` to get a `DocumentRecord`.
   c. On `ValueError` from parsing, create a fallback `DocumentRecord` with `doc_type="other"` and summary `"[extraction failed]"`.
3. Return `FolderDescription(folder_path=..., folder_type=..., documents=[...], updated_at=...)`.

**New `_get_or_extract_metadata()`:**

```python
def _get_or_extract_metadata(
    filename: str,
    content: bytes,
    describer: AnthropicDescriber,
    cache: SummaryCache | None,
) -> str:
    """Return cached metadata YAML or extract fresh metadata.

    Same cache pattern as the old _get_or_generate_summary: check cache
    by content hash, call describer.extract_metadata on miss, store result.

    Args:
        filename: Name of the file.
        content: Raw file content bytes.
        describer: AnthropicDescriber for extracting new metadata.
        cache: Optional cache to check/populate.

    Returns:
        Raw YAML metadata string.
    """
```

### D4: Config default change in `src/semantic_folder/config.py`

Change the default value of `folder_description_filename` from `"folder_description.md"` to `"folder_description.yaml"`:

```python
# In AppConfig:
folder_description_filename: str = "folder_description.yaml"

# In load_config():
folder_description_filename=os.environ.get(
    "SF_FOLDER_DESCRIPTION_FILENAME", "folder_description.yaml"
),
```

### D5: Processor serialization update in `src/semantic_folder/orchestration/processor.py`

Change `upload_description()` to call `to_yaml()` instead of `to_markdown()`:

```python
def upload_description(self, listing: FolderListing) -> None:
    ...
    content = description.to_yaml().encode("utf-8")
    ...
```

Update the docstring to reference YAML instead of Markdown. Update the log message field from `file_count` / `description.files` to `document_count` / `description.documents`:

```python
logger.info(
    "[upload_description] uploaded description; folder_path:%s;document_count:%d",
    listing.folder_path,
    len(description.documents),
)
```

Update the default parameter in `FolderProcessor.__init__` to match the new config default:

```python
def __init__(
    self,
    ...
    folder_description_filename: str = "folder_description.yaml",
    ...
) -> None:
```

### D6: Add PyYAML dependency

```bash
poetry add pyyaml
poetry add --group dev types-PyYAML   # for pyright type stubs
```

### D7: Unit tests

#### D7a: `tests/unit/description/test_models.py` -- complete rewrite

Remove all `FileDescription` and `to_markdown()` tests. Replace with:

**`TestDocumentRecord`:**
- `test_stores_all_envelope_fields` -- construct with all fields, assert each
- `test_tags_defaults_to_empty_list` -- construct without tags, assert `[]`
- `test_facts_defaults_to_empty_dict` -- construct without facts, assert `{}`
- `test_parties_to_defaults_to_none` -- `Parties(from_="X")`, assert `to is None`

**`TestFolderDescription`:**
- `test_stores_all_fields` -- construct with folder_path, folder_type, documents, updated_at
- `test_documents_defaults_to_empty_list`
- `test_updated_at_defaults_to_empty_string`

**`TestToYaml`:**
- `test_produces_folder_block_with_path_type_updated_at` -- assert `folder:` block present with correct values
- `test_produces_documents_list` -- two `DocumentRecord`s, assert both appear under `documents:`
- `test_document_record_has_all_envelope_fields` -- verify file, doc_type, doc_lang, date, parties (from/to), summary, tags in output
- `test_facts_block_present_when_non_empty` -- verify `facts:` key with sub-keys
- `test_facts_block_absent_when_empty` -- verify no `facts:` key when facts is `{}`
- `test_tags_rendered_as_flow_sequence` -- verify `tags: [a, b, c]` format (not block sequence)
- `test_parties_null_to_rendered_correctly` -- verify `to: null` when `Parties.to` is `None`
- `test_empty_documents_produces_empty_list` -- verify `documents: []`
- `test_output_ends_with_trailing_newline`
- `test_output_is_valid_yaml` -- `yaml.safe_load()` round-trip succeeds

**`TestDocTypes`:**
- `test_doc_types_contains_expected_values` -- spot-check several known types
- `test_doc_types_is_frozenset` -- verify immutability

#### D7b: `tests/unit/description/test_describer.py` -- add `TestExtractMetadata`

New test class alongside existing tests (existing `summarize_file` tests remain unchanged):

- `test_text_file_sends_extraction_prompt` -- verify the extraction prompt template is used (not "Summarize this file in one sentence"), verify `max_tokens=1024`
- `test_pdf_sends_document_block_with_extraction_prompt` -- verify base64 document block + extraction prompt text
- `test_image_sends_image_block_with_extraction_prompt` -- verify base64 image block + extraction prompt text
- `test_docx_extracts_text_then_sends_extraction_prompt` -- verify docx text extraction + extraction prompt
- `test_returns_raw_yaml_string` -- verify the raw LLM text is returned as-is
- `test_filename_substituted_in_prompt` -- verify `{filename}` is replaced with actual filename
- `test_sleeps_before_api_call` -- verify `time.sleep(request_delay)` is called
- `test_propagates_api_errors` -- verify exceptions are NOT caught (unlike `summarize_file`)

#### D7c: `tests/unit/description/test_generator.py` -- rewrite for new flow

Replace `_make_describer_mock` to include `extract_metadata` instead of `summarize_file`:

```python
def _make_describer_mock() -> MagicMock:
    mock = MagicMock()
    mock.classify_folder.return_value = "project-docs"
    mock.extract_metadata.side_effect = lambda name, content: (
        f'file: "{name}"\n'
        f"doc_type: other\n"
        f"doc_lang: en\n"
        f'date: "2026-01-01"\n'
        f"parties:\n"
        f"  from: unknown\n"
        f"  to: null\n"
        f"summary: Mock extraction of {name}\n"
        f"tags: [test]\n"
        f"facts: {{}}\n"
    )
    return mock
```

**`TestGenerateDescription`:**
- `test_returns_folder_description_type`
- `test_folder_path_matches_listing`
- `test_calls_classify_folder_with_correct_args`
- `test_folder_type_comes_from_describer`
- `test_calls_extract_metadata_once_per_file` -- verify `extract_metadata` called (not `summarize_file`)
- `test_uses_empty_bytes_for_missing_file_content`
- `test_one_document_record_per_file` -- verify `len(result.documents)`
- `test_document_records_from_extraction` -- verify `DocumentRecord` fields populated from parsed YAML
- `test_updated_at_is_todays_date`
- `test_empty_files_produces_empty_documents_list`
- `test_filenames_preserved_in_order` -- verify `[d.file for d in result.documents]` order
- `test_extraction_failure_produces_fallback_record` -- mock `extract_metadata` to raise, verify fallback `DocumentRecord` with `doc_type="other"`

**`TestGenerateDescriptionWithCache`:**
- `test_cache_hit_skips_extract_metadata` -- cached YAML string returned, `extract_metadata` not called
- `test_cache_miss_calls_extract_metadata_and_stores`
- `test_does_not_cache_empty_content`
- `test_classify_folder_always_called_with_cache`
- `test_mixed_cache_hits_and_misses`
- `test_without_cache_calls_extract_metadata_for_all_files`

**`TestParseDocumentRecord`:**
- `test_parses_valid_yaml_into_document_record` -- full YAML string, verify all fields
- `test_unknown_doc_type_falls_back_to_other`
- `test_missing_parties_defaults_to_unknown`
- `test_missing_tags_defaults_to_empty_list`
- `test_missing_facts_defaults_to_empty_dict`
- `test_missing_doc_lang_defaults_to_und`
- `test_missing_date_defaults_to_empty_string`
- `test_missing_summary_defaults_to_empty_string`
- `test_filename_fallback_when_file_field_missing`
- `test_raises_value_error_on_unparseable_yaml`
- `test_parties_from_key_mapped_to_from_underscore` -- verify YAML `from:` maps to `Parties.from_`
- `test_parties_to_null_maps_to_none` -- verify YAML `to: null` maps to `Parties.to = None`

**`TestGetOrExtractMetadata`:**
- `test_no_cache_calls_extract_metadata_directly`
- `test_cache_hit_returns_cached_and_skips_llm`
- `test_cache_miss_calls_llm_and_stores`
- `test_empty_content_bypasses_cache`

#### D7d: `tests/unit/orchestration/test_processor.py` -- update affected tests

Update `_make_processor` helper: configure `mock_describer.extract_metadata` (returning valid YAML strings) since `generate_description` now calls `extract_metadata` instead of `summarize_file`. The `summarize_file` mock may be kept but is no longer exercised by the upload path.

- `TestUploadDescription.test_content_is_utf8_encoded_markdown` -- rename to `test_content_is_utf8_encoded_yaml`, update assertions to check for YAML structure (`folder:`, `documents:`) instead of Markdown (`---`, `## a.txt`)
- `TestUploadDescriptionWithCache` -- update `mock_desc.to_markdown.return_value` to `mock_desc.to_yaml.return_value`
- `TestUploadDescription.test_calls_put_content_with_correct_path` -- update expected path to use `folder_description.yaml` instead of `folder_description.md`
- `TestUploadDescription.test_reads_file_contents_then_generates_description` -- update assertion from `mock_describer.summarize_file.assert_called_once_with(...)` to `mock_describer.extract_metadata.assert_called_once_with(...)`
- `TestFolderProcessorFromConfig.test_passes_folder_description_filename` -- update expected filename in assertions

#### D7e: `tests/unit/config/test_config.py` -- add default verification

- `test_folder_description_filename_defaults_to_yaml` -- verify `AppConfig()` default is `"folder_description.yaml"`
- `test_load_config_folder_description_filename_defaults_to_yaml` -- verify `load_config()` produces `"folder_description.yaml"` when env var not set

### D8: Update `CLAUDE.md` Architecture section

Update the `description/models.py` entry in the Architecture section from:

> `description/models.py` -- `FileDescription`, `FolderDescription` dataclasses with Markdown serialization

to:

> `description/models.py` -- `Parties`, `DocumentRecord`, `FolderDescription` dataclasses with YAML serialization; `DOC_TYPES` controlled vocabulary constant

Also update the `description/describer.py` entry to mention metadata extraction alongside summarization:

> `description/describer.py` -- `AnthropicDescriber` wraps the Anthropic Messages API for file summarization, structured metadata extraction, and folder classification; includes rate-limit resilience via SDK retries (`max_retries`) and inter-request delay (`time.sleep`)

## Acceptance Criteria

1. `make lint` passes (ruff check + format)
2. `make typecheck` passes (pyright basic)
3. `make test` passes with all new and existing tests
4. `FileDescription` class is removed from `description/models.py`
5. `to_markdown()` method is removed from `FolderDescription`
6. `FolderDescription.to_yaml()` produces valid YAML matching the design document structure
7. `extract_metadata()` sends the full extraction prompt with correct content blocks per file type
8. `extract_metadata()` uses `max_tokens=1024` (not 150)
9. `parse_document_record()` validates `doc_type` against `DOC_TYPES` and falls back to `"other"`
10. `generate_description()` calls `extract_metadata` (not `summarize_file`) and produces `DocumentRecord` instances
11. `generate_description()` creates a fallback `DocumentRecord` when extraction fails
12. Default `folder_description_filename` is `"folder_description.yaml"` in both `AppConfig` and `load_config()`
13. `upload_description()` calls `to_yaml()` (not `to_markdown()`)
14. Cache integration works: cache hit skips `extract_metadata`, cache miss stores the raw YAML string
15. Coverage remains at or above 90%
16. PyYAML is listed as a dependency in `pyproject.toml`
17. `types-PyYAML` is listed as a dev dependency

## Pre-Development Review

### Specification Review

| # | Skill / Area | Finding | Status |
| --- | --- | --- | --- |
| 1 | Architecture / Three-Layer Design | All changes stay within their correct layers: models in `description/models.py`, AI interaction in `description/describer.py`, coordination in `description/generator.py`, orchestration in `orchestration/processor.py`, config in `config.py`. No layer violations. | PASS |
| 2 | Architecture / Dependency Injection | `extract_metadata()` is a method on `AnthropicDescriber` (injected via constructor). `generate_description()` receives `describer` as a parameter. `FolderProcessor` receives all dependencies via constructor. No module reads `os.environ` directly except `load_config()`. | PASS |
| 3 | Architecture / Encapsulation | D2 spec allows either refactoring shared private methods or duplicating dispatch logic. Both approaches keep the extraction logic inside `AnthropicDescriber`. No public interface leaks internal dispatch details. | PASS |
| 4 | Constants / No Magic Strings | `DOC_TYPES` is a named frozenset constant. `_EXTRACTION_PROMPT_TEMPLATE` and `_EXTRACTION_MAX_TOKENS` are named constants. The allowed doc_type list in the prompt text must stay in sync with the `DOC_TYPES` frozenset. **Action:** Add a note to D2 that the allowed doc_type list in `_EXTRACTION_PROMPT_TEMPLATE` MUST be generated from or validated against the `DOC_TYPES` constant, not hardcoded as a separate string. | PASS with NOTE |
| 5 | Constants / Placement | `DOC_TYPES` lives in `description/models.py` -- correct placement alongside the dataclasses that use it. `_EXTRACTION_PROMPT_TEMPLATE` lives in `description/describer.py` -- correct placement alongside the AI interaction code. | PASS |
| 6 | Configuration Management / Factory Pattern | D4 changes the default in both `AppConfig` and `load_config()`. No new env vars are introduced. The `folder_description_filename` flows through `folder_processor_from_config` -> `FolderProcessor` -> `upload_description` and also through `delta_processor_from_config` -> `DeltaProcessor` -> loop prevention. The filename change propagates correctly through both paths. | PASS |
| 7 | Configuration Management / FolderProcessor Default | The `FolderProcessor.__init__` has a default `folder_description_filename="folder_description.md"` (line 42 of processor.py). This default must also be updated to `"folder_description.yaml"` for consistency. **Action:** Add this to D5 scope -- update the default parameter in `FolderProcessor.__init__`. | FINDING |
| 8 | Code Style / Line Length | The `_EXTRACTION_PROMPT_TEMPLATE` string uses backslash line continuations. Multi-line strings in Python triple-quotes embed literal newlines, which is fine. The backslash continuations within the template are used to control where line breaks appear in the prompt sent to the LLM. Ruff does not check line length inside string literals for triple-quoted strings. | PASS |
| 9 | Code Style / Docstrings | All new public functions and methods have Google-style docstrings specified (Args, Returns, Raises). Private helpers need docstrings per existing codebase convention. | PASS |
| 10 | Code Style / Pyright | `Parties.from_` uses a trailing underscore to avoid the `from` keyword. The YAML key `from` must be explicitly mapped to `from_` in `parse_document_record`. `dict[str, object]` for `facts` is correct for pyright basic mode (allows any value type). | PASS |
| 11 | Testing / Mirror Structure | Tests remain in `tests/unit/description/test_models.py`, `test_describer.py`, `test_generator.py` and `tests/unit/orchestration/test_processor.py`. Structure mirrors `src/`. | PASS |
| 12 | Testing / Mock Patterns | All Anthropic API calls mocked via `MagicMock`. YAML parsing tested with real strings (no mock needed). Cache mocked via `MagicMock(spec=SummaryCache)`. Consistent with existing patterns. | PASS |
| 13 | Testing / Coverage | D7 specifies 50+ test cases across 5 test files covering all new code paths, validation branches, fallback paths, and cache integration. Combined with unchanged tests for `summarize_file`, `classify_folder`, and graph modules, coverage should remain above 90%. | PASS |
| 14 | Testing / D7d Processor Tests | The `_make_processor` helper in `test_processor.py` sets up `mock_describer.summarize_file` but the real code will now call `extract_metadata` via `generate_description`. Since `test_content_is_utf8_encoded_yaml` calls real `upload_description` which calls real `generate_description`, the mock must set up `extract_metadata` not just `summarize_file`. **Action:** D7d must specify that `_make_processor` mock helper is updated to configure `mock_describer.extract_metadata` in addition to (or instead of) `mock_describer.summarize_file`. | FINDING |
| 15 | Cache / Semantic Change | The cache previously stored one-sentence summary strings. After IT-9, it stores raw YAML extraction strings (much longer). This is a semantic change but not a breaking one -- the cache key is the content hash, so old cached summaries will simply be treated as (invalid) YAML, which `parse_document_record` will handle via fallback. **However**: old cached one-line summaries will fail YAML parsing and produce fallback records every time until the cache entry expires or is overwritten. **Action:** Add a note in the spec that existing cache entries from pre-IT-9 runs will produce fallback `DocumentRecord` results until overwritten. This is acceptable behavior (self-healing). | PASS with NOTE |
| 16 | YAML Serialization / `from` Key | The `Parties` dataclass uses `from_` (with underscore) but the YAML output must use `from` (without underscore). `to_yaml()` must explicitly map `from_` -> `from` when building the dict for serialization. **Action:** Confirm this mapping is specified. Reviewing D1: the spec says "build a plain dict structure from the dataclass fields" but does not explicitly call out the `from_` -> `from` mapping. Add this to D1 implementation details. | FINDING |
| 17 | YAML Serialization / `tags` Flow Style | The spec requests flow-style `[a, b, c]` for tags. PyYAML default_flow_style=False will render tags as block sequences. A custom representer is needed. The spec mentions "Use a custom yaml.Dumper subclass or representer" which is correct but vague. Acceptable -- implementation detail. | PASS |
| 18 | CLAUDE.md Update | CLAUDE.md line 46 documents `description/models.py` as "`FileDescription`, `FolderDescription` dataclasses with Markdown serialization". After IT-9, this must be updated to reflect the new models. **Action:** Add a deliverable or note to update CLAUDE.md Architecture section after implementation. | FINDING |

### Findings Summary

**4 findings requiring spec amendments:**

1. **[F7] FolderProcessor default parameter** -- The default `folder_description_filename="folder_description.md"` in `FolderProcessor.__init__` must be updated to `"folder_description.yaml"`. Add to D5.

2. **[F14] Processor test mock setup** -- D7d must specify that `_make_processor` and `_make_describer_mock` in `test_processor.py` configure `mock_describer.extract_metadata` (not just `summarize_file`), since `generate_description` now calls `extract_metadata`.

3. **[F16] Parties from_ -> from YAML mapping** -- D1 must explicitly specify that `to_yaml()` maps `Parties.from_` to the YAML key `from` (without underscore) when building the serialization dict.

4. **[F18] CLAUDE.md update** -- Add a note that CLAUDE.md Architecture section must be updated after implementation to reflect `DocumentRecord`, `Parties`, `FolderDescription` with YAML serialization (replacing `FileDescription` with Markdown serialization).

**2 notes (no spec change required, informational):**

- **[N4] DOC_TYPES sync** -- The allowed doc_type list in `_EXTRACTION_PROMPT_TEMPLATE` must stay in sync with the `DOC_TYPES` frozenset. Implementer should generate the list from the constant or add a test that validates sync.
- **[N15] Cache semantic change** -- Existing pre-IT-9 cache entries will produce fallback records until overwritten. Self-healing, no action needed.

### Spec Amendments Applied

The following amendments address the 4 findings above:

**Amendment 1 (F7):** D5 expanded to include updating `FolderProcessor.__init__` default parameter.

**Amendment 2 (F14):** D7d expanded to specify mock helper updates for `extract_metadata`.

**Amendment 3 (F16):** D1 `to_yaml()` implementation details expanded to specify `from_` -> `from` key mapping.

**Amendment 4 (F18):** New deliverable D8 added for CLAUDE.md update.

**Specification Review Status: APPROVED (with amendments applied below)**

## Independent Validation

### Readiness Checklist

- [x] **Scope clear and bounded** -- 8 deliverables (D1-D8), each targeting a single file or concern. In-scope and out-of-scope sections are explicit. No ambiguity about what ships in IT-9 vs. deferred iterations.
- [x] **Deliverables actionable** -- Each deliverable specifies exact file paths, method signatures, dataclass definitions, constant values, and code snippets. An implementer can start coding from D1 through D8 in order without needing to make design decisions.
- [x] **Acceptance criteria testable** -- All 17 criteria map to verifiable assertions: lint/typecheck/test gates (AC 1-3), specific class/method removal (AC 4-5), output format (AC 6), prompt content (AC 7-8), validation behavior (AC 9), call graph (AC 10-11), config defaults (AC 12), serialization (AC 13), cache (AC 14), coverage (AC 15), dependencies (AC 16-17).
- [x] **Dependencies satisfied** -- IT-8 is complete (commit b2c3987). PyYAML is available on PyPI and has no conflicts with existing dependencies. `types-PyYAML` stubs available for pyright.
- [x] **No blocking issues** -- All Phase 3 findings have been resolved via spec amendments. No open questions remain.

### Five Pillars

#### Pillar 1: Interface Contracts

- [x] `AnthropicDescriber.extract_metadata(filename: str, content: bytes) -> str` -- new public method, signature specified in D2. Does not modify existing `summarize_file` or `classify_folder` signatures.
- [x] `generate_description(listing, describer, file_contents, cache) -> FolderDescription` -- signature unchanged (D3). Internal behavior changes from `summarize_file` to `extract_metadata` calls.
- [x] `parse_document_record(yaml_str: str, filename: str) -> DocumentRecord` -- new public function, signature specified in D3. Raises `ValueError` on unparseable YAML.
- [x] `_get_or_extract_metadata(filename, content, describer, cache) -> str` -- new private function, signature specified in D3. Same cache pattern as predecessor.
- [x] `FolderDescription.to_yaml() -> str` -- new method replacing `to_markdown()`, signature specified in D1.
- [x] `FolderProcessor.upload_description(listing)` -- signature unchanged, internal call changes from `to_markdown` to `to_yaml` (D5).

#### Pillar 2: Data Structures

- [x] `Parties(from_: str, to: str | None = None)` -- dataclass specified in D1. `from_` trailing underscore documented; YAML `from` mapping specified in D1 implementation details.
- [x] `DocumentRecord(file, doc_type, doc_lang, date, parties, summary, tags, facts)` -- dataclass specified in D1. All field types explicit. `tags: list[str]` defaults to `[]`, `facts: dict[str, object]` defaults to `{}`.
- [x] `FolderDescription(folder_path, folder_type, documents: list[DocumentRecord], updated_at)` -- replaces old `files: list[FileDescription]` field. Specified in D1.
- [x] `DOC_TYPES: frozenset[str]` -- 24 values enumerated in D1. Used for validation in `parse_document_record` (D3).

#### Pillar 3: Configuration Formats

- [x] `AppConfig.folder_description_filename` default changes from `"folder_description.md"` to `"folder_description.yaml"` (D4). Both the dataclass default and `load_config()` fallback are specified.
- [x] `FolderProcessor.__init__` default parameter updated to `"folder_description.yaml"` (D5).
- [x] No new environment variables introduced. `SF_FOLDER_DESCRIPTION_FILENAME` continues to work for override.
- [x] PyYAML added as runtime dependency, `types-PyYAML` as dev dependency (D6). Neither conflicts with existing `pyproject.toml` dependencies.

#### Pillar 4: Behavioral Requirements

- [x] **Extraction prompt** -- `_EXTRACTION_PROMPT_TEMPLATE` specified verbatim in D2. `{filename}` placeholder documented. `_EXTRACTION_MAX_TOKENS = 1024` specified.
- [x] **File-type dispatch** -- `extract_metadata` uses same extension-based dispatch as `summarize_file` (text/docx/pdf/image). D2 specifies this explicitly.
- [x] **Error propagation** -- `extract_metadata` does NOT catch exceptions (unlike `summarize_file`). Errors propagate to `generate_description` which creates a fallback `DocumentRecord` (D3 step 2c).
- [x] **YAML parsing validation** -- `parse_document_record` validates `doc_type` against `DOC_TYPES`, defaults missing fields, raises `ValueError` on unparseable input. All validation rules enumerated in D3.
- [x] **Fallback DocumentRecord** -- On `ValueError`, `generate_description` creates `DocumentRecord(file=name, doc_type="other", doc_lang="und", date="", parties=Parties(from_="unknown"), summary="[extraction failed]")`. Specified in D3 step 2c.
- [x] **Cache behavior** -- `_get_or_extract_metadata` follows identical pattern to old `_get_or_generate_summary`: check cache by content hash, call describer on miss, store result. Empty content bypasses cache. Specified in D3.
- [x] **YAML serialization** -- `to_yaml()` produces `folder:` block + `documents:` list. `from_` -> `from` mapping, `tags` flow style, `facts` omission when empty -- all specified in D1 implementation details.
- [x] **Loop prevention** -- Delta processor uses `self._folder_description_filename` (configurable). Changing the config default propagates automatically via `delta_processor_from_config`. Verified in Phase 3 review item #6.

#### Pillar 5: Quality Criteria

- [x] **Lint gate** -- AC 1: `make lint` (ruff check + format). Prompt template uses triple-quoted strings; ruff does not enforce line length inside them.
- [x] **Type check gate** -- AC 2: `make typecheck` (pyright basic). `dict[str, object]` for facts is valid. `Parties.from_` avoids keyword conflict. `types-PyYAML` stubs provide type coverage for `yaml` module.
- [x] **Test gate** -- AC 3: `make test` (pytest with coverage). D7 specifies 50+ test cases across 5 files. Tests cover: model construction (D7a), YAML serialization (D7a), extraction prompt (D7b), YAML parsing/validation (D7c), generator flow (D7c), cache integration (D7c), processor updates (D7d), config defaults (D7e).
- [x] **Coverage** -- AC 15: >= 90%. Old `FileDescription` and `to_markdown` tests removed but replaced by more comprehensive `DocumentRecord`, `to_yaml`, `parse_document_record`, and `extract_metadata` tests. Existing `summarize_file`, `classify_folder`, graph, and delta tests remain unchanged.
- [x] **No regressions** -- Existing `summarize_file` and all `_summarize_*` methods preserved. `classify_folder` unchanged. Graph and delta modules untouched except loop prevention (which uses configurable filename already).

**Independent Validation Status: READY_FOR_DEV**

## Reference Documents

- `documentation/Generic Document Extraction System.md` -- Full design specification for the two-layer schema, extraction prompt, and YAML format
- `CLAUDE.md/Architecture` -- Three-layer design, dependency injection, module responsibilities
- `CLAUDE.md/Constants` -- Named constants policy (`DOC_TYPES` as frozenset)
- `CLAUDE.md/Configuration Management` -- Config defaults, `*_from_config()` factory pattern
- `CLAUDE.md/Code Style` -- Ruff rules (E, F, I, W, UP, B, SIM, RUF), Pyright basic, Google-style docstrings, line length 100
- `CLAUDE.md/Testing` -- Mock patterns, coverage target >= 90%, tests mirror `src/` structure
- `iterations/it-8.in.md` -- Predecessor iteration (image summarization)
