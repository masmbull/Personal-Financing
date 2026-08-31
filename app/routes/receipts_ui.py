"""Receipt web UI - upload -> preview -> review -> confirm workflow.

These Jinja pages reuse the SAME receipt services as the REST API; no
business logic lives here. OCR never creates transactions: the confirm
page posts explicit user-entered values.
"""
from datetime import date

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Account, Category, ReceiptStatus
from app.services import receipts as receipts_service
from app.utils import format_rupiah, today_str
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

STATUS_LABELS = {
    ReceiptStatus.PENDING: ("Diupload", "badge-yellow"),
    ReceiptStatus.PROCESSING: ("Sedang dibaca", "badge-blue"),
    ReceiptStatus.PROCESSED: ("Siap direview", "badge-green"),
    ReceiptStatus.CONFIRMED: ("Tercatat", "badge-green"),
    ReceiptStatus.FAILED: ("Gagal", "badge-red"),
}


def _view(r) -> dict:
    label, cls = STATUS_LABELS.get(r.ocr_status, ("Diupload", ""))
    tx = r.transaction
    return {
        "row": r,
        "id": r.id,
        "filename": r.original_filename or f"struk-{r.id}",
        "status_label": label,
        "status_class": cls,
        "confirmed": r.transaction_id is not None,
        "transaction_id": r.transaction_id,
        "merchant": (tx.description if tx else None) or r.original_filename,
        "amount": tx.amount if tx else None,
        "created": r.created_at,
        "size_kb": round(r.size_bytes / 1024, 1),
    }


@router.get("/receipts", response_class=HTMLResponse)
def receipts_list(request: Request, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    items = [_view(r) for r in receipts_service.list_receipts(db, user.id)]
    return templates.TemplateResponse(request, "receipts/list.html", { "items": items,
        "format_rupiah": format_rupiah,
    })


@router.get("/receipts/upload", response_class=HTMLResponse)
def upload_form(request: Request, user: CurrentUser = Depends(get_current_user)):
    from app.config import get_settings
    return templates.TemplateResponse(request, "receipts/upload.html", { "max_mb": get_settings().RECEIPT_MAX_SIZE_MB,
    })


@router.post("/receipts/upload")
async def upload_submit(request: Request, db: Session = Depends(get_db),
                        user: CurrentUser = Depends(get_current_user)):
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise HTTPException(status_code=400, detail="Pilih foto struk dulu")
    try:
        receipt = receipts_service.save_receipt(db, upload, user.id)
    except receipts_service.ReceiptValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # synchronous local OCR (fast, CPU-only); never blocks on network
    receipts_service.run_ocr(db, receipt.id, user.id)
    return RedirectResponse(url=f"/receipts/{receipt.id}?uploaded=1",
                            status_code=303)


@router.get("/receipts/{receipt_id}", response_class=HTMLResponse)
def receipt_detail(receipt_id: int, request: Request,
                   uploaded: int = 0, confirmed: int = 0, error: str = "",
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    try:
        receipt = receipts_service.get_receipt(db, receipt_id, user.id)
    except receipts_service.ReceiptNotFound:
        raise HTTPException(status_code=404, detail="Struk tidak ditemukan")
    view = _view(receipt)
    view["ocr"] = receipts_service._parse_ocr_data(receipt.ocr_data)
    view["status_value"] = receipt.ocr_status.value.lower()
    view["file_hash"] = receipt.file_hash

    from app.services.receipt_ocr import suggest_category
    ocr_merchant = None
    if view.get("ocr"):
        ocr_merchant = getattr(view["ocr"], "merchant", None)
    view["suggested_category"] = suggest_category(ocr_merchant)
    dup = receipts_service.duplicate_for(db, receipt, user.id)
    view["duplicate_id"] = dup.id if dup else None

    categories = db.query(Category).order_by(Category.name).all()
    accounts = db.query(Account).filter(
        (Account.user_id == user.id) | (Account.user_id.is_(None))
    ).order_by(Account.name).all()
    return templates.TemplateResponse(request, "receipts/detail.html", { "r": view,
        "categories": categories, "accounts": accounts,
        "format_rupiah": format_rupiah,
        "just_uploaded": bool(uploaded),
        "just_confirmed": bool(confirmed),
        "error": error,
        "today": today_str(),
    })


@router.get("/receipts/{receipt_id}/image")
def receipt_image(receipt_id: int, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    """Serve the stored image through an id-based route.

    The service enforces that the resolved path stays inside the upload
    directory - filesystem layout and paths are never exposed to clients.
    """
    path = receipts_service.read_receipt_file(db, receipt_id, user.id)
    if path is None:
        raise HTTPException(status_code=404, detail="Gambar struk tidak ditemukan")
    media = "image/png" if path.suffix.lower() == ".png" else (
        "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg")
    return FileResponse(path, media_type=media)


def _confirm(db: Session, receipt_id: int, form, user_id: int) -> RedirectResponse:
    try:
        receipts_service.confirm_receipt(
            db, receipt_id, user_id,
            type=form.get("type", "EXPENSE"),
            amount=int(form.get("amount") or 0),
            account_id=int(form.get("account_id") or 0) or None,
            category_id=int(form.get("category_id") or 0) or None,
            tx_date=date.fromisoformat(form.get("date") or today_str()),
            description=form.get("description") or None,
            merchant=form.get("merchant") or None,
            notes=form.get("notes") or None,
        )
    except receipts_service.ReceiptNotFound:
        raise HTTPException(status_code=404, detail="Struk tidak ditemukan")
    except receipts_service.ReceiptAlreadyConfirmed:
        return RedirectResponse(url=f"/receipts/{receipt_id}?error=already",
                                status_code=303)
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/receipts/{receipt_id}?error={quote(str(e))}", status_code=303)
    return RedirectResponse(url=f"/receipts/{receipt_id}?confirmed=1",
                            status_code=303)


@router.post("/receipts/{receipt_id}/confirm")
async def confirm_receipt_page(receipt_id: int, request: Request,
                               db: Session = Depends(get_db),
                               user: CurrentUser = Depends(get_current_user)):
    form = await request.form()
    return _confirm(db, receipt_id, form, user.id)


@router.post("/receipts/{receipt_id}/delete")
async def delete_receipt_page(receipt_id: int, request: Request,
                              db: Session = Depends(get_db),
                              user: CurrentUser = Depends(get_current_user)):
    try:
        receipts_service.delete_receipt(db, receipt_id, user.id)
    except receipts_service.ReceiptNotFound:
        raise HTTPException(status_code=404, detail="Struk tidak ditemukan")
    return RedirectResponse(url="/receipts", status_code=303)