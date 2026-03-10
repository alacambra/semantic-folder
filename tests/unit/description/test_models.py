"""Unit tests for description/models.py -- DocumentRecord, Parties, FolderDescription, DOC_TYPES."""

import yaml

from semantic_folder.description.models import (
    DOC_TYPES,
    DocumentRecord,
    FolderDescription,
    Parties,
)

# ---------------------------------------------------------------------------
# DocumentRecord tests
# ---------------------------------------------------------------------------


class TestDocumentRecord:
    def test_stores_all_envelope_fields(self) -> None:
        parties = Parties(from_="Acme Corp", to="Datamantics UG")
        record = DocumentRecord(
            file="invoice.pdf",
            doc_type="invoice-incoming",
            doc_lang="de",
            date="2026-01-15",
            parties=parties,
            summary="An invoice for consulting services.",
            tags=["invoice", "consulting"],
            facts={"amount": 1500.0, "currency": "EUR"},
        )
        assert record.file == "invoice.pdf"
        assert record.doc_type == "invoice-incoming"
        assert record.doc_lang == "de"
        assert record.date == "2026-01-15"
        assert record.parties.from_ == "Acme Corp"
        assert record.parties.to == "Datamantics UG"
        assert record.summary == "An invoice for consulting services."
        assert record.tags == ["invoice", "consulting"]
        assert record.facts == {"amount": 1500.0, "currency": "EUR"}

    def test_tags_defaults_to_empty_list(self) -> None:
        record = DocumentRecord(
            file="f.txt",
            doc_type="other",
            doc_lang="en",
            date="",
            parties=Parties(from_="unknown"),
            summary="",
        )
        assert record.tags == []

    def test_facts_defaults_to_empty_dict(self) -> None:
        record = DocumentRecord(
            file="f.txt",
            doc_type="other",
            doc_lang="en",
            date="",
            parties=Parties(from_="unknown"),
            summary="",
        )
        assert record.facts == {}

    def test_parties_to_defaults_to_none(self) -> None:
        parties = Parties(from_="Sender")
        assert parties.to is None


# ---------------------------------------------------------------------------
# FolderDescription tests
# ---------------------------------------------------------------------------


class TestFolderDescription:
    def test_stores_all_fields(self) -> None:
        record = DocumentRecord(
            file="a.pdf",
            doc_type="other",
            doc_lang="en",
            date="2026-01-01",
            parties=Parties(from_="X"),
            summary="A document.",
        )
        desc = FolderDescription(
            folder_path="/drive/root:/Docs",
            folder_type="project-docs",
            documents=[record],
            updated_at="2026-03-10",
        )
        assert desc.folder_path == "/drive/root:/Docs"
        assert desc.folder_type == "project-docs"
        assert len(desc.documents) == 1
        assert desc.updated_at == "2026-03-10"

    def test_documents_defaults_to_empty_list(self) -> None:
        desc = FolderDescription(folder_path="/p", folder_type="t")
        assert desc.documents == []

    def test_updated_at_defaults_to_empty_string(self) -> None:
        desc = FolderDescription(folder_path="/p", folder_type="t")
        assert desc.updated_at == ""


# ---------------------------------------------------------------------------
# to_yaml() tests
# ---------------------------------------------------------------------------


def _make_record(
    file: str = "test.pdf",
    doc_type: str = "invoice-incoming",
    doc_lang: str = "en",
    date: str = "2026-01-15",
    from_: str = "Acme Corp",
    to: str | None = "Datamantics UG",
    summary: str = "A test document.",
    tags: list[str] | None = None,
    facts: dict[str, object] | None = None,
) -> DocumentRecord:
    return DocumentRecord(
        file=file,
        doc_type=doc_type,
        doc_lang=doc_lang,
        date=date,
        parties=Parties(from_=from_, to=to),
        summary=summary,
        tags=tags if tags is not None else ["test", "invoice"],
        facts=facts if facts is not None else {},
    )


class TestToYaml:
    def test_produces_folder_block_with_path_type_updated_at(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Docs",
            folder_type="invoices",
            updated_at="2026-03-10",
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        assert parsed["folder"]["path"] == "/drive/root:/Docs"
        assert parsed["folder"]["type"] == "invoices"
        assert parsed["folder"]["updated_at"] == "2026-03-10"

    def test_produces_documents_list(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(file="a.pdf"), _make_record(file="b.pdf")],
            updated_at="2026-01-01",
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        assert len(parsed["documents"]) == 2
        assert parsed["documents"][0]["file"] == "a.pdf"
        assert parsed["documents"][1]["file"] == "b.pdf"

    def test_document_record_has_all_envelope_fields(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(
                    file="invoice.pdf",
                    doc_type="invoice-incoming",
                    doc_lang="de",
                    date="2026-01-15",
                    from_="Sender Inc",
                    to="Receiver Ltd",
                    summary="An important invoice.",
                    tags=["invoice", "payment"],
                    facts={"amount": 100.0},
                )
            ],
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        doc = parsed["documents"][0]
        assert doc["file"] == "invoice.pdf"
        assert doc["doc_type"] == "invoice-incoming"
        assert doc["doc_lang"] == "de"
        assert doc["date"] == "2026-01-15"
        assert doc["parties"]["from"] == "Sender Inc"
        assert doc["parties"]["to"] == "Receiver Ltd"
        assert doc["summary"] == "An important invoice."
        assert doc["tags"] == ["invoice", "payment"]
        assert doc["facts"]["amount"] == 100.0

    def test_facts_block_present_when_non_empty(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(facts={"amount": 50.0, "currency": "EUR"})],
        )
        output = desc.to_yaml()
        assert "facts:" in output
        parsed = yaml.safe_load(output)
        assert parsed["documents"][0]["facts"]["amount"] == 50.0
        assert parsed["documents"][0]["facts"]["currency"] == "EUR"

    def test_facts_block_absent_when_empty(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(facts={})],
        )
        output = desc.to_yaml()
        assert "facts:" not in output

    def test_tags_rendered_as_flow_sequence(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(tags=["alpha", "beta", "gamma"])],
        )
        output = desc.to_yaml()
        assert "[alpha, beta, gamma]" in output

    def test_parties_null_to_rendered_correctly(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(to=None)],
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        assert parsed["documents"][0]["parties"]["to"] is None

    def test_empty_documents_produces_empty_list(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[],
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        assert parsed["documents"] == []

    def test_output_ends_with_trailing_newline(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record()],
            updated_at="2026-01-01",
        )
        output = desc.to_yaml()
        assert output.endswith("\n")

    def test_output_is_valid_yaml(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Test",
            folder_type="invoices",
            documents=[
                _make_record(
                    facts={"amount": 100.0, "currency": "EUR"},
                    tags=["invoice", "test"],
                )
            ],
            updated_at="2026-03-10",
        )
        output = desc.to_yaml()
        parsed = yaml.safe_load(output)
        assert isinstance(parsed, dict)
        assert "folder" in parsed
        assert "documents" in parsed


# ---------------------------------------------------------------------------
# DOC_TYPES tests
# ---------------------------------------------------------------------------


class TestDocTypes:
    def test_doc_types_contains_expected_values(self) -> None:
        expected = {
            "invoice-incoming",
            "invoice-outgoing",
            "receipt",
            "contract",
            "other",
            "tax-notice",
            "insurance-policy",
            "correspondence",
        }
        for value in expected:
            assert value in DOC_TYPES

    def test_doc_types_is_frozenset(self) -> None:
        assert isinstance(DOC_TYPES, frozenset)
