from fastapi import APIRouter, Depends, HTTPException

from src.schemas.payments import PaymentApprovalCreate, PaymentOrderCreate, ReceiptCreate
from src.services.payment_service import (
    PaymentConflict,
    PaymentError,
    PaymentNotFound,
    approve_payment,
    create_order,
    get_payment_overview,
    register_receipt,
    resolve_suspension,
)
from src.utils.auth import current_user, require_roles

router = APIRouter(tags=["payments"])

# 核定、开单、回执登记与挂起处理均属风险主管（核赔岗）职责
manager = require_roles("risk_manager")


def _raise(exc):
    if isinstance(exc, PaymentNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PaymentConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/claims/{claim_id}/payments")
def payments(claim_id: int, user=Depends(current_user)):
    try:
        return get_payment_overview(claim_id)
    except PaymentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/claims/{claim_id}/payment-approval")
def approve(claim_id: int, payload: PaymentApprovalCreate, user=Depends(manager)):
    try:
        return approve_payment(claim_id, payload, user["id"])
    except Exception as exc:
        _raise(exc)


@router.post("/claims/{claim_id}/payment-orders")
def open_order(claim_id: int, payload: PaymentOrderCreate, user=Depends(manager)):
    try:
        return create_order(claim_id, payload, user["id"])
    except Exception as exc:
        _raise(exc)


@router.post("/payment-orders/{order_id}/receipts")
def receipt(order_id: int, payload: ReceiptCreate, user=Depends(manager)):
    try:
        return register_receipt(order_id, payload, user["id"])
    except Exception as exc:
        _raise(exc)


@router.post("/payment-orders/{order_id}/suspension")
def suspension(order_id: int, payload: dict, user=Depends(manager)):
    try:
        return resolve_suspension(order_id, payload, user["id"])
    except Exception as exc:
        _raise(exc)
