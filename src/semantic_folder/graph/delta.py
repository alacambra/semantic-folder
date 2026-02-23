"""Delta API processor with token persistence in Azure Blob Storage."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from semantic_folder.graph.client import GRAPH_BASE_URL, GraphClient
from semantic_folder.graph.models import (
    FIELD_DELETED,
    FIELD_FOLDER,
    FIELD_ID,
    FIELD_NAME,
    FIELD_PARENT_REFERENCE,
    FIELD_PATH,
    FIELD_TOKEN,
    ODATA_DELTA_LINK,
    ODATA_NEXT_LINK,
    ODATA_VALUE,
    DriveItem,
)

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)


class DeltaProcessor:
    """Processes OneDrive delta API responses and persists the delta token."""

    def __init__(
        self,
        graph_client: GraphClient,
        storage_connection_string: str,
        drive_user: str,
        delta_container: str,
        delta_blob: str,
        folder_description_filename: str,
    ) -> None:
        """Initialise the delta processor.

        Args:
            graph_client: Authenticated GraphClient instance.
            storage_connection_string: Azure Storage connection string for token persistence.
            drive_user: UPN or object ID of the user whose OneDrive to poll
                (e.g. "alice@contoso.onmicrosoft.com"). Required when using app
                permissions (client credentials flow) where /me is not available.
            delta_container: Blob container name for delta token storage.
            delta_blob: Blob path for the delta token file.
            folder_description_filename: Name of the generated description file
                (used for loop prevention).
        """
        self._graph = graph_client
        self._blob_service = BlobServiceClient.from_connection_string(storage_connection_string)
        self._drive_user = drive_user
        self._delta_container = delta_container
        self._delta_blob = delta_blob
        self._folder_description_filename = folder_description_filename

    def get_delta_token(self) -> str | None:
        """Read the persisted delta token from blob storage.

        Returns:
            The stored token string, or None if no token has been saved yet
            (i.e. this is the first run).
        """
        try:
            container_client = self._blob_service.get_container_client(self._delta_container)
            blob_client = container_client.get_blob_client(self._delta_blob)
            data = blob_client.download_blob().readall()
            return data.decode("utf-8")
        except ResourceNotFoundError:
            logger.info("[get_delta_token] no delta token found in blob storage — first run")
            return None

    def save_delta_token(self, token: str) -> None:
        """Write the delta token to blob storage, creating the container if needed.

        Args:
            token: Delta token string from the @odata.deltaLink URL.
        """
        container_client = self._blob_service.get_container_client(self._delta_container)
        try:
            container_client.create_container()
            logger.info(
                "[save_delta_token] created blob container; container:%s",
                self._delta_container,
            )
        except Exception:
            # Container already exists — this is the expected steady-state path.
            pass

        blob_client = container_client.get_blob_client(self._delta_blob)
        blob_client.upload_blob(token.encode("utf-8"), overwrite=True)
        logger.info("[save_delta_token] saved delta token to blob storage")

    def fetch_changes(self, token: str | None) -> tuple[list[DriveItem], str]:
        """Fetch changed drive items from the OneDrive delta API.

        On the first run (token is None), calls /users/{drive_user}/drive/root/delta
        without a token parameter to enumerate all current items and establish a baseline.
        On subsequent runs, calls the same endpoint with ?token=<token> to retrieve
        only the items that changed since the previous run.

        Follows @odata.nextLink pagination until @odata.deltaLink is reached.
        Extracts the new delta token from the @odata.deltaLink URL.

        Applies loop prevention: if the only changed item within a folder is
        folder_description.md (the file this system writes), that folder is
        excluded from the returned list to prevent infinite regeneration loops.

        Args:
            token: Delta token from the previous run, or None for first run.

        Returns:
            A tuple of (items, new_token) where items is the list of changed
            DriveItem objects and new_token is the delta token for the next run.
        """
        base = f"/users/{self._drive_user}/drive/root/delta"
        path = base if token is None else f"{base}?token={token}"

        items: list[DriveItem] = []
        new_token: str | None = None

        # Follow pagination until we reach the deltaLink.
        next_path: str | None = path
        while next_path is not None:
            response = self._graph.get(next_path)

            for raw in response.get(ODATA_VALUE, []):
                item = self._parse_drive_item(raw)
                items.append(item)

            if ODATA_DELTA_LINK in response:
                new_token = self._extract_token_from_delta_link(response[ODATA_DELTA_LINK])
                next_path = None
            elif ODATA_NEXT_LINK in response:
                # Strip the base URL to get a relative path for GraphClient.get().
                next_path = self._relative_path(response[ODATA_NEXT_LINK])
            else:
                # Malformed response — stop pagination to avoid infinite loop.
                logger.warning(
                    "[fetch_changes] delta response has neither nextLink nor deltaLink; stopping"
                )
                next_path = None

        if new_token is None:
            raise ValueError("Delta response did not contain an @odata.deltaLink")

        # Loop prevention: exclude folders where the only change is folder_description.md.
        filtered = self._apply_loop_prevention(items)
        return filtered, new_token

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_drive_item(raw: dict) -> DriveItem:  # type: ignore[type-arg]
        """Map a raw Graph API item dict to a DriveItem dataclass."""
        parent_ref = raw.get(FIELD_PARENT_REFERENCE, {})
        return DriveItem(
            id=raw.get(FIELD_ID, ""),
            name=raw.get(FIELD_NAME, ""),
            parent_id=parent_ref.get(FIELD_ID, ""),
            parent_path=parent_ref.get(FIELD_PATH, ""),
            is_folder=FIELD_FOLDER in raw,
            is_deleted=FIELD_DELETED in raw,
        )

    @staticmethod
    def _extract_token_from_delta_link(delta_link: str) -> str:
        """Extract the token query parameter from an @odata.deltaLink URL."""
        parsed = urlparse(delta_link)
        params = parse_qs(parsed.query)
        tokens = params.get(FIELD_TOKEN, [])
        if tokens:
            return tokens[0]
        # If the token is not a query param, return the full URL as the token
        # (some Graph implementations embed the full URL).
        return delta_link

    @staticmethod
    def _relative_path(full_url: str) -> str:
        """Convert a full Graph API URL to a relative path for GraphClient.get()."""
        prefix = GRAPH_BASE_URL
        if full_url.startswith(prefix):
            return full_url[len(prefix) :]
        # Fall back to returning as-is if it doesn't match expected format.
        return full_url

    def _apply_loop_prevention(self, items: list[DriveItem]) -> list[DriveItem]:
        """Exclude items in folders where only folder_description.md changed.

        Groups items by parent_id. For any parent_id where every changed item
        has the name 'folder_description.md', all items for that parent are
        excluded from the result to prevent the system from triggering itself.

        Args:
            items: All changed DriveItem objects from the delta API.

        Returns:
            Filtered list with loop-inducing items removed.
        """
        # Group by parent_id.
        by_parent: dict[str, list[DriveItem]] = {}
        for item in items:
            by_parent.setdefault(item.parent_id, []).append(item)

        excluded_parents: set[str] = set()
        for parent_id, parent_items in by_parent.items():
            names = {i.name for i in parent_items}
            if names == {self._folder_description_filename}:
                excluded_parents.add(parent_id)
                logger.info(
                    "[_apply_loop_prevention] excluding folder — only description file changed;"
                    " parent_id:%s;filename:%s",
                    parent_id,
                    self._folder_description_filename,
                )

        return [i for i in items if i.parent_id not in excluded_parents]


def delta_processor_from_config(graph_client: GraphClient, config: AppConfig) -> DeltaProcessor:
    """Construct a DeltaProcessor from application configuration.

    Args:
        graph_client: Authenticated GraphClient instance.
        config: Application configuration instance.

    Returns:
        Configured DeltaProcessor instance.
    """
    return DeltaProcessor(
        graph_client=graph_client,
        storage_connection_string=config.storage_connection_string,
        drive_user=config.drive_user,
        delta_container=config.delta_container,
        delta_blob=config.delta_blob,
        folder_description_filename=config.folder_description_filename,
    )
