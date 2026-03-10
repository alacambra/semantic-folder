"""Folder processor — orchestrates delta processing and folder enumeration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from semantic_folder.description.cache import SummaryCache, summary_cache_from_config
from semantic_folder.description.describer import (
    AnthropicDescriber,
    anthropic_describer_from_config,
)
from semantic_folder.description.generator import generate_description
from semantic_folder.graph.client import GraphClient, graph_client_from_config
from semantic_folder.graph.delta import DeltaProcessor, delta_processor_from_config
from semantic_folder.graph.models import (
    FIELD_FOLDER,
    FIELD_ID,
    FIELD_NAME,
    FIELD_PARENT_REFERENCE,
    FIELD_PATH,
    ODATA_VALUE,
    DriveItem,
    FolderListing,
)

if TYPE_CHECKING:
    from typing import Any

    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)

ODATA_NEXT_LINK = "@odata.nextLink"


class FolderProcessor:
    """Orchestrates the full delta-to-folder-listing pipeline."""

    def __init__(
        self,
        delta_processor: DeltaProcessor,
        graph_client: GraphClient,
        drive_user: str,
        describer: AnthropicDescriber,
        folder_description_filename: str = "folder_description.json",
        cache: SummaryCache | None = None,
        index_filename: str = "onedrive_index.json",
        index_owner: str = "Datamantics UG (Albert Lacambra Basil)",
    ) -> None:
        """Initialise the folder processor.

        Args:
            delta_processor: DeltaProcessor instance for fetching and persisting delta state.
            graph_client: Authenticated GraphClient for enumerating folder children.
            drive_user: UPN or object ID of the OneDrive user (same as DeltaProcessor).
            describer: AnthropicDescriber instance for AI description generation.
            folder_description_filename: Name of the description file to generate and upload.
            cache: Optional SummaryCache for skipping redundant LLM calls.
            index_filename: Name of the root index file to generate.
            index_owner: Owner name to include in the index metadata.
        """
        self._delta = delta_processor
        self._graph = graph_client
        self._drive_user = drive_user
        self._describer = describer
        self._folder_description_filename = folder_description_filename
        self._cache = cache
        self._index_filename = index_filename
        self._index_owner = index_owner

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

        excluded = {
            self._folder_description_filename,
            "folder_description.yaml",
            "folder_description.md",
        }
        files = [
            child[FIELD_NAME]
            for child in children
            if FIELD_FOLDER not in child
            and FIELD_NAME in child
            and child[FIELD_NAME] not in excluded
        ]

        file_ids = [
            child[FIELD_ID]
            for child in children
            if FIELD_FOLDER not in child
            and FIELD_ID in child
            and child.get(FIELD_NAME) not in excluded
        ]

        return FolderListing(
            folder_id=folder_id, folder_path=folder_path, files=files, file_ids=file_ids
        )

    def read_file_contents(self, listing: FolderListing) -> dict[str, bytes]:
        """Download content for each file in a folder listing.

        Args:
            listing: FolderListing with file names and IDs.

        Returns:
            Mapping of filename to raw bytes content.
        """
        contents: dict[str, bytes] = {}
        for name, file_id in zip(listing.files, listing.file_ids, strict=True):
            path = f"/users/{self._drive_user}/drive/items/{file_id}/content"
            try:
                contents[name] = self._graph.get_content(path)
            except Exception:
                logger.warning(
                    "[read_file_contents] failed to read file; filename:%s;file_id:%s",
                    name,
                    file_id,
                )
                contents[name] = b""
        return contents

    def upload_description(self, listing: FolderListing) -> None:
        """Generate an AI-powered description and upload it to OneDrive.

        Reads file content for each file in the listing, generates an
        AI description using the Anthropic describer, serializes the
        result to JSON, and uploads it as ``folder_description.json``
        (or the configured filename) to the folder in OneDrive.

        Args:
            listing: FolderListing for the folder to describe.
        """
        file_contents = self.read_file_contents(listing)
        description = generate_description(listing, self._describer, file_contents, self._cache)
        content = description.to_json().encode("utf-8")
        path = (
            f"/users/{self._drive_user}/drive/items/{listing.folder_id}"
            f":/{self._folder_description_filename}:/content"
        )
        self._graph.put_content(path, content, content_type="application/json")
        logger.info(
            "[upload_description] uploaded description; folder_path:%s;document_count:%d",
            listing.folder_path,
            len(description.documents),
        )

    def update_index(self) -> None:
        """Search for all folder_description.json files, build index, upload.

        Uses the Graph search API to find all folder description files,
        downloads each one, extracts folder and overview data, and
        uploads a root-level index file.

        Follows @odata.nextLink pagination until exhausted.
        """
        logger.info("[update_index] searching for folder description files")
        search_path = (
            f"/users/{self._drive_user}/drive/root/search(q='{self._folder_description_filename}')"
        )

        all_items: list[dict[str, Any]] = []
        response = self._graph.get(search_path)
        all_items.extend(response.get(ODATA_VALUE, []))

        while ODATA_NEXT_LINK in response:
            next_url = response[ODATA_NEXT_LINK]
            # nextLink is a full URL; extract the path portion
            from semantic_folder.graph.client import GRAPH_BASE_URL

            if next_url.startswith(GRAPH_BASE_URL):
                next_path = next_url[len(GRAPH_BASE_URL) :]
            else:
                next_path = next_url
            response = self._graph.get(next_path)
            all_items.extend(response.get(ODATA_VALUE, []))

        # Filter to exact filename matches (search may return partial matches)
        description_items = [
            item for item in all_items if item.get(FIELD_NAME) == self._folder_description_filename
        ]

        folders: list[dict[str, Any]] = []
        for item in description_items:
            item_id = item.get(FIELD_ID)
            if not item_id:
                continue
            try:
                content_bytes = self._graph.get_content(
                    f"/users/{self._drive_user}/drive/items/{item_id}/content"
                )
                data = json.loads(content_bytes)
            except Exception:
                logger.warning(
                    "[update_index] failed to read description; item_id:%s",
                    item_id,
                )
                continue

            folder_data = data.get("folder", {})
            overview_data = data.get("overview", {})
            folders.append(
                {
                    "path": folder_data.get("path", ""),
                    "type": folder_data.get("type", ""),
                    "period": folder_data.get("period"),
                    "document_count": overview_data.get("document_count", 0),
                    "total_eur": overview_data.get("total_amount_eur", 0.0),
                }
            )

        index = {
            "schema_version": "1.0",
            "updated_at": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
            "owner": self._index_owner,
            "folders": folders,
        }

        index_content = (json.dumps(index, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        index_path = f"/users/{self._drive_user}/drive/root:/{self._index_filename}:/content"
        self._graph.put_content(index_path, index_content, content_type="application/json")
        logger.info(
            "[update_index] uploaded index; folder_count:%d",
            len(folders),
        )

    def cleanup_legacy_descriptions(self, *, dry_run: bool = False) -> list[str]:
        """Find and delete all legacy folder_description.yaml/.md files.

        Uses Graph search API to find files, then deletes each via
        DELETE /users/{drive_user}/drive/items/{item_id}.

        Args:
            dry_run: If True, return paths without deleting.

        Returns:
            List of deleted (or would-be-deleted) file paths.
        """
        legacy_names = {"folder_description.yaml", "folder_description.md"}
        deleted_paths: list[str] = []

        for query_name in legacy_names:
            search_path = f"/users/{self._drive_user}/drive/root/search(q='{query_name}')"
            response = self._graph.get(search_path)
            items: list[dict[str, Any]] = list(response.get(ODATA_VALUE, []))

            while ODATA_NEXT_LINK in response:
                next_url = response[ODATA_NEXT_LINK]
                from semantic_folder.graph.client import GRAPH_BASE_URL

                if next_url.startswith(GRAPH_BASE_URL):
                    next_path = next_url[len(GRAPH_BASE_URL) :]
                else:
                    next_path = next_url
                response = self._graph.get(next_path)
                items.extend(response.get(ODATA_VALUE, []))

            for item in items:
                if item.get(FIELD_NAME) != query_name:
                    continue
                item_id = item.get(FIELD_ID)
                if not item_id:
                    continue

                parent_ref = item.get(FIELD_PARENT_REFERENCE, {})
                parent_path = parent_ref.get(FIELD_PATH, "")
                file_path = f"{parent_path}/{query_name}"

                if dry_run:
                    logger.info(
                        "[cleanup_legacy] would delete; path:%s",
                        file_path,
                    )
                else:
                    self._graph.delete(f"/users/{self._drive_user}/drive/items/{item_id}")
                    logger.info(
                        "[cleanup_legacy] deleted; path:%s",
                        file_path,
                    )
                deleted_paths.append(file_path)

        return deleted_paths

    def process_delta(self) -> list[FolderListing]:
        """Run the full delta-to-folder-listing pipeline.

        Steps:
            1. Retrieve the persisted delta token (None on first run).
            2. Fetch changed items from the delta API.
            3. Resolve unique parent folder IDs from changed file items.
            4. Enumerate each folder's children to build FolderListing objects.
            5. Generate and upload a description file for each folder.
            6. Update the root index file.
            7. Persist the new delta token.
            8. Return the list of FolderListing objects.

        Descriptions and index are uploaded before the delta token is saved
        so that a failed upload does not advance the token, allowing retry
        on the next cycle.

        Returns:
            List of FolderListing objects for folders that were processed.
        """
        logger.info("[process_delta] starting delta processing pipeline")
        token = self._delta.get_delta_token()
        items, new_token = self._delta.fetch_changes(token)
        logger.info("[process_delta] fetched changes; item_count:%d", len(items))
        folder_ids = self.resolve_folders(items)
        logger.info("[process_delta] resolved folders; folder_count:%d", len(folder_ids))
        listings = [self.list_folder(fid) for fid in folder_ids]
        for listing in listings:
            self.upload_description(listing)
        if listings:
            self.update_index()
        self._delta.save_delta_token(new_token)
        logger.info("[process_delta] pipeline complete; listing_count:%d", len(listings))
        return listings


def folder_processor_from_config(config: AppConfig) -> FolderProcessor:
    """Construct a FolderProcessor from application configuration.

    Creates a GraphClient, DeltaProcessor, and AnthropicDescriber from the
    config, then wires them into a FolderProcessor.

    Args:
        config: Application configuration instance.

    Returns:
        Configured FolderProcessor instance.
    """
    client = graph_client_from_config(config)
    delta = delta_processor_from_config(client, config)
    describer = anthropic_describer_from_config(config)
    cache = summary_cache_from_config(config)
    return FolderProcessor(
        delta_processor=delta,
        graph_client=client,
        drive_user=config.drive_user,
        describer=describer,
        folder_description_filename=config.folder_description_filename,
        cache=cache,
        index_filename=config.index_filename,
        index_owner=config.index_owner,
    )
