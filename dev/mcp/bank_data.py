"""Datos sintéticos del mock MCP: los mismos de mock-bank-api (Banco Demo, ficticio), en memoria.

Se cargan en memoria al arrancar: las acciones (bloquear, registrar, actualizar) cambian esta copia y se pierden al reiniciar.
"""

from copy import deepcopy
from datetime import date

from bank_models import (
    Branch,
    Card,
    CardStatus,
    ChargedFee,
    Claim,
    CreditLine,
    CreditProfile,
    Customer,
    ServiceRequest,
    Transaction,
)

CUSTOMERS = [
    Customer(id="CUS-1001", full_name="Lucía Quispe Ramos", document_masked="****4821", email="lucia.quispe@correo.demo",
             phone="+51 900 100 101", segment="personal"),
    Customer(id="CUS-1002", full_name="Mateo Huamán Torres", document_masked="****7350", email="mateo.huaman@correo.demo",
             phone="+51 900 100 102", segment="personal"),
    Customer(id="CUS-1003", full_name="Valentina Rojas Paredes", document_masked="****1946", email="valentina.rojas@correo.demo",
             phone="+51 900 100 103", segment="premium"),
]

CARDS = [
    Card(id="CRD-2001", customer_id="CUS-1001", product="Visa Clásica", last4="4417", status=CardStatus.ACTIVE, currency="PEN"),
    Card(id="CRD-2002", customer_id="CUS-1002", product="Visa Platinum", last4="9083", status=CardStatus.ACTIVE, currency="PEN"),
    Card(id="CRD-2003", customer_id="CUS-1003", product="Mastercard Black", last4="6625", status=CardStatus.ACTIVE, currency="PEN"),
]

CREDIT_LINES = {
    "CRD-2001": CreditLine(card_id="CRD-2001", limit=3000, used=1240.5, available=1759.5, max_eligible=4500, currency="PEN"),
    "CRD-2002": CreditLine(card_id="CRD-2002", limit=12000, used=3100, available=8900, max_eligible=15000, currency="PEN"),
    "CRD-2003": CreditLine(card_id="CRD-2003", limit=25000, used=18200, available=6800, max_eligible=25000, currency="PEN"),
}

# CUS-1001 tiene el cargo duplicado del caso del curso: dos consumos iguales en el mismo comercio y el mismo día.
TRANSACTIONS = {
    "CUS-1001": [
        Transaction(id="TRX-3001", date=date(2026, 10, 20), description="SUPERMERCADO DEMO SAN ISIDRO", amount=-186.4,
                    currency="PEN", card_id="CRD-2001", channel="pos"),
        Transaction(id="TRX-3002", date=date(2026, 10, 20), description="SUPERMERCADO DEMO SAN ISIDRO", amount=-186.4,
                    currency="PEN", card_id="CRD-2001", channel="pos"),
        Transaction(id="TRX-3003", date=date(2026, 10, 18), description="RETIRO CAJERO OTRO BANCO", amount=-200,
                    currency="PEN", card_id=None, channel="atm"),
        Transaction(id="TRX-3004", date=date(2026, 10, 15), description="ABONO DE HABERES", amount=3500,
                    currency="PEN", card_id=None, channel="transfer"),
    ],
    "CUS-1002": [
        Transaction(id="TRX-3101", date=date(2026, 10, 22), description="COMPRA ONLINE TIENDA DESCONOCIDA", amount=-1450,
                    currency="USD", card_id="CRD-2002", channel="ecommerce"),
        Transaction(id="TRX-3102", date=date(2026, 10, 21), description="RESTAURANTE DEMO MIRAFLORES", amount=-98,
                    currency="PEN", card_id="CRD-2002", channel="pos"),
    ],
    "CUS-1003": [
        Transaction(id="TRX-3201", date=date(2026, 10, 19), description="TRANSFERENCIA INTERBANCARIA", amount=-2500,
                    currency="PEN", card_id=None, channel="transfer"),
    ],
}

FEES = {
    "CUS-1001": [
        ChargedFee(id="FEE-4001", date=date(2026, 10, 18), concept="Retiro en cajero de otro banco", amount=6.5,
                   currency="PEN", refundable=False),
        ChargedFee(id="FEE-4002", date=date(2026, 10, 1), concept="Mantenimiento de cuenta", amount=12,
                   currency="PEN", refundable=True),
    ],
    "CUS-1002": [
        ChargedFee(id="FEE-4101", date=date(2026, 10, 5), concept="Membresía anual de tarjeta", amount=180,
                   currency="PEN", refundable=True),
    ],
    "CUS-1003": [],
}

CLAIMS = [
    Claim(id="CLM-5001", customer_id="CUS-1002", transaction_id="TRX-3101", reason="No reconozco la compra en línea",
          status="in_review", opened_on=date(2026, 10, 23), response_due_on=date(2026, 11, 22)),
]

CREDIT_PROFILES = {
    "CUS-1001": CreditProfile(customer_id="CUS-1001", score_band="B", max_loan_amount=25000, active_loans=0, debt_to_income=0.18),
    "CUS-1002": CreditProfile(customer_id="CUS-1002", score_band="A", max_loan_amount=80000, active_loans=1, debt_to_income=0.27),
    "CUS-1003": CreditProfile(customer_id="CUS-1003", score_band="C", max_loan_amount=10000, active_loans=2, debt_to_income=0.46),
}

SERVICE_REQUESTS = [
    ServiceRequest(id="REQ-6001", customer_id="CUS-1001", type="Reposición de tarjeta", status="in_progress", channel="app",
                   updated_on=date(2026, 10, 24)),
    ServiceRequest(id="REQ-6002", customer_id="CUS-1003", type="Constancia de no adeudo", status="done", channel="agency",
                   updated_on=date(2026, 10, 12)),
]

BRANCHES = [
    Branch(id="BRN-01", name="Agencia San Isidro", district="San Isidro", address="Av. Demo 123", hours="L-V 9:00-18:00, S 9:00-13:00",
           services=["caja", "plataforma", "cajero"]),
    Branch(id="BRN-02", name="Agencia Miraflores", district="Miraflores", address="Calle Ficticia 456", hours="L-V 9:00-18:00",
           services=["caja", "plataforma"]),
    Branch(id="BRN-03", name="Agente Demo Surco", district="Santiago de Surco", address="Jr. Ejemplo 789", hours="L-D 8:00-22:00",
           services=["cajero", "depósitos"]),
]


def fresh_state() -> dict:
    """Copia nueva de los datos: cada app (y cada test) arranca desde cero."""
    return deepcopy({
        "customers": {customer.id: customer for customer in CUSTOMERS},
        "cards": {card.id: card for card in CARDS},
        "credit_lines": CREDIT_LINES,
        "transactions": TRANSACTIONS,
        "fees": FEES,
        "claims": {claim.id: claim for claim in CLAIMS},
        "credit_profiles": CREDIT_PROFILES,
        "service_requests": {request.id: request for request in SERVICE_REQUESTS},
        "branches": BRANCHES,
        "created": [],  # solicitudes registradas por las acciones: devoluciones, aumentos y préstamos
    })
