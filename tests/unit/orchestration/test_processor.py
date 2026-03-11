"""Unit tests for orchestration/processor.py — FolderProcessor behaviour."""

from unittest.mock import MagicMock, patch

from semantic_folder.description.cache import SummaryCache
from semantic_folder.graph.models import DriveItem, FolderListing
from semantic_folder.orchestration.processor import (
    FolderProcessor,
    folder_processor_from_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processor() -> tuple[FolderProcessor, MagicMock, MagicMock, MagicMock]:
    """Return (processor, mock_delta_processor, mock_graph_client, mock_describer)."""
    mock_delta = MagicMock()
    mock_graph = MagicMock()
    mock_describer = MagicMock()
    mock_describer.classify_folder.return_value = "project-docs"
    mock_describer.extract_metadata.side_effect = lambda name, content: (
        f'{{"file": "{name}", "doc_type": "other", "doc_lang": "en", '
        f'"date": "2026-01-01", "parties": {{"from": "unknown", "to": null}}, '
        f'"summary": "Mock extraction of {name}", "tags": ["test"], "facts": {{}}}}'
    )
    processor = FolderProcessor(
        delta_processor=mock_delta,
        graph_client=mock_graph,
        drive_user="testuser@contoso.onmicrosoft.com",
        describer=mock_describer,
    )
    return processor, mock_delta, mock_graph, mock_describer


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
        processor, _, _, _ = _make_processor()

        items = [
            _file_item(id="i1", parent_id="p1"),
            _file_item(id="i2", parent_id="p2"),
            _file_item(id="i3", parent_id="p1"),  # duplicate parent
        ]

        result = processor.resolve_folders(items)

        assert sorted(result) == ["p1", "p2"]

    def test_excludes_folder_items(self) -> None:
        processor, _, _, _ = _make_processor()

        items = [
            _folder_item(id="f1", parent_id="root"),
            _file_item(id="i1", parent_id="p1"),
        ]

        result = processor.resolve_folders(items)

        assert result == ["p1"]
        assert "root" not in result

    def test_excludes_deleted_items(self) -> None:
        processor, _, _, _ = _make_processor()

        items = [
            _deleted_item(id="d1", parent_id="p-deleted"),
            _file_item(id="i1", parent_id="p-alive"),
        ]

        result = processor.resolve_folders(items)

        assert result == ["p-alive"]
        assert "p-deleted" not in result

    def test_returns_empty_list_for_no_file_items(self) -> None:
        processor, _, _, _ = _make_processor()

        items = [
            _folder_item(),
            _deleted_item(),
        ]

        result = processor.resolve_folders(items)

        assert result == []

    def test_preserves_insertion_order(self) -> None:
        processor, _, _, _ = _make_processor()

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
        processor, _, mock_graph, _ = _make_processor()

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

    def test_populates_file_ids_from_graph_response(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

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

        assert result.file_ids == ["child-1", "child-2"]

    def test_excludes_sub_folders_from_file_ids(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

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
        assert result.file_ids == ["file-1"]

    def test_excludes_sub_folders_from_files_list(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

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
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {"value": []}

        processor.list_folder("specific-folder-id")

        mock_graph.get.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/specific-folder-id/children"
        )

    def test_empty_folder_returns_empty_files_list(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {"value": []}

        result = processor.list_folder("empty-folder")

        assert result.files == []
        assert result.file_ids == []
        assert result.folder_path == ""

    def test_excludes_description_files_from_listing(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "f1",
                    "name": "invoice.pdf",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "f2",
                    "name": "folder_description.yaml",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "f3",
                    "name": "folder_description.md",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
                {
                    "id": "f4",
                    "name": "folder_description.json",
                    "parentReference": {"id": "p1", "path": "/drive/root:/Docs"},
                },
            ]
        }

        result = processor.list_folder("p1")

        assert result.files == ["invoice.pdf"]
        assert result.file_ids == ["f1"]

    def test_folder_path_from_first_child_parent_reference(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

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
# read_file_contents tests
# ---------------------------------------------------------------------------


class TestReadFileContents:
    def test_calls_get_content_for_each_file_id(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.return_value = b"file data"

        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["a.txt", "b.txt"],
            file_ids=["id-a", "id-b"],
        )

        processor.read_file_contents(listing)

        assert mock_graph.get_content.call_count == 2
        mock_graph.get_content.assert_any_call(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/id-a/content"
        )
        mock_graph.get_content.assert_any_call(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/id-b/content"
        )

    def test_returns_mapping_of_filename_to_bytes(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.side_effect = [b"content-a", b"content-b"]

        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["a.txt", "b.txt"],
            file_ids=["id-a", "id-b"],
        )

        result = processor.read_file_contents(listing)

        assert result == {"a.txt": b"content-a", "b.txt": b"content-b"}

    def test_returns_empty_bytes_on_download_failure(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.side_effect = Exception("Network error")

        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["fail.txt"],
            file_ids=["id-fail"],
        )

        result = processor.read_file_contents(listing)

        assert result == {"fail.txt": b""}

    def test_logs_warning_on_download_failure(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.side_effect = Exception("Network error")

        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["fail.txt"],
            file_ids=["id-fail"],
        )

        with patch("semantic_folder.orchestration.processor.logger") as mock_logger:
            processor.read_file_contents(listing)
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "fail.txt" in str(call_args)
            assert "id-fail" in str(call_args)

    def test_empty_listing_returns_empty_dict(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        listing = FolderListing(folder_id="f1", folder_path="/p")

        result = processor.read_file_contents(listing)

        assert result == {}
        mock_graph.get_content.assert_not_called()


# ---------------------------------------------------------------------------
# process_delta tests
# ---------------------------------------------------------------------------


class TestProcessDelta:
    def test_calls_components_in_correct_order(self) -> None:
        processor, mock_delta, mock_graph, _ = _make_processor()

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
        mock_graph.get_content.return_value = b"file data"

        results = processor.process_delta()

        mock_delta.get_delta_token.assert_called_once()
        mock_delta.fetch_changes.assert_called_once_with("existing-token")
        mock_graph.get.assert_any_call(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/folder-abc/children"
        )
        mock_delta.save_delta_token.assert_called_once_with("new-token")
        assert len(results) == 1
        assert results[0].folder_id == "folder-abc"

    def test_saves_token_after_listing_all_folders(self) -> None:
        """Token must be saved even when multiple folders are processed."""
        processor, mock_delta, mock_graph, _ = _make_processor()

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
        processor, mock_delta, _, _ = _make_processor()

        mock_delta.get_delta_token.return_value = "tok"
        mock_delta.fetch_changes.return_value = ([], "tok-new")

        results = processor.process_delta()

        assert results == []

    def test_correct_folder_listing_contents(self) -> None:
        """FolderListing must carry correct path and files from Graph response."""
        processor, mock_delta, mock_graph, _ = _make_processor()

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
        mock_graph.get_content.return_value = b"data"

        results = processor.process_delta()

        assert len(results) == 1
        listing = results[0]
        assert listing.folder_id == "folder-xyz"
        assert listing.folder_path == "/drive/root:/My Folder"
        assert sorted(listing.files) == ["data.csv", "readme.md"]

    def test_saves_token_before_processing_folders(self) -> None:
        """Delta token must be saved before folder processing begins."""
        processor, mock_delta, mock_graph, _ = _make_processor()

        mock_delta.get_delta_token.return_value = "tok"
        mock_delta.fetch_changes.return_value = (
            [_file_item(parent_id="folder-1")],
            "new-tok",
        )
        mock_graph.get.return_value = {
            "value": [
                {
                    "id": "c1",
                    "name": "file.txt",
                    "parentReference": {"id": "folder-1", "path": "/drive/root:/Docs"},
                }
            ]
        }
        mock_graph.get_content.return_value = b"data"

        call_order: list[str] = []
        mock_graph.put_content.side_effect = lambda *a, **kw: call_order.append("put_content")
        mock_delta.save_delta_token.side_effect = lambda *a, **kw: call_order.append(
            "save_delta_token"
        )

        processor.process_delta()

        assert call_order[0] == "save_delta_token"
        assert all(c == "put_content" for c in call_order[1:])

    def test_uploads_description_for_each_listing(self) -> None:
        """Each folder listing should trigger a put_content call."""
        processor, mock_delta, mock_graph, _ = _make_processor()

        mock_delta.get_delta_token.return_value = None
        mock_delta.fetch_changes.return_value = (
            [
                _file_item(id="i1", parent_id="p1"),
                _file_item(id="i2", parent_id="p2"),
            ],
            "tok",
        )
        mock_graph.get.return_value = {"value": []}

        processor.process_delta()

        assert mock_graph.put_content.call_count == 3

    def test_continues_on_folder_failure(self) -> None:
        """A failure processing one folder should not stop the rest."""
        processor, mock_delta, mock_graph, _ = _make_processor()

        mock_delta.get_delta_token.return_value = None
        mock_delta.fetch_changes.return_value = (
            [
                _file_item(id="i1", parent_id="p1"),
                _file_item(id="i2", parent_id="p2"),
            ],
            "tok",
        )

        call_count = 0

        def get_side_effect(path: str, **kwargs: object) -> dict:  # type: ignore[type-arg]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Graph API error")
            return {"value": []}

        mock_graph.get.side_effect = get_side_effect

        results = processor.process_delta()

        assert len(results) == 1
        mock_delta.save_delta_token.assert_called_once_with("tok")


# ---------------------------------------------------------------------------
# upload_description tests
# ---------------------------------------------------------------------------


class TestUploadDescription:
    def test_calls_put_content_with_correct_path(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.return_value = b"content"

        listing = FolderListing(
            folder_id="folder-abc",
            folder_path="/drive/root:/Docs",
            files=["report.pdf"],
            file_ids=["id-report"],
        )

        processor.upload_description(listing)

        mock_graph.put_content.assert_called_once()
        call_args = mock_graph.put_content.call_args
        path = call_args[0][0]
        assert path == (
            "/users/testuser@contoso.onmicrosoft.com/drive/items/folder-abc"
            ":/folder_description.json:/content"
        )

    def test_reads_file_contents_then_generates_description(self) -> None:
        processor, _, mock_graph, mock_describer = _make_processor()
        mock_graph.get_content.side_effect = [b"report data"]

        listing = FolderListing(
            folder_id="f1",
            folder_path="/drive/root:/Docs",
            files=["report.pdf"],
            file_ids=["id-report"],
        )

        processor.upload_description(listing)

        # Verify get_content was called for the file
        mock_graph.get_content.assert_called_once_with(
            "/users/testuser@contoso.onmicrosoft.com/drive/items/id-report/content"
        )
        # Verify describer was called with the content
        mock_describer.extract_metadata.assert_called_once_with("report.pdf", b"report data")
        mock_describer.classify_folder.assert_called_once()

    def test_uses_configured_filename(self) -> None:
        mock_delta = MagicMock()
        mock_graph = MagicMock()
        mock_describer = MagicMock()
        mock_describer.classify_folder.return_value = "docs"
        mock_describer.extract_metadata.return_value = '{"doc_type": "other"}'
        processor = FolderProcessor(
            delta_processor=mock_delta,
            graph_client=mock_graph,
            drive_user="user@example.com",
            describer=mock_describer,
            folder_description_filename="custom_desc.md",
        )

        listing = FolderListing(folder_id="f1", folder_path="/p", files=[], file_ids=[])

        processor.upload_description(listing)

        path = mock_graph.put_content.call_args[0][0]
        assert ":/custom_desc.md:/content" in path

    def test_content_is_utf8_encoded_json(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get_content.return_value = b"data"

        listing = FolderListing(
            folder_id="f1",
            folder_path="/drive/root:/Test",
            files=["a.txt"],
            file_ids=["id-a"],
        )

        processor.upload_description(listing)

        content = mock_graph.put_content.call_args[0][1]
        assert isinstance(content, bytes)
        text = content.decode("utf-8")
        assert '"folder"' in text
        assert '"documents"' in text


# ---------------------------------------------------------------------------
# folder_processor_from_config tests
# ---------------------------------------------------------------------------


class TestFolderProcessorAcceptsCache:
    def test_accepts_optional_cache_parameter(self) -> None:
        mock_cache = MagicMock(spec=SummaryCache)
        processor = FolderProcessor(
            delta_processor=MagicMock(),
            graph_client=MagicMock(),
            drive_user="user@contoso.com",
            describer=MagicMock(),
            cache=mock_cache,
        )
        assert processor._cache is mock_cache

    def test_cache_defaults_to_none(self) -> None:
        processor = FolderProcessor(
            delta_processor=MagicMock(),
            graph_client=MagicMock(),
            drive_user="user@contoso.com",
            describer=MagicMock(),
        )
        assert processor._cache is None


class TestUploadDescriptionWithCache:
    @patch("semantic_folder.orchestration.processor.generate_description")
    def test_passes_cache_to_generate_description(self, mock_gen_desc: MagicMock) -> None:
        mock_cache = MagicMock(spec=SummaryCache)
        mock_graph = MagicMock()
        mock_graph.get_content.return_value = b"data"
        mock_describer = MagicMock()
        mock_describer.classify_folder.return_value = "docs"
        mock_describer.extract_metadata.return_value = '{"doc_type": "other"}'

        # Set up generate_description mock return
        mock_desc = MagicMock()
        mock_desc.to_json.return_value = '{"folder": {"path": "/p"}}\n'
        mock_desc.documents = []
        mock_gen_desc.return_value = mock_desc

        processor = FolderProcessor(
            delta_processor=MagicMock(),
            graph_client=mock_graph,
            drive_user="user@contoso.com",
            describer=mock_describer,
            cache=mock_cache,
        )
        listing = FolderListing(
            folder_id="f1", folder_path="/p", files=["a.txt"], file_ids=["id-a"]
        )

        processor.upload_description(listing)

        mock_gen_desc.assert_called_once()
        call_kwargs = mock_gen_desc.call_args
        # Fourth positional arg (or keyword) is the cache
        assert call_kwargs[0][3] is mock_cache

    @patch("semantic_folder.orchestration.processor.generate_description")
    def test_passes_none_cache_when_not_configured(self, mock_gen_desc: MagicMock) -> None:
        mock_graph = MagicMock()
        mock_graph.get_content.return_value = b"data"

        mock_desc = MagicMock()
        mock_desc.to_json.return_value = '{"folder": {"path": "/p"}}\n'
        mock_desc.documents = []
        mock_gen_desc.return_value = mock_desc

        processor = FolderProcessor(
            delta_processor=MagicMock(),
            graph_client=mock_graph,
            drive_user="user@contoso.com",
            describer=MagicMock(),
        )
        listing = FolderListing(
            folder_id="f1", folder_path="/p", files=["a.txt"], file_ids=["id-a"]
        )

        processor.upload_description(listing)

        mock_gen_desc.assert_called_once()
        call_kwargs = mock_gen_desc.call_args
        assert call_kwargs[0][3] is None


# ---------------------------------------------------------------------------
# update_index tests
# ---------------------------------------------------------------------------


class TestUpdateIndex:
    def test_searches_for_description_files(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {"value": []}

        processor.update_index()

        mock_graph.get.assert_called_once()
        call_path = mock_graph.get.call_args[0][0]
        assert "search(q='folder_description.json')" in call_path

    def test_builds_index_from_found_descriptions(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {
            "value": [
                {"id": "desc-1", "name": "folder_description.json"},
            ]
        }
        mock_graph.get_content.return_value = (
            b'{"folder": {"path": "/drive/root:/Docs", "type": "project-docs"},'
            b' "overview": {"document_count": 2, "total_amount_eur": 100.0}}'
        )

        processor.update_index()

        # Should upload the index
        assert mock_graph.put_content.call_count == 1
        call_args = mock_graph.put_content.call_args
        path = call_args[0][0]
        assert "onedrive_index.json" in path

        import json

        content = json.loads(call_args[0][1].decode("utf-8"))
        assert content["schema_version"] == "1.0"
        assert len(content["folders"]) == 1
        assert content["folders"][0]["path"] == "/drive/root:/Docs"
        assert content["folders"][0]["document_count"] == 2

    def test_filters_non_matching_filenames(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {
            "value": [
                {"id": "desc-1", "name": "folder_description.json"},
                {"id": "desc-2", "name": "old_folder_description.json"},
            ]
        }
        mock_graph.get_content.return_value = (
            b'{"folder": {"path": "/p", "type": "t"}, "overview": {}}'
        )

        processor.update_index()

        # get_content called only for exact match
        mock_graph.get_content.assert_called_once()

    def test_follows_pagination(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.side_effect = [
            {
                "value": [{"id": "d1", "name": "folder_description.json"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
            },
            {
                "value": [{"id": "d2", "name": "folder_description.json"}],
            },
        ]
        mock_graph.get_content.return_value = (
            b'{"folder": {"path": "/p", "type": "t"}, "overview": {"document_count": 1}}'
        )

        processor.update_index()

        assert mock_graph.get.call_count == 2
        assert mock_graph.get_content.call_count == 2

    def test_skips_items_without_id(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {
            "value": [
                {"name": "folder_description.json"},  # no id
            ]
        }

        processor.update_index()

        mock_graph.get_content.assert_not_called()

    def test_continues_on_read_failure(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {
            "value": [
                {"id": "d1", "name": "folder_description.json"},
                {"id": "d2", "name": "folder_description.json"},
            ]
        }
        mock_graph.get_content.side_effect = [
            Exception("read error"),
            b'{"folder": {"path": "/p2", "type": "t"}, "overview": {}}',
        ]

        processor.update_index()

        import json

        content = json.loads(mock_graph.put_content.call_args[0][1].decode("utf-8"))
        assert len(content["folders"]) == 1


# ---------------------------------------------------------------------------
# cleanup_legacy_descriptions tests
# ---------------------------------------------------------------------------


class TestCleanupLegacyDescriptions:
    def test_searches_for_yaml_and_md_files(self) -> None:
        processor, _, mock_graph, _ = _make_processor()
        mock_graph.get.return_value = {"value": []}

        processor.cleanup_legacy_descriptions()

        assert mock_graph.get.call_count == 2
        calls = [c[0][0] for c in mock_graph.get.call_args_list]
        search_queries = [c for c in calls if "search" in c]
        assert len(search_queries) == 2

    def test_deletes_matching_files(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        def _search(path: str) -> dict:
            if "folder_description.yaml" in path:
                return {
                    "value": [
                        {
                            "id": "y1",
                            "name": "folder_description.yaml",
                            "parentReference": {"path": "/drive/root:/Docs"},
                        },
                    ]
                }
            return {"value": []}

        mock_graph.get.side_effect = _search

        result = processor.cleanup_legacy_descriptions()

        mock_graph.delete.assert_called_once()
        delete_path = mock_graph.delete.call_args[0][0]
        assert "y1" in delete_path
        assert len(result) == 1
        assert "folder_description.yaml" in result[0]

    def test_dry_run_does_not_delete(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        def _search(path: str) -> dict:
            if "folder_description.yaml" in path:
                return {
                    "value": [
                        {
                            "id": "y1",
                            "name": "folder_description.yaml",
                            "parentReference": {"path": "/drive/root:/Docs"},
                        },
                    ]
                }
            return {"value": []}

        mock_graph.get.side_effect = _search

        result = processor.cleanup_legacy_descriptions(dry_run=True)

        mock_graph.delete.assert_not_called()
        assert len(result) == 1

    def test_filters_non_matching_names(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        def _search(path: str) -> dict:
            if "folder_description.yaml" in path:
                return {
                    "value": [
                        {
                            "id": "x1",
                            "name": "other_description.yaml",
                            "parentReference": {"path": "/drive/root:/Docs"},
                        },
                    ]
                }
            return {"value": []}

        mock_graph.get.side_effect = _search

        result = processor.cleanup_legacy_descriptions()

        mock_graph.delete.assert_not_called()
        assert result == []

    def test_skips_items_without_id(self) -> None:
        processor, _, mock_graph, _ = _make_processor()

        def _search(path: str) -> dict:
            if "folder_description.yaml" in path:
                return {
                    "value": [
                        {
                            "name": "folder_description.yaml",
                            "parentReference": {"path": "/drive/root:/Docs"},
                        },
                    ]
                }
            return {"value": []}

        mock_graph.get.side_effect = _search

        result = processor.cleanup_legacy_descriptions()

        mock_graph.delete.assert_not_called()
        assert result == []


class TestFolderProcessorFromConfig:
    @patch("semantic_folder.orchestration.processor.summary_cache_from_config")
    @patch("semantic_folder.orchestration.processor.anthropic_describer_from_config")
    @patch("semantic_folder.orchestration.processor.delta_processor_from_config")
    @patch("semantic_folder.orchestration.processor.graph_client_from_config")
    def test_passes_folder_description_filename(
        self,
        mock_gcfc: MagicMock,
        mock_dpfc: MagicMock,
        mock_adfc: MagicMock,
        mock_scfc: MagicMock,
    ) -> None:
        config = MagicMock()
        config.drive_user = "user@example.com"
        config.folder_description_filename = "custom.md"

        processor = folder_processor_from_config(config)

        assert processor._folder_description_filename == "custom.md"

    @patch("semantic_folder.orchestration.processor.summary_cache_from_config")
    @patch("semantic_folder.orchestration.processor.anthropic_describer_from_config")
    @patch("semantic_folder.orchestration.processor.delta_processor_from_config")
    @patch("semantic_folder.orchestration.processor.graph_client_from_config")
    def test_creates_describer_from_config(
        self,
        mock_gcfc: MagicMock,
        mock_dpfc: MagicMock,
        mock_adfc: MagicMock,
        mock_scfc: MagicMock,
    ) -> None:
        config = MagicMock()
        config.drive_user = "user@example.com"
        config.folder_description_filename = "desc.md"

        processor = folder_processor_from_config(config)

        mock_adfc.assert_called_once_with(config)
        assert processor._describer == mock_adfc.return_value

    @patch("semantic_folder.orchestration.processor.summary_cache_from_config")
    @patch("semantic_folder.orchestration.processor.anthropic_describer_from_config")
    @patch("semantic_folder.orchestration.processor.delta_processor_from_config")
    @patch("semantic_folder.orchestration.processor.graph_client_from_config")
    def test_creates_cache_from_config(
        self,
        mock_gcfc: MagicMock,
        mock_dpfc: MagicMock,
        mock_adfc: MagicMock,
        mock_scfc: MagicMock,
    ) -> None:
        config = MagicMock()
        config.drive_user = "user@example.com"
        config.folder_description_filename = "desc.md"

        processor = folder_processor_from_config(config)

        mock_scfc.assert_called_once_with(config)
        assert processor._cache == mock_scfc.return_value
