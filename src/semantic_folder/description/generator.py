"""AI-powered description generator for folder contents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from semantic_folder.description.models import FileDescription, FolderDescription

if TYPE_CHECKING:
    from semantic_folder.description.describer import AnthropicDescriber
    from semantic_folder.graph.models import FolderListing


def generate_description(
    listing: FolderListing,
    describer: AnthropicDescriber,
    file_contents: dict[str, bytes],
) -> FolderDescription:
    """Generate a folder description using AI.

    Args:
        listing: FolderListing from the folder enumeration step.
        describer: AnthropicDescriber instance for AI generation.
        file_contents: Mapping of filename to raw file content bytes.

    Returns:
        FolderDescription with AI-generated content.
    """
    folder_type = describer.classify_folder(listing.folder_path, listing.files)
    files = [
        FileDescription(
            filename=name,
            summary=describer.summarize_file(name, file_contents.get(name, b"")),
        )
        for name in listing.files
    ]
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type=folder_type,
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )
