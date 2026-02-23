---
document_id: IT-7-IN
version: 1.0.0
last_updated: 2026-02-23
status: Ready
purpose: Add Anthropic API rate-limit resilience via SDK retries and inter-request delay
audience: [Developers, reviewers]
dependencies: [IT-6-IN]
review_triggers:
  [
    Rate-limit strategy changes,
    Retry parameter changes,
    Delay mechanism changes,
    Config field additions,
  ]
---

# Iteration 7: Anthropic API Rate-Limit Resilience

## Objective

Add two-layer rate-limit resilience to the Anthropic API integration: (1) configure the SDK's built-in retry mechanism for automatic 429 backoff, and (2) introduce a configurable inter-request delay between consecutive API calls to proactively throttle throughput below the organization's rate limit.

## Motivation

**Business driver:** The application crashes in production with `anthropic.RateLimitError` (HTTP 429) when processing folders with many files. The organization's rate limit is 50,000 input tokens per minute. With approximately 8,200 tokens per file summary call, just 6-7 files in quick succession exceed the limit. There is currently zero retry or rate-limiting logic -- the exception propagates unhandled and kills the entire timer-triggered run, leaving all folders unprocessed.

**How this iteration fulfills it:** Two complementary defenses are added to `AnthropicDescriber`:

1. **SDK built-in retry** -- The `anthropic.Anthropic()` client constructor accepts a `max_retries` parameter (default 2 in the SDK). Setting this to a configurable value (default 3) enables automatic retry with exponential backoff on 429 responses, without any custom retry logic.

2. **Inter-request delay** -- A configurable `time.sleep()` delay (default 1.0 second) is inserted before each Anthropic API call in the describer. This proactively spaces out requests to stay below the rate limit, following the same pattern as the sibling project (smartpreop) which uses `aiolimiter.AsyncLimiter` for RPM-based throttling. Since semantic-folder is synchronous, a simple sleep is the equivalent mechanism.

Together, the delay prevents most 429 errors from occurring, and the SDK retry handles any that slip through due to concurrent usage or burst patterns.

## Architecture Diagram

```text
                     generate_description()
                              |
                         for each file:
                              |
                              v
                  _get_or_generate_summary()
                              |
                    cache miss -> summarize_file()
                                       |
                                       v
                           +------------------------+
                           | AnthropicDescriber     |
                           |                        |
                           |  time.sleep(delay)  <--|-- NEW: inter-request delay
                           |         |              |
                           |         v              |
                           |  _client.messages      |
                           |    .create(...)        |
                           |         |              |
                           |         v              |
                           |  Anthropic SDK         |
                           |  max_retries=3      <--|-- NEW: SDK built-in retry
                           |  (exp. backoff on 429) |
                           +------------------------+
                                       |
                                       v
                              Anthropic API
                          (50k input tokens/min)

    Two-layer defense:
    Layer 1 (proactive):  time.sleep(request_delay) before each call
    Layer 2 (reactive):   SDK retries with exponential backoff on 429
```

## Prerequisites

- All IT-6 prerequisites remain (Azure AD credentials, `AzureWebJobsStorage`, `SF_ANTHROPIC_API_KEY`)
- Anthropic Python SDK >= 0.18.0 (supports `max_retries` parameter on client constructor)

## Scope

### In Scope

1. New `AppConfig` fields: `anthropic_max_retries` (int, default 3), `anthropic_request_delay` (float, default 1.0)
2. New environment variables: `SF_ANTHROPIC_MAX_RETRIES`, `SF_ANTHROPIC_REQUEST_DELAY`
3. Pass `max_retries` to `anthropic.Anthropic()` constructor in `AnthropicDescriber.__init__()`
4. Add `time.sleep(request_delay)` before each `self._client.messages.create()` call in `AnthropicDescriber`
5. Update `anthropic_describer_from_config()` to pass new config fields
6. Unit tests for all new and modified behavior
7. Update `.env.example` with new environment variables

### Out of Scope

- Async rate limiting (project is synchronous)
- RPM-based token bucket / sliding window limiter (simple delay is sufficient for current scale)
- Per-endpoint or per-model rate limit differentiation
- Custom retry logic outside the SDK's built-in mechanism
- Changes to `SummaryCache`, `generate_description()`, or `FolderProcessor` (rate limiting is encapsulated in the describer)
- Circuit breaker or dead-letter patterns
- Infrastructure / Terraform changes

## Deliverables

### D1: Extend `AppConfig` in `src/semantic_folder/config.py`

Add two new optional fields with defaults:

```python
# Domain constants -- defaults provided, overridable via env
anthropic_max_retries: int = 3
anthropic_request_delay: float = 1.0
```

Update `load_config()` to read from environment:

```python
anthropic_max_retries=int(os.environ.get("SF_ANTHROPIC_MAX_RETRIES", "3")),
anthropic_request_delay=float(os.environ.get("SF_ANTHROPIC_REQUEST_DELAY", "1.0")),
```

Update `load_config()` docstring to document the new optional environment variables.

**Design notes:**
- Default `max_retries=3` gives 4 total attempts (1 initial + 3 retries), which is one more than the SDK default (2) -- appropriate for a timer-triggered batch process that runs once daily
- Default `request_delay=1.0` second means ~60 requests per minute, well under any reasonable RPM limit; with ~8,200 tokens per call, this is ~492,000 tokens/minute throughput, but the sequential nature of the loop means actual throughput is lower due to API latency
- Both values are configurable via env vars for tuning without code changes

### D2: Update `AnthropicDescriber` in `src/semantic_folder/description/describer.py`

Modify `__init__` to accept and apply new parameters:

```python
# Named constants for rate-limit defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_DELAY = 1.0

class AnthropicDescriber:

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_file_content_bytes: int = DEFAULT_MAX_FILE_CONTENT_BYTES,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ) -> None:
        """Initialise the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model identifier to use for generation.
            max_file_content_bytes: Max bytes to read per file for summarization.
            max_retries: Max retry attempts for rate-limited requests (SDK built-in).
            request_delay: Seconds to sleep before each API call to throttle throughput.
        """
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=max_retries)
        self._model = model
        self._max_file_content_bytes = max_file_content_bytes
        self._request_delay = request_delay
```

Add `time.sleep(self._request_delay)` before each `self._client.messages.create()` call. There are four call sites:
- `_summarize_text()` -- line 130
- `_summarize_docx()` -- line 159
- `_summarize_pdf()` -- line 180
- `classify_folder()` -- line 233

Each call site gets the same pattern:

```python
if self._request_delay > 0:
    time.sleep(self._request_delay)
message = self._client.messages.create(...)
```

The `if self._request_delay > 0` guard allows disabling the delay by setting it to 0 (useful for tests and development).

Update `anthropic_describer_from_config()`:

```python
def anthropic_describer_from_config(config: AppConfig) -> AnthropicDescriber:
    return AnthropicDescriber(
        api_key=config.anthropic_api_key,
        model=config.anthropic_model,
        max_file_content_bytes=config.max_file_content_bytes,
        max_retries=config.anthropic_max_retries,
        request_delay=config.anthropic_request_delay,
    )
```

**Design notes:**
- `max_retries` is passed directly to the SDK client constructor -- no custom retry logic needed
- `time.sleep()` is called before each API call, not after, ensuring the delay applies even to the first call in a burst
- The `> 0` guard avoids sleeping when delay is 0.0 (development/testing)
- All four API call sites get the delay: `_summarize_text`, `_summarize_docx`, `_summarize_pdf`, and `classify_folder` -- all consume input tokens and contribute to the rate limit
- Import `time` is added to the module imports

### D3: Update `.env.example`

Add the new environment variables with documentation:

```
# Anthropic API
SF_ANTHROPIC_API_KEY=<your-anthropic-api-key>
SF_ANTHROPIC_MODEL=claude-haiku-4-5-20251001
SF_ANTHROPIC_MAX_RETRIES=3
SF_ANTHROPIC_REQUEST_DELAY=1.0
```

### D4: Tests

**`tests/unit/description/test_describer.py`** (updated)

New/updated tests:

- `TestAnthropicDescriberInit::test_creates_client_with_max_retries` -- verify `anthropic.Anthropic()` is called with `max_retries` parameter
- `TestAnthropicDescriberInit::test_creates_client_with_default_max_retries` -- verify default `max_retries=3` when not specified
- `TestAnthropicDescriberInit::test_stores_request_delay` -- verify `_request_delay` attribute is set
- `TestAnthropicDescriberInit::test_default_request_delay` -- verify default `_request_delay=1.0`
- `TestSummarizeFileText::test_sleeps_before_api_call` -- verify `time.sleep(delay)` is called before `messages.create()` with correct delay value
- `TestSummarizeFileText::test_no_sleep_when_delay_is_zero` -- verify no `time.sleep()` call when `request_delay=0.0`
- `TestSummarizeFileDocx::test_sleeps_before_api_call` -- verify delay on docx path
- `TestSummarizeFilePdf::test_sleeps_before_api_call` -- verify delay on pdf path
- `TestClassifyFolder::test_sleeps_before_api_call` -- verify delay on classify path
- `TestAnthropicDescriberFromConfig::test_passes_max_retries_from_config` -- verify factory passes `max_retries`
- `TestAnthropicDescriberFromConfig::test_passes_request_delay_from_config` -- verify factory passes `request_delay`

Existing `TestAnthropicDescriberInit::test_creates_client_with_api_key` must be updated to also assert `max_retries` is passed.

**`tests/unit/config/test_config.py`** (additions)

- `TestAppConfig::test_anthropic_max_retries_has_default` -- verify default value is 3
- `TestAppConfig::test_anthropic_request_delay_has_default` -- verify default value is 1.0
- `TestLoadConfig::test_reads_anthropic_max_retries_from_env` -- verify `SF_ANTHROPIC_MAX_RETRIES` is read and parsed as int
- `TestLoadConfig::test_reads_anthropic_request_delay_from_env` -- verify `SF_ANTHROPIC_REQUEST_DELAY` is read and parsed as float

**Test approach:**
- `time.sleep` is mocked via `@patch("semantic_folder.description.describer.time.sleep")` to avoid actual delays in tests
- Call ordering is verified using `mock.call_args_list` or `mock.assert_called_with()` to ensure sleep happens before the API call
- Existing tests that construct `AnthropicDescriber` directly continue to work since `max_retries` and `request_delay` have defaults

## Acceptance Criteria

1. `make lint` passes -- ruff reports no errors in all new and modified modules
2. `make typecheck` passes -- pyright reports no type errors
3. `make test` runs and all tests pass without real Anthropic credentials
4. `AppConfig` includes `anthropic_max_retries` (default `3`) and `anthropic_request_delay` (default `1.0`)
5. `load_config()` reads `SF_ANTHROPIC_MAX_RETRIES` from env and parses as int
6. `load_config()` reads `SF_ANTHROPIC_REQUEST_DELAY` from env and parses as float
7. `anthropic.Anthropic()` is constructed with `max_retries` from config
8. `time.sleep(request_delay)` is called before each `self._client.messages.create()` call (all 4 call sites)
9. No sleep occurs when `request_delay` is `0.0`
10. `anthropic_describer_from_config()` passes `max_retries` and `request_delay` from config
11. Existing tests continue to pass without modification (backward compatible defaults)
12. Coverage remains at or above 90%

## Pre-Development Review

### Specification Review

**Skills loaded:** Architecture (layer responsibilities, encapsulation of rate-limit logic), Configuration Management (AppConfig pattern, factory functions, env vars), Testing (mocking patterns, time.sleep mocking), Code Style (ruff, pyright, constants, logging).

| Skill | Finding | Status |
|-------|---------|--------|
| Architecture/Encapsulation | Rate-limit logic is entirely within `AnthropicDescriber` -- no changes to `generator.py`, `processor.py`, or `cache.py`. The describer is the single point of contact with the Anthropic API, so rate limiting belongs here. No layer boundary violations. | PASS |
| Architecture/Interface Design | `AnthropicDescriber.__init__` extended with two optional parameters (`max_retries`, `request_delay`) with backward-compatible defaults. No changes to public method signatures (`summarize_file`, `classify_folder`). Non-breaking change. | PASS |
| Configuration Management | Two new optional fields with sensible defaults. `load_config()` reads `SF_ANTHROPIC_MAX_RETRIES` and `SF_ANTHROPIC_REQUEST_DELAY` from env. Factory function `anthropic_describer_from_config()` passes new fields. Only `load_config()` reads `os.environ`. | PASS |
| Configuration Management/Type Safety | `max_retries` parsed as `int()`, `request_delay` parsed as `float()` -- type-safe env var handling consistent with `max_file_content_bytes` pattern. | PASS |
| Constants | `DEFAULT_MAX_RETRIES` and `DEFAULT_REQUEST_DELAY` are named constants in `describer.py`. No magic numbers in constructor defaults or sleep calls. | PASS |
| Testing/Mocking | `time.sleep` mocked via `@patch` to avoid real delays. `anthropic.Anthropic` constructor args verified. Call ordering testable. Existing tests unaffected due to default parameter values. | PASS |
| Code Style | Google-style docstrings updated with new parameters. `import time` added to module imports. Ruff and pyright compatibility maintained. | PASS |

**Specification Review Status: APPROVED**

## Independent Validation

### Readiness Checklist

- [x] Scope clear and bounded -- rate-limit resilience in describer only, no changes to cache/generator/processor
- [x] Deliverables actionable -- exact code changes specified for all files, including constructor signatures and call site modifications
- [x] Acceptance criteria testable -- each criterion maps to a verifiable assertion
- [x] Reference docs identified -- CLAUDE.md patterns (Architecture, Configuration, Testing, Code Style)
- [x] Dependencies satisfied -- IT-6 complete, Anthropic SDK already supports `max_retries`

### Five Pillars

- [x] Interface Contracts defined -- `AnthropicDescriber.__init__` extended signature specified; public methods unchanged; factory function updated
- [x] Data Structures specified -- `AppConfig` fields typed (`int`, `float`) with defaults
- [x] Configuration Formats documented -- `SF_ANTHROPIC_MAX_RETRIES` (int), `SF_ANTHROPIC_REQUEST_DELAY` (float) env vars with defaults
- [x] Behavioral Requirements clear -- sleep before each API call when delay > 0; SDK retries on 429 with exponential backoff; no sleep when delay is 0
- [x] Quality Criteria measurable -- 12 numbered acceptance criteria, all testable

**Independent Validation Status: READY_FOR_DEV**

## Reference Documents

- `CLAUDE.md/Architecture` -- Rate-limit logic encapsulated in `description/describer.py` (infrastructure adapter for Anthropic API); no cross-layer changes
- `CLAUDE.md/Configuration Management` -- Two new optional env vars (`SF_ANTHROPIC_MAX_RETRIES`, `SF_ANTHROPIC_REQUEST_DELAY`) with defaults; factory function `anthropic_describer_from_config()` updated to pass new fields; only `load_config()` reads `os.environ`
- `CLAUDE.md/Constants` -- `DEFAULT_MAX_RETRIES` and `DEFAULT_REQUEST_DELAY` named constants; no magic numbers
- `CLAUDE.md/Testing` -- `time.sleep` mocked; `anthropic.Anthropic` constructor args verified; existing tests unaffected by backward-compatible defaults
- `CLAUDE.md/Code Style` -- Ruff rules, Pyright basic mode, Google-style docstrings, stdlib logging
- `iterations/it-6.in.md` -- Predecessor iteration establishing the summary cache that IT-7's rate limiting protects from 429 errors during cache-miss bursts
