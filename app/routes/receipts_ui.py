"""Receipt web UI - upload -> preview -> review -> confirm workflow.

These Jinja pages reuse the SAME receipt services as the REST API; no
business logic lives here. OCR never creates transactions: the confirm
page posts explicit user-entered values.
"""
import time as _time
from datetime import date, timezone

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Account, AccountType, Category, ReceiptStatus
from app.services import receipts as receipts_service
from app.utils import format_rupiah, today_str
from app.validation import parse_idr_input
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _created_ts_ms(dt) -> int:
    """Epoch milliseconds for a (naive UTC) datetime.  Used by the detail
    page's processing UI so the live elapsed timer survives reloads."""
    if dt is None:
        return int(_time.time() * 1000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ocr_estimate() -> tuple[int, str]:
    """Engine-aware (target_seconds, human_label) for the processing UI.

    The progress bar caps at ``target_seconds``; the label is the realistic
    range based on the configured OCR engine.  Vision path uses the actual
    Ollama/openai timeout (CPU inference rarely hits the ceiling, but Tesseract
    fallback can add ~5s on failure)."""
    from app.config import settings
    s = settings
    if s.RECEIPT_AI_ENABLED and s.RECEIPT_AI_PROVIDER == "ollama":
        ceil = max(15, int(s.OLLAMA_TIMEOUT_SECONDS))
        return ceil, f"\u00b115\u2013{ceil} detik"
    if s.RECEIPT_AI_ENABLED and s.RECEIPT_AI_PROVIDER in ("openai", "gemini"):
        key = "OPENAI" if s.RECEIPT_AI_PROVIDER == "openai" else "GEMINI"
        timeout = getattr(s, f"{key}_TIMEOUT_SECONDS")
        ceil = max(20, int(timeout))
        return ceil, f"\u00b120\u2013{ceil} detik"
    # Tesseract-only (local CPU) or offline placeholder.
    return 8, "2\u20138 detik"


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
        "created_at_ts": _created_ts_ms(r.created_at),
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
    # OCR runs in a background thread so the HTTP response returns immediately.
    # This prevents Nginx/Cloudflare proxy timeouts from killing the connection
    # during slow Ollama inference on a CPU-only server.  The detail page
    # auto-polls until OCR finishes.
    receipts_service.run_ocr_background(receipt.id, user.id)
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
    # Auto-recover receipts stuck in PROCESSING/PENDING (stale > 10 min).
    receipts_service.recover_stale_ocr(db)
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
    accounts = (db.query(Account)
                .filter(Account.user_id == user.id)
                .order_by(Account.name).all())

    # Pilihan akun: hanya akun yang bisa dipakai membayar (ada saldo, atau
    # kartu kredit dengan limit). Kalau tak ada, jatuh ke semua akun agar
    # form tidak pernah kosong.
    def _funded(a):
        if (a.current_balance or 0) > 0:
            return True
        return a.type == AccountType.CREDIT_CARD and (a.credit_limit or 0) > 0
    funded = [a for a in accounts if _funded(a)]
    accounts = funded or accounts
    eta_sec, eta_label = _ocr_estimate()
    return templates.TemplateResponse(request, "receipts/detail.html", { "r": view,
        "categories": categories, "accounts": accounts,
        "format_rupiah": format_rupiah,
        "just_uploaded": bool(uploaded),
        "just_confirmed": bool(confirmed),
        "error": error,
        "today": today_str(),
        "ocr_eta_sec": eta_sec,
        "ocr_eta_label": eta_label,
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
            amount=parse_idr_input(form.get("amount", "")),
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


@router.post("/receipts/{receipt_id}/retry-ocr")
async def retry_ocr_page(receipt_id: int,
                         db: Session = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    """Re-run OCR on a failed/stuck receipt.  Redirects back to detail page.
    Idempotent: confirmed receipts are silently skipped."""
    receipts_service.recover_stale_ocr(db)
    receipt = receipts_service.get_receipt(db, receipt_id, user.id)
    if receipt.transaction_id is not None:
        return RedirectResponse(url=f"/receipts/{receipt_id}",
                                status_code=303)
    receipts_service.retry_ocr(receipt.id, user.id)
    return RedirectResponse(url=f"/receipts/{receipt_id}",
                            status_code=303)


@router.post("/receipts/{receipt_id}/delete")
async def delete_receipt_page(receipt_id: int, request: Request,
                              db: Session = Depends(get_db),
                              user: CurrentUser = Depends(get_current_user)):
    try:
        receipts_service.delete_receipt(db, receipt_id, user.id)
    except receipts_service.ReceiptNotFound:
        raise HTTPException(status_code=404, detail="Struk tidak ditemukan")
    return RedirectResponse(url="/receipts", status_code=303)