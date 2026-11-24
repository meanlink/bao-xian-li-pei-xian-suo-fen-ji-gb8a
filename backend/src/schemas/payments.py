from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class PaymentApprovalCreate(BaseModel):
    approved_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)] | None = None


class PaymentOrderCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payee_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    payee_account: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=40)]
    bank_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    purpose: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]


class ReceiptCreate(BaseModel):
    receipt_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)]
    result: Literal["confirmed", "rejected", "mismatch"]
    received_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)] | None = None
