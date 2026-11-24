"""MCP simulado para desarrollo: las 15 tools de bank-mcp con el mismo contrato, sobre datos sintéticos en memoria.

Arranque: uv run python dev/mcp/mock_mcp.py        (Streamable HTTP en http://127.0.0.1:8200/mcp)
Dominio: el header X-Bank-Domain (fees, cards, fraud, loans, support) deja ver solo las tools de ese dominio, como el MCP
compartido. Sin el header se ven las 15.
"""

from datetime import timedelta
from itertools import count
from typing import Annotated

from bank_data import fresh_state
from bank_models import (
    Branch,
    Card,
    CardStatus,
    ChargedFee,
    Claim,
    CreditLine,
    CreditLineIncreaseRequest,
    CreditProfile,
    Customer,
    LoanApplication,
    LoanSimulation,
    RefundRequest,
    ServiceRequest,
    Transaction,
)
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthContext
from fastmcp.server.dependencies import get_http_headers
from mcp.types import ToolAnnotations
from pydantic import Field

PORT = 8200
DOMAINS = ("fees", "cards", "fraud", "loans", "support")
DOMAIN_HEADER = "x-bank-domain"
CLAIM_RESPONSE_DAYS = 30

CustomerId = Annotated[str, Field(description="Código del cliente, por ejemplo CUS-1001.", pattern=r"^CUS-\d{4}$")]
CardId = Annotated[str, Field(description="Código de la tarjeta, por ejemplo CRD-2001.", pattern=r"^CRD-\d{4}$")]
Reason = Annotated[str, Field(description="Motivo, con las palabras del cliente.", min_length=5)]

INSTRUCTIONS = (
    "Tools del Banco Demo (ficticio). Las de solo lectura consultan datos del cliente; las demás registran una operación "
    "y, en el agente, requieren aprobación humana. Si una tool responde con error, explícale el motivo al cliente."
)


def allowed_for(domains: set[str]):
    """La tool aparece solo si el header X-Bank-Domain es uno de sus dominios, o si no viene (en memoria, en los tests)."""

    def check(ctx: AuthContext) -> bool:
        domain = get_http_headers().get(DOMAIN_HEADER)
        return domain is None or domain in domains

    return check


def monthly_installment(amount: float, term_months: int, annual_rate: float) -> float:
    """Cuota fija (sistema francés) a partir de la TEA."""
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    return round(amount * monthly_rate / (1 - (1 + monthly_rate) ** -term_months), 2)


def create_server() -> FastMCP:
    state = fresh_state()
    ids = count(9001)
    mcp = FastMCP("mock-mcp", instructions=INSTRUCTIONS)

    def tool(*domains: str, read_only: bool):
        return mcp.tool(
            tags=set(domains),
            annotations=ToolAnnotations(read_only_hint=read_only, destructive_hint=not read_only,
                                        idempotent_hint=read_only, open_world_hint=False),
            auth=allowed_for(set(domains)),
        )

    def found(collection: str, key: str, label: str):
        item = state[collection].get(key)
        if item is None:
            raise ToolError(f"{label} {key} no existe")
        return item

    def customer(customer_id: str) -> Customer:
        return found("customers", customer_id, "El cliente")

    def card(card_id: str) -> Card:
        return found("cards", card_id, "La tarjeta")

    # ---------- fees · tarifario y comisiones ----------
    @tool("fees", "fraud", read_only=True)
    async def get_transactions(customer_id: CustomerId,
                               limit: Annotated[int, Field(ge=1, le=50, description="Cuántos movimientos traer.")] = 10
                               ) -> list[Transaction]:
        """Últimos movimientos del cliente, del más reciente al más antiguo. Un monto negativo es un cargo."""
        customer(customer_id)
        return state["transactions"].get(customer_id, [])[:limit]

    @tool("fees", read_only=True)
    async def get_charged_fees(customer_id: CustomerId) -> list[ChargedFee]:
        """Comisiones cobradas al cliente, con la marca de si el tarifario permite pedir su devolución."""
        customer(customer_id)
        return state["fees"].get(customer_id, [])

    @tool("fees", read_only=False)
    async def request_fee_refund(fee_id: Annotated[str, Field(description="Código de la comisión, por ejemplo FEE-4002.")],
                                 reason: Reason) -> RefundRequest:
        """Registra el pedido de devolución de una comisión cobrada. Acción sensible."""
        fee = next((fee for fees in state["fees"].values() for fee in fees if fee.id == fee_id), None)
        if fee is None:
            raise ToolError(f"La comisión {fee_id} no existe")
        if not fee.refundable:
            raise ToolError(f"La comisión {fee_id} ({fee.concept}) no admite devolución según el tarifario")
        return RefundRequest(id=f"RFD-{next(ids)}", fee_id=fee_id, status="registered", reason=reason)

    # ---------- cards · tarjetas de crédito ----------
    @tool("cards", read_only=True)
    async def get_cards(customer_id: CustomerId) -> list[Card]:
        """Tarjetas del cliente, con su producto, últimos 4 dígitos y estado."""
        customer(customer_id)
        return [c for c in state["cards"].values() if c.customer_id == customer_id]

    @tool("cards", read_only=True)
    async def get_credit_line(card_id: CardId) -> CreditLine:
        """Línea de crédito de una tarjeta: total, usada, disponible y máxima a la que puede aumentarse."""
        card(card_id)
        return state["credit_lines"][card_id]

    @tool("cards", read_only=False)
    async def request_credit_line_increase(
        card_id: CardId, requested_limit: Annotated[float, Field(gt=0, description="Nueva línea total pedida, en soles.")]
    ) -> CreditLineIncreaseRequest:
        """Registra el pedido de aumento de línea de una tarjeta. Acción sensible."""
        card(card_id)
        line = state["credit_lines"][card_id]
        if requested_limit <= line.limit:
            raise ToolError(f"La línea pedida debe ser mayor que la actual ({line.limit:.2f} {line.currency})")
        if requested_limit > line.max_eligible:
            raise ToolError(f"La línea máxima para esta tarjeta es {line.max_eligible:.2f} {line.currency}")
        return CreditLineIncreaseRequest(id=f"CLI-{next(ids)}", card_id=card_id, requested_limit=requested_limit,
                                         status="registered")

    # ---------- fraud · fraude, bloqueo y reclamos ----------
    @tool("fraud", read_only=True)
    async def get_claim_status(claim_id: Annotated[str, Field(description="Código del reclamo, por ejemplo CLM-5001.")]) -> Claim:
        """Estado de un reclamo y fecha límite de respuesta."""
        return found("claims", claim_id, "El reclamo")

    @tool("fraud", read_only=False)
    async def block_card(card_id: CardId, reason: Annotated[str, Field(min_length=3, description="Motivo: robo, pérdida, fraude.")]
                         ) -> Card:
        """Bloquea una tarjeta de forma definitiva. Acción sensible."""
        current = card(card_id)
        if current.status == CardStatus.BLOCKED:
            raise ToolError(f"La tarjeta {card_id} ya está bloqueada")
        state["cards"][card_id] = current.model_copy(update={"status": CardStatus.BLOCKED})
        return state["cards"][card_id]

    @tool("fraud", read_only=False)
    async def file_claim(customer_id: CustomerId,
                         transaction_id: Annotated[str, Field(description="Movimiento reclamado, por ejemplo TRX-3002.")],
                         reason: Reason) -> Claim:
        """Registra un reclamo por un movimiento del cliente. Acción sensible."""
        customer(customer_id)
        transaction = next((t for t in state["transactions"].get(customer_id, []) if t.id == transaction_id), None)
        if transaction is None:
            raise ToolError(f"El movimiento {transaction_id} no es del cliente {customer_id}")
        opened = transaction.date + timedelta(days=8)  # fecha ficticia y fija: los datos son de octubre de 2026
        claim = Claim(id=f"CLM-{next(ids)}", customer_id=customer_id, transaction_id=transaction_id, reason=reason,
                      status="registered", opened_on=opened, response_due_on=opened + timedelta(days=CLAIM_RESPONSE_DAYS))
        state["claims"][claim.id] = claim
        return claim

    # ---------- loans · préstamos ----------
    @tool("loans", read_only=True)
    async def simulate_installment(
        amount: Annotated[float, Field(gt=0, le=500_000, description="Monto del préstamo, en soles.")],
        term_months: Annotated[int, Field(ge=6, le=360, description="Plazo en meses.")],
        annual_rate: Annotated[float, Field(gt=0, lt=1, description="TEA como fracción: 0.18 es 18 %.")] = 0.18,
    ) -> LoanSimulation:
        """Calcula la cuota mensual fija de un préstamo. La cuota siempre sale de esta tool, nunca de una estimación."""
        installment = monthly_installment(amount, term_months, annual_rate)
        return LoanSimulation(amount=amount, term_months=term_months, annual_rate=annual_rate, monthly_installment=installment,
                              total_paid=round(installment * term_months, 2), currency="PEN")

    @tool("loans", read_only=True)
    async def get_credit_profile(customer_id: CustomerId) -> CreditProfile:
        """Perfil crediticio del cliente: banda, monto máximo preaprobado y endeudamiento."""
        customer(customer_id)
        return state["credit_profiles"][customer_id]

    @tool("loans", read_only=False)
    async def submit_loan_application(
        customer_id: CustomerId,
        product: Annotated[str, Field(description="Producto: personal, vehicular o hipotecario.")],
        amount: Annotated[float, Field(gt=0, description="Monto pedido, en soles.")],
        term_months: Annotated[int, Field(ge=6, le=360, description="Plazo en meses.")],
    ) -> LoanApplication:
        """Registra una solicitud de préstamo. Acción sensible."""
        customer(customer_id)
        profile = state["credit_profiles"][customer_id]
        if amount > profile.max_loan_amount:
            raise ToolError(f"El monto supera el máximo preaprobado ({profile.max_loan_amount:.2f} PEN)")
        return LoanApplication(id=f"LOA-{next(ids)}", customer_id=customer_id, product=product, amount=amount,
                               term_months=term_months, status="registered")

    # ---------- support · atención y FAQ ----------
    @tool("support", read_only=True)
    async def get_request_status(request_id: Annotated[str, Field(description="Código de la solicitud, por ejemplo REQ-6001.")]
                                 ) -> ServiceRequest:
        """Estado de una solicitud de atención del cliente."""
        return found("service_requests", request_id, "La solicitud")

    @tool("support", read_only=True)
    async def find_branches(district: Annotated[str | None, Field(description="Distrito, por ejemplo Miraflores.")] = None,
                            service: Annotated[str | None, Field(description="Servicio: caja, plataforma, cajero.")] = None
                            ) -> list[Branch]:
        """Agencias y agentes, filtrados por distrito o por servicio."""
        branches = state["branches"]
        if district:
            branches = [b for b in branches if district.lower() in b.district.lower()]
        if service:
            branches = [b for b in branches if service.lower() in (s.lower() for s in b.services)]
        return branches

    @tool("support", read_only=False)
    async def update_contact_details(customer_id: CustomerId,
                                     email: Annotated[str | None, Field(description="Nuevo correo.")] = None,
                                     phone: Annotated[str | None, Field(description="Nuevo teléfono.")] = None) -> Customer:
        """Actualiza el correo o el teléfono del cliente. Acción sensible."""
        current = customer(customer_id)
        changes = {key: value for key, value in {"email": email, "phone": phone}.items() if value}
        if not changes:
            raise ToolError("Indica al menos un dato de contacto: email o teléfono")
        state["customers"][customer_id] = current.model_copy(update=changes)
        return state["customers"][customer_id]

    return mcp


if __name__ == "__main__":
    create_server().run(transport="http", host="127.0.0.1", port=PORT, path="/mcp")