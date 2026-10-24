import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import AnalysisRecord, ModuleKey, User
from app.repositories import history as history_repo
from app.schemas.common import Page
from app.schemas.history import HistoryItem


def list_history(
    db: Session, user: User, *, module: ModuleKey | None, page: int, page_size: int
) -> Page[HistoryItem]:
    rows, total = history_repo.list_page(
        db, user.id, module=module, limit=page_size, offset=(page - 1) * page_size
    )
    return Page.build([HistoryItem.model_validate(r) for r in rows], total, page, page_size)


def get_owned_or_404(db: Session, user: User, record_id: uuid.UUID) -> AnalysisRecord:
    record = history_repo.get_owned(db, record_id, user.id)
    if record is None:
        raise NotFoundError("History entry not found.", code="history_not_found")
    return record


def delete(db: Session, user: User, record_id: uuid.UUID) -> None:
    db.delete(get_owned_or_404(db, user, record_id))
    db.commit()
