"""Data models for folder description content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileDescription:
    """Description of a single file within a folder.

    Attributes:
        filename: Name of the file (e.g. "SOW_2026_01.pdf").
        summary: Text summary of the file contents. Placeholder in IT-4,
            AI-generated in IT-5.
    """

    filename: str
    summary: str


@dataclass
class FolderDescription:
    """Complete description of a folder and its files.

    Attributes:
        folder_path: OneDrive path of the folder (from parentReference.path).
        folder_type: Classification of the folder. Placeholder in IT-4,
            AI-inferred in IT-5.
        files: Ordered list of file descriptions.
        updated_at: ISO date string (YYYY-MM-DD) when the description was generated.
    """

    folder_path: str
    folder_type: str
    files: list[FileDescription] = field(default_factory=list)
    updated_at: str = ""

    def to_markdown(self) -> str:
        """Serialize this folder description to Markdown with YAML frontmatter.

        Returns:
            String content suitable for writing to folder_description.md.
        """
        lines: list[str] = [
            "---",
            f"folder_path: {self.folder_path}",
            f'folder_type: "{self.folder_type}"',
            f"updated_at: {self.updated_at}",
            "---",
        ]
        for fd in self.files:
            lines.append("")
            lines.append(f"## {fd.filename}")
            lines.append("")
            lines.append(fd.summary)

        # Ensure trailing newline.
        lines.append("")
        return "\n".join(lines)
