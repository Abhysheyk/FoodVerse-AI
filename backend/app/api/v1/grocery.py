import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, DbSession, require_csrf_header
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.grocery import (
    GroceryListCreate, GroceryListDetail, GroceryListSummary, GroceryListUpdate,
)
from app.services import grocery_service

router = APIRouter(prefix="/grocery-lists", tags=["grocery-lists"])


@router.post(
    "", response_model=GroceryListDetail, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def create_list(body: GroceryListCreate, user: CurrentUser, db: DbSession) -> GroceryListDetail:
    return grocery_service.create_from_plan(db, user, body)


@router.get("", response_model=Page[GroceryListSummary])
def list_lists(
    user: CurrentUser, db: DbSession,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[GroceryListSummary]:
    return grocery_service.list_lists(db, user, page=page, page_size=page_size)


@router.get("/{list_id}", response_model=GroceryListDetail)
def get_list(list_id: uuid.UUID, user: CurrentUser, db: DbSession) -> GroceryListDetail:
    return grocery_service.get_list(db, user, list_id)


@router.put(
    "/{list_id}", response_model=GroceryListDetail,
    dependencies=[Depends(require_csrf_header)],
)
def update_list(
    list_id: uuid.UUID, body: GroceryListUpdate, user: CurrentUser, db: DbSession,
) -> GroceryListDetail:
    return grocery_service.update_list(db, user, list_id, body)


@router.delete(
    "/{list_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_list(list_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    grocery_service.delete_list(db, user, list_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)