"""Unit tests for description/models.py -- DocumentRecord, Parties, FolderDescription, DOC_TYPES."""

import json

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
# to_json() tests
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


class TestToJson:
    def test_produces_folder_block_with_path_type_updated_at(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Docs",
            folder_type="invoices",
            updated_at="2026-03-10",
        )
        output = desc.to_json()
        parsed = json.loads(output)
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
        output = desc.to_json()
        parsed = json.loads(output)
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
        output = desc.to_json()
        parsed = json.loads(output)
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
        output = desc.to_json()
        assert '"facts"' in output
        parsed = json.loads(output)
        assert parsed["documents"][0]["facts"]["amount"] == 50.0
        assert parsed["documents"][0]["facts"]["currency"] == "EUR"

    def test_facts_block_absent_when_empty(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(facts={})],
        )
        output = desc.to_json()
        assert '"facts"' not in output

    def test_tags_rendered_as_json_array(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(tags=["alpha", "beta", "gamma"])],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["documents"][0]["tags"] == ["alpha", "beta", "gamma"]
        assert isinstance(parsed["documents"][0]["tags"], list)

    def test_parties_null_to_rendered_correctly(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record(to=None)],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["documents"][0]["parties"]["to"] is None

    def test_empty_documents_produces_empty_list(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["documents"] == []

    def test_output_ends_with_trailing_newline(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[_make_record()],
            updated_at="2026-01-01",
        )
        output = desc.to_json()
        assert output.endswith("\n")

    def test_output_is_valid_json(self) -> None:
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
        output = desc.to_json()
        parsed = json.loads(output)
        assert isinstance(parsed, dict)
        assert "folder" in parsed
        assert "documents" in parsed

    # -- overview tests --

    def test_overview_document_count(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(file="a.pdf"),
                _make_record(file="b.pdf"),
                _make_record(file="c.pdf"),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["overview"]["document_count"] == 3

    def test_overview_types_present(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(doc_type="receipt"),
                _make_record(doc_type="invoice-incoming"),
                _make_record(doc_type="receipt"),
                _make_record(doc_type="contract"),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["overview"]["types_present"] == ["contract", "invoice-incoming", "receipt"]

    def test_overview_total_amount_eur_sums_eur_only(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(facts={"amount": 100.0, "currency": "EUR"}),
                _make_record(facts={"amount": 250.0, "currency": "EUR"}),
                _make_record(facts={"amount": 999.0, "currency": "USD"}),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["overview"]["total_amount_eur"] == 350.0

    def test_overview_by_expense_category(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(facts={"expense_category": "travel", "amount": 100.0}),
                _make_record(facts={"expense_category": "travel", "amount": 200.0}),
                _make_record(facts={"expense_category": "office", "amount": 50.0}),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        by_cat = parsed["overview"]["by_expense_category"]
        assert by_cat["travel"] == {"count": 2, "total": 300.0}
        assert by_cat["office"] == {"count": 1, "total": 50.0}

    def test_overview_by_country(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(facts={"country": "DE", "amount": 100.0}),
                _make_record(facts={"country": "DE", "amount": 50.0}),
                _make_record(facts={"country": "US", "amount": 200.0}),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        by_country = parsed["overview"]["by_country"]
        assert by_country["DE"] == {"count": 2, "total": 150.0}
        assert by_country["US"] == {"count": 1, "total": 200.0}

    def test_overview_date_range(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[
                _make_record(date="2026-03-15"),
                _make_record(date="2026-01-01"),
                _make_record(date="2026-06-30"),
            ],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["overview"]["date_range"] == "2026-01-01 to 2026-06-30"

    def test_overview_empty_documents(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            documents=[],
        )
        output = desc.to_json()
        parsed = json.loads(output)
        overview = parsed["overview"]
        assert overview["document_count"] == 0
        assert overview["date_range"] == ""
        assert overview["types_present"] == []
        assert overview["total_amount_eur"] == 0.0
        assert overview["by_expense_category"] == {}
        assert overview["by_country"] == {}

    # -- period tests --

    def test_period_included_when_set(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            period="2026-01",
            updated_at="2026-03-10",
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert parsed["folder"]["period"] == "2026-01"

    def test_period_omitted_when_none(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            period=None,
            updated_at="2026-03-10",
        )
        output = desc.to_json()
        parsed = json.loads(output)
        assert "period" not in parsed["folder"]


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
