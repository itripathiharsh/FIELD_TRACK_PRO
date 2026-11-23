from tally_sync_agent.validators.data_validator import DataValidator


def test_validate_customer():
    valid, err = DataValidator.validate_customer({
        "source_reference": "GUID_001",
        "name": "Shree Ganesh Enterprises",
    })
    assert valid is True
    assert err is None

    # Missing name
    invalid, err = DataValidator.validate_customer({
        "source_reference": "GUID_002",
        "name": "",
    })
    assert invalid is False
    assert "Missing customer name" in err


def test_validate_invoice():
    valid, err = DataValidator.validate_invoice({
        "source_reference": "INV_001",
        "invoice_number": "SGRG/2026/001",
        "customer_name": "Aashi Mobile",
        "invoice_date": "2026-08-18",
        "amount": 1080.0,
    })
    assert valid is True

    # Bad date format
    invalid, err = DataValidator.validate_invoice({
        "source_reference": "INV_002",
        "invoice_number": "SGRG/2026/002",
        "customer_name": "Aashi Mobile",
        "invoice_date": "18/08/2026",
        "amount": 1080.0,
    })
    assert invalid is False
    assert "Invalid invoice_date" in err

    # Negative amount
    invalid_amt, err = DataValidator.validate_invoice({
        "source_reference": "INV_003",
        "invoice_number": "SGRG/2026/003",
        "customer_name": "Aashi Mobile",
        "invoice_date": "2026-08-18",
        "amount": -50.0,
    })
    assert invalid_amt is False


def test_validate_payment():
    valid, err = DataValidator.validate_payment({
        "source_reference": "RCPT_001",
        "receipt_number": "RCPT-101",
        "customer_name": "Aashi Mobile",
        "payment_date": "2026-08-18",
        "amount": 5000.0,
    })
    assert valid is True

    # Zero amount is invalid for payment
    invalid, err = DataValidator.validate_payment({
        "source_reference": "RCPT_002",
        "receipt_number": "RCPT-102",
        "customer_name": "Aashi Mobile",
        "payment_date": "2026-08-18",
        "amount": 0.0,
    })
    assert invalid is False
