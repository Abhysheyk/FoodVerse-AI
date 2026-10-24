from pydantic import BaseModel

from app.models import ModuleKey
from app.schemas.history import HistoryItem


class ModuleRead(BaseModel):
    key: ModuleKey
    title: str
    description: str
    available: bool


class MediaUsage(BaseModel):
    count: int
    total_bytes: int
    quota_bytes: int
    max_upload_bytes: int


class HistoryUsage(BaseModel):
    total: int
    by_module: dict[str, int]


class DashboardSummary(BaseModel):
    media: MediaUsage
    history: HistoryUsage
    recent: list[HistoryItem]
