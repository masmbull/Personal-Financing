"""CSV Import API — upload and preview, then confirm import."""
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.services import csv_import

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview", summary="Preview CSV rows before importing")
def preview_csv(
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    col_date: int | None = Form(None),
    col_description: int | None = Form(None),
    col_amount: int | None = Form(None),
    col_type: int | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
):
    content = file.file.read().decode("utf-8-sig", errors="replace")
    return csv_import.parse_csv(
        content, delimiter=delimiter,
        col_date=col_date, col_description=col_description,
        col_amount=col_amount, col_type=col_type,
    )


@router.post("/confirm", summary="Confirm and create transactions from parsed rows")
def confirm_import(
    account_id: int = Form(...),
    default_category_id: int | None = Form(None),
    rows_json: str = Form(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = json.loads(rows_json)
    return csv_import.import_transactions(
        db, user_id=user.id, account_id=account_id,
        rows=rows, default_category_id=default_category_id,
    )
