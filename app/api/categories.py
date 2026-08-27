from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas.category import (
    CategoryCreate, CategoryListResponse, CategoryResponse, CategoryUpdate,
)
from app.services import categories as categories_service

router = APIRouter(prefix="/categories", tags=["categories"])


def _out(cat) -> CategoryResponse:
    return CategoryResponse(
        id=cat.id, name=cat.name, type=cat.type,
        group=cat.group, icon=cat.icon, is_default=cat.is_default,
    )


@router.get("", response_model=CategoryListResponse, summary="List categories")
def list_categories(type: Optional[str] = Query(None, description="EXPENSE | INCOME"),
                    db: Session = Depends(get_db)):
    items = [_out(c) for c in categories_service.list_categories(db, type)]
    return CategoryListResponse(items=items, total=len(items))


@router.post(
    "", response_model=CategoryResponse, status_code=http_status.HTTP_201_CREATED,
    summary="Create a category",
)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    return _out(categories_service.create_category(
        db, name=payload.name, type_=payload.type,
        group=payload.group, icon=payload.icon,
    ))


@router.get(
    "/{category_id}", response_model=CategoryResponse,
    summary="Get one category", responses={404: {"description": "Not found"}},
)
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = categories_service.get_category(db, category_id)
    if not cat:
        from app.api.errors import ApiError
        raise ApiError(404, "CATEGORY_NOT_FOUND", f"Category {category_id} not found")
    return _out(cat)


@router.put(
    "/{category_id}", response_model=CategoryResponse,
    summary="Update a category (partial)",
    responses={404: {"description": "Not found"}},
)
def update_category(category_id: int, payload: CategoryUpdate,
                    db: Session = Depends(get_db)):
    return _out(categories_service.update_category(
        db, category_id, payload.model_dump(exclude_unset=True)
    ))


@router.delete(
    "/{category_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
    responses={409: {"description": "Category is used by transactions"}},
)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    categories_service.delete_category(db, category_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)