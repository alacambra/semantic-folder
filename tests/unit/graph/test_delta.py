"""Unit tests for graph/delta.py — DeltaProcessor behaviour."""

from unittest.mock import MagicMock, patch

import pytest

from semantic_folder.graph.delta import DeltaProcessor
from semantic_folder.graph.models import DriveItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processor() -> tuple[DeltaProcessor, MagicMock, MagicMock]:
    """Return (processor, mock_graph_client, mock_blob_service_client)."""
    mock_graph = MagicMock()
    mock_blob_service = MagicMock()

    with patch(
        "semantic_folder.graph.delta.BlobServiceClient.from_connection_string",
        return_value=mock_blob_service,
    ):
        processor = DeltaProcessor(
            graph_client=mock_graph,
            storage_connection_string="DefaultEndpointsProtocol=https;...",
            drive_user="testuser@contoso.onmicrosoft.com",
            delta_container="semantic-folder-state",
            delta_blob="delta-token/current.txt",
            folder_description_filename="folder_description.md",
        )

    return processor, mock_graph, mock_blob_service


def _make_drive_item(
    *,
    id: str = "item-1",
    name: str = "file.docx",
    parent_id: str = "parent-1",
    parent_path: str = "/drive/root:/Docs",
    is_folder: bool = False,
    is_deleted: bool = False,
) -> DriveItem:
    return DriveItem(
        id=id,
        name=name,
        parent_id=parent_id,
        parent_path=parent_path,
        is_folder=is_folder,
        is_deleted=is_deleted,
    )


# ---------------------------------------------------------------------------
# get_delta_token tests
# ---------------------------------------------------------------------------


class TestGetDeltaToken:
    def test_returns_none_when_blob_not_found(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.side_effect = ResourceNotFoundError("not found")

        result = processor.get_delta_token()

        assert result is None

    def test_returns_stored_token_when_blob_exists(self) -> None:
        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_download = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.return_value = mock_download
        mock_download.readall.return_value = b"tok-abc-123"

        result = processor.get_delta_token()

        assert result == "tok-abc-123"
        mock_blob_service.get_container_client.assert_called_with("semantic-folder-state")
        mock_container.get_blob_client.assert_called_with("delta-token/current.txt")

    def test_uses_correct_container_and_blob_names(self) -> None:
        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_download = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.download_blob.return_value = mock_download
        mock_download.readall.return_value = b"tok"

        processor.get_delta_token()

        mock_blob_service.get_container_client.assert_called_with("semantic-folder-state")
        mock_container.get_blob_client.assert_called_with("delta-token/current.txt")


# ---------------------------------------------------------------------------
# save_delta_token tests
# ---------------------------------------------------------------------------


class TestSaveDeltaToken:
    def test_uploads_token_as_utf8_bytes(self) -> None:
        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob

        processor.save_delta_token("new-token-xyz")

        mock_blob.upload_blob.assert_called_once_with(b"new-token-xyz", overwrite=True)

    def test_creates_container_if_not_exists(self) -> None:
        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container

        processor.save_delta_token("tok")

        mock_container.create_container.assert_called_once()

    def test_continues_if_container_already_exists(self) -> None:
        processor, _, mock_blob_service = _make_processor()

        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob
        # Simulate container already existing (create_container raises).
        mock_container.create_container.side_effect = Exception("ContainerAlreadyExists")

        # Should not raise.
        processor.save_delta_token("tok")
        mock_blob.upload_blob.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_changes tests
# ---------------------------------------------------------------------------


class TestFetchChanges:
    def _delta_response(
        self,
        items: list[dict],  # type: ignore[type-arg]
        delta_link: str = "https://graph.microsoft.com/v1.0/users/testuser@contoso.onmicrosoft.com/drive/root/delta?token=new-tok",
    ) -> dict:  # type: ignore[type-arg]
        return {"value": items, "@odata.deltaLink": delta_link}

    def _file_item(
        self,
        id: str = "i1",
        name: str = "doc.docx",
        parent_id: str = "p1",
        parent_path: str = "/drive/root:/Docs",
    ) -> dict:  # type: ignore[type-arg]
        return {
            "id": id,
            "name": name,
            "parentReference": {"id": parent_id, "path": parent_path},
        }

    def _folder_item(self, id: str = "f1", name: str = "Folder") -> dict:  # type: ignore[type-arg]
        return {
            "id": id,
            "name": name,
            "folder": {},
            "parentReference": {"id": "root", "path": "/drive/root:"},
        }

    def test_fetch_changes_with_no_token_calls_delta_without_param(self) -> None:
        processor, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = self._delta_response([self._file_item()])

        processor.fetch_changes(None)

        mock_graph.get.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/root/delta"
        )

    def test_fetch_changes_with_token_includes_token_param(self) -> None:
        processor, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = self._delta_response([self._file_item()])

        processor.fetch_changes("tok123")

        mock_graph.get.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/root/delta?token=tok123"
        )

    def test_returns_correct_new_token(self) -> None:
        processor, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = self._delta_response(
            [self._file_item()],
            delta_link="https://graph.microsoft.com/v1.0/users/testuser@contoso.onmicrosoft.com/drive/root/delta?token=extracted-tok",
        )

        _, new_token = processor.fetch_changes(None)

        assert new_token == "extracted-tok"

    def test_returns_full_delta_link_when_no_token_param(self) -> None:
        processor, mock_graph, _ = _make_processor()
        # deltaLink without a ?token= query param
        delta_link = "https://graph.microsoft.com/v1.0/users/testuser@contoso.onmicrosoft.com/drive/root/delta"
        mock_graph.get.return_value = self._delta_response(
            [self._file_item()],
            delta_link=delta_link,
        )

        _, new_token = processor.fetch_changes(None)

        assert new_token == delta_link

    def test_maps_raw_items_to_drive_items(self) -> None:
        processor, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = self._delta_response(
            [self._file_item(id="item-99", name="report.xlsx", parent_id="parent-99")]
        )

        items, _ = processor.fetch_changes(None)

        assert len(items) == 1
        assert items[0].id == "item-99"
        assert items[0].name == "report.xlsx"
        assert items[0].parent_id == "parent-99"
        assert items[0].is_folder is False
        assert items[0].is_deleted is False

    def test_maps_folder_item(self) -> None:
        processor, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = self._delta_response([self._folder_item()])

        items, _ = processor.fetch_changes(None)

        assert items[0].is_folder is True

    def test_pagination_follows_next_link(self) -> None:
        processor, mock_graph, _ = _make_processor()

        page1 = {
            "value": [self._file_item(id="i1")],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/testuser@contoso.onmicrosoft.com/drive/root/delta?$skiptoken=abc",
        }
        page2 = self._delta_response(
            [self._file_item(id="i2")],
            delta_link="https://graph.microsoft.com/v1.0/users/testuser@contoso.onmicrosoft.com/drive/root/delta?token=final-tok",
        )
        mock_graph.get.side_effect = [page1, page2]

        items, new_token = processor.fetch_changes(None)

        assert len(items) == 2
        assert mock_graph.get.call_count == 2
        # Second call uses relative path from nextLink.
        second_call_path = mock_graph.get.call_args_list[1][0][0]
        assert second_call_path.startswith(
            "/users/testuser@contoso.onmicrosoft.com/drive/root/delta"
        )
        assert new_token == "final-tok"

    def test_loop_prevention_excludes_folder_description_only_parent(self) -> None:
        processor, mock_graph, _ = _make_processor()

        # Parent p1 only has folder_description.md changed.
        # Parent p2 has a real file changed — should be kept.
        response = self._delta_response(
            [
                {
                    "id": "fd-1",
                    "name": "folder_description.md",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "real-1",
                    "name": "report.docx",
                    "parentReference": {"id": "p2", "path": "/drive/root:/Other"},
                },
            ]
        )
        mock_graph.get.return_value = response

        items, _ = processor.fetch_changes(None)

        parent_ids = {i.parent_id for i in items}
        assert "p1" not in parent_ids, "Loop prevention should exclude p1"
        assert "p2" in parent_ids, "p2 has real changes and must be kept"

    def test_loop_prevention_keeps_parent_with_mixed_changes(self) -> None:
        """A folder where folder_description.md AND another file changed is kept."""
        processor, mock_graph, _ = _make_processor()

        response = self._delta_response(
            [
                {
                    "id": "fd-1",
                    "name": "folder_description.md",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "real-1",
                    "name": "report.docx",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
            ]
        )
        mock_graph.get.return_value = response

        items, _ = processor.fetch_changes(None)

        parent_ids = {i.parent_id for i in items}
        assert "p1" in parent_ids

    def test_raises_value_error_when_no_delta_link(self) -> None:
        processor, mock_graph, _ = _make_processor()
        # Response has neither nextLink nor deltaLink.
        mock_graph.get.return_value = {"value": []}

        with pytest.raises(ValueError, match="deltaLink"):
            processor.fetch_changes(None)

    def test_deleted_item_mapped_correctly(self) -> None:
        processor, mock_graph, _ = _make_processor()

        mock_graph.get.return_value = self._delta_response(
            [
                {
                    "id": "del-1",
                    "name": "gone.docx",
                    "deleted": {},
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                }
            ]
        )

        items, _ = processor.fetch_changes(None)

        assert items[0].is_deleted is True
