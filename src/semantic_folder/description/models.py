"""Data models for structured folder description content."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_RESOURCES_DIR = Path(__file__).parent / "resources"


def _load_doc_types() -> frozenset[str]:
    """Load allowed doc_type values from the YAML resource file.

    Returns:
        Frozenset of allowed doc_type strings.
    """
    path = _RESOURCES_DIR / "doc_types.yaml"
    with path.open() as f:
        data = yaml.safe_load(f)
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
    facts: dict[str, object] = field(default_factory=dict)


class _FlowSequenceDumper(yaml.Dumper):
    """Custom YAML dumper that renders tagged lists as flow sequences."""


def _flow_sequence_representer(dumper: yaml.Dumper, data: _FlowSequenceList) -> Any:
    """Represent a _FlowSequenceList as a flow-style YAML sequence."""
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


class _FlowSequenceList(list):  # type: ignore[type-arg]
    """List subclass that signals flow-style rendering in YAML."""


_FlowSequenceDumper.add_representer(_FlowSequenceList, _flow_sequence_representer)


@dataclass
class FolderDescription:
    """Complete structured description of a folder and its files.

    Attributes:
        folder_path: OneDrive path of the folder (from parentReference.path).
        folder_type: Classification of the folder (AI-inferred).
        documents: Ordered list of structured document records.
        updated_at: ISO date string (YYYY-MM-DD) when the description was generated.
    """

    folder_path: str
    folder_type: str
    documents: list[DocumentRecord] = field(default_factory=list)
    updated_at: str = ""

    def to_yaml(self) -> str:
        """Serialize this folder description to YAML.

        Returns:
            String content suitable for writing to folder_description.yaml.
        """
        data: dict[str, object] = {
            "folder": {
                "path": self.folder_path,
                "type": self.folder_type,
                "updated_at": self.updated_at,
            },
            "documents": self._build_documents_list(),
        }
        return yaml.dump(
            data,
            Dumper=_FlowSequenceDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def _build_documents_list(self) -> list[dict[str, object]]:
        """Build a list of plain dicts from document records for YAML serialization."""
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
                "tags": _FlowSequenceList(doc.tags),
            }
            if doc.facts:
                record["facts"] = doc.facts
            result.append(record)
        return result
