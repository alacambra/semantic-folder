"""Unit tests for description/generator.py — AI-powered description generation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from semantic_folder.description.cache import SummaryCache
from semantic_folder.description.generator import (
    _get_or_generate_summary,
    generate_description,
)
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


def _make_cache_mock() -> MagicMock:
    """Return a mock SummaryCache."""
    return MagicMock(spec=SummaryCache)


# ---------------------------------------------------------------------------
# generate_description tests (no cache)
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


# ---------------------------------------------------------------------------
# generate_description tests (with cache)
# ---------------------------------------------------------------------------


class TestGenerateDescriptionWithCache:
    def test_without_cache_calls_summarize_for_all_files(self) -> None:
        """Backward compat: cache=None still calls summarize_file() for every file."""
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt", "b.txt"])
        describer = _make_describer_mock()
        result = generate_description(
            listing, describer, {"a.txt": b"aaa", "b.txt": b"bbb"}, cache=None
        )
        assert describer.summarize_file.call_count == 2
        assert len(result.files) == 2

    def test_cache_hit_skips_summarize_file(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = "Cached summary of a.txt"

        result = generate_description(listing, describer, {"a.txt": b"content"}, cache=cache)

        describer.summarize_file.assert_not_called()
        assert result.files[0].summary == "Cached summary of a.txt"

    def test_cache_miss_calls_summarize_and_stores(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = None

        result = generate_description(listing, describer, {"a.txt": b"content"}, cache=cache)

        describer.summarize_file.assert_called_once_with("a.txt", b"content")
        cache.put.assert_called_once()
        assert result.files[0].summary == "Summary of a.txt"

    def test_does_not_cache_empty_content(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["empty.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()

        generate_description(listing, describer, {"empty.txt": b""}, cache=cache)

        # Empty content bypasses cache entirely
        cache.get.assert_not_called()
        cache.put.assert_not_called()
        describer.summarize_file.assert_called_once_with("empty.txt", b"")

    def test_classify_folder_always_called_with_cache(self) -> None:
        """classify_folder() is never cached — it must be called every time."""
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = "cached"

        generate_description(listing, describer, {"a.txt": b"data"}, cache=cache)

        describer.classify_folder.assert_called_once_with("/p", ["a.txt"])

    def test_mixed_cache_hits_and_misses(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["cached.txt", "fresh.txt"],
        )
        describer = _make_describer_mock()
        cache = _make_cache_mock()

        # First file is a hit, second is a miss
        cache.get.side_effect = ["Cached summary", None]

        result = generate_description(
            listing,
            describer,
            {"cached.txt": b"old content", "fresh.txt": b"new content"},
            cache=cache,
        )

        # Only fresh.txt should trigger summarize_file
        describer.summarize_file.assert_called_once_with("fresh.txt", b"new content")
        assert result.files[0].summary == "Cached summary"
        assert result.files[1].summary == "Summary of fresh.txt"


# ---------------------------------------------------------------------------
# _get_or_generate_summary tests
# ---------------------------------------------------------------------------


class TestGetOrGenerateSummary:
    def test_no_cache_calls_summarize_directly(self) -> None:
        describer = _make_describer_mock()
        result = _get_or_generate_summary("a.txt", b"content", describer, cache=None)
        describer.summarize_file.assert_called_once_with("a.txt", b"content")
        assert result == "Summary of a.txt"

    def test_cache_hit_returns_cached_and_skips_llm(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = "From cache"

        result = _get_or_generate_summary("a.txt", b"content", describer, cache)

        describer.summarize_file.assert_not_called()
        cache.put.assert_not_called()
        assert result == "From cache"

    def test_cache_miss_calls_llm_and_stores(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = None

        result = _get_or_generate_summary("a.txt", b"content", describer, cache)

        describer.summarize_file.assert_called_once_with("a.txt", b"content")
        content_hash = SummaryCache.content_hash(b"content")
        cache.put.assert_called_once_with(content_hash, "Summary of a.txt")
        assert result == "Summary of a.txt"

    def test_empty_content_bypasses_cache(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()

        result = _get_or_generate_summary("a.txt", b"", describer, cache)

        cache.get.assert_not_called()
        cache.put.assert_not_called()
        describer.summarize_file.assert_called_once_with("a.txt", b"")
        assert result == "Summary of a.txt"

    def test_computes_correct_content_hash(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = None

        content = b"specific content bytes"
        _get_or_generate_summary("a.txt", content, describer, cache)

        expected_hash = SummaryCache.content_hash(content)
        cache.get.assert_called_once_with(expected_hash)
