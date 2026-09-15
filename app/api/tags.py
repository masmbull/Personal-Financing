"""Tags API — CRUD + attach/detach to transactions."""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.services import tags as tag_service

router = APIRouter(prefix="/tags", tags=["tags"])


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(None, max_length=7)


class TagAttach(BaseModel):
    tag_ids: list[int]


@router.get("", summary="List all tags")
def list_tags(user: CurrentUser = Depends(get_current_user),
              db: Session = Depends(get_db)):
    return tag_service.list_tags(db, user.id)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a tag")
def create_tag(body: TagCreate, user: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return tag_service.create_tag(db, user.id, body.name, body.color)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a tag")
def delete_tag(tag_id: int, user: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)):
    tag_service.delete_tag(db, tag_id, user.id)


@router.put("/transaction/{transaction_id}", summary="Set tags on a transaction")
def set_tags(transaction_id: int, body: TagAttach,
             user: CurrentUser = Depends(get_current_user),
             db: Session = Depends(get_db)):
    tag_service.attach_tags(db, transaction_id, body.tag_ids, user.id)
    return tag_service.tags_for_transaction(db, transaction_id)


@router.get("/transaction/{transaction_id}", summary="Get tags for a transaction")
def get_tx_tags(transaction_id: int,
                user: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return tag_service.tags_for_transaction(db, transaction_id)
