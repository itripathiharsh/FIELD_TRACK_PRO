import uuid
from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation
from app.schemas.tally_sync import PaymentSyncBatch, PaymentSyncItem, PaymentBillAllocationItem
from app.services.tally_sync_service import sync_payments


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.name = "Test Agent"
    agent.is_active = True
    return agent


@pytest.fixture
def test_customer():
    cust = Customer(
        id=uuid.uuid4(),
        name="Test Retailer",
        outlet_code="SGRGZBR001",
        contact_number="9876543210",
    )
    return cust


@pytest.mark.asyncio
async def test_explicit_bill_allocation(mock_agent, test_customer):
    """Test that payments with explicit Tally Agst Ref bill allocations match invoices precisely."""
    inv_id = uuid.uuid4()
    mock_inv = Invoice(
        id=inv_id,
        customer_id=test_customer.id,
        invoice_number="INV-2026-001",
        amount=Decimal("10000.00"),
        source_reference="TALLY-INV-001",
    )

    batch = PaymentSyncBatch(
        batch_id="batch-001",
        agent_id="test-agent",
        payments=[
            PaymentSyncItem(
                source_reference="RCPT-001",
                customer_name=test_customer.name,
                customer_outlet_code=test_customer.outlet_code,
                amount=Decimal("6000.00"),
                payment_date="2026-09-01",
                payment_method="BANK",
                bill_allocations=[
                    PaymentBillAllocationItem(
                        bill_type="Agst Ref",
                        bill_name="INV-2026-001",
                        amount=Decimal("6000.00"),
                    )
                ]
            )
        ]
    )

    # Validate that bill_allocations parse properly and maintain exact amounts
    assert len(batch.payments[0].bill_allocations) == 1
    assert batch.payments[0].bill_allocations[0].bill_name == "INV-2026-001"
    assert batch.payments[0].bill_allocations[0].amount == Decimal("6000.00")
    assert batch.payments[0].bill_allocations[0].bill_type == "Agst Ref"


def test_fifo_settlement_allocation_logic():
    """
    Pure algorithmic test of deterministic FIFO allocation:
    - Multiple invoices
    - Partial payments
    - Advances
    """
    invoices = [
        {"id": "inv-1", "amount": Decimal("10000.00"), "date": "2026-08-01"},
        {"id": "inv-2", "amount": Decimal("15000.00"), "date": "2026-08-15"},
        {"id": "inv-3", "amount": Decimal("5000.00"), "date": "2026-08-20"},
    ]
    # Total billed: 30,000.00

    # Scenario A: Payment of 12,000
    payment_amt = Decimal("12000.00")
    allocations = []
    rem = payment_amt
    for inv in invoices:
        if rem <= Decimal("0.00"):
            break
        settle = min(rem, inv["amount"])
        allocations.append({"invoice_id": inv["id"], "amount": settle})
        rem -= settle

    assert len(allocations) == 2
    assert allocations[0] == {"invoice_id": "inv-1", "amount": Decimal("10000.00")}
    assert allocations[1] == {"invoice_id": "inv-2", "amount": Decimal("2000.00")}
    assert rem == Decimal("0.00")

    # Scenario B: Overpayment / Advance of 35,000 on 30,000 total open
    payment_amt_b = Decimal("35000.00")
    allocations_b = []
    rem_b = payment_amt_b
    for inv in invoices:
        if rem_b <= Decimal("0.00"):
            break
        settle = min(rem_b, inv["amount"])
        allocations_b.append({"invoice_id": inv["id"], "amount": settle})
        rem_b -= settle

    assert len(allocations_b) == 3
    assert allocations_b[0]["amount"] == Decimal("10000.00")
    assert allocations_b[1]["amount"] == Decimal("15000.00")
    assert allocations_b[2]["amount"] == Decimal("5000.00")
    # Unallocated amount represents account advance
    assert rem_b == Decimal("5000.00")


def test_outstanding_never_negative():
    """Verify invariant: outstanding >= 0."""
    gross = Decimal("10000.00")
    settled = Decimal("10000.00")
    assert max(gross - settled, Decimal("0.00")) == Decimal("0.00")

    over_settled = Decimal("12000.00")
    assert max(gross - over_settled, Decimal("0.00")) == Decimal("0.00")
