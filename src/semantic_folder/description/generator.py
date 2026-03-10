"""AI-powered description generator for folder contents."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from semantic_folder.description.cache import SummaryCache
from semantic_folder.description.models import (
    DOC_TYPES,
    DocumentRecord,
    FolderDescription,
    Parties,
)

if TYPE_CHECKING:
    from semantic_folder.description.describer import AnthropicDescriber
    from semantic_folder.graph.models import FolderListing

logger = logging.getLogger(__name__)


def generate_description(
    listing: FolderListing,
    describer: AnthropicDescriber,
    file_contents: dict[str, bytes],
    cache: SummaryCache | None = None,
) -> FolderDescription:
    """Generate a folder description using AI.

    Args:
        listing: FolderListing from the folder enumeration step.
        describer: AnthropicDescriber instance for AI generation.
        file_contents: Mapping of filename to raw file content bytes.
        cache: Optional SummaryCache for skipping redundant LLM calls.

    Returns:
        FolderDescription with AI-generated structured document records.
    """
    folder_type = describer.classify_folder(listing.folder_path, listing.files)
    documents: list[DocumentRecord] = []
    for name in listing.files:
        content = file_contents.get(name, b"")
        try:
            json_str = _get_or_extract_metadata(name, content, describer, cache)
            record = parse_document_record(json_str, name)
        except (ValueError, Exception):
            logger.exception("[generate_description] extraction failed; filename:%s", name)
            record = DocumentRecord(
                file=name,
                doc_type="other",
                doc_lang="und",
                date="",
                parties=Parties(from_="unknown"),
                summary="[extraction failed]",
            )
        documents.append(record)

    # Infer period from document dates
    period = _infer_period(documents)

    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type=folder_type,
        documents=documents,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
        period=period,
    )


def _infer_period(documents: list[DocumentRecord]) -> str | None:
    """Infer a common period from document dates.

    If all non-empty dates share the same YYYY-MM, return that as
    the period string. Otherwise return None.
    """
    months: set[str] = set()
    for doc in documents:
        if doc.date and len(doc.date) >= 7:
            months.add(doc.date[:7])
    if len(months) == 1:
        return months.pop()
    return None


_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json|ya?ml)?\s*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    match = _MARKDOWN_FENCE_RE.search(text)
    return match.group(1) if match else text


def parse_document_record(json_str: str, filename: str) -> DocumentRecord:
    """Parse a raw JSON string from the LLM into a DocumentRecord.

    Validates doc_type against DOC_TYPES. Falls back to "other" for
    unknown types. Handles missing or malformed fields gracefully.

    Args:
        json_str: Raw JSON string returned by the LLM.
        filename: Original filename (used as fallback for the file field).

    Returns:
        Validated DocumentRecord instance.

    Raises:
        ValueError: If the JSON cannot be parsed at all.
    """
    cleaned = _strip_markdown_fences(json_str)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")

    doc_type = data.get("doc_type", "other")
    if doc_type not in DOC_TYPES:
        doc_type = "other"

    # Parse parties
    parties_raw = data.get("parties")
    if isinstance(parties_raw, dict):
        parties = Parties(
            from_=str(parties_raw.get("from", "unknown")),
            to=parties_raw.get("to"),
        )
    else:
        parties = Parties(from_="unknown")

    # Parse tags
    tags_raw = data.get("tags")
    tags = tags_raw if isinstance(tags_raw, list) else []

    # Parse facts
    facts_raw = data.get("facts")
    facts = facts_raw if isinstance(facts_raw, dict) else {}

    return DocumentRecord(
        file=str(data.get("file", filename)),
        doc_type=doc_type,
        doc_lang=str(data.get("doc_lang", "und")),
        date=str(data.get("date", "")),
        parties=parties,
        summary=str(data.get("summary", "")),
        tags=tags,
        facts=facts,
    )


def _get_or_extract_metadata(
    filename: str,
    content: bytes,
    describer: AnthropicDescriber,
    cache: SummaryCache | None,
) -> str:
    """Return cached metadata JSON or extract fresh metadata.

    Same cache pattern as the old _get_or_generate_summary: check cache
    by content hash, call describer.extract_metadata on miss, store result.

    Args:
        filename: Name of the file.
        content: Raw file content bytes.
        describer: AnthropicDescriber for extracting new metadata.
        cache: Optional cache to check/populate.

    Returns:
        Raw JSON metadata string.
    """
    if cache is not None and content:
        content_hash = SummaryCache.content_hash(content)
        cached = cache.get(content_hash)
        if cached is not None:
            return cached
        result = describer.extract_metadata(filename, content)
        cache.put(content_hash, result)
        return result
    return describer.extract_metadata(filename, content)
