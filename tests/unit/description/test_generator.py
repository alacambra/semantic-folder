"""Unit tests for description/generator.py -- AI-powered description generation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from semantic_folder.description.cache import SummaryCache
from semantic_folder.description.generator import (
    _get_or_extract_metadata,
    generate_description,
    parse_document_record,
)
from semantic_folder.description.models import DocumentRecord, FolderDescription
from semantic_folder.graph.models import FolderListing

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_YAML = """\
file: "{name}"
doc_type: other
doc_lang: en
date: "2026-01-01"
parties:
  from: unknown
  to: null
summary: Mock extraction of {name}
tags: [test]
facts: {{}}
"""


def _make_yaml(name: str) -> str:
    return _VALID_YAML.format(name=name)


def _make_describer_mock() -> MagicMock:
    """Return a mock AnthropicDescriber."""
    mock = MagicMock()
    mock.classify_folder.return_value = "project-docs"
    mock.extract_metadata.side_effect = lambda name, content: _make_yaml(name)
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

    def test_calls_extract_metadata_once_per_file(self) -> None:
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
        assert describer.extract_metadata.call_count == 3
        describer.extract_metadata.assert_any_call("report.pdf", b"report data")
        describer.extract_metadata.assert_any_call("budget.xlsx", b"budget data")
        describer.extract_metadata.assert_any_call("notes.txt", b"notes data")

    def test_uses_empty_bytes_for_missing_file_content(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["missing.pdf"])
        describer = _make_describer_mock()
        generate_description(listing, describer, {})
        describer.extract_metadata.assert_called_once_with("missing.pdf", b"")

    def test_one_document_record_per_file(self) -> None:
        listing = FolderListing(
            folder_id="f1",
            folder_path="/p",
            files=["report.pdf", "budget.xlsx", "notes.txt"],
        )
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert len(result.documents) == 3

    def test_document_records_from_extraction(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["SOW_2026.pdf"])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {"SOW_2026.pdf": b"data"})
        doc = result.documents[0]
        assert isinstance(doc, DocumentRecord)
        assert doc.file == "SOW_2026.pdf"
        assert doc.doc_type == "other"
        assert doc.doc_lang == "en"
        assert doc.summary == "Mock extraction of SOW_2026.pdf"

    def test_updated_at_is_todays_date(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        with patch("semantic_folder.description.generator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 23, tzinfo=UTC)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = generate_description(listing, describer, {"a.txt": b"data"})
        assert result.updated_at == "2026-02-23"

    def test_empty_files_produces_empty_documents_list(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=[])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert result.documents == []

    def test_filenames_preserved_in_order(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["z.txt", "a.txt", "m.txt"])
        describer = _make_describer_mock()
        result = generate_description(listing, describer, {})
        assert [d.file for d in result.documents] == ["z.txt", "a.txt", "m.txt"]

    def test_extraction_failure_produces_fallback_record(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["bad.pdf"])
        describer = _make_describer_mock()
        describer.extract_metadata.side_effect = RuntimeError("API error")
        result = generate_description(listing, describer, {"bad.pdf": b"data"})
        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc.file == "bad.pdf"
        assert doc.doc_type == "other"
        assert doc.doc_lang == "und"
        assert doc.summary == "[extraction failed]"
        assert doc.parties.from_ == "unknown"


# ---------------------------------------------------------------------------
# generate_description tests (with cache)
# ---------------------------------------------------------------------------


class TestGenerateDescriptionWithCache:
    def test_cache_hit_skips_extract_metadata(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = _make_yaml("a.txt")

        result = generate_description(listing, describer, {"a.txt": b"content"}, cache=cache)

        describer.extract_metadata.assert_not_called()
        assert result.documents[0].file == "a.txt"

    def test_cache_miss_calls_extract_metadata_and_stores(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = None

        result = generate_description(listing, describer, {"a.txt": b"content"}, cache=cache)

        describer.extract_metadata.assert_called_once_with("a.txt", b"content")
        cache.put.assert_called_once()
        assert result.documents[0].file == "a.txt"

    def test_does_not_cache_empty_content(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["empty.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()

        generate_description(listing, describer, {"empty.txt": b""}, cache=cache)

        cache.get.assert_not_called()
        cache.put.assert_not_called()
        describer.extract_metadata.assert_called_once_with("empty.txt", b"")

    def test_classify_folder_always_called_with_cache(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt"])
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = _make_yaml("a.txt")

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
        cache.get.side_effect = [_make_yaml("cached.txt"), None]

        result = generate_description(
            listing,
            describer,
            {"cached.txt": b"old content", "fresh.txt": b"new content"},
            cache=cache,
        )

        describer.extract_metadata.assert_called_once_with("fresh.txt", b"new content")
        assert result.documents[0].file == "cached.txt"
        assert result.documents[1].file == "fresh.txt"

    def test_without_cache_calls_extract_metadata_for_all_files(self) -> None:
        listing = FolderListing(folder_id="f1", folder_path="/p", files=["a.txt", "b.txt"])
        describer = _make_describer_mock()
        result = generate_description(
            listing, describer, {"a.txt": b"aaa", "b.txt": b"bbb"}, cache=None
        )
        assert describer.extract_metadata.call_count == 2
        assert len(result.documents) == 2


# ---------------------------------------------------------------------------
# parse_document_record tests
# ---------------------------------------------------------------------------


class TestParseDocumentRecord:
    def test_parses_valid_yaml_into_document_record(self) -> None:
        yaml_str = (
            'file: "invoice.pdf"\n'
            "doc_type: invoice-incoming\n"
            "doc_lang: de\n"
            'date: "2026-01-15"\n'
            "parties:\n"
            "  from: Acme Corp\n"
            "  to: Datamantics UG\n"
            "summary: An invoice for consulting.\n"
            "tags: [invoice, consulting]\n"
            "facts:\n"
            "  amount: 1500.0\n"
            "  currency: EUR\n"
        )
        record = parse_document_record(yaml_str, "fallback.pdf")
        assert record.file == "invoice.pdf"
        assert record.doc_type == "invoice-incoming"
        assert record.doc_lang == "de"
        assert record.date == "2026-01-15"
        assert record.parties.from_ == "Acme Corp"
        assert record.parties.to == "Datamantics UG"
        assert record.summary == "An invoice for consulting."
        assert record.tags == ["invoice", "consulting"]
        assert record.facts == {"amount": 1500.0, "currency": "EUR"}

    def test_unknown_doc_type_falls_back_to_other(self) -> None:
        yaml_str = "doc_type: banana-split\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.doc_type == "other"

    def test_missing_parties_defaults_to_unknown(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.parties.from_ == "unknown"
        assert record.parties.to is None

    def test_missing_tags_defaults_to_empty_list(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.tags == []

    def test_missing_facts_defaults_to_empty_dict(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.facts == {}

    def test_missing_doc_lang_defaults_to_und(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.doc_lang == "und"

    def test_missing_date_defaults_to_empty_string(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.date == ""

    def test_missing_summary_defaults_to_empty_string(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.summary == ""

    def test_filename_fallback_when_file_field_missing(self) -> None:
        yaml_str = "doc_type: other\n"
        record = parse_document_record(yaml_str, "fallback_name.pdf")
        assert record.file == "fallback_name.pdf"

    def test_raises_value_error_on_unparseable_yaml(self) -> None:
        with pytest.raises(ValueError, match="Failed to parse YAML"):
            parse_document_record("{{{{invalid yaml:::::", "test.pdf")

    def test_parties_from_key_mapped_to_from_underscore(self) -> None:
        yaml_str = "parties:\n  from: Sender Corp\n  to: Receiver Ltd\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.parties.from_ == "Sender Corp"

    def test_parties_to_null_maps_to_none(self) -> None:
        yaml_str = "parties:\n  from: Sender\n  to: null\n"
        record = parse_document_record(yaml_str, "test.pdf")
        assert record.parties.to is None


# ---------------------------------------------------------------------------
# _get_or_extract_metadata tests
# ---------------------------------------------------------------------------


class TestGetOrExtractMetadata:
    def test_no_cache_calls_extract_metadata_directly(self) -> None:
        describer = _make_describer_mock()
        result = _get_or_extract_metadata("a.txt", b"content", describer, cache=None)
        describer.extract_metadata.assert_called_once_with("a.txt", b"content")
        assert "a.txt" in result

    def test_cache_hit_returns_cached_and_skips_llm(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = "cached yaml string"

        result = _get_or_extract_metadata("a.txt", b"content", describer, cache)

        describer.extract_metadata.assert_not_called()
        cache.put.assert_not_called()
        assert result == "cached yaml string"

    def test_cache_miss_calls_llm_and_stores(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()
        cache.get.return_value = None

        result = _get_or_extract_metadata("a.txt", b"content", describer, cache)

        describer.extract_metadata.assert_called_once_with("a.txt", b"content")
        content_hash = SummaryCache.content_hash(b"content")
        cache.put.assert_called_once_with(content_hash, result)

    def test_empty_content_bypasses_cache(self) -> None:
        describer = _make_describer_mock()
        cache = _make_cache_mock()

        result = _get_or_extract_metadata("a.txt", b"", describer, cache)

        cache.get.assert_not_called()
        cache.put.assert_not_called()
        describer.extract_metadata.assert_called_once_with("a.txt", b"")
        assert "a.txt" in result
