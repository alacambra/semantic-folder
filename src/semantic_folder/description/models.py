"""Data models for structured folder description content."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RESOURCES_DIR = Path(__file__).parent / "resources"


def _load_doc_types() -> frozenset[str]:
    """Load allowed doc_type values from the JSON resource file.

    Returns:
        Frozenset of allowed doc_type strings.
    """
    path = _RESOURCES_DIR / "doc_types.json"
    with path.open() as f:
        data = json.load(f)
    return frozenset(data["doc_types"])


DOC_TYPES: frozenset[str] = _load_doc_types()


@dataclass
class Parties:
    """Sender and recipient of a document.

    Attributes:
        from_: Who sent or issued the document.
        to: Who received the document, or None if not applicable.
    """

    from_: str
    to: str | None = None


@dataclass
class DocumentRecord:
    """Structured metadata for a single file extracted by the LLM.

    Layer 1 (universal envelope) fields are always present.
    Layer 2 (facts) is a free-form dict whose keys vary by doc_type.

    Attributes:
        file: Filename as it appears in OneDrive.
        doc_type: Controlled vocabulary value from DOC_TYPES.
        doc_lang: Two-letter ISO 639-1 language code.
        date: Primary date in YYYY-MM-DD format (issued, created, received).
        parties: Sender and recipient.
        summary: 2-3 sentence factual summary in English.
        tags: Lowercase keyword list for search (4-8 terms).
        facts: Free-form key-value pairs with domain-specific structured data.
    """

    file: str
    doc_type: str
    doc_lang: str
    date: str
    parties: Parties
    summary: str
    tags: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class CategoryBreakdown:
    """Aggregated count and total for a category."""

    count: int
    total: float


@dataclass
class FolderDescription:
    """Complete structured description of a folder and its files.

    Attributes:
        folder_path: OneDrive path of the folder (from parentReference.path).
        folder_type: Classification of the folder (AI-inferred).
        documents: Ordered list of structured document records.
        updated_at: ISO date string (YYYY-MM-DD) when the description was generated.
        period: Optional period string (e.g. "2026-01"), inferred from document dates.
    """

    folder_path: str
    folder_type: str
    documents: list[DocumentRecord] = field(default_factory=list)
    updated_at: str = ""
    period: str | None = None

    def to_json(self) -> str:
        """Serialize this folder description to JSON.

        Returns:
            String content suitable for writing to folder_description.json.
        """
        data: dict[str, object] = {
            "folder": self._build_folder_block(),
            "overview": self._build_overview(),
            "documents": self._build_documents_list(),
        }
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    def _build_folder_block(self) -> dict[str, object]:
        """Build the folder metadata block."""
        block: dict[str, object] = {
            "path": self.folder_path,
            "type": self.folder_type,
        }
        if self.period is not None:
            block["period"] = self.period
        block["updated_at"] = self.updated_at
        return block

    def _build_overview(self) -> dict[str, object]:
        """Compute overview statistics from the documents list."""
        dates: list[str] = [d.date for d in self.documents if d.date]
        types_present = sorted({d.doc_type for d in self.documents})

        total_amount_eur = 0.0
        by_expense: dict[str, CategoryBreakdown] = {}
        by_country: dict[str, CategoryBreakdown] = {}

        for doc in self.documents:
            amount = doc.facts.get("amount")
            currency = doc.facts.get("currency")

            if isinstance(amount, (int, float)) and currency == "EUR":
                total_amount_eur += amount

            category = doc.facts.get("expense_category")
            if isinstance(category, str) and category:
                entry = by_expense.setdefault(category, CategoryBreakdown(count=0, total=0.0))
                entry.count += 1
                if isinstance(amount, (int, float)):
                    entry.total += amount

            country = doc.facts.get("country")
            if isinstance(country, str) and country:
                entry = by_country.setdefault(country, CategoryBreakdown(count=0, total=0.0))
                entry.count += 1
                if isinstance(amount, (int, float)):
                    entry.total += amount

        date_range = ""
        if dates:
            sorted_dates = sorted(dates)
            date_range = f"{sorted_dates[0]} to {sorted_dates[-1]}"

        return {
            "document_count": len(self.documents),
            "date_range": date_range,
            "types_present": types_present,
            "total_amount_eur": round(total_amount_eur, 2),
            "has_action_items": False,
            "by_expense_category": {
                k: {"count": v.count, "total": round(v.total, 2)} for k, v in by_expense.items()
            },
            "by_country": {
                k: {"count": v.count, "total": round(v.total, 2)} for k, v in by_country.items()
            },
        }

    def _build_documents_list(self) -> list[dict[str, object]]:
        """Build a list of plain dicts from document records for JSON serialization."""
        result: list[dict[str, object]] = []
        for doc in self.documents:
            record: dict[str, object] = {
                "file": doc.file,
                "doc_type": doc.doc_type,
                "doc_lang": doc.doc_lang,
                "date": doc.date,
                "parties": {
                    "from": doc.parties.from_,
                    "to": doc.parties.to,
                },
                "summary": doc.summary,
                "tags": list(doc.tags),
            }
            if doc.facts:
                record["facts"] = doc.facts
            result.append(record)
        return result
