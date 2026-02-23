"""Unit tests for description/models.py — FileDescription and FolderDescription."""

from semantic_folder.description.models import FileDescription, FolderDescription

# ---------------------------------------------------------------------------
# FileDescription tests
# ---------------------------------------------------------------------------


class TestFileDescription:
    def test_stores_filename_and_summary(self) -> None:
        fd = FileDescription(filename="report.pdf", summary="A quarterly report")
        assert fd.filename == "report.pdf"
        assert fd.summary == "A quarterly report"


# ---------------------------------------------------------------------------
# FolderDescription tests
# ---------------------------------------------------------------------------


class TestFolderDescription:
    def test_stores_all_fields(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Docs",
            folder_type="customer",
            files=[FileDescription(filename="a.pdf", summary="summary-a")],
            updated_at="2026-02-23",
        )
        assert desc.folder_path == "/drive/root:/Docs"
        assert desc.folder_type == "customer"
        assert len(desc.files) == 1
        assert desc.updated_at == "2026-02-23"

    def test_files_defaults_to_empty_list(self) -> None:
        desc = FolderDescription(folder_path="/p", folder_type="t")
        assert desc.files == []

    def test_updated_at_defaults_to_empty_string(self) -> None:
        desc = FolderDescription(folder_path="/p", folder_type="t")
        assert desc.updated_at == ""


# ---------------------------------------------------------------------------
# to_markdown() tests
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_produces_yaml_frontmatter_and_file_sections(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Customers/Nexplore",
            folder_type="[folder-type]",
            files=[
                FileDescription(filename="SOW.pdf", summary="[SOW.pdf-description]"),
                FileDescription(filename="invoice.pdf", summary="[invoice.pdf-description]"),
            ],
            updated_at="2026-02-23",
        )

        md = desc.to_markdown()

        assert md.startswith("---\n")
        assert "folder_path: /drive/root:/Customers/Nexplore\n" in md
        assert 'folder_type: "[folder-type]"\n' in md
        assert "updated_at: 2026-02-23\n" in md
        assert "\n## SOW.pdf\n" in md
        assert "\n[SOW.pdf-description]\n" in md
        assert "\n## invoice.pdf\n" in md
        assert "\n[invoice.pdf-description]\n" in md

    def test_folder_type_is_quoted_in_yaml(self) -> None:
        desc = FolderDescription(
            folder_path="/p", folder_type="[folder-type]", updated_at="2026-01-01"
        )
        md = desc.to_markdown()
        assert 'folder_type: "[folder-type]"' in md

    def test_empty_files_produces_frontmatter_only(self) -> None:
        desc = FolderDescription(
            folder_path="/drive/root:/Empty",
            folder_type="unknown",
            files=[],
            updated_at="2026-02-23",
        )

        md = desc.to_markdown()

        assert "---\n" in md
        assert "## " not in md

    def test_output_ends_with_trailing_newline(self) -> None:
        desc = FolderDescription(
            folder_path="/p",
            folder_type="t",
            files=[FileDescription(filename="f.txt", summary="s")],
            updated_at="2026-01-01",
        )
        md = desc.to_markdown()
        assert md.endswith("\n")

    def test_frontmatter_delimiters_present(self) -> None:
        desc = FolderDescription(folder_path="/p", folder_type="t", updated_at="2026-01-01")
        md = desc.to_markdown()
        lines = md.split("\n")
        assert lines[0] == "---"
        assert "---" in lines[4]  # closing delimiter
