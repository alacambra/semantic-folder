"""Data models for Microsoft Graph API drive items and folder listings."""

from dataclasses import dataclass, field

# Graph API JSON field names
FIELD_ID = "id"
FIELD_NAME = "name"
FIELD_FOLDER = "folder"
FIELD_DELETED = "deleted"
FIELD_PARENT_REFERENCE = "parentReference"
FIELD_PATH = "path"
FIELD_TOKEN = "token"

# OData response keys
ODATA_DELTA_LINK = "@odata.deltaLink"
ODATA_NEXT_LINK = "@odata.nextLink"
ODATA_VALUE = "value"


@dataclass
class DriveItem:
    """Represents a single item (file or folder) from the OneDrive delta API."""

    id: str
    name: str
    parent_id: str
    parent_path: str
    is_folder: bool
    is_deleted: bool


@dataclass
class FolderListing:
    """Represents the contents of a OneDrive folder after enumeration."""

    folder_id: str
    folder_path: str
    files: list[str] = field(default_factory=list)
