from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[T]):  # noqa: UP046  (py3.11 target: no PEP 695 syntax)
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
