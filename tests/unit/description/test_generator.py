"""Unit tests for description/generator.py — AI-powered description generation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from semantic_folder.description.generator import generate_description
from semantic_folder.description.models import FolderDescription
from semantic_folder.graph.models import FolderListing

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_describer_mock() -> MagicMock:
    """Return a mock AnthropicDescriber."""
    mock = MagicMock()
    mock.classify_folder.return_value = "project-docs"
    mock.summarize_file.side_effect = lambda name, content: f"Summary of {name}"
    return mock


# ---------------------------------------------------------------------------
# generate_description tests
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    def test_returns_folder_description_type(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/drive/root:/Docs", files=["a.pdf"])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {"a.pdf": b"content"})
        assert isinstance(result, FolderDescription)

    def test_folder_path_matches_listing(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/drive/root:/Customers/Acme", files=[])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert result.folder_path == "/drive/root:/Customers/Acme"

    def test_calls_classify_folder_with_correct_args(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/drive/root:/Invoices",
            files=["inv-001.pdf", "inv-002.pdf"],
        )
        describer = _make_describer_mock()
        generate_description(listing, describer, {})
        describer.classify_folder.assert_called_once_with(
            "/drive/root:/Invoices", ["inv-001.pdf", "inv-002.pdf"]
        )

    def test_folder_type_comes_from_describer(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        describer = _make_describer_mock()
        describer.classify_folder.return_value = "invoices"
        result = generate_description(listing, describer, {})
        assert result.folder_type == "invoices"

    def test_calls_summarize_file_once_per_file(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["report.pdf", "budget.xlsx", "notes.txt"],
        )
        describer = _make_describer_mock()
        file_contents = {
            "report.pdf": b"report data",
            "budget.xlsx": b"budget data",
            "notes.txt": b"notes data",
        }
        generate_description(listing, describer, file_contents)
        assert describer.summarize_file.call_count == 3
        describer.summarize_file.assert_any_call("report.pdf", b"report data")
        describer.summarize_file.assert_any_call("budget.xlsx", b"budget data")
        describer.summarize_file.assert_any_call("notes.txt", b"notes data")

    def test_uses_empty_bytes_for_missing_file_content(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["missing.pdf"])
        describer = _make_describer_mock()
        generate_description(listing, describer, {})
        describer.summarize_file.assert_called_once_with("missing.pdf", b"")

    def test_one_file_description_per_file(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["report.pdf", "budget.xlsx", "notes.txt"],
        )
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert len(result.files) == 3

    def test_summary_comes_from_describer(self) -> None:
        listing = FolderListing(
            folder_id="f1", folder_path="/p", files=["SOW_2026.pdf", "invoice.pdf"]
        )
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert result.files[0].filename == "SOW_2026.pdf"
        assert result.files[0].summary == "Summary of SOW_2026.pdf"
        assert result.files[1].filename == "invoice.pdf"
        assert result.files[1].summary == "Summary of invoice.pdf"

    def test_updated_at_is_todays_date(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        with patch("semantic_folder.description.generator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 23, tzinfo=UTC)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = generate_description(listing, describer, {"a.txt": b"data"})
        assert result.updated_at == "2026-02-23"

    def test_empty_files_produces_empty_description_files(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert result.files == []

    def test_empty_files_still_calls_classify_folder(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        describer = _make_describer_mock()
        generate_description(listing, describer, {})
        describer.classify_folder.assert_called_once()

    def test_filenames_preserved_in_order(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["z.txt", "a.txt", "m.txt"])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert [f.filename for f in result.files] == ["z.txt", "a.txt", "m.txt"]
