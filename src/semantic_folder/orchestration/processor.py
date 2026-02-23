"""Folder processor — orchestrates delta processing and folder enumeration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from semantic_folder.graph.client import GraphClient, graph_client_from_config
from semantic_folder.graph.delta import DeltaProcessor, delta_processor_from_config
from semantic_folder.graph.models import (
    FIELD_FOLDER,
    FIELD_NAME,
    FIELD_PARENT_REFERENCE,
    FIELD_PATH,
    ODATA_VALUE,
    DriveItem,
    FolderListing,
)

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)


class FolderProcessor:
    """Orchestrates the full delta-to-folder-listing pipeline."""

    def __init__(
        self,
        delta_processor: DeltaProcessor,
        graph_client: GraphClient,
        drive_user: str,
    ) -> None:
        """Initialise the folder processor.

        Args:
            delta_processor: DeltaProcessor instance for fetching and persisting delta state.
            graph_client: Authenticated GraphClient for enumerating folder children.
            drive_user: UPN or object ID of the OneDrive user (same as DeltaProcessor).
        """
        self._delta = delta_processor
        self._graph = graph_client
        self._drive_user = drive_user

    def resolve_folders(self, items: list[DriveItem]) -> list[str]:
        """Deduplicate parent folder IDs from non-deleted, non-folder items.

        Only file items (not folders themselves, not deleted items) are
        considered when determining which folders need regeneration.

        Args:
            items: List of changed DriveItem objects from the delta API.

        Returns:
            Deduplicated list of parent folder IDs.
        """
        seen: set[str] = set()
        folder_ids: list[str] = []
        for item in items:
            if item.is_folder or item.is_deleted:
                continue
            if item.parent_id not in seen:
                seen.add(item.parent_id)
                folder_ids.append(item.parent_id)
        return folder_ids

    def list_folder(self, folder_id: str) -> FolderListing:
        """Enumerate the children of a OneDrive folder.

        Calls GET /users/{drive_user}/drive/items/{folder_id}/children and maps the response
        to a FolderListing. Only file names are included in the files list
        (sub-folders are excluded).

        Args:
            folder_id: The OneDrive item ID of the folder to enumerate.

        Returns:
            FolderListing with the folder's path and list of file names.
        """
        response = self._graph.get(f"/users/{self._drive_user}/drive/items/{folder_id}/children")
        children = response.get(ODATA_VALUE, [])

        # Extract the folder path from the first child's parentReference.
        folder_path = ""
        if children:
            parent_ref = children[0].get(FIELD_PARENT_REFERENCE, {})
            folder_path = parent_ref.get(FIELD_PATH, "")

        files = [
            child[FIELD_NAME]
            for child in children
            if FIELD_FOLDER not in child and FIELD_NAME in child
        ]

        return FolderListing(folder_id=folder_id, folder_path=folder_path, files=files)

    def process_delta(self) -> list[FolderListing]:
        """Run the full delta-to-folder-listing pipeline.

        Steps:
            1. Retrieve the persisted delta token (None on first run).
            2. Fetch changed items from the delta API.
            3. Resolve unique parent folder IDs from changed file items.
            4. Enumerate each folder's children to build FolderListing objects.
            5. Persist the new delta token.
            6. Return the list of FolderListing objects.

        Returns:
            List of FolderListing objects for folders that need regeneration.
        """
        token = self._delta.get_delta_token()
        items, new_token = self._delta.fetch_changes(token)
        folder_ids = self.resolve_folders(items)
        listings = [self.list_folder(fid) for fid in folder_ids]
        self._delta.save_delta_token(new_token)
        return listings


def folder_processor_from_config(config: AppConfig) -> FolderProcessor:
    """Construct a FolderProcessor from application configuration.

    Creates a GraphClient and DeltaProcessor from the config, then
    wires them into a FolderProcessor.

    Args:
        config: Application configuration instance.

    Returns:
        Configured FolderProcessor instance.
    """
    client = graph_client_from_config(config)
    delta = delta_processor_from_config(client, config)
    return FolderProcessor(
        delta_processor=delta,
        graph_client=client,
        drive_user=config.drive_user,
    )
