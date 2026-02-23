"""Unit tests for orchestration/processor.py — FolderProcessor behaviour."""

from unittest.mock import MagicMock

from semantic_folder.graph.models import DriveItem
from semantic_folder.orchestration.processor import FolderProcessor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processor() -> tuple[FolderProcessor, MagicMock, MagicMock]:
    """Return (processor, mock_delta_processor, mock_graph_client)."""
    mock_delta = MagicMock()
    mock_graph = MagicMock()
    processor = FolderProcessor(
        delta_processor=mock_delta,
        graph_client=mock_graph,
        drive_user="testuser@contoso.onmicrosoft.com",
    )
    return processor, mock_delta, mock_graph


def _file_item(
    id: str = "item-1",
    name: str = "file.docx",
    parent_id: str = "parent-1",
    parent_path: str = "/drive/root:/Docs",
) -> DriveItem:
    return DriveItem(
        id=id,
        name=name,
        parent_id=parent_id,
        parent_path=parent_path,
        is_folder=False,
        is_deleted=False,
    )


def _folder_item(id: str = "folder-1", parent_id: str = "root") -> DriveItem:
    return DriveItem(
        id=id,
        name="Folder",
        parent_id=parent_id,
        parent_path="/drive/root:",
        is_folder=True,
        is_deleted=False,
    )


def _deleted_item(id: str = "del-1", parent_id: str = "parent-1") -> DriveItem:
    return DriveItem(
        id=id,
        name="gone.docx",
        parent_id=parent_id,
        parent_path="/drive/root:/Docs",
        is_folder=False,
        is_deleted=True,
    )


# ---------------------------------------------------------------------------
# resolve_folders tests
# ---------------------------------------------------------------------------


class TestResolveFolders:
    def test_returns_unique_parent_ids_from_file_items(self) -> None:
        processor, _, _ = _make_processor()

        items = [
            _file_item(id="i1", parent_id="p1"),
            _file_item(id="i2", parent_id="p2"),
            _file_item(id="i3", parent_id="p1"),  # duplicate parent
        ]

        result = processor.resolve_folders(items)

        assert sorted(result) == ["p1", "p2"]

    def test_excludes_folder_items(self) -> None:
        processor, _, _ = _make_processor()

        items = [
            _folder_item(id="f1", parent_id="root"),
            _file_item(id="i1", parent_id="p1"),
        ]

        result = processor.resolve_folders(items)

        assert result == ["p1"]
        assert "root" not in result

    def test_excludes_deleted_items(self) -> None:
        processor, _, _ = _make_processor()

        items = [
            _deleted_item(id="d1", parent_id="p-deleted"),
            _file_item(id="i1", parent_id="p-alive"),
        ]

        result = processor.resolve_folders(items)

        assert result == ["p-alive"]
        assert "p-deleted" not in result

    def test_returns_empty_list_for_no_file_items(self) -> None:
        processor, _, _ = _make_processor()

        items = [
            _folder_item(),
            _deleted_item(),
        ]

        result = processor.resolve_folders(items)

        assert result == []

    def test_preserves_insertion_order(self) -> None:
        processor, _, _ = _make_processor()

        items = [
            _file_item(id="i1", parent_id="p3"),
            _file_item(id="i2", parent_id="p1"),
            _file_item(id="i3", parent_id="p2"),
        ]

        result = processor.resolve_folders(items)

        assert result == ["p3", "p1", "p2"]


# ---------------------------------------------------------------------------
# list_folder tests
# ---------------------------------------------------------------------------


class TestListFolder:
    def test_returns_folder_listing_with_file_names(self) -> None:
        processor, _, mock_graph = _make_processor()

        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "child-1",
                    "name": "report.docx",
                    "parentReference": {"id": "folder-99", "path": "/drive/root:/Projects"},
                },
                {
                    "id": "child-2",
                    "name": "notes.txt",
                    "parentReference": {"id": "folder-99", "path": "/drive/root:/Projects"},
                },
            ]
        }

        result = processor.list_folder("folder-99")

        assert result.folder_id == "folder-99"
        assert result.folder_path == "/drive/root:/Projects"
        assert sorted(result.files) == ["notes.txt", "report.docx"]

    def test_excludes_sub_folders_from_files_list(self) -> None:
        processor, _, mock_graph = _make_processor()

        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "sub-1",
                    "name": "SubFolder",
                    "folder": {},
                    "parentReference": {"id": "folder-1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "file-1",
                    "name": "doc.docx",
                    "parentReference": {"id": "folder-1", "path": "/drive/root:/Docs"},
                },
            ]
        }

        result = processor.list_folder("folder-1")

        assert result.files == ["doc.docx"]

    def test_calls_correct_graph_endpoint(self) -> None:
        processor, _, mock_graph = _make_processor()
        mock_graph.get.return_value = {"value": []}

        processor.list_folder("specific-folder-id")

        mock_graph.get.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/specific-folder-id/children"
        )

    def test_empty_folder_returns_empty_files_list(self) -> None:
        processor, _, mock_graph = _make_processor()
        mock_graph.get.return_value = {"value": []}

        result = processor.list_folder("empty-folder")

        assert result.files == []
        assert result.folder_path == ""

    def test_folder_path_from_first_child_parent_reference(self) -> None:
        processor, _, mock_graph = _make_processor()

        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "c1",
                    "name": "file.md",
                    "parentReference": {"id": "f1", "path": "/drive/root:/My Docs"},
                }
            ]
        }

        result = processor.list_folder("f1")

        assert result.folder_path == "/drive/root:/My Docs"


# ---------------------------------------------------------------------------
# process_delta tests
# ---------------------------------------------------------------------------


class TestProcessDelta:
    def test_calls_components_in_correct_order(self) -> None:
        processor, mock_delta, mock_graph = _make_processor()

        mock_delta.get_delta_token.return_value = "existing-token"
        mock_delta.fetch_changes.return_value = (
            [_file_item(parent_id="folder-abc")],
            "new-token",
        )
        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "c1",
                    "name": "file.md",
                    "parentReference": {"id": "folder-abc", "path": "/drive/root:/Docs"},
                }
            ]
        }

        results = processor.process_delta()

        mock_delta.get_delta_token.assert_called_once()
        mock_delta.fetch_changes.assert_called_once_with("existing-token")
        mock_graph.get.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/folder-abc/children"
        )
        mock_delta.save_delta_token.assert_called_once_with("new-token")
        assert len(results) == 1
        assert results[0].folder_id == "folder-abc"

    def test_saves_token_after_listing_all_folders(self) -> None:
        """Token must be saved even when multiple folders are processed."""
        processor, mock_delta, mock_graph = _make_processor()

        mock_delta.get_delta_token.return_value = None
        mock_delta.fetch_changes.return_value = (
            [
                _file_item(id="i1", parent_id="p1"),
                _file_item(id="i2", parent_id="p2"),
            ],
            "token-after",
        )
        mock_graph.get.return_value = {"value": []}

        processor.process_delta()

        mock_delta.save_delta_token.assert_called_once_with("token-after")

    def test_returns_empty_list_when_no_changes(self) -> None:
        processor, mock_delta, _ = _make_processor()

        mock_delta.get_delta_token.return_value = "tok"
        mock_delta.fetch_changes.return_value = ([], "tok-new")

        results = processor.process_delta()

        assert results == []

    def test_correct_folder_listing_contents(self) -> None:
        """FolderListing must carry correct path and files from Graph response."""
        processor, mock_delta, mock_graph = _make_processor()

        mock_delta.get_delta_token.return_value = None
        mock_delta.fetch_changes.return_value = (
            [_file_item(parent_id="folder-xyz")],
            "new-tok",
        )
        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "f1",
                    "name": "readme.md",
                    "parentReference": {"id": "folder-xyz", "path": "/drive/root:/My Folder"},
                },
                {
                    "id": "f2",
                    "name": "data.csv",
                    "parentReference": {"id": "folder-xyz", "path": "/drive/root:/My Folder"},
                },
            ]
        }

        results = processor.process_delta()

        assert len(results) == 1
        listing = results[0]
        assert listing.folder_id == "folder-xyz"
        assert listing.folder_path == "/drive/root:/My Folder"
        assert sorted(listing.files) == ["data.csv", "readme.md"]
