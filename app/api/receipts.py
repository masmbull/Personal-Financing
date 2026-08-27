from datetime import date

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.receipt import ReceiptConfirmRequest, ReceiptResponse
from app.services import receipts as receipts_service

router = APIRouter(prefix="/receipts", tags=["receipts"])


def _out(receipt) -> ReceiptResponse:
    d = receipts_service.to_response_dict(receipt)
    return ReceiptResponse(**d)


@router.post(
    "",
    response_model=ReceiptResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Upload a receipt image (OCR processing)",
    description=(
        "Accepts JPEG/PNG/WebP/HEIC up to the configured size limit, stores "
        "the file safely, runs local OCR (processing -> ready/failed) and "
        "returns the extracted draft. OCR output NEVER creates a transaction - "
        "confirmation via POST /receipts/{{id}}/confirm is always required. "
        "Re-uploads of the same image set file_hash for duplicate detection."
    ),
    responses={
        201: {"description": "Stored and processed"},
        400: {"description": "Unsupported type / empty / too large / not an image"},
    },
)
def upload_receipt(file: UploadFile,
                   db: Session = Depends(get_db),
                   _user: CurrentUser = Depends(get_current_user)):
    try:
        receipt = receipts_service.save_receipt(db, file)
    except receipts_service.ReceiptValidationError as e:
        from app.api.errors import ApiError
        code = "RECEIPT_INVALID"
        msg = str(e).lower()
        if "unsupported" in msg:
            code = "UNSUPPORTED_FILE_TYPE"
        elif "too large" in msg:
            code = "FILE_TOO_LARGE"
        raise ApiError(400, code, str(e))
    receipt = receipts_service.run_ocr(db, receipt.id)  # PROCESSING -> READY/FAILED
    return _out(receipt)


@router.get(
    "", response_model=list[ReceiptResponse],
    summary="List uploaded receipts (newest first)",
)
def list_receipts(limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db)):
    return [_out(r) for r in receipts_service.list_receipts(db, limit, offset)]


@router.get(
    "/{receipt_id}", response_model=ReceiptResponse,
    summary="Get one receipt",
    description="Poll this while waiting for OCR; ocr_status moves "
                "pending -> processed once an engine is attached.",
    responses={404: {"description": "Not found"}},
)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    return _out(receipts_service.get_receipt(db, receipt_id))


@router.post(
    "/{receipt_id}/confirm", response_model=ReceiptResponse,
    summary="Confirm a receipt as a real transaction (user action required)",
    description=(
        "Creates the transaction EXACTLY as specified in this request body "
        "(validated like any other transaction) and links it to the "
        "receipt. This is the only path from a receipt to a transaction - "
        "OCR output can never post by itself. A second confirm returns 409."
    ),
    responses={
        200: {"description": "Confirmed and linked"},
        400: {"description": "Invalid transaction payload"},
        404: {"description": "Receipt not found"},
        409: {"description": "Already confirmed"},
    },
)
def confirm_receipt(receipt_id: int, payload: ReceiptConfirmRequest,
                    db: Session = Depends(get_db)):
    try:
        receipt, _tx = receipts_service.confirm_receipt(
            db, receipt_id,
            type=payload.type, amount=payload.amount,
            account_id=payload.account_id, category_id=payload.category_id,
            tx_date=payload.date or date.today(),
            description=payload.description, merchant=payload.merchant,
            notes=payload.notes,
        )
    except ValueError as e:
        from app.api.errors import ApiError
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return _out(receipt)


@router.delete(
    "/{receipt_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a receipt",
    description="Removes metadata. Set remove_file=true to also delete the stored image.",
    responses={404: {"description": "Not found"}},
)
def delete_receipt(receipt_id: int, remove_file: bool = Query(False),
                   db: Session = Depends(get_db)):
    receipts_service.delete_receipt(db, receipt_id, remove_file=remove_file)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)