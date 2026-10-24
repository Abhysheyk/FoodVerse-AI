import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import AnalysisStatus, ModuleKey


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module: ModuleKey
    status: AnalysisStatus
    title: str
    summary: str | None
    media_id: uuid.UUID | None
    created_at: datetime


class HistoryDetail(HistoryItem):
    result: dict[str, Any] | None
