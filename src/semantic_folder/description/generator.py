"""Placeholder description generator for folder contents."""

from __future__ import annotations

from datetime import UTC, datetime

from semantic_folder.description.models import FileDescription, FolderDescription
from semantic_folder.graph.models import FolderListing


def generate_description(listing: FolderListing) -> FolderDescription:
    """Generate a placeholder folder description from a folder listing.

    Creates a FolderDescription with placeholder values for folder_type
    and per-file summaries. These placeholders will be replaced with
    AI-generated content in IT-5.

    Args:
        listing: FolderListing from the folder enumeration step.

    Returns:
        FolderDescription with placeholder content for all files.
    """
    files = [
        FileDescription(
            filename=name,
            summary=f"[{name}-description]",
        )
        for name in listing.files
    ]
    return FolderDescription(
        folder_path=listing.folder_path,
        folder_type="[folder-type]",
        files=files,
        updated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    )
