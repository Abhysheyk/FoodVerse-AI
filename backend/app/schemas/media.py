import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import MediaKind


class MediaRead(BaseModel):
    """Public view of a media asset. storage_key and paths are deliberately absent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MediaKind
    content_type: str
    display_name: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: float | None
    created_at: datetime
