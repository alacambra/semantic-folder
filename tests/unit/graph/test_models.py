"""Unit tests for graph/models.py — data model instantiation and field access."""

from semantic_folder.graph.models import DriveItem, FolderListing


class TestDriveItem:
    def test_instantiation_with_all_fields(self) -> None:
        item = DriveItem(
            id="item-001",
            name="report.docx",
            parent_id="parent-001",
            parent_path="/drive/root:/Documents",
            is_folder=False,
            is_deleted=False,
        )
        assert item.id == "item-001"
        assert item.name == "report.docx"
        assert item.parent_id == "parent-001"
        assert item.parent_path == "/drive/root:/Documents"
        assert item.is_folder is False
        assert item.is_deleted is False

    def test_folder_item(self) -> None:
        item = DriveItem(
            id="folder-001",
            name="Projects",
            parent_id="root",
            parent_path="/drive/root:",
            is_folder=True,
            is_deleted=False,
        )
        assert item.is_folder is True

    def test_deleted_item(self) -> None:
        item = DriveItem(
            id="deleted-001",
            name="old-file.txt",
            parent_id="parent-001",
            parent_path="/drive/root:/Docs",
            is_folder=False,
            is_deleted=True,
        )
        assert item.is_deleted is True

    def test_equality(self) -> None:
        a = DriveItem("1", "a.txt", "p1", "/root", False, False)
        b = DriveItem("1", "a.txt", "p1", "/root", False, False)
        assert a == b

    def test_repr_contains_name(self) -> None:
        item = DriveItem("1", "hello.md", "p1", "/root", False, False)
        assert "hello.md" in repr(item)


class TestFolderListing:
    def test_instantiation_defaults(self) -> None:
        listing = FolderListing(folder_id="f-001", folder_path="/drive/root:/Documents")
        assert listing.folder_id == "f-001"
        assert listing.folder_path == "/drive/root:/Documents"
        assert listing.files == []

    def test_instantiation_with_files(self) -> None:
        listing = FolderListing(
            folder_id="f-002",
            folder_path="/drive/root:/Projects",
            files=["readme.md", "plan.docx"],
        )
        assert len(listing.files) == 2
        assert "readme.md" in listing.files

    def test_files_default_factory_independent(self) -> None:
        """Each FolderListing instance must have its own files list."""
        a = FolderListing(folder_id="1", folder_path="/root")
        b = FolderListing(folder_id="2", folder_path="/root")
        a.files.append("x.txt")
        assert b.files == []

    def test_file_ids_defaults_to_empty_list(self) -> None:
        listing = FolderListing(folder_id="f-001", folder_path="/drive/root:/Documents")
        assert listing.file_ids == []

    def test_instantiation_with_file_ids(self) -> None:
        listing = FolderListing(
            folder_id="f-002",
            folder_path="/drive/root:/Projects",
            files=["readme.md", "plan.docx"],
            file_ids=["id-1", "id-2"],
        )
        assert listing.file_ids == ["id-1", "id-2"]

    def test_file_ids_default_factory_independent(self) -> None:
        """Each FolderListing instance must have its own file_ids list."""
        a = FolderListing(folder_id="1", folder_path="/root")
        b = FolderListing(folder_id="2", folder_path="/root")
        a.file_ids.append("id-x")
        assert b.file_ids == []

    def test_equality(self) -> None:
        a = FolderListing("1", "/root", ["a.txt"])
        b = FolderListing("1", "/root", ["a.txt"])
        assert a == b
