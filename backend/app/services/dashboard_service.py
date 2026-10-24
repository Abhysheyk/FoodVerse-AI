from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import User
from app.repositories import history as history_repo
from app.repositories import media as media_repo
from app.schemas.dashboard import DashboardSummary, HistoryUsage, MediaUsage
from app.schemas.history import HistoryItem

RECENT_LIMIT = 5


def summary(db: Session, settings: Settings, user: User) -> DashboardSummary:
    """Real counts only. A new account gets zeros and an empty list, never placeholders."""
    count, total_bytes = media_repo.usage(db, user.id)
    by_module = history_repo.counts_by_module(db, user.id)
    recent, _ = history_repo.list_page(db, user.id, module=None, limit=RECENT_LIMIT, offset=0)
    return DashboardSummary(
        media=MediaUsage(
            count=count,
            total_bytes=total_bytes,
            quota_bytes=settings.user_media_quota_bytes,
            max_upload_bytes=settings.max_upload_bytes,
        ),
        history=HistoryUsage(total=sum(by_module.values()), by_module=by_module),
        recent=[HistoryItem.model_validate(r) for r in recent],
    )
