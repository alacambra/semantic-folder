"""AI-powered description generator for folder contents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from semantic_folder.description.cache import SummaryCache
from semantic_folder.description.models import FileDescription, FolderDescription

if TYPE_CHECKING:
    from semantic_folder.description.describer import AnthropicDescriber
    from semantic_folder.graph.models import FolderListing


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
        FolderDescription with AI-generated content.
    """
    folder_type = describer.classify_folder(listing.folder_path, listing.files)
    files: list[FileDescription] = []
    for name in listing.files:
        content = file_contents.get(name, b"")
        summary = _get_or_generate_summary(name, content, describer, cache)
        files.append(FileDescription(filename=name, summary=summary))
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type=folder_type,
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )


def _get_or_generate_summary(
    filename: str,
    content: bytes,
    describer: AnthropicDescriber,
    cache: SummaryCache | None,
) -> str:
    """Return a cached summary or generate a new one.

    Args:
        filename: Name of the file.
        content: Raw file content bytes.
        describer: AnthropicDescriber for generating new summaries.
        cache: Optional cache to check/populate.

    Returns:
        Summary string (from cache or freshly generated).
    """
    if cache is not None and content:
        content_hash = SummaryCache.content_hash(content)
        cached = cache.get(content_hash)
        if cached is not None:
            return cached
        summary = describer.summarize_file(filename, content)
        cache.put(content_hash, summary)
        return summary
    return describer.summarize_file(filename, content)
