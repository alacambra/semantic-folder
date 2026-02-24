---
document_id: IT-8-IN
version: 1.0.0
last_updated: 2026-02-23
status: Ready
purpose: Add native image summarization via base64-encoded image content blocks
audience: [Developers, reviewers]
dependencies: [IT-7-IN]
review_triggers:
  [
    Image extension list changes,
    Content block format changes,
    New summarize dispatch path,
  ]
---

# Iteration 8: Native Image Summarization

## Objective

Add native image file support to `AnthropicDescriber` so that image files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) are sent to the Anthropic API as base64-encoded image content blocks instead of being decoded as UTF-8 text.

## Motivation

**Business driver:** Image files currently fall through to `_summarize_text`, which decodes binary bytes as UTF-8 with replacement characters. Claude receives garbled text and returns useless summaries like "this is compressed binary data." OneDrive folders commonly contain screenshots, photos, and diagrams that should be summarized visually.

**How this iteration fulfills it:** A new `_summarize_image` method sends images using the Anthropic `"type": "image"` content block with base64 encoding — the same pattern already used for PDFs (`_summarize_pdf`). The file extension is mapped to the correct MIME type, and the dispatch logic in `summarize_file` routes image extensions to the new method.

## Architecture Diagram

```text
                     summarize_file(filename, content)
                              |
                         ext = _file_extension(filename)
                              |
                    +---------+---------+---------+----------+
                    |         |         |         |          |
                  .docx     .pdf     .png/.jpg  .gif/.webp  other
                    |         |         |         |          |
              _summarize   _summarize  _summarize_image     _summarize
              _docx        _pdf       (NEW)                 _text
                                       |
                                       v
                              base64 encode content
                                       |
                                       v
                              messages.create(
                                content=[
                                  {"type": "image",
                                   "source": {"type": "base64",
                                              "media_type": "image/png",
                                              "data": <b64>}},
                                  {"type": "text",
                                   "text": "Summarize..."}
                                ])
```

## Prerequisites

- All IT-7 prerequisites remain
- Anthropic API must support image content blocks (supported since launch)

## Scope

### In Scope

1. New `_IMAGE_EXTENSIONS` mapping constant: extension -> MIME type for `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
2. New `_summarize_image()` method in `AnthropicDescriber` using `"type": "image"` content block
3. Update `summarize_file()` dispatch to route image extensions to `_summarize_image()`
4. Update `summarize_file()` docstring to document image handling
5. Unit tests for the new image summarization path

### Out of Scope

- Changes to `.docx` handling (stays as python-docx text extraction)
- Changes to PDF handling (already uses base64 document blocks)
- Changes to `AppConfig`, `load_config()`, or `.env.example` (no new config needed)
- Changes to `SummaryCache`, `generate_description()`, or `FolderProcessor`
- SVG support (SVG is text-based XML, works fine with `_summarize_text`)
- Image resizing or compression before sending

## Deliverables

### D1: Add image extension mapping in `src/semantic_folder/description/describer.py`

Add a constant mapping image extensions to their MIME types, alongside the existing extension sets:

```python
_IMAGE_EXTENSIONS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
```

### D2: Add `_summarize_image()` method

Mirrors `_summarize_pdf` but uses `"type": "image"` instead of `"type": "document"`:

```python
def _summarize_image(self, filename: str, content: bytes, media_type: str) -> str:
    """Summarize an image file using a base64-encoded image content block."""
    encoded = base64.standard_b64encode(content).decode("ascii")
    logger.info(
        "[summarize_file] sending image block; filename:%s;raw_bytes:%d",
        filename,
        len(content),
    )
    if self._request_delay > 0:
        time.sleep(self._request_delay)
    message = self._client.messages.create(
        model=self._model,
        max_tokens=150,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": encoded,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Summarize this file in one sentence. File name: {filename}",
                    },
                ],
            }
        ],
    )
    result = _extract_text(message)
    logger.info(
        "[summarize_file] received response; filename:%s;summary:%s",
        filename,
        result,
    )
    return result
```

### D3: Update `summarize_file()` dispatch

Add image check before the text fallback:

```python
def summarize_file(self, filename: str, content: bytes) -> str:
    ext = _file_extension(filename)
    if ext in _DOCX_EXTENSIONS:
        return self._summarize_docx(filename, content)
    if ext in _PDF_EXTENSIONS:
        return self._summarize_pdf(filename, content)
    if ext in _IMAGE_EXTENSIONS:
        return self._summarize_image(filename, content, _IMAGE_EXTENSIONS[ext])
    return self._summarize_text(filename, content)
```

Update the docstring to mention image handling.

### D4: Tests in `tests/unit/description/test_describer.py`

New `TestSummarizeFileImage` class:

- `test_sends_base64_image_block` — verify content block structure (`"type": "image"`, correct media_type, base64 data) for `.png`
- `test_jpg_uses_jpeg_media_type` — verify `.jpg` maps to `image/jpeg`
- `test_jpeg_uses_jpeg_media_type` — verify `.jpeg` maps to `image/jpeg`
- `test_case_insensitive_extension` — verify `.PNG` routes to image path
- `test_sleeps_before_api_call` — verify delay on image path
- `test_does_not_truncate_image_content` — verify full image sent (not truncated to `max_file_content_bytes`)

Import `_IMAGE_EXTENSIONS` in test file imports.

## Acceptance Criteria

1. `make lint` passes
2. `make typecheck` passes
3. `make test` passes with all new and existing tests
4. `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` files are sent as `"type": "image"` content blocks
5. Image content is base64-encoded, not truncated
6. Correct MIME type is used for each extension
7. `time.sleep(request_delay)` is called before image API calls
8. Existing text/docx/pdf paths are unaffected
9. Coverage remains at or above 90%

## Pre-Development Review

### Specification Review

| Skill | Finding | Status |
|-------|---------|--------|
| Architecture/Encapsulation | Image handling is entirely within `AnthropicDescriber` — no changes to other modules. Follows existing PDF pattern. | PASS |
| Architecture/Interface Design | No changes to public method signatures. `summarize_file` gains a new dispatch path internally. Non-breaking. | PASS |
| Constants | `_IMAGE_EXTENSIONS` is a named constant dict. No magic strings. | PASS |
| Testing/Mocking | Same patterns as PDF tests. `time.sleep` mocked. `base64` encoding verified. | PASS |
| Code Style | Google-style docstrings. Ruff and pyright compatible. | PASS |

**Specification Review Status: APPROVED**

## Independent Validation

### Readiness Checklist

- [x] Scope clear and bounded — image support in describer only
- [x] Deliverables actionable — exact code changes specified
- [x] Acceptance criteria testable — each criterion maps to a verifiable assertion
- [x] Dependencies satisfied — IT-7 complete, Anthropic SDK supports image blocks

### Five Pillars

- [x] Interface Contracts defined — `_summarize_image` method signature specified; public API unchanged
- [x] Data Structures specified — `_IMAGE_EXTENSIONS` dict typed
- [x] Configuration Formats documented — no new config needed
- [x] Behavioral Requirements clear — base64 encode, correct MIME type, no truncation
- [x] Quality Criteria measurable — 9 numbered acceptance criteria

**Independent Validation Status: READY_FOR_DEV**

## Reference Documents

- `CLAUDE.md/Architecture` — Image handling encapsulated in `description/describer.py`
- `CLAUDE.md/Constants` — `_IMAGE_EXTENSIONS` named constant
- `CLAUDE.md/Testing` — Mock patterns, existing PDF test class as template
- `CLAUDE.md/Code Style` — Ruff rules, Pyright, Google-style docstrings
- `iterations/it-7.in.md` — Predecessor iteration (rate-limit resilience applied to new image call site)
