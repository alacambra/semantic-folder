"""Unit tests for description/generator.py — placeholder description generation."""

from datetime import UTC, datetime
from unittest.mock import patch

from semantic_folder.description.generator import generate_description
from semantic_folder.description.models import FolderDescription
from semantic_folder.graph.models import FolderListing

# ---------------------------------------------------------------------------
# generate_description tests
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    def test_returns_folder_description_type(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/drive/root:/Docs", files=["a.pdf"])
        result = generate_description(listing)
        assert isinstance(result, FolderDescription)

    def test_folder_path_matches_listing(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/drive/root:/Customers/Acme", files=[])
        result = generate_description(listing)
        assert result.folder_path == "/drive/root:/Customers/Acme"

    def test_folder_type_is_placeholder(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        result = generate_description(listing)
        assert result.folder_type == "[folder-type]"

    def test_one_file_description_per_file(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["report.pdf", "budget.xlsx", "notes.txt"],
        )
        result = generate_description(listing)
        assert len(result.files) == 3

    def test_summary_matches_placeholder_pattern(self) -> None:
        listing = FolderListing(
            folder_id="f1", folder_path="/p", files=["SOW_2026.pdf", "invoice.pdf"]
        )
        result = generate_description(listing)
        assert result.files[0].filename == "SOW_2026.pdf"
        assert result.files[0].summary == "[SOW_2026.pdf-description]"
        assert result.files[1].filename == "invoice.pdf"
        assert result.files[1].summary == "[invoice.pdf-description]"

    def test_updated_at_is_todays_date(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        with patch("semantic_folder.description.generator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 23, tzinfo=UTC)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = generate_description(listing)
        assert result.updated_at == "2026-02-23"

    def test_empty_files_produces_empty_description_files(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        result = generate_description(listing)
        assert result.files == []

    def test_filenames_preserved_in_order(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["z.txt", "a.txt", "m.txt"])
        result = generate_description(listing)
        assert [f.filename for f in result.files] == ["z.txt", "a.txt", "m.txt"]
