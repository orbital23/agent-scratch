"""Lo que devuelven las tools del mock MCP: los mismos modelos de bank-mcp, para que el contrato coincida."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Customer(BaseModel):
    id: str
    full_name: str
    document_masked: str = Field(description="Documento de identidad enmascarado, por ejemplo ****5678.")
    email: str
    phone: str
    segment: str


class Transaction(BaseModel):
    id: str
    date: date
    description: str
    amount: float = Field(description="Monto en la moneda indicada; negativo es un cargo.")
    currency: str
    card_id: str | None
    channel: str


class ChargedFee(BaseModel):
    id: str
    date: date
    concept: str
    amount: float
    currency: str
    refundable: bool = Field(description="Si el tarifario permite pedir la devolución de esta comisión.")


class RefundRequest(BaseModel):
    id: str
    fee_id: str
    status: str
    reason: str


class CardStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class Card(BaseModel):
    id: str
    customer_id: str
    product: str
    last4: str
    status: CardStatus
    currency: str


class CreditLine(BaseModel):
    card_id: str
    limit: float
    used: float
    available: float
    max_eligible: float = Field(description="Línea máxima a la que el cliente puede pedir un aumento.")
    currency: str


class CreditLineIncreaseRequest(BaseModel):
    id: str
    card_id: str
    requested_limit: float
    status: str


class Claim(BaseModel):
    id: str
    customer_id: str
    transaction_id: str | None
    reason: str
    status: str
    opened_on: date
    response_due_on: date


class LoanSimulation(BaseModel):
    amount: float
    term_months: int
    annual_rate: float
    monthly_installment: float
    total_paid: float
    currency: str


class CreditProfile(BaseModel):
    customer_id: str
    score_band: str
    max_loan_amount: float
    active_loans: int
    debt_to_income: float


class LoanApplication(BaseModel):
    id: str
    customer_id: str
    product: str
    amount: float
    term_months: int
    status: str


class ServiceRequest(BaseModel):
    id: str
    customer_id: str
    type: str
    status: str
    channel: str
    updated_on: date


class Branch(BaseModel):
    id: str
    name: str
    district: str
    address: str
    hours: str
    services: list[str]
